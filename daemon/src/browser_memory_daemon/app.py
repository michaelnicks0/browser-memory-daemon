from __future__ import annotations

import ipaddress
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .api_errors import (
    APIError,
    ForbiddenError,
    NotFoundError,
    ResourceUnavailableError,
    UnauthorizedError,
    UnsupportedMethodError,
    ValidationError,
    classify_exception,
)
from .config import RuntimeConfig
from .db import audit, connect, init_db
from .forget import forget
from .ingest import ingest_capture
from .lifecycle import record_visit_event
from .media import (
    fetch_pending_media_artifacts,
    media_artifact,
    media_queue_status,
    purge_media_cache,
    store_media_artifact,
    store_media_blob_stream,
)
from .media_resources import MediaResourceUnavailable, media_resource_budget
from .media_storage import media_blob_store_and_locator, media_root_readiness
from .models import CapturePayload
from .ops import doctor, document_detail, recent_captures, snapshot_detail, timeline
from .policy import POLICY_MODE_ALL, evaluate_capture
from .policy_store import create_policy_rule, delete_policy_rule, evaluate_policy_rules, list_policy_rules
from .routes import match_route
from .search import search_memory

UI_ROOT = Path(__file__).resolve().parents[3] / "ui"
REQUEST_QUEUE_SIZE = 128
_DB_READY_LOCK = threading.Lock()
_DB_READY_PATHS: set[Path] = set()


class MemoryHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = REQUEST_QUEUE_SIZE


def _db_ready_key(config: RuntimeConfig) -> Path:
    return config.db_path.resolve()


def _mark_db_ready(config: RuntimeConfig) -> None:
    with _DB_READY_LOCK:
        _DB_READY_PATHS.add(_db_ready_key(config))


def _origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    if origin.startswith("chrome-extension://"):
        return True
    try:
        parsed = urlparse(origin)
    except Exception:
        return False
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict | list) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    origin = handler.headers.get("Origin", "")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    if _origin_allowed(origin):
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
    handler.send_header("Access-Control-Allow-Headers", "authorization, content-type, x-bmd-document-id, x-bmd-snapshot-id, x-bmd-source-url")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _api_error_response(handler: BaseHTTPRequestHandler, error: Exception, *, extra: dict[str, object] | None = None) -> None:
    api_error = classify_exception(error)
    _json_response(handler, api_error.status, api_error.payload(extra))


def _text_response(handler: BaseHTTPRequestHandler, status: int, body: bytes, *, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def _ui_bootstrap_script(config: RuntimeConfig) -> str:
    payload = {
        "api_token": config.api_token,
        "policy_mode": config.policy_mode,
        "storage_root": str(config.data_root),
        "blob_root": str(config.blob_root),
        "derivative_root": str(config.clean_text_root.parent),
        "media_root": str(config.media_root),
    }
    # JSON script bodies are still parsed as HTML script text; escape closing
    # tags so a future non-url-safe token value cannot terminate the script.
    body = json.dumps(payload, sort_keys=True).replace("</", "<\\/")
    return f'    <script id="bmd-bootstrap" type="application/json">{body}</script>\n'


def _ui_file_body(path: Path, config: RuntimeConfig) -> bytes:
    body = path.read_bytes()
    if path.name != "index.html":
        return body
    text = body.decode("utf-8")
    marker = '    <script src="/ui/app.js"></script>'
    if marker not in text:
        return body
    return text.replace(marker, _ui_bootstrap_script(config) + marker, 1).encode("utf-8")


def _binary_stream_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    stream,
    *,
    content_length: int,
    content_type: str,
    filename: str | None = None,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type or "application/octet-stream")
    handler.send_header("Content-Length", str(content_length))
    handler.send_header("X-Content-Type-Options", "nosniff")
    if filename:
        handler.send_header("Content-Disposition", f'inline; filename="{filename}"')
    handler.end_headers()
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        handler.wfile.write(chunk)


def _read_json(handler: BaseHTTPRequestHandler, max_bytes: int) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length > max_bytes:
        raise ValueError("payload too large")
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _authorized(handler: BaseHTTPRequestHandler, config: RuntimeConfig) -> bool:
    header = handler.headers.get("Authorization", "")
    return header == f"Bearer {config.api_token}"


def _is_loopback_host(value: str, *, allow_names: bool = True) -> bool:
    host = (value or "").strip().strip("[]").rstrip(".").lower()
    if allow_names and (host == "localhost" or host.endswith(".localhost")):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _request_host_header(handler: BaseHTTPRequestHandler) -> str:
    raw = str(handler.headers.get("Host") or "").split(",", 1)[0].strip()
    if not raw:
        return ""
    parsed = urlparse(f"//{raw}")
    return parsed.hostname or raw.split(":", 1)[0]


def _loopback_ui_allowed(handler: BaseHTTPRequestHandler, config: RuntimeConfig) -> bool:
    host_header_ok = _is_loopback_host(_request_host_header(handler), allow_names=True)
    if not host_header_ok:
        return False
    if _is_loopback_host(config.host, allow_names=True):
        return True
    client_host = str(handler.client_address[0]) if handler.client_address else ""
    return _is_loopback_host(client_host, allow_names=False)


def _ui_file_for_path(path: str) -> Path | None:
    if path in {"/", "/ui", "/ui/"}:
        candidate = UI_ROOT / "index.html"
    elif path.startswith("/ui/"):
        relative = unquote(path.removeprefix("/ui/"))
        candidate = UI_ROOT / relative
    else:
        return None
    try:
        resolved = candidate.resolve()
        if not resolved.is_relative_to(UI_ROOT.resolve()) or not resolved.is_file():
            return None
        return resolved
    except Exception:
        return None


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def _coerce_limit(value, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _truthy_query_value(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "full", "filesystem"}


def _ensure_db(config: RuntimeConfig) -> None:
    # Request handlers still ensure the versioned schema is ready, but the
    # process-level cache prevents repeated migration compatibility checks.
    key = _db_ready_key(config)
    if key in _DB_READY_PATHS and config.db_path.exists():
        return
    with _DB_READY_LOCK:
        if key in _DB_READY_PATHS and config.db_path.exists():
            return
        init_db(config)
        _DB_READY_PATHS.add(key)


def _background_fetch_pending_media(config: RuntimeConfig, *, snapshot_id: str, limit: int) -> None:
    try:
        _ensure_db(config)
        with connect(config.db_path) as conn:
            result = fetch_pending_media_artifacts(conn, config, snapshot_id=snapshot_id, limit=limit)
            audit(
                conn,
                "media.fetch_pending",
                {
                    "snapshot_id": snapshot_id,
                    "attempted": result["attempted"],
                    "stored": result["stored"],
                    "failed": result["failed"],
                    "skipped": result["skipped"],
                    "remaining": result["remaining"],
                    "background": True,
                },
            )
            conn.commit()
    except Exception:
        return


def _start_background_fetch_pending_media(config: RuntimeConfig, *, snapshot_id: str, media_ref_count: int) -> None:
    if not config.media_fetch_on_capture or not snapshot_id or media_ref_count <= 0:
        return
    limit = min(config.max_media_fetches_per_capture, media_ref_count)
    thread = threading.Thread(target=_background_fetch_pending_media, kwargs={"config": config, "snapshot_id": snapshot_id, "limit": limit}, daemon=True)
    thread.start()


def make_handler(config: RuntimeConfig):
    class MemoryHandler(BaseHTTPRequestHandler):
        server_version = "BrowserMemoryDaemon/0.1"

        def log_message(self, format: str, *args) -> None:
            return

        def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
            default_message = self.responses.get(code, ("error", ""))[0]
            if code == 501:
                _api_error_response(self, UnsupportedMethodError(message or default_message))
                return
            _api_error_response(self, APIError(status=code, code="http_error", message=message or default_message))

        def do_OPTIONS(self) -> None:
            _json_response(self, 204, {})

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            route_match = match_route("GET", parsed.path)
            if route_match and route_match.route.name == "health":
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "version": __version__,
                        "storage_root": str(config.data_root),
                        "blob_root": str(config.blob_root),
                        "derivative_root": str(config.clean_text_root.parent),
                        "media_root": str(config.media_root),
                        "media_spool_enabled": config.media_spool_enabled,
                        "media_root_status": media_root_readiness(config).status,
                        "capture_enabled": True,
                        "policy_mode": config.policy_mode,
                    },
                )
                return
            ui_file = _ui_file_for_path(parsed.path)
            if ui_file:
                if not _loopback_ui_allowed(self, config):
                    _api_error_response(self, ForbiddenError("ui is loopback-only"))
                    return
                _text_response(self, 200, _ui_file_body(ui_file, config), content_type=_content_type(ui_file))
                return
            if not _authorized(self, config):
                _api_error_response(self, UnauthorizedError())
                return
            params = parse_qs(parsed.query)
            try:
                if route_match and route_match.route.name == "ready":
                    _ensure_db(config)
                    _json_response(self, 200, {"ready": True, "db_path": str(config.db_path)})
                    return
                if route_match and route_match.route.name == "search":
                    query = params.get("q", [""])[0]
                    limit = int(params.get("limit", ["10"])[0])
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        results = search_memory(conn, query, limit=limit)
                        audit(conn, "search", {"query_len": len(query), "result_count": len(results)})
                        conn.commit()
                    _json_response(self, 200, {"results": results})
                    return
                if route_match and route_match.route.name == "recent":
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        results = recent_captures(conn, limit=params.get("limit", ["25"])[0])
                        audit(conn, "recent", {"result_count": len(results)})
                        conn.commit()
                    _json_response(self, 200, {"results": results})
                    return
                if route_match and route_match.route.name == "timeline":
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        results = timeline(
                            conn,
                            day=params.get("date", [None])[0],
                            after=params.get("after", [None])[0],
                            before=params.get("before", [None])[0],
                            limit=params.get("limit", ["100"])[0],
                        )
                        audit(conn, "timeline", {"result_count": results["count"]})
                        conn.commit()
                    _json_response(self, 200, results)
                    return
                if route_match and route_match.route.name == "document-detail":
                    document_id = route_match.parameters["document_id"]
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = document_detail(conn, config, document_id)
                        audit(conn, "document.detail", {"document_id": document_id})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if route_match and route_match.route.name == "snapshot-detail":
                    snapshot_id = route_match.parameters["snapshot_id"]
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = snapshot_detail(conn, config, snapshot_id)
                        audit(conn, "snapshot.detail", {"snapshot_id": snapshot_id})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if route_match and route_match.route.name == "media-queue-status":
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = media_queue_status(conn, config, limit=_coerce_limit(params.get("limit", ["50"])[0], 50, 200))
                        audit(conn, "media.queue_status", {})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if route_match and route_match.route.name == "media-detail":
                    artifact_id = route_match.parameters["artifact_id"]
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        artifact = media_artifact(conn, config, artifact_id)
                        audit(conn, "media.detail", {"artifact_id": artifact_id})
                        conn.commit()
                    artifact.pop("resolved_file_path", None)
                    store, locator, tier_status = media_blob_store_and_locator(config, artifact)
                    resolution = store.resolve(locator, require_file=True) if store is not None else None
                    if not artifact.get("has_file") or resolution is None or resolution.path is None:
                        _api_error_response(
                            self,
                            NotFoundError("media artifact file not stored"),
                            extra={
                                "storage_status": tier_status,
                                "artifact": {
                                    k: v
                                    for k, v in artifact.items()
                                    if k not in {"file_path", "blob_locator", "spool_locator"}
                                },
                            },
                        )
                        return
                    assert store is not None
                    assert locator is not None
                    try:
                        content_length = resolution.path.stat().st_size
                        with media_resource_budget(config).acquire(
                            byte_count=content_length,
                            request_count=1,
                            timeout=0,
                        ):
                            with store.open(locator) as stream:
                                _binary_stream_response(
                                    self,
                                    200,
                                    stream,
                                    content_length=content_length,
                                    content_type=artifact.get("mime_type") or "application/octet-stream",
                                    filename=resolution.path.name,
                                )
                    except MediaResourceUnavailable as exc:
                        _api_error_response(self, ResourceUnavailableError(str(exc)))
                    return
                if route_match and route_match.route.name == "doctor":
                    _ensure_db(config)
                    storage_census = _truthy_query_value(params.get("storage_census", [None])[0])
                    with connect(config.db_path) as conn:
                        result = doctor(config, conn, storage_census=storage_census)
                        audit(conn, "doctor", {"ok": result["ok"]})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if route_match and route_match.route.name == "policy-rules-list":
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        _json_response(self, 200, {"rules": list_policy_rules(conn)})
                    return
                if route_match and route_match.route.name == "policy-evaluate":
                    url = params.get("url", [""])[0]
                    static_decision = evaluate_capture(url, policy_mode=config.policy_mode)
                    persistent_decision = static_decision
                    if static_decision.allowed:
                        _ensure_db(config)
                        with connect(config.db_path) as conn:
                            rules_decision = evaluate_policy_rules(conn, url)
                            if not rules_decision.allowed:
                                persistent_decision = rules_decision
                    _json_response(
                        self,
                        200,
                        {
                            "allowed": persistent_decision.allowed,
                            "reason": persistent_decision.reason,
                            "privacy_class": persistent_decision.privacy_class,
                            "policy_mode": config.policy_mode,
                            "static_reason": static_decision.reason,
                        },
                    )
                    return
            except KeyError as exc:
                _api_error_response(self, exc)
                return
            except Exception as exc:
                _api_error_response(self, exc)
                return
            _api_error_response(self, NotFoundError())

        def do_PUT(self) -> None:
            if not _authorized(self, config):
                _api_error_response(self, UnauthorizedError())
                return
            parsed = urlparse(self.path)
            route_match = match_route("PUT", parsed.path)
            if route_match and route_match.route.name == "media-blob-put":
                artifact_id = unquote(parsed.path.removeprefix("/media-artifacts/").removesuffix("/blob").strip("/"))
                try:
                    content_length = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError:
                    _api_error_response(self, ValidationError("invalid content length"))
                    return
                if content_length < 0:
                    _api_error_response(self, ValidationError("invalid content length"))
                    return
                try:
                    _ensure_db(config)
                    with media_resource_budget(config).acquire(
                        byte_count=content_length,
                        request_count=1,
                        timeout=0,
                    ):
                        with connect(config.db_path) as conn:
                            headers = {key: self.headers.get(key, "") for key in ["Content-Type", "X-BMD-Document-ID", "X-BMD-Snapshot-ID", "X-BMD-Source-URL"]}
                            result = store_media_blob_stream(conn, config, artifact_id, self.rfile, headers=headers, content_length=content_length)
                            audit(conn, "media.blob_put", {"artifact_id": artifact_id, "stored": result["stored"], "capture_status": result["capture_status"], "byte_size": result["byte_size"]})
                            conn.commit()
                    _json_response(self, 201 if result["stored"] else 200, result)
                    return
                except MediaResourceUnavailable as exc:
                    _api_error_response(self, ResourceUnavailableError(str(exc)))
                    return
                except KeyError as exc:
                    _api_error_response(self, exc)
                    return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
            _api_error_response(self, NotFoundError())

        def do_POST(self) -> None:
            if not _authorized(self, config):
                _api_error_response(self, UnauthorizedError())
                return
            parsed = urlparse(self.path)
            route_match = match_route("POST", parsed.path)
            media_request_lease = None
            try:
                max_bytes = config.max_media_payload_bytes if route_match and route_match.route.name == "media-artifact-store" else config.max_payload_bytes
                if route_match and route_match.route.name == "media-artifact-store":
                    media_request_lease = media_resource_budget(config).acquire(
                        byte_count=int(self.headers.get("Content-Length", "0") or 0),
                        request_count=1,
                        timeout=0,
                    )
                data = _read_json(self, max_bytes)
            except MediaResourceUnavailable as exc:
                _api_error_response(self, ResourceUnavailableError(str(exc)))
                return
            except Exception as exc:
                if media_request_lease is not None:
                    media_request_lease.release()
                _api_error_response(self, exc)
                return
            if route_match and route_match.route.name == "media-cache-purge":
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = purge_media_cache(conn, config, data)
                        audit(conn, "media.cache_purge", {"dry_run": result["dry_run"], "rehydrate": result["rehydrate"], "selected": result["selected"], "purged": result["purged"], "bytes": result["bytes"]})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
            if route_match and route_match.route.name == "media-fetch-pending":
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = fetch_pending_media_artifacts(
                            conn,
                            config,
                            snapshot_id=data.get("snapshot_id") or data.get("snapshotId"),
                            document_id=data.get("document_id") or data.get("documentId"),
                            domain=data.get("domain"),
                            limit=_coerce_limit(data.get("limit"), config.max_media_fetches_per_call, config.max_media_fetches_per_call),
                        )
                        audit(
                            conn,
                            "media.fetch_pending",
                            {
                                "snapshot_id": data.get("snapshot_id") or data.get("snapshotId"),
                                "document_id": data.get("document_id") or data.get("documentId"),
                                "domain": data.get("domain"),
                                "attempted": result["attempted"],
                                "stored": result["stored"],
                                "failed": result["failed"],
                                "skipped": result["skipped"],
                                "remaining": result["remaining"],
                                "background": False,
                            },
                        )
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
            if route_match and route_match.route.name == "media-artifact-store":
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = store_media_artifact(conn, config, data)
                        audit(
                            conn,
                            "media.stored" if result["stored"] else "media.metadata",
                            {
                                "artifact_id": result["artifact_id"],
                                "document_id": result["document_id"],
                                "snapshot_id": result["snapshot_id"],
                                "media_type": result["media_type"],
                                "capture_status": result["capture_status"],
                                "byte_size": result["byte_size"],
                            },
                        )
                        conn.commit()
                    _json_response(self, 201 if result["stored"] else 200, result)
                    return
                except KeyError as exc:
                    _api_error_response(self, exc)
                    return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
                finally:
                    if media_request_lease is not None:
                        media_request_lease.release()
            if route_match and route_match.route.name == "visit-event-store":
                try:
                    url = str(data.get("url") or "")
                    decision = evaluate_capture(
                        url,
                        is_incognito=bool(data.get("is_incognito") or data.get("incognito") or False),
                        policy_mode=config.policy_mode,
                    )
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        if decision.allowed:
                            rules_decision = evaluate_policy_rules(conn, url)
                            if not rules_decision.allowed:
                                decision = rules_decision
                        if not decision.allowed:
                            audit(conn, "visit_event.blocked", {"reason": decision.reason})
                            conn.commit()
                            _json_response(self, 200, {"stored": False, "blocked": True, "reason": decision.reason})
                            return
                        result = record_visit_event(conn, data, policy_mode=config.policy_mode)
                        _json_response(self, 201 if result["stored"] else 200, result)
                        return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
            if route_match and route_match.route.name == "capture-store":
                try:
                    url = str(data.get("url") or "")
                    decision = evaluate_capture(
                        url,
                        is_incognito=bool(data.get("is_incognito") or data.get("incognito") or False),
                        policy_mode=config.policy_mode,
                    )
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        if decision.allowed:
                            rules_decision = evaluate_policy_rules(conn, url)
                            if not rules_decision.allowed:
                                decision = rules_decision
                        if not decision.allowed:
                            audit(conn, "capture.blocked", {"reason": decision.reason})
                            conn.commit()
                            _json_response(self, 200, {"stored": False, "blocked": True, "reason": decision.reason})
                            return
                        payload = CapturePayload.from_dict(data, allow_any_url=config.policy_mode == POLICY_MODE_ALL)
                        result = ingest_capture(conn, config, payload)
                        _start_background_fetch_pending_media(
                            config,
                            snapshot_id=result.get("snapshot_id", ""),
                            media_ref_count=int(result.get("media_ref_count") or 0),
                        )
                        _json_response(self, 201, result)
                        return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
            if route_match and route_match.route.name == "forget":
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = forget(conn, config, domain=data.get("domain"), url=data.get("url"))
                        audit(conn, "forget", {"receipt_id": result["receipt_id"], "scope_keys": sorted(result["scope"].keys())})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
            if route_match and route_match.route.name == "policy-rule-create":
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        rule = create_policy_rule(
                            conn,
                            rule_type=str(data.get("rule_type") or data.get("ruleType") or "domain"),
                            pattern=str(data.get("pattern") or ""),
                            action=str(data.get("action") or "block"),
                        )
                    _json_response(self, 201, {"rule": rule})
                    return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
            _api_error_response(self, NotFoundError())

        def do_DELETE(self) -> None:
            if not _authorized(self, config):
                _api_error_response(self, UnauthorizedError())
                return
            parsed = urlparse(self.path)
            route_match = match_route("DELETE", parsed.path)
            if route_match and route_match.route.name == "policy-rule-delete":
                rule_id = route_match.parameters["rule_id"]
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = delete_policy_rule(conn, rule_id)
                    _json_response(self, 200, result)
                    return
                except Exception as exc:
                    _api_error_response(self, exc)
                    return
            _api_error_response(self, NotFoundError())

    return MemoryHandler


def make_server(config: RuntimeConfig) -> ThreadingHTTPServer:
    init_db(config)
    _mark_db_ready(config)
    return MemoryHTTPServer((config.host, config.port), make_handler(config))
