import base64
import io
import json
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import browser_memory_daemon.media_fetch as media_fetch_module
import browser_memory_daemon.media_hls as media_hls_module
import browser_memory_daemon.media_transport as media_transport_module
from browser_memory_daemon.app import make_server
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.media import (
    claim_media_fetch_tasks,
    fetch_pending_media_artifacts,
    media_artifacts_for_snapshot,
    purge_media_cache,
    store_media_artifact,
    store_media_blob_stream,
)
from browser_memory_daemon.media_ops import reconcile_cdp_blob_coverage
from browser_memory_daemon.media_resources import media_resource_budget
from browser_memory_daemon.media_worker import run_once
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.search import search_memory


def post_json(url: str, token: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8") or "{}")


@contextmanager
def http_status_fixture_server(status_code: int, *, content_type: str = "image/png", body: bytes = b""):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def allow_loopback_public_fetch(cfg):
    return replace(cfg, media_public_fetch_allow_private_hosts=("127.0.0.1", "localhost", "::1"))


class FakeFetchResponse:
    def __init__(self, *, status: int = 200, headers: dict[str, str] | None = None, body: bytes = b""):
        self.status = status
        self.headers = {"content-length": str(len(body)), **(headers or {})}
        self._body = io.BytesIO(body)
        self._sock: object | None = None
        self.bytes_read = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        chunk = self._body.read(size)
        self.bytes_read += len(chunk)
        return chunk


def fake_resolver_for(mapping: dict[str, str]):
    def resolver(host: str, port: int, *args, **kwargs):
        address = mapping[host]
        family = media_fetch_module.socket.AF_INET6 if ":" in address else media_fetch_module.socket.AF_INET
        sockaddr = (address, port, 0, 0) if family == media_fetch_module.socket.AF_INET6 else (address, port)
        return [(family, media_fetch_module.socket.SOCK_STREAM, 6, "", sockaddr)]

    return resolver


def test_guarded_public_fetch_rejects_dns_to_private_without_opening(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    opened: list[str] = []

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"cdn.example": "10.0.0.5"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", lambda request, *, timeout: opened.append(request.full_url))

    content, mime_type, reason = media_transport_module._fetch_media_bytes(
        "https://cdn.example/private.png",
        "https://page.example/full/path?secret=1",
        media_type="image",
        max_bytes=100,
        timeout_seconds=1,
        config=cfg,
    )

    assert content == b""
    assert mime_type == ""
    assert reason == "fetch-blocked-private-address"
    assert opened == []


def test_guarded_public_fetch_rejects_ipv6_loopback_literal_without_resolving(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    opened: list[str] = []

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("resolver should not run")))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", lambda request, *, timeout: opened.append(request.full_url))

    _content, _mime_type, reason = media_transport_module._fetch_media_bytes(
        "http://[::1]/loopback.png",
        "https://page.example/full/path?secret=1",
        media_type="image",
        max_bytes=100,
        timeout_seconds=1,
        config=cfg,
    )

    assert reason == "fetch-blocked-private-address"
    assert opened == []


def test_guarded_public_fetch_allowlisted_private_host_omits_referer(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, media_public_fetch_allow_private_hosts=("private.example",))
    requests = []

    def opener(request, *, timeout):
        requests.append(request)
        return FakeFetchResponse(headers={"content-type": "image/png"}, body=b"image-bytes")

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"private.example": "10.0.0.8"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", opener)

    content, mime_type, reason = media_transport_module._fetch_media_bytes(
        "https://private.example/image.png",
        "https://page.example/full/path?secret=1",
        media_type="image",
        max_bytes=100,
        timeout_seconds=1,
        config=cfg,
    )

    assert content == b"image-bytes"
    assert mime_type == "image/png"
    assert reason == ""
    headers = {key.lower(): value for key, value in requests[0].header_items()}
    assert "referer" not in headers


def test_guarded_public_fetch_revalidates_public_to_private_redirect(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    opened: list[str] = []

    def opener(request, *, timeout):
        opened.append(request.full_url)
        return FakeFetchResponse(status=302, headers={"location": "http://private.internal/image.png"})

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"public.example": "8.8.8.8", "private.internal": "10.0.0.9"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", opener)

    _content, _mime_type, reason = media_transport_module._fetch_media_bytes(
        "https://public.example/redirect.png",
        "https://page.example/full/path?secret=1",
        media_type="image",
        max_bytes=100,
        timeout_seconds=1,
        config=cfg,
    )

    assert reason == "fetch-blocked-private-address"
    assert opened == ["https://public.example/redirect.png"]


def test_guarded_public_fetch_detects_redirect_loop(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    opened: list[str] = []

    def opener(request, *, timeout):
        opened.append(request.full_url)
        return FakeFetchResponse(status=302, headers={"location": request.full_url})

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"loop.example": "8.8.8.8"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", opener)

    _content, _mime_type, reason = media_transport_module._fetch_media_bytes(
        "https://loop.example/media.png",
        "https://page.example/full/path?secret=1",
        media_type="image",
        max_bytes=100,
        timeout_seconds=1,
        config=cfg,
    )

    assert reason == "fetch-redirect-loop"
    assert opened == ["https://loop.example/media.png"]


def test_guarded_hls_revalidates_private_child_url(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    opened: list[str] = []

    def opener(request, *, timeout):
        opened.append(request.full_url)
        return FakeFetchResponse(
            headers={"content-type": "application/x-mpegURL"},
            body=b"#EXTM3U\n#EXTINF:1.0,\nhttp://192.168.1.10/segment.ts\n#EXT-X-ENDLIST\n",
        )

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"media.example": "8.8.8.8"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", opener)

    _content, _mime_type, reason = media_transport_module._fetch_media_bytes(
        "https://media.example/master.m3u8",
        "https://page.example/full/path?secret=1",
        media_type="video",
        max_bytes=1000,
        timeout_seconds=1,
        config=cfg,
    )

    assert reason == "fetch-blocked-private-address"
    assert opened == ["https://media.example/master.m3u8"]


def test_guarded_hls_enforces_total_request_budget(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, media_hls_max_requests=1)
    opened: list[str] = []

    def opener(request, *, timeout):
        opened.append(request.full_url)
        return FakeFetchResponse(
            headers={"content-type": "application/x-mpegURL"},
            body=b"#EXTM3U\n#EXTINF:1.0,\nhttps://media.example/segment.ts\n#EXT-X-ENDLIST\n",
        )

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"media.example": "8.8.8.8"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", opener)

    _content, _mime_type, reason = media_transport_module._fetch_media_bytes(
        "https://media.example/master.m3u8",
        "https://page.example/full/path?secret=1",
        media_type="video",
        max_bytes=1000,
        timeout_seconds=1,
        config=cfg,
    )

    assert reason == "hls-request-budget-exceeded"
    assert opened == ["https://media.example/master.m3u8"]


def test_guarded_hls_initial_redirect_claims_total_request_budget(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, media_hls_max_requests=1)
    opened: list[str] = []

    def opener(request, *, timeout):
        opened.append(request.full_url)
        return FakeFetchResponse(status=302, headers={"location": "https://media.example/master.m3u8"})

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"media.example": "8.8.8.8"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", opener)

    _content, _mime_type, reason = media_transport_module._fetch_media_bytes(
        "https://media.example/redirect",
        "https://page.example/full/path?secret=1",
        media_type="video",
        max_bytes=1000,
        timeout_seconds=1,
        config=cfg,
    )

    assert reason == "hls-request-budget-exceeded"
    assert opened == ["https://media.example/redirect"]


def test_guarded_fetch_enforces_deadline_during_slow_response_body(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    clock = {"now": 100.0}

    class SlowFetchResponse(FakeFetchResponse):
        def read(self, size: int = -1) -> bytes:
            chunk = super().read(size)
            clock["now"] += 2.0
            return chunk

    read_timeouts: list[float] = []

    class FakeSocket:
        def settimeout(self, timeout: float) -> None:
            read_timeouts.append(timeout)

    response = SlowFetchResponse(headers={"content-type": "video/mp2t"}, body=b"abc")
    response._sock = FakeSocket()

    def monotonic() -> float:
        return clock["now"]

    monkeypatch.setattr(media_fetch_module.time, "monotonic", monotonic)
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"media.example": "8.8.8.8"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", lambda request, *, timeout: response)
    output = io.BytesIO()

    _content, _content_type, _final_url, reason = media_fetch_module._guarded_public_fetch(
        cfg,
        "https://media.example/segment.ts",
        "https://page.example/full/path?secret=1",
        accept="video/*",
        max_bytes=1000,
        timeout_seconds=10,
        deadline=101.0,
        output_stream=output,
    )

    assert reason == "hls-time-budget-exceeded"
    assert response.bytes_read == 3
    assert read_timeouts == [1.0]
    assert output.getvalue() == b""


def test_guarded_hls_enforces_initial_playlist_byte_budget(monkeypatch, tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, media_hls_playlist_max_bytes=32)
    opened: list[str] = []

    response = FakeFetchResponse(
        headers={"content-type": "application/octet-stream"},
        body=b"#EXTM3U\n" + b"# oversized playlist padding\n" * 4,
    )

    def opener(request, *, timeout):
        opened.append(request.full_url)
        return response

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_RESOLVER", fake_resolver_for({"media.example": "8.8.8.8"}))
    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", opener)

    _content, _mime_type, reason = media_transport_module._fetch_media_bytes(
        "https://media.example/disguised.bin",
        "https://page.example/full/path?secret=1",
        media_type="video",
        max_bytes=1000,
        timeout_seconds=1,
        config=cfg,
    )

    assert reason == "media-too-large"
    assert opened == ["https://media.example/disguised.bin"]
    assert response.bytes_read == cfg.media_hls_playlist_max_bytes + 1


def test_media_worker_processes_data_url_task_and_marks_success(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/worker-media",
            "title": "Worker Media",
            "text": "Readable worker media body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
        assert summary["attempted"] == 1
        assert summary["stored"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "stored"
        task = conn.execute("SELECT status FROM media_fetch_tasks").fetchone()
        assert task["status"] == "succeeded"


def test_media_resource_pressure_does_not_roll_back_searchable_text(tmp_path, monkeypatch):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, max_media_concurrent_requests=1, media_fetch_timeout_seconds=0.01)
    init_db(cfg)
    monkeypatch.setattr(
        media_fetch_module,
        "_PUBLIC_FETCH_RESOLVER",
        fake_resolver_for({"media.example": "93.184.216.34"}),
    )

    def unexpected_open(*_args, **_kwargs):
        raise AssertionError("request slot exhaustion must prevent network open")

    monkeypatch.setattr(media_fetch_module, "_PUBLIC_FETCH_OPENER", unexpected_open)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/text-first-budget",
            "title": "Text first under media pressure",
            "text": "Searchable text commits before optional media fetch.",
            "media_artifacts": [
                {
                    "media_type": "image",
                    "source_url": "https://media.example/image.png",
                    "mime_type": "image/png",
                }
            ],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        capture = ingest_capture(conn, cfg, payload)
        conn.commit()
        with media_resource_budget(cfg).acquire(byte_count=0, request_count=1, timeout=0):
            summary = run_once(conn, cfg, worker_id="pressure-worker", limit=1)
        media = media_artifacts_for_snapshot(conn, capture["snapshot_id"])[0]
        results = search_memory(conn, "Searchable text commits", limit=5)

    assert summary["attempted"] == 1
    assert media["capture_status"] == "retrying"
    assert media["status_reason"] == "media-resource-budget"
    assert results and results[0]["snapshot_id"] == capture["snapshot_id"]


def test_init_db_does_not_repeat_historical_media_task_seed(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/seed-task",
            "title": "Seed Task",
            "text": "Readable seed task body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        conn.execute("DELETE FROM media_fetch_tasks")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM media_fetch_tasks").fetchone()[0] == 0
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM media_fetch_tasks").fetchone()[0] == 0


def test_media_worker_marks_pending_task_succeeded_when_artifact_already_stored(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/already-stored-task",
            "title": "Already Stored Task",
            "text": "Readable already stored task body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        assert run_once(conn, cfg, worker_id="test-worker", limit=10)["stored"] == 1
        stored_media = conn.execute("SELECT id, file_path FROM media_artifacts").fetchone()
        stored_path = stored_media["file_path"]
        stored_bytes = open(stored_path, "rb").read()
        conn.execute(
            "UPDATE media_fetch_tasks SET status = 'pending', last_error = 'stale lease', lease_owner = 'old-worker', lease_until = '2099-01-01T00:00:00Z'"
        )
        conn.commit()
        summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
        task = conn.execute("SELECT status, last_error, lease_owner, lease_until FROM media_fetch_tasks").fetchone()
        assert summary["attempted"] == 0
        assert summary["reconciled_stored_tasks"] == 1
        assert task["status"] == "succeeded"
        assert task["last_error"] is None
        assert task["lease_owner"] is None
        assert task["lease_until"] is None
        final_media = conn.execute("SELECT file_path FROM media_artifacts WHERE id = ?", (stored_media["id"],)).fetchone()
        assert final_media["file_path"] == stored_path
        assert open(final_media["file_path"], "rb").read() == stored_bytes
        assert Path(final_media["file_path"]).parent == cfg.media_root
        assert Path(final_media["file_path"]).name != f"{stored_media['id']}.png"
        assert len([path for path in cfg.media_root.iterdir() if path.is_file()]) == 1


def test_media_worker_does_not_auto_requeue_terminal_budget_skips(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/terminal-budget",
            "title": "Terminal budget",
            "text": "Terminal budget work must converge to no work.",
            "media_artifacts": [{"media_type": "image", "source_url": "https://cdn.example/budget.png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        conn.execute(
            "UPDATE media_artifacts SET capture_status = 'skipped', status_reason = 'snapshot-media-budget' WHERE id = ?",
            (media["id"],),
        )
        conn.execute(
            "UPDATE media_fetch_tasks SET status = 'skipped', last_error = 'snapshot-media-budget' WHERE artifact_id = ?",
            (media["id"],),
        )
        conn.commit()

        first = run_once(conn, cfg, worker_id="test-worker", limit=10)
        second = run_once(conn, cfg, worker_id="test-worker", limit=10)
        assert first["attempted"] == second["attempted"] == 0
        assert first["reconciled_cdp_blob_coverage"] == second["reconciled_cdp_blob_coverage"] == 0
        row = conn.execute(
            "SELECT capture_status, status_reason FROM media_artifacts WHERE id = ?",
            (media["id"],),
        ).fetchone()
        assert tuple(row) == ("skipped", "snapshot-media-budget")


def test_fetch_pending_media_artifacts_respects_active_lease_and_recovers_stale_lease(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/manual-fetch-lease",
            "title": "Manual Fetch Lease",
            "text": "Readable manual fetch lease body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        with conn:
            claimed = claim_media_fetch_tasks(conn, worker_id="worker-a", limit=1, lease_seconds=300)
        assert len(claimed) == 1

        fetched = fetch_pending_media_artifacts(conn, cfg, snapshot_id=result["snapshot_id"], limit=10, worker_id="manual-fetch")
        assert fetched["attempted"] == 0
        assert fetched["remaining"] == 1
        active_task = conn.execute("SELECT status, lease_owner, lease_until FROM media_fetch_tasks").fetchone()
        assert active_task["status"] == "leased"
        assert active_task["lease_owner"] == "worker-a"
        assert active_task["lease_until"] is not None

        conn.execute("UPDATE media_fetch_tasks SET lease_until = '2000-01-01T00:00:00Z' WHERE artifact_id = ?", (claimed[0]["id"],))
        conn.commit()
        recovered = fetch_pending_media_artifacts(conn, cfg, snapshot_id=result["snapshot_id"], limit=10, worker_id="manual-fetch")
        assert recovered["attempted"] == 1
        assert recovered["stored"] == 1
        assert recovered["remaining"] == 0
        final_task = conn.execute("SELECT status, attempts, lease_owner, lease_until FROM media_fetch_tasks").fetchone()
        assert final_task["status"] == "succeeded"
        assert final_task["attempts"] == 1
        assert final_task["lease_owner"] is None
        assert final_task["lease_until"] is None


def test_capture_media_fetch_on_capture_background_uses_task_leasing(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    cfg = replace(cfg, media_fetch_on_capture=True, max_media_fetches_per_capture=1)
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, stored = post_json(
            f"{base}/capture",
            "test-token",
            {
                "visit_id": "media-fetch-on-capture-1",
                "url": "https://example.com/media-fetch-on-capture",
                "title": "Media Fetch On Capture",
                "text": "Readable media fetch on capture body.",
                "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
            },
        )
        assert status == 201
        assert stored["media_ref_count"] == 1

        deadline = time.time() + 5
        final_media = None
        final_task = None
        final_audit = None
        while time.time() < deadline:
            with connect(cfg.db_path) as conn:
                final_media = conn.execute("SELECT capture_status, file_path FROM media_artifacts").fetchone()
                final_task = conn.execute("SELECT status, attempts, lease_owner, lease_until FROM media_fetch_tasks").fetchone()
                final_audit = conn.execute(
                    "SELECT metadata_json FROM audit_events WHERE event_type = 'media.fetch_pending' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
            if final_media and final_media["capture_status"] == "stored" and final_task and final_task["status"] == "succeeded":
                break
            time.sleep(0.05)

        assert final_media is not None
        assert final_media["capture_status"] == "stored"
        assert final_media["file_path"]
        assert final_task is not None
        assert final_task["status"] == "succeeded"
        assert final_task["attempts"] == 1
        assert final_task["lease_owner"] is None
        assert final_task["lease_until"] is None
        assert final_audit is not None
        assert json.loads(final_audit["metadata_json"])["background"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_concurrent_media_blob_writes_use_distinct_temp_files(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/concurrent-blob-writes",
            "title": "Concurrent Blob Writes",
            "text": "Readable concurrent media blob body.",
            "media_artifacts": [{"media_type": "image", "source_url": "https://example.com/concurrent.png", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]

    def upload(content: bytes):
        with connect(cfg.db_path) as conn:
            return store_media_blob_stream(
                conn,
                cfg,
                media["id"],
                io.BytesIO(content),
                headers={
                    "Content-Type": "image/png",
                    "X-BMD-Document-ID": result["document_id"],
                    "X-BMD-Snapshot-ID": result["snapshot_id"],
                },
                content_length=len(content),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(upload, [b"first-upload", b"second-upload"]))

    assert [item["stored"] for item in results] == [True, True]
    with connect(cfg.db_path) as conn:
        row = conn.execute("SELECT file_path, capture_status FROM media_artifacts WHERE id = ?", (media["id"],)).fetchone()
    assert row["capture_status"] == "stored"
    assert open(row["file_path"], "rb").read() in {b"first-upload", b"second-upload"}
    committed_files = [
        path for path in cfg.media_root.rglob("*") if path.is_file() and ".staging" not in path.parts
    ]
    assert committed_files == [Path(row["file_path"])]
    staging_root = cfg.media_root / ".staging"
    assert not staging_root.exists() or list(staging_root.iterdir()) == []
    tmp_root = cfg.media_root / ".tmp"
    if tmp_root.exists():
        assert not list(tmp_root.iterdir())


def test_media_worker_rehydrates_purged_cache_when_source_still_fetchable(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/worker-rehydrate",
            "title": "Worker Rehydrate",
            "text": "Readable worker rehydrate body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert run_once(conn, cfg, worker_id="test-worker", limit=10)["stored"] == 1
        purged = purge_media_cache(conn, cfg, {"domain": "example.com", "dry_run": False, "rehydrate": True})
        assert purged["purged"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"], cfg)[0]
        assert media["capture_status"] == "purged"
        assert media["has_file"] is False
        summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
        assert summary["stored"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"], cfg)[0]
        assert media["capture_status"] == "stored"
        assert media["has_file"] is True


def test_purge_media_cache_skips_db_paths_outside_media_root(tmp_path):
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    outside_media = outside_root / "media.png"
    outside_media.write_bytes(b"outside")
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/purge-outside",
            "title": "Purge Outside",
            "text": "Readable purge outside media body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert run_once(conn, cfg, worker_id="test-worker", limit=10)["stored"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        conn.execute(
            "UPDATE media_artifacts SET file_path = ?, blob_locator = ?, byte_size = ? WHERE id = ?",
            (str(outside_media), str(outside_media), outside_media.stat().st_size, media["id"]),
        )

        purged = purge_media_cache(conn, cfg, {"domain": "example.com", "dry_run": False})
        row = conn.execute("SELECT capture_status, file_path FROM media_artifacts WHERE id = ?", (media["id"],)).fetchone()

    assert purged["selected"] == 0
    assert purged["purged"] == 0
    assert purged["skipped_out_of_root"] == 1
    assert row["capture_status"] == "stored"
    assert row["file_path"] == str(outside_media)
    assert outside_media.exists()





def test_media_worker_retry_backoff_releases_lease_and_waits_until_due(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = allow_loopback_public_fetch(cfg)
    init_db(cfg)
    with http_status_fixture_server(429) as base_url:
        payload = CapturePayload.from_dict(
            {
                "url": "https://example.com/retry-backoff",
                "title": "Retry Backoff",
                "text": "Readable worker retry backoff body.",
                "media_artifacts": [{"media_type": "image", "source_url": f"{base_url}/rate.png", "mime_type": "image/png"}],
            },
            allow_any_url=True,
        )
        with connect(cfg.db_path) as conn:
            result = ingest_capture(conn, cfg, payload)
            first = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert first["attempted"] == 1
            assert first["stored"] == 0
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
            assert media["capture_status"] == "retrying"
            assert media["status_reason"] == "fetch-status-429"
            task = conn.execute("SELECT status, attempts, next_attempt_at, lease_owner, lease_until, last_error FROM media_fetch_tasks").fetchone()
            assert task["status"] == "retrying"
            assert task["attempts"] == 1
            assert task["next_attempt_at"] is not None
            assert task["lease_owner"] is None
            assert task["lease_until"] is None
            assert task["last_error"] == "fetch-status-429"

            second = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert second["attempted"] == 0
            conn.execute("UPDATE media_fetch_tasks SET next_attempt_at = '2000-01-01T00:00:00Z'")
            conn.commit()
            third = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert third["attempted"] == 1
            task = conn.execute("SELECT status, attempts, lease_owner, lease_until FROM media_fetch_tasks").fetchone()
            assert task["status"] == "retrying"
            assert task["attempts"] == 2
            assert task["lease_owner"] is None
            assert task["lease_until"] is None





@contextmanager
def hls_fixture_server():
    init_bytes = b"\x00\x00\x00 ftypiso5"
    seg1 = b"video-segment-one"
    seg2 = b"video-segment-two"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            paths = {
                "/master.m3u8": (
                    "application/x-mpegURL",
                    b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=200,RESOLUTION=320x180\n/variant.m3u8\n",
                ),
                "/variant.m3u8": (
                    "application/vnd.apple.mpegurl",
                    b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXT-X-MAP:URI=\"/init.mp4\"\n#EXTINF:1.0,\n/seg1.m4s\n#EXTINF:1.0,\n/seg2.m4s\n#EXT-X-ENDLIST\n",
                ),
                "/audio.m3u8": (
                    "application/x-mpegURL",
                    b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:1.0,\n/audio.m4s\n#EXT-X-ENDLIST\n",
                ),
                "/mp4a/audio.m3u8": (
                    "application/x-mpegURL",
                    b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:1.0,\n/audio.m4s\n#EXT-X-ENDLIST\n",
                ),
                "/init.mp4": ("video/mp4", init_bytes),
                "/seg1.m4s": ("video/iso.segment", seg1),
                "/seg2.m4s": ("video/iso.segment", seg2),
                "/audio.m4s": ("audio/mp4", b"audio-only"),
            }
            if self.path not in paths:
                self.send_response(404)
                self.end_headers()
                return
            content_type, body = paths[self.path]
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", init_bytes + seg1 + seg2
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_media_worker_stores_hls_master_playlist_as_video_mp4(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = allow_loopback_public_fetch(cfg)
    init_db(cfg)
    with hls_fixture_server() as (base_url, expected_bytes):
        payload = CapturePayload.from_dict(
            {
                "url": "https://example.com/hls-video",
                "title": "HLS Video",
                "text": "Readable worker HLS video body.",
                "media_artifacts": [{"media_type": "video", "source_url": f"{base_url}/master.m3u8"}],
            },
            allow_any_url=True,
        )
        with connect(cfg.db_path) as conn:
            result = ingest_capture(conn, cfg, payload)
            summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert summary["attempted"] == 1
            assert summary["stored"] == 1
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"], cfg)[0]
            assert media["capture_status"] == "stored"
            assert media["mime_type"] == "video/mp4"
            assert media["byte_size"] == len(expected_bytes)
            assert media["has_file"] is True
            file_row = conn.execute("SELECT file_path FROM media_artifacts WHERE id = ?", (media["id"],)).fetchone()
            assert open(file_row["file_path"], "rb").read() == expected_bytes


def test_hls_assembly_uses_single_deadline_across_segments(monkeypatch, tmp_path):
    clock = {"now": 100.0}
    fetched: list[str] = []

    def monotonic() -> float:
        return clock["now"]

    def fake_fetch_hls_asset(source_url: str, page_url: str, *, max_bytes: int, timeout_seconds: float, **_kwargs) -> tuple[bytes, str]:
        fetched.append(source_url)
        clock["now"] += 2.0
        return b"segment", ""

    monkeypatch.setattr(media_hls_module.time, "monotonic", monotonic)
    monkeypatch.setattr(media_hls_module, "_fetch_hls_asset", fake_fetch_hls_asset)
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")

    content, mime_type, reason = media_hls_module._hls_playlist_to_media(
        "https://media.example/playlist.m3u8",
        "https://example.com/page",
        "#EXTM3U\n#EXTINF:1.0,\nseg1.ts\n#EXTINF:1.0,\nseg2.ts\n#EXT-X-ENDLIST\n",
        max_bytes=100,
        timeout_seconds=10,
        config=cfg,
        budget=media_hls_module._HlsFetchBudget(requests_remaining=10, deadline=101.0),
        deadline=101.0,
    )

    assert content == b""
    assert mime_type == ""
    assert reason == "hls-time-budget-exceeded"
    assert fetched == ["https://media.example/seg1.ts"]











def test_media_worker_stores_hls_audio_rendition_sidecar(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = allow_loopback_public_fetch(cfg)
    init_db(cfg)
    with hls_fixture_server() as (base_url, _expected_bytes):
        payload = CapturePayload.from_dict(
            {
                "url": "https://example.com/hls-audio",
                "title": "HLS Audio",
                "text": "Readable worker HLS audio body.",
                "media_artifacts": [{"media_type": "video", "source_url": f"{base_url}/mp4a/audio.m3u8"}],
            },
            allow_any_url=True,
        )
        with connect(cfg.db_path) as conn:
            result = ingest_capture(conn, cfg, payload)
            summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert summary["stored"] == 1
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
            assert media["capture_status"] == "stored"
            assert media["status_reason"] in {None, ""}
            assert media["mime_type"] == "audio/mp4"
            stored_row = conn.execute("SELECT file_path FROM media_artifacts WHERE id = ?", (media["id"],)).fetchone()
            assert stored_row["file_path"].endswith(".m4a")
            task = conn.execute("SELECT status FROM media_fetch_tasks WHERE artifact_id = ?", (media["id"],)).fetchone()
            assert task["status"] == "succeeded"








def test_media_worker_marks_blob_video_refs_covered_by_cdp_bytes(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://x.com/home",
            "title": "X Home",
            "text": "Readable X page with blob video.",
            "media_artifacts": [{"media_type": "video", "source_url": "blob:https://x.com/video-123"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        followup = CapturePayload.from_dict(
            {
                "url": "https://x.com/home",
                "title": "X Home",
                "text": "Readable X page with nearby CDP bytes.",
                "media_artifacts": [],
            },
            allow_any_url=True,
        )
        result2 = ingest_capture(conn, cfg, followup)
        assert result2["document_id"] == result["document_id"]
        blob_media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        stored = store_media_artifact(
            conn,
            cfg,
            {
                "document_id": result["document_id"],
                "snapshot_id": result2["snapshot_id"],
                "visit_id": result["visit_id"],
                "page_url": "https://x.com/home",
                "source_url": "https://video.twimg.com/ext_tw_video/segment.m4s",
                "media_type": "video",
                "role": "content",
                "mime_type": "video/mp4",
                "metadata": {"cdp_recorder": True},
                "capture_status": "stored",
                "content_base64": base64.b64encode(b"fake-mp4-segment").decode("ascii"),
            },
        )
        assert stored["stored"] is True
        assert reconcile_cdp_blob_coverage(conn, limit=10) == 1
        row = conn.execute("SELECT capture_status, status_reason FROM media_artifacts WHERE id = ?", (blob_media["id"],)).fetchone()
        assert row["capture_status"] == "referenced"
        assert row["status_reason"] == "covered-by-cdp-recorder"


def test_media_worker_classifies_uncovered_blob_video_refs_as_opaque(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://x.com/home",
            "title": "X Home",
            "text": "Readable X page with opaque blob video.",
            "media_artifacts": [{"media_type": "video", "source_url": "blob:https://x.com/uncovered-video"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        row = conn.execute("SELECT capture_status, status_reason FROM media_artifacts WHERE id = ?", (media["id"],)).fetchone()
        assert row["capture_status"] == "referenced"
        assert row["status_reason"] == "opaque-browser-blob"
        stored = store_media_artifact(
            conn,
            cfg,
            {
                "artifact_id": media["id"],
                "document_id": result["document_id"],
                "snapshot_id": result["snapshot_id"],
                "media_type": "video",
                "source_url": "blob:https://x.com/uncovered-video",
                "mime_type": "video/mp4",
                "capture_status": "stored",
                "content_base64": base64.b64encode(b"stored-blob-video").decode("ascii"),
            },
        )
        assert stored["stored"] is True
        ingest_capture(conn, cfg, payload)
        refreshed = conn.execute(
            "SELECT capture_status, status_reason FROM media_artifacts WHERE id = ?",
            (media["id"],),
        ).fetchone()
        assert tuple(refreshed) == ("stored", None)
