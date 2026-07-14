from __future__ import annotations

import ipaddress
import json
import re
import secrets
import sys
import threading
import time
import weakref
from collections.abc import Iterable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO, cast
from urllib.parse import parse_qs, unquote, urlparse

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
from .application import MemoryApplication
from .config import RuntimeConfig
from .media_resources import MediaResourceUnavailable, media_resource_budget
from .routes import match_route
from .x_observation_export import XObservationCompatibilityError, export_x_observations

_API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
_UI_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self' http://127.0.0.1:* http://localhost:*; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)
_SAFE_ROUTE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_CONTEXT_LOCK = threading.RLock()
_TELEMETRY_LOCK = threading.Lock()
_CLIENT_DISCONNECT_ERRORS = (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, TimeoutError)
UI_ROOT = Path(__file__).resolve().parents[3] / "ui"
REQUEST_QUEUE_SIZE = 128


@dataclass
class _RequestContext:
    request_id: str
    started: float
    route: str = "unknown"
    complete: bool = False


_CONTEXTS: weakref.WeakKeyDictionary[BaseHTTPRequestHandler, _RequestContext] = weakref.WeakKeyDictionary()


def begin_request(handler: BaseHTTPRequestHandler) -> None:
    with _CONTEXT_LOCK:
        _CONTEXTS[handler] = _RequestContext(
            request_id=f"req_{secrets.token_hex(16)}",
            started=time.monotonic(),
        )


def _request_context(handler: BaseHTTPRequestHandler) -> _RequestContext:
    with _CONTEXT_LOCK:
        context = _CONTEXTS.get(handler)
        if context is None:
            context = _RequestContext(
                request_id=f"req_{secrets.token_hex(16)}",
                started=time.monotonic(),
            )
            _CONTEXTS[handler] = context
        return context


def request_id(handler: BaseHTTPRequestHandler) -> str:
    return _request_context(handler).request_id


def set_request_route(handler: BaseHTTPRequestHandler, route: str) -> None:
    safe_route = route if _SAFE_ROUTE.fullmatch(route) else "unknown"
    with _CONTEXT_LOCK:
        _request_context(handler).route = safe_route


def send_security_headers(handler: BaseHTTPRequestHandler, *, ui: bool = False) -> None:
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Security-Policy", _UI_CONTENT_SECURITY_POLICY if ui else _API_CONTENT_SECURITY_POLICY)
    handler.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("X-Request-ID", request_id(handler))


def abandon_request(handler: BaseHTTPRequestHandler, *, error_code: str = "client_disconnected") -> bool:
    handler.close_connection = True
    complete_request(handler, status=499, error_code=error_code)
    return False


def send_response_headers(
    handler: BaseHTTPRequestHandler,
    status: int,
    headers: Iterable[tuple[str, str]],
    *,
    ui: bool = False,
) -> bool:
    try:
        handler.send_response(status)
        for name, value in headers:
            handler.send_header(name, value)
        send_security_headers(handler, ui=ui)
        handler.end_headers()
    except _CLIENT_DISCONNECT_ERRORS:
        return abandon_request(handler)
    except OSError:
        return abandon_request(handler)
    return True


def _failed_response_body(handler: BaseHTTPRequestHandler, *, status: int, error_code: str) -> bool:
    handler.close_connection = True
    complete_request(handler, status=status, error_code=error_code)
    return False


def write_response_bytes(
    handler: BaseHTTPRequestHandler,
    content: bytes,
    *,
    status: int,
    error_code: str | None = None,
) -> bool:
    try:
        handler.wfile.write(content)
    except _CLIENT_DISCONNECT_ERRORS:
        return _failed_response_body(handler, status=499, error_code="client_disconnected")
    except Exception:
        return _failed_response_body(handler, status=500, error_code="response_write_failed")
    complete_request(handler, status=status, error_code=error_code)
    return True


def stream_response_body(
    handler: BaseHTTPRequestHandler,
    stream: BinaryIO,
    *,
    status: int,
    chunk_size: int = 64 * 1024,
    expected_bytes: int | None = None,
) -> bool:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    sent_bytes = 0
    while True:
        try:
            chunk = stream.read(chunk_size)
        except Exception:
            return _failed_response_body(handler, status=500, error_code="response_stream_failed")
        if not chunk:
            if expected_bytes is not None and sent_bytes != expected_bytes:
                return _failed_response_body(handler, status=500, error_code="response_stream_incomplete")
            complete_request(handler, status=status)
            return True
        if not isinstance(chunk, (bytes, bytearray, memoryview)) or len(chunk) > chunk_size:
            return _failed_response_body(handler, status=500, error_code="response_stream_failed")
        sent_bytes += len(chunk)
        if expected_bytes is not None and sent_bytes > expected_bytes:
            return _failed_response_body(handler, status=500, error_code="response_stream_failed")
        try:
            handler.wfile.write(bytes(chunk))
        except _CLIENT_DISCONNECT_ERRORS:
            return _failed_response_body(handler, status=499, error_code="client_disconnected")
        except Exception:
            return _failed_response_body(handler, status=500, error_code="response_write_failed")


def complete_request(handler: BaseHTTPRequestHandler, *, status: int, error_code: str | None = None) -> None:
    with _CONTEXT_LOCK:
        context = _request_context(handler)
        if context.complete:
            return
        context.complete = True
        request_identifier = context.request_id
        route = context.route if _SAFE_ROUTE.fullmatch(context.route) else "unknown"
        latency_ms = max(0, int((time.monotonic() - context.started) * 1000))
    method = str(getattr(handler, "command", "UNKNOWN") or "UNKNOWN").upper()
    if not method.isascii() or not method.isalpha() or len(method) > 12:
        method = "UNKNOWN"
    event = {
        "event": "http.request",
        "request_id": request_identifier,
        "method": method,
        "route": route,
        "status": int(status),
        "latency_ms": latency_ms,
        "error_code": error_code,
    }
    try:
        line = json.dumps(event, sort_keys=True, separators=(",", ":"))
        with _TELEMETRY_LOCK:
            sys.stderr.write(line + "\n")
            sys.stderr.flush()
    except Exception:
        # Request telemetry must never alter the HTTP outcome.
        return


class MemoryHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = REQUEST_QUEUE_SIZE


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


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any] | list[Any]) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    request_headers = getattr(handler, "headers", None)
    origin = request_headers.get("Origin", "") if request_headers is not None else ""
    headers = [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Headers", "authorization, content-type, x-bmd-document-id, x-bmd-snapshot-id, x-bmd-source-url"),
        ("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"),
        ("Access-Control-Expose-Headers", "X-Request-ID"),
    ]
    if _origin_allowed(origin):
        headers.extend([("Access-Control-Allow-Origin", origin), ("Vary", "Origin")])
    if not send_response_headers(handler, status, headers):
        return
    error_code = payload.get("error_code") if isinstance(payload, dict) else None
    write_response_bytes(
        handler,
        body,
        status=status,
        error_code=error_code if isinstance(error_code, str) else None,
    )


def _api_error_response(handler: BaseHTTPRequestHandler, error: Exception) -> None:
    api_error = classify_exception(error)
    payload = api_error.payload()
    payload["request_id"] = request_id(handler)
    _json_response(handler, api_error.status, payload)


def _text_response(handler: BaseHTTPRequestHandler, status: int, body: bytes, *, content_type: str) -> None:
    headers = [("Content-Type", content_type), ("Content-Length", str(len(body)))]
    if not send_response_headers(handler, status, headers, ui=True):
        return
    write_response_bytes(handler, body, status=status)


def _ui_bootstrap_script(config: RuntimeConfig) -> str:
    payload = {
        "api_token": config.api_token,
        "policy_mode": config.policy_mode,
        "storage_root": str(config.data_root),
        "blob_root": str(config.blob_root),
        "derivative_root": str(config.clean_text_root.parent),
        "media_root": str(config.media_root),
    }
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
    stream: BinaryIO,
    *,
    content_length: int,
    content_type: str,
    filename: str | None = None,
) -> None:
    headers = [
        ("Content-Type", content_type or "application/octet-stream"),
        ("Content-Length", str(content_length)),
    ]
    if filename:
        headers.append(("Content-Disposition", f'inline; filename="{filename}"'))
    if not send_response_headers(handler, status, headers):
        return
    stream_response_body(handler, stream, status=status, expected_bytes=content_length)


def _content_length(handler: BaseHTTPRequestHandler, *, required: bool = False) -> int:
    values = handler.headers.get_all("Content-Length", [])
    if not values:
        if required:
            raise ValidationError("content length is required")
        return 0
    raw = values[0]
    if len(values) != 1 or len(raw) > 20 or not raw.isascii() or not raw.isdigit():
        raise ValidationError("invalid content length")
    return int(raw)


def _read_json(handler: BaseHTTPRequestHandler, max_bytes: int) -> dict[str, Any]:
    length = _content_length(handler)
    if length > max_bytes:
        raise ValidationError("payload too large")
    raw = handler.rfile.read(length)
    if len(raw) != length:
        raise ValidationError("request body shorter than content length")
    if not raw:
        return {}
    return cast(dict[str, Any], json.loads(raw.decode("utf-8")))


def _authorized(handler: BaseHTTPRequestHandler, config: RuntimeConfig) -> bool:
    return handler.headers.get("Authorization", "") == f"Bearer {config.api_token}"


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
    if not _is_loopback_host(_request_host_header(handler), allow_names=True):
        return False
    if _is_loopback_host(config.host, allow_names=True):
        return True
    client_host = str(handler.client_address[0]) if handler.client_address else ""
    return _is_loopback_host(client_host, allow_names=False)


def _ui_file_for_path(path: str) -> Path | None:
    if path in {"/", "/ui", "/ui/"}:
        candidate = UI_ROOT / "index.html"
    elif path.startswith("/ui/"):
        candidate = UI_ROOT / unquote(path.removeprefix("/ui/"))
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
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
    }.get(path.suffix.lower(), "application/octet-stream")


def _coerce_limit(value: int | str | None, default: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _truthy_query_value(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "full", "filesystem"}


def make_handler(config: RuntimeConfig, application: MemoryApplication) -> type[BaseHTTPRequestHandler]:
    class MemoryHandler(BaseHTTPRequestHandler):
        server_version = "BrowserMemoryDaemon/0.1"

        def handle_one_request(self) -> None:
            begin_request(self)
            super().handle_one_request()

        def log_message(self, format: str, *args: object) -> None:
            return

        def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
            default_message = self.responses.get(code, ("error", ""))[0]
            if code == 501:
                _api_error_response(self, UnsupportedMethodError(message or default_message))
                return
            _api_error_response(self, APIError(status=code, code="http_error", message=message or default_message))

        def do_OPTIONS(self) -> None:
            set_request_route(self, "options")
            _json_response(self, 204, {})

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            route_match = match_route("GET", parsed.path)
            set_request_route(self, route_match.route.name if route_match else "unknown")
            if route_match and route_match.route.name == "health":
                _json_response(self, 200, application.health())
                return
            ui_file = _ui_file_for_path(parsed.path)
            if ui_file:
                set_request_route(self, "ui")
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
                    _json_response(self, 200, application.ready())
                    return
                if route_match and route_match.route.name == "search":
                    query = params.get("q", [""])[0]
                    results = application.search(query, limit=int(params.get("limit", ["10"])[0]))
                    _json_response(self, 200, {"results": results})
                    return
                if route_match and route_match.route.name == "recent":
                    results = application.recent(limit=params.get("limit", ["25"])[0])
                    _json_response(self, 200, {"results": results})
                    return
                if route_match and route_match.route.name == "timeline":
                    result = application.timeline(
                        day=params.get("date", [None])[0],
                        after=params.get("after", [None])[0],
                        before=params.get("before", [None])[0],
                        limit=params.get("limit", ["100"])[0],
                    )
                    _json_response(self, 200, result)
                    return
                if route_match and route_match.route.name == "x-observation-export":
                    try:
                        result = export_x_observations(
                            config.db_path,
                            cursor=params.get("cursor", [None])[0],
                            limit=int(params.get("limit", ["100"])[0]),
                        )
                    except XObservationCompatibilityError as exc:
                        raise ResourceUnavailableError(str(exc)) from exc
                    _json_response(self, 200, result)
                    return
                if route_match and route_match.route.name == "document-detail":
                    result = application.document_detail(route_match.parameters["document_id"])
                    _json_response(self, 200, result)
                    return
                if route_match and route_match.route.name == "snapshot-detail":
                    result = application.snapshot_detail(route_match.parameters["snapshot_id"])
                    _json_response(self, 200, result)
                    return
                if route_match and route_match.route.name == "media-queue-status":
                    limit = _coerce_limit(params.get("limit", ["50"])[0], 50, 200)
                    _json_response(self, 200, application.media_queue_status(limit=limit))
                    return
                if route_match and route_match.route.name == "media-detail":
                    with application.media_download(route_match.parameters["artifact_id"]) as download:
                        _binary_stream_response(
                            self,
                            200,
                            download.stream,
                            content_length=download.content_length,
                            content_type=download.content_type,
                            filename=download.filename,
                        )
                    return
                if route_match and route_match.route.name == "doctor":
                    storage_census = _truthy_query_value(params.get("storage_census", [None])[0])
                    _json_response(self, 200, application.doctor(storage_census=storage_census))
                    return
                if route_match and route_match.route.name == "policy-rules-list":
                    _json_response(self, 200, {"rules": application.list_policy_rules()})
                    return
                if route_match and route_match.route.name == "policy-evaluate":
                    _json_response(self, 200, application.evaluate_policy(params.get("url", [""])[0]))
                    return
            except Exception as exc:
                _api_error_response(self, exc)
                return
            _api_error_response(self, NotFoundError())

        def do_PUT(self) -> None:
            parsed = urlparse(self.path)
            route_match = match_route("PUT", parsed.path)
            set_request_route(self, route_match.route.name if route_match else "unknown")
            if not _authorized(self, config):
                _api_error_response(self, UnauthorizedError())
                return
            if not route_match or route_match.route.name != "media-blob-put":
                _api_error_response(self, NotFoundError())
                return
            try:
                content_length = _content_length(self, required=True)
            except ValidationError as exc:
                _api_error_response(self, exc)
                return
            try:
                headers = {
                    key: self.headers.get(key, "")
                    for key in ["Content-Type", "X-BMD-Document-ID", "X-BMD-Snapshot-ID", "X-BMD-Source-URL"]
                }
                result = application.store_media_blob(
                    route_match.parameters["artifact_id"],
                    self.rfile,
                    headers=headers,
                    content_length=content_length,
                )
                _json_response(self, 201 if result["stored"] else 200, result)
            except Exception as exc:
                _api_error_response(self, exc)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            route_match = match_route("POST", parsed.path)
            set_request_route(self, route_match.route.name if route_match else "unknown")
            if not _authorized(self, config):
                _api_error_response(self, UnauthorizedError())
                return
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
                if route_match and route_match.route.name == "media-cache-purge":
                    _json_response(self, 200, application.purge_media_cache(data))
                    return
                if route_match and route_match.route.name == "media-fetch-pending":
                    _json_response(self, 200, application.fetch_pending_media(data))
                    return
                if route_match and route_match.route.name == "media-artifact-store":
                    result = application.store_media_artifact(data)
                    _json_response(self, 201 if result["stored"] else 200, result)
                    return
                if route_match and route_match.route.name == "visit-event-store":
                    result = application.record_visit_event(data)
                    _json_response(self, 201 if result["stored"] else 200, result)
                    return
                if route_match and route_match.route.name == "capture-store":
                    result = application.capture(data)
                    _json_response(self, 200 if result.get("blocked") else 201, result)
                    return
                if route_match and route_match.route.name == "forget":
                    _json_response(self, 200, application.forget(data))
                    return
                if route_match and route_match.route.name == "policy-rule-create":
                    rule = application.create_policy_rule(
                        rule_type=str(data.get("rule_type") or data.get("ruleType") or "domain"),
                        pattern=str(data.get("pattern") or ""),
                        action=str(data.get("action") or "block"),
                    )
                    _json_response(self, 201, {"rule": rule})
                    return
                _api_error_response(self, NotFoundError())
            except MediaResourceUnavailable as exc:
                _api_error_response(self, ResourceUnavailableError(str(exc)))
            except Exception as exc:
                _api_error_response(self, exc)
            finally:
                if media_request_lease is not None:
                    media_request_lease.release()

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            route_match = match_route("DELETE", parsed.path)
            set_request_route(self, route_match.route.name if route_match else "unknown")
            if not _authorized(self, config):
                _api_error_response(self, UnauthorizedError())
                return
            if route_match and route_match.route.name == "policy-rule-delete":
                try:
                    result = application.delete_policy_rule(route_match.parameters["rule_id"])
                    _json_response(self, 200, result)
                except Exception as exc:
                    _api_error_response(self, exc)
                return
            _api_error_response(self, NotFoundError())

    return MemoryHandler


def create_http_server(config: RuntimeConfig, application: MemoryApplication) -> ThreadingHTTPServer:
    return MemoryHTTPServer((config.host, config.port), make_handler(config, application))
