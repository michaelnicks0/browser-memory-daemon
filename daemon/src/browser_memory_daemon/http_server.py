from __future__ import annotations

import json
import re
import secrets
import sys
import threading
import time
import weakref
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler

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
