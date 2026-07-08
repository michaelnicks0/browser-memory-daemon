from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
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
from .models import CapturePayload
from .ops import doctor, document_detail, recent_captures, snapshot_detail, timeline
from .policy import POLICY_MODE_ALL, evaluate_capture
from .policy_store import create_policy_rule, delete_policy_rule, evaluate_policy_rules, list_policy_rules
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


def _binary_response(handler: BaseHTTPRequestHandler, status: int, body: bytes, *, content_type: str, filename: str | None = None) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type or "application/octet-stream")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    if filename:
        handler.send_header("Content-Disposition", f'inline; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(body)


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
    # Request handlers still ensure the schema exists, but they must not run the
    # legacy media-task backfill on every capture/event. That backfill can scan
    # and write thousands of rows and contend with the media worker.
    key = _db_ready_key(config)
    if key in _DB_READY_PATHS and config.db_path.exists():
        return
    with _DB_READY_LOCK:
        if key in _DB_READY_PATHS and config.db_path.exists():
            return
        init_db(config, seed_media_tasks=False)
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
            _json_response(self, code, {"error": message or default_message})

        def do_OPTIONS(self) -> None:
            _json_response(self, 204, {})

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "version": __version__,
                        "storage_root": str(config.data_root),
                        "blob_root": str(config.blob_root),
                        "capture_enabled": True,
                        "policy_mode": config.policy_mode,
                    },
                )
                return
            ui_file = _ui_file_for_path(parsed.path)
            if ui_file:
                _text_response(self, 200, _ui_file_body(ui_file, config), content_type=_content_type(ui_file))
                return
            if not _authorized(self, config):
                _json_response(self, 401, {"error": "unauthorized"})
                return
            params = parse_qs(parsed.query)
            try:
                if parsed.path == "/ready":
                    _ensure_db(config)
                    _json_response(self, 200, {"ready": True, "db_path": str(config.db_path)})
                    return
                if parsed.path == "/search":
                    query = params.get("q", [""])[0]
                    limit = int(params.get("limit", ["10"])[0])
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        results = search_memory(conn, query, limit=limit)
                        audit(conn, "search", {"query_len": len(query), "result_count": len(results)})
                        conn.commit()
                    _json_response(self, 200, {"results": results})
                    return
                if parsed.path == "/recent":
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        results = recent_captures(conn, limit=params.get("limit", ["25"])[0])
                        audit(conn, "recent", {"result_count": len(results)})
                        conn.commit()
                    _json_response(self, 200, {"results": results})
                    return
                if parsed.path == "/timeline":
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
                if parsed.path.startswith("/documents/"):
                    document_id = unquote(parsed.path.removeprefix("/documents/"))
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = document_detail(conn, document_id)
                        audit(conn, "document.detail", {"document_id": document_id})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if parsed.path.startswith("/snapshots/"):
                    snapshot_id = unquote(parsed.path.removeprefix("/snapshots/"))
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = snapshot_detail(conn, snapshot_id)
                        audit(conn, "snapshot.detail", {"snapshot_id": snapshot_id})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if parsed.path == "/media-artifacts/queue-status":
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = media_queue_status(conn, config, limit=_coerce_limit(params.get("limit", ["50"])[0], 50, 200))
                        audit(conn, "media.queue_status", {})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if parsed.path.startswith("/media-artifacts/"):
                    artifact_id = unquote(parsed.path.removeprefix("/media-artifacts/"))
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        artifact = media_artifact(conn, artifact_id)
                        audit(conn, "media.detail", {"artifact_id": artifact_id})
                        conn.commit()
                    path = Path(artifact.get("file_path") or "")
                    if not artifact.get("has_file") or not path.exists():
                        _json_response(self, 404, {"error": "media artifact file not stored", "artifact": {k: v for k, v in artifact.items() if k != "file_path"}})
                        return
                    _binary_response(
                        self,
                        200,
                        path.read_bytes(),
                        content_type=artifact.get("mime_type") or "application/octet-stream",
                        filename=path.name,
                    )
                    return
                if parsed.path == "/doctor":
                    _ensure_db(config)
                    storage_census = _truthy_query_value(params.get("storage_census", [None])[0])
                    with connect(config.db_path) as conn:
                        result = doctor(config, conn, storage_census=storage_census)
                        audit(conn, "doctor", {"ok": result["ok"]})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if parsed.path == "/policy/rules":
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        _json_response(self, 200, {"rules": list_policy_rules(conn)})
                    return
                if parsed.path == "/policy/evaluate":
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
                _json_response(self, 404, {"error": str(exc).strip("'")})
                return
            except Exception as exc:
                _json_response(self, 400, {"error": str(exc)})
                return
            _json_response(self, 404, {"error": "not found"})

        def do_PUT(self) -> None:
            if not _authorized(self, config):
                _json_response(self, 401, {"error": "unauthorized"})
                return
            parsed = urlparse(self.path)
            if parsed.path.startswith("/media-artifacts/") and parsed.path.endswith("/blob"):
                artifact_id = unquote(parsed.path.removeprefix("/media-artifacts/").removesuffix("/blob").strip("/"))
                try:
                    content_length = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError:
                    _json_response(self, 400, {"error": "invalid content length"})
                    return
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        headers = {key: self.headers.get(key, "") for key in ["Content-Type", "X-BMD-Document-ID", "X-BMD-Snapshot-ID", "X-BMD-Source-URL"]}
                        result = store_media_blob_stream(conn, config, artifact_id, self.rfile, headers=headers, content_length=content_length)
                        audit(conn, "media.blob_put", {"artifact_id": artifact_id, "stored": result["stored"], "capture_status": result["capture_status"], "byte_size": result["byte_size"]})
                        conn.commit()
                    _json_response(self, 201 if result["stored"] else 200, result)
                    return
                except KeyError as exc:
                    _json_response(self, 404, {"error": str(exc).strip("'")})
                    return
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                    return
            _json_response(self, 404, {"error": "not found"})

        def do_POST(self) -> None:
            if not _authorized(self, config):
                _json_response(self, 401, {"error": "unauthorized"})
                return
            parsed = urlparse(self.path)
            try:
                max_bytes = config.max_media_payload_bytes if parsed.path == "/media-artifacts" else config.max_payload_bytes
                data = _read_json(self, max_bytes)
            except Exception as exc:
                _json_response(self, 400, {"error": str(exc)})
                return
            if parsed.path == "/media-artifacts/purge-cache":
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = purge_media_cache(conn, config, data)
                        audit(conn, "media.cache_purge", {"dry_run": result["dry_run"], "rehydrate": result["rehydrate"], "selected": result["selected"], "purged": result["purged"], "bytes": result["bytes"]})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                    return
            if parsed.path == "/media-artifacts/fetch-pending":
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
                    _json_response(self, 400, {"error": str(exc)})
                    return
            if parsed.path == "/media-artifacts":
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
                    _json_response(self, 404, {"error": str(exc).strip("'")})
                    return
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                    return
            if parsed.path == "/visit-events":
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
                    try:
                        result = record_visit_event(conn, data, policy_mode=config.policy_mode)
                        _json_response(self, 201 if result["stored"] else 200, result)
                        return
                    except Exception as exc:
                        _json_response(self, 400, {"error": str(exc)})
                        return
            if parsed.path == "/capture":
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
                    try:
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
                        _json_response(self, 400, {"error": str(exc)})
                        return
            if parsed.path == "/forget":
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = forget(conn, domain=data.get("domain"), url=data.get("url"))
                        audit(conn, "forget", {"receipt_id": result["receipt_id"], "scope_keys": sorted(result["scope"].keys())})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                    return
            if parsed.path == "/policy/rules":
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
                    _json_response(self, 400, {"error": str(exc)})
                    return
            _json_response(self, 404, {"error": "not found"})

        def do_DELETE(self) -> None:
            if not _authorized(self, config):
                _json_response(self, 401, {"error": "unauthorized"})
                return
            parsed = urlparse(self.path)
            if parsed.path.startswith("/policy/rules/"):
                rule_id = unquote(parsed.path.removeprefix("/policy/rules/"))
                try:
                    _ensure_db(config)
                    with connect(config.db_path) as conn:
                        result = delete_policy_rule(conn, rule_id)
                    _json_response(self, 200, result)
                    return
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                    return
            _json_response(self, 404, {"error": "not found"})

    return MemoryHandler


def make_server(config: RuntimeConfig) -> ThreadingHTTPServer:
    init_db(config)
    _mark_db_ready(config)
    return MemoryHTTPServer((config.host, config.port), make_handler(config))
