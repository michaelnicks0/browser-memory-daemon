from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .config import RuntimeConfig
from .db import audit, connect, init_db
from .forget import forget
from .ingest import ingest_capture
from .lifecycle import record_visit_event
from .models import CapturePayload
from .ops import doctor, document_detail, recent_captures, snapshot_detail, timeline
from .policy import evaluate_capture
from .policy_store import create_policy_rule, delete_policy_rule, evaluate_policy_rules, list_policy_rules
from .search import search_memory


UI_ROOT = Path(__file__).resolve().parents[3] / "ui"


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
    handler.send_header("Access-Control-Allow-Headers", "authorization, content-type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, body: bytes, *, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-Content-Type-Options", "nosniff")
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
            ui_file = _ui_file_for_path(parsed.path)
            if ui_file:
                _text_response(self, 200, ui_file.read_bytes(), content_type=_content_type(ui_file))
                return
            if not _authorized(self, config):
                _json_response(self, 401, {"error": "unauthorized"})
                return
            params = parse_qs(parsed.query)
            try:
                if parsed.path == "/ready":
                    init_db(config)
                    _json_response(self, 200, {"ready": True, "db_path": str(config.db_path)})
                    return
                if parsed.path == "/search":
                    query = params.get("q", [""])[0]
                    limit = int(params.get("limit", ["10"])[0])
                    init_db(config)
                    with connect(config.db_path) as conn:
                        results = search_memory(conn, query, limit=limit)
                        audit(conn, "search", {"query_len": len(query), "result_count": len(results)})
                        conn.commit()
                    _json_response(self, 200, {"results": results})
                    return
                if parsed.path == "/recent":
                    init_db(config)
                    with connect(config.db_path) as conn:
                        results = recent_captures(conn, limit=params.get("limit", ["25"])[0])
                        audit(conn, "recent", {"result_count": len(results)})
                        conn.commit()
                    _json_response(self, 200, {"results": results})
                    return
                if parsed.path == "/timeline":
                    init_db(config)
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
                    init_db(config)
                    with connect(config.db_path) as conn:
                        result = document_detail(conn, document_id)
                        audit(conn, "document.detail", {"document_id": document_id})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if parsed.path.startswith("/snapshots/"):
                    snapshot_id = unquote(parsed.path.removeprefix("/snapshots/"))
                    init_db(config)
                    with connect(config.db_path) as conn:
                        result = snapshot_detail(conn, snapshot_id)
                        audit(conn, "snapshot.detail", {"snapshot_id": snapshot_id})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if parsed.path == "/doctor":
                    init_db(config)
                    with connect(config.db_path) as conn:
                        result = doctor(config, conn)
                        audit(conn, "doctor", {"ok": result["ok"]})
                        conn.commit()
                    _json_response(self, 200, result)
                    return
                if parsed.path == "/policy/rules":
                    init_db(config)
                    with connect(config.db_path) as conn:
                        _json_response(self, 200, {"rules": list_policy_rules(conn)})
                    return
                if parsed.path == "/policy/evaluate":
                    url = params.get("url", [""])[0]
                    static_decision = evaluate_capture(url)
                    persistent_decision = static_decision
                    if static_decision.allowed:
                        init_db(config)
                        with connect(config.db_path) as conn:
                            persistent_decision = evaluate_policy_rules(conn, url)
                    _json_response(
                        self,
                        200,
                        {
                            "allowed": persistent_decision.allowed,
                            "reason": persistent_decision.reason,
                            "privacy_class": persistent_decision.privacy_class,
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

        def do_POST(self) -> None:
            if not _authorized(self, config):
                _json_response(self, 401, {"error": "unauthorized"})
                return
            parsed = urlparse(self.path)
            try:
                data = _read_json(self, config.max_payload_bytes)
            except Exception as exc:
                _json_response(self, 400, {"error": str(exc)})
                return
            if parsed.path == "/visit-events":
                url = str(data.get("url") or "")
                decision = evaluate_capture(url, is_incognito=bool(data.get("is_incognito") or data.get("incognito") or False))
                init_db(config)
                with connect(config.db_path) as conn:
                    if decision.allowed:
                        decision = evaluate_policy_rules(conn, url)
                    if not decision.allowed:
                        audit(conn, "visit_event.blocked", {"reason": decision.reason})
                        conn.commit()
                        _json_response(self, 200, {"stored": False, "blocked": True, "reason": decision.reason})
                        return
                    try:
                        result = record_visit_event(conn, data)
                        _json_response(self, 201 if result["stored"] else 200, result)
                        return
                    except Exception as exc:
                        _json_response(self, 400, {"error": str(exc)})
                        return
            if parsed.path == "/capture":
                url = str(data.get("url") or "")
                decision = evaluate_capture(url, is_incognito=bool(data.get("is_incognito") or data.get("incognito") or False))
                init_db(config)
                with connect(config.db_path) as conn:
                    if decision.allowed:
                        decision = evaluate_policy_rules(conn, url)
                    if not decision.allowed:
                        audit(conn, "capture.blocked", {"reason": decision.reason})
                        conn.commit()
                        _json_response(self, 200, {"stored": False, "blocked": True, "reason": decision.reason})
                        return
                    try:
                        payload = CapturePayload.from_dict(data)
                        result = ingest_capture(conn, config, payload)
                        _json_response(self, 201, result)
                        return
                    except Exception as exc:
                        _json_response(self, 400, {"error": str(exc)})
                        return
            if parsed.path == "/forget":
                try:
                    init_db(config)
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
                    init_db(config)
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
                    init_db(config)
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
    return ThreadingHTTPServer((config.host, config.port), make_handler(config))
