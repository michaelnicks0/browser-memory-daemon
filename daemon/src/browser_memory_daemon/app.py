from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .config import RuntimeConfig
from .db import audit, connect, init_db
from .forget import forget
from .ingest import ingest_capture
from .models import CapturePayload
from .policy import evaluate_capture
from .search import search_memory


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict | list) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    origin = handler.headers.get("Origin", "")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if origin.startswith("chrome-extension://") or origin in {"http://127.0.0.1", "http://localhost"}:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
    handler.send_header("Access-Control-Allow-Headers", "authorization, content-type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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


def make_handler(config: RuntimeConfig):
    class MemoryHandler(BaseHTTPRequestHandler):
        server_version = "BrowserMemoryDaemon/0.1"

        def log_message(self, format: str, *args) -> None:
            return

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
                        "capture_enabled": True,
                    },
                )
                return
            if not _authorized(self, config):
                _json_response(self, 401, {"error": "unauthorized"})
                return
            if parsed.path == "/ready":
                init_db(config)
                _json_response(self, 200, {"ready": True, "db_path": str(config.db_path)})
                return
            if parsed.path == "/search":
                params = parse_qs(parsed.query)
                query = params.get("q", [""])[0]
                try:
                    limit = int(params.get("limit", ["10"])[0])
                    with connect(config.db_path) as conn:
                        results = search_memory(conn, query, limit=limit)
                        audit(conn, "search", {"query_len": len(query), "result_count": len(results)})
                        conn.commit()
                    _json_response(self, 200, {"results": results})
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                return
            _json_response(self, 404, {"error": "not found"})

        def do_POST(self) -> None:
            if not _authorized(self, config):
                _json_response(self, 401, {"error": "unauthorized"})
                return
            try:
                data = _read_json(self, config.max_payload_bytes)
            except Exception as exc:
                _json_response(self, 400, {"error": str(exc)})
                return
            if self.path == "/capture":
                url = str(data.get("url") or "")
                decision = evaluate_capture(url, is_incognito=bool(data.get("is_incognito") or data.get("incognito") or False))
                if not decision.allowed:
                    init_db(config)
                    with connect(config.db_path) as conn:
                        audit(conn, "capture.blocked", {"reason": decision.reason})
                        conn.commit()
                    _json_response(self, 200, {"stored": False, "blocked": True, "reason": decision.reason})
                    return
                try:
                    payload = CapturePayload.from_dict(data)
                    init_db(config)
                    with connect(config.db_path) as conn:
                        result = ingest_capture(conn, config, payload)
                    _json_response(self, 201, result)
                    return
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                    return
            if self.path == "/forget":
                try:
                    init_db(config)
                    with connect(config.db_path) as conn:
                        result = forget(conn, domain=data.get("domain"), url=data.get("url"))
                    _json_response(self, 200, result)
                    return
                except Exception as exc:
                    _json_response(self, 400, {"error": str(exc)})
                    return
            _json_response(self, 404, {"error": "not found"})

    return MemoryHandler


def make_server(config: RuntimeConfig) -> ThreadingHTTPServer:
    init_db(config)
    return ThreadingHTTPServer((config.host, config.port), make_handler(config))
