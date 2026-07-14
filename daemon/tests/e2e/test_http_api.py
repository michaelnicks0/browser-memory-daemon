import json
import re
import socket
import sqlite3
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace

import browser_memory_daemon.app as app_module
import browser_memory_daemon.application as application_module
import browser_memory_daemon.http_server as http_server_module
import browser_memory_daemon.media_storage as media_storage_module
from browser_memory_daemon.app import make_server
from browser_memory_daemon.blob_store import BlobStore
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect
from browser_memory_daemon.media_resources import media_resource_budget
from browser_memory_daemon.routes import ROUTES


def request(method, url, token="test-token", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, json.loads(response.read().decode() or "{}")


def error_request(method, url, token: str | None = "test-token", body=None, raw_body=None, content_type="application/json"):
    data = raw_body if raw_body is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, dict(response.headers), json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        return exc.code, dict(exc.headers), json.loads(text or "{}")


def raw_request(method, url, token: str | None = "test-token", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, response.headers, response.read()


def assert_common_security_headers(headers):
    assert headers.get("Cache-Control") == "no-store"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Permissions-Policy") == "camera=(), microphone=(), geolocation=()"
    assert headers.get("Content-Security-Policy")
    request_id = headers.get("X-Request-ID", "")
    assert re.fullmatch(r"req_[0-9a-f]{32}", request_id)
    return request_id


def abort_socket(sock):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    sock.close()


def wait_until(predicate, *, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition did not converge before timeout")


def binary_request(method, url, token="test-token", body=b"", content_type="application/octet-stream", headers=None):
    req = urllib.request.Request(url, data=body, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", content_type)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, json.loads(response.read().decode() or "{}")


def test_malformed_request_line_does_not_crash_error_handling(tmp_path, capsys):
    cfg = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        host="127.0.0.1",
        port=0,
        policy_mode="all",
    )
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        address = ("127.0.0.1", int(server.server_address[1]))
        with socket.create_connection(address, timeout=3) as sock:
            sock.sendall(b"not-http\r\n\r\n")
            sock.shutdown(socket.SHUT_WR)
            response = sock.recv(4096)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    diagnostic = capsys.readouterr().err
    assert b'"error_code": "http_error"' in response
    assert "Traceback" not in diagnostic
    assert "object has no attribute 'headers'" not in diagnostic


def test_http_capture_skips_request_time_db_initialization_after_startup(tmp_path, monkeypatch):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    cfg = replace(cfg, media_fetch_on_capture=False)
    init_calls = 0
    real_init_db = app_module.init_db

    def spy_init_db(config):
        nonlocal init_calls
        init_calls += 1
        return real_init_db(config)

    monkeypatch.setattr(app_module, "init_db", spy_init_db)
    server = app_module.make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, stored = request("POST", f"{base}/capture", body={
            "visit_id": "http-no-backfill-1",
            "url": "https://example.org/no-backfill",
            "title": "No per-request init",
            "text": "Capture requests should not rerun schema or reseed legacy media tasks.",
        })
        assert status == 201
        assert stored["stored"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert init_calls == 1


def test_authenticated_x_observation_export_uses_query_only_contract_without_audit_write(tmp_path):
    cfg = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        host="127.0.0.1",
        port=0,
        policy_mode="all",
    )
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, stored = request(
            "POST",
            f"{base}/capture",
            body={
                "observation_id": "browser-http-export",
                "visit_id": "visit-http-export",
                "url": "https://x.com/httpfixture/status/456",
                "title": "HTTP fixture title",
                "text": "HTTP-FIXTURE-BODY",
                "captured_at": "2026-07-11T00:00:00Z",
            },
        )
        assert status == 201
        with connect(cfg.db_path) as conn:
            audit_before = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]

        unauthorized, _headers, error = error_request(
            "GET", f"{base}/exports/x-observations?limit=1", token=None
        )
        assert unauthorized == 401
        assert error["error_code"] == "unauthorized"

        status, payload = request("GET", f"{base}/exports/x-observations?limit=1")
        assert status == 200
        assert payload["contract"] == "bmd.x-observations"
        assert [row["observation_id"] for row in payload["records"]] == [stored["observation_id"]]
        assert "HTTP-FIXTURE-BODY" not in json.dumps(payload)

        with connect(cfg.db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == audit_before
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_upload_get_and_purge_use_bounded_spool_during_media_root_outage(tmp_path, monkeypatch):
    def forbid_whole_blob_read(*_args, **_kwargs):
        raise AssertionError("media GET must stream through BlobStore.open")

    monkeypatch.setattr(BlobStore, "read_bytes", forbid_whole_blob_read)
    runtime_root = tmp_path / "runtime"
    external_media_root = tmp_path / "external-media"
    spool_root = runtime_root / "media-spool"
    monkeypatch.setenv("BMD_MEDIA_ROOT_IDENTITY", "http-spool-test")
    monkeypatch.setenv("BMD_MAX_MEDIA_SPOOL_BYTES", "64")
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda _path: False)
    cfg = load_config(
        runtime_root=runtime_root,
        media_root=external_media_root,
        media_spool_root=spool_root,
        test_mode=True,
        token="test-token",
        host="127.0.0.1",
        port=0,
        policy_mode="all",
    )
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, captured = request(
            "POST",
            f"{base}/capture",
            body={
                "visit_id": "http-spool-1",
                "url": "https://example.org/spool",
                "title": "Spool outage",
                "text": "Local text remains authoritative while final media is unavailable.",
                "media_artifacts": [
                    {
                        "media_type": "image",
                        "source_url": "https://cdn.example.org/spool.png",
                        "mime_type": "image/png",
                    }
                ],
            },
        )
        assert status == 201
        artifact_id = captured["media_artifacts"][0]["artifact_id"]
        status, uploaded = binary_request(
            "PUT",
            f"{base}/media-artifacts/{artifact_id}/blob",
            body=b"spooled-bytes",
            content_type="image/png",
            headers={
                "X-BMD-Document-ID": captured["document_id"],
                "X-BMD-Snapshot-ID": captured["snapshot_id"],
            },
        )
        assert status == 201
        assert uploaded["storage_tier"] == "spool"
        status, _headers, content = raw_request("GET", f"{base}/media-artifacts/{artifact_id}")
        assert status == 200
        assert content == b"spooled-bytes"
        assert not external_media_root.exists()

        status, purged = request(
            "POST",
            f"{base}/media-artifacts/purge-cache",
            body={"domain": "example.org", "dry_run": False},
        )
        assert status == 200
        assert purged["purged"] == 1
        assert not any(path.is_file() for path in spool_root.rglob("*") if ".staging" not in path.parts)
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_media_fetch_raw_upload_and_purge_rehydrate_controls(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    cfg = replace(cfg, media_fetch_on_capture=False)
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, stored = request("POST", f"{base}/capture", body={
            "visit_id": "http-media-fetch-1",
            "url": "https://example.org/data-media",
            "title": "Data media fetch fallback",
            "text": "Daemon-side media fetch fallback body text.",
            "media_artifacts": [{
                "media_type": "image",
                "source_url": "data:image/png;base64,iVBORw0KGgo=",
                "alt_text": "fallback image",
                "mime_type": "image/png",
            }],
        })
        assert status == 201
        assert stored["media_ref_count"] == 1
        artifact_id = stored["media_artifacts"][0]["artifact_id"]

        status, uploaded = binary_request(
            "PUT",
            f"{base}/media-artifacts/{artifact_id}/blob",
            body=b"\x89PNG\r\n\x1a\n",
            content_type="image/png",
            headers={"X-BMD-Document-ID": stored["document_id"], "X-BMD-Snapshot-ID": stored["snapshot_id"]},
        )
        assert status == 201
        assert uploaded["stored"] is True
        status, headers, binary = raw_request("GET", f"{base}/media-artifacts/{artifact_id}")
        assert status == 200
        assert headers.get_content_type() == "image/png"
        assert_common_security_headers(headers)
        assert binary == b"\x89PNG\r\n\x1a\n"

        status, queue_status = request("GET", f"{base}/media-artifacts/queue-status")
        assert status == 200
        assert queue_status["artifacts"]["stored"] == 1
        assert queue_status["bytes"]["stored"] == 8
        assert queue_status["resources"] == {
            "max_inflight_bytes": cfg.max_media_inflight_bytes,
            "max_concurrent_requests": cfg.max_media_concurrent_requests,
            "inflight_bytes": 0,
            "active_requests": 0,
        }

        status, dry = request("POST", f"{base}/media-artifacts/purge-cache", body={"domain": "example.org", "dry_run": True})
        assert status == 200
        assert dry["selected"] == 1
        assert dry["bytes"] == 8
        status, headers, binary = raw_request("GET", f"{base}/media-artifacts/{artifact_id}")
        assert status == 200

        status, purged = request("POST", f"{base}/media-artifacts/purge-cache", body={"domain": "example.org", "dry_run": False, "rehydrate": True})
        assert status == 200
        assert purged["purged"] == 1
        try:
            raw_request("GET", f"{base}/media-artifacts/{artifact_id}")
            raise AssertionError("purged media file should not be available")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404

        status, fetched = request("POST", f"{base}/media-artifacts/fetch-pending", body={"snapshot_id": stored["snapshot_id"], "limit": 10})
        assert status == 200
        assert fetched["attempted"] == 1
        assert fetched["stored"] == 1
        assert fetched["remaining"] == 0
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_raw_media_upload_requires_explicit_decimal_content_length(tmp_path):
    cfg = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        host="127.0.0.1",
        port=0,
        policy_mode="all",
    )
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for content_length, expected_error in [
            (None, "content length is required"),
            ("-1", "invalid content length"),
            ("+1", "invalid content length"),
        ]:
            sock = socket.create_connection(server.server_address, timeout=5)
            length_header = "" if content_length is None else f"Content-Length: {content_length}\r\n"
            sock.sendall(
                (
                    "PUT /media-artifacts/not-an-artifact/blob HTTP/1.0\r\n"
                    "Host: 127.0.0.1\r\n"
                    "Authorization: Bearer test-token\r\n"
                    f"{length_header}"
                    "\r\n"
                ).encode("ascii")
            )
            response = b""
            while True:
                chunk = sock.recv(64 * 1024)
                if not chunk:
                    break
                response += chunk
            sock.close()
            head, body = response.split(b"\r\n\r\n", 1)
            assert b"HTTP/1.0 400 Bad Request" in head
            payload = json.loads(body)
            assert payload["error"] == expected_error
            assert payload["error_code"] == "invalid_request"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_json_body_rejects_ambiguous_invalid_and_truncated_content_lengths(tmp_path):
    cfg = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        host="127.0.0.1",
        port=0,
        policy_mode="all",
    )
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cases = [
        (["Content-Length: -1"], b"", "invalid content length"),
        (["Content-Length: +2"], b"{}", "invalid content length"),
        (["Content-Length: 2", "Content-Length: 2"], b"{}", "invalid content length"),
        (["Content-Length: 3"], b"{}", "request body shorter than content length"),
    ]
    try:
        for length_headers, body, expected_error in cases:
            sock = socket.create_connection(server.server_address, timeout=5)
            request_head = [
                "POST /media-cache/purge HTTP/1.0",
                "Host: 127.0.0.1",
                f"Authorization: Bearer {cfg.api_token}",
                "Content-Type: application/json",
                *length_headers,
                "",
                "",
            ]
            sock.sendall("\r\n".join(request_head).encode("ascii") + body)
            sock.shutdown(socket.SHUT_WR)
            response = b""
            while True:
                chunk = sock.recv(64 * 1024)
                if not chunk:
                    break
                response += chunk
            sock.close()
            head, response_body = response.split(b"\r\n\r\n", 1)
            assert b"HTTP/1.0 400 Bad Request" in head
            payload = json.loads(response_body)
            assert payload["error"] == expected_error
            assert payload["error_code"] == "invalid_request"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_raw_media_upload_disconnect_cleans_staging_reservations_and_process_budget(tmp_path, monkeypatch, capsys):
    cfg = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        host="127.0.0.1",
        port=0,
        policy_mode="all",
    )
    cfg = replace(
        cfg,
        media_fetch_on_capture=False,
        max_media_artifact_bytes=1_000_003,
        max_media_inflight_bytes=1_000_003,
    )
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, captured = request(
            "POST",
            f"{base}/capture",
            body={
                "url": "https://example.org/disconnected-upload",
                "title": "Disconnected upload",
                "text": "Searchable text is already committed before media upload.",
                "media_artifacts": [
                    {
                        "media_type": "image",
                        "source_url": "https://example.org/disconnected.png",
                        "mime_type": "image/png",
                    }
                ],
            },
        )
        assert status == 201
        artifact_id = captured["media_artifacts"][0]["artifact_id"]
        capsys.readouterr()

        stage_started = threading.Event()
        response_completed = threading.Event()
        original_stage = BlobStore.stage
        original_complete_request = http_server_module.complete_request

        def observed_stage(self, source, **kwargs):
            stage_started.set()
            return original_stage(self, source, **kwargs)

        def observed_complete_request(handler, *, status, error_code=None):
            original_complete_request(handler, status=status, error_code=error_code)
            response_completed.set()

        monkeypatch.setattr(BlobStore, "stage", observed_stage)
        monkeypatch.setattr(http_server_module, "complete_request", observed_complete_request)
        sock = socket.create_connection(server.server_address, timeout=5)
        request_head = (
            f"PUT /media-artifacts/{artifact_id}/blob HTTP/1.0\r\n"
            "Host: 127.0.0.1\r\n"
            "Authorization: Bearer test-token\r\n"
            "Content-Type: image/png\r\n"
            f"X-BMD-Document-ID: {captured['document_id']}\r\n"
            f"X-BMD-Snapshot-ID: {captured['snapshot_id']}\r\n"
            "Content-Length: 524288\r\n"
            "\r\n"
        ).encode("ascii")
        sock.sendall(request_head + b"x" * (64 * 1024))
        assert stage_started.wait(timeout=5)
        abort_socket(sock)
        assert response_completed.wait(timeout=5)

        def upload_cleanup_converged():
            budget = media_resource_budget(cfg).snapshot()
            try:
                with connect(cfg.db_path) as conn:
                    cache_reservations = conn.execute("SELECT COUNT(*) FROM media_cache_reservations").fetchone()[0]
                    spool_reservations = conn.execute("SELECT COUNT(*) FROM media_spool_reservations").fetchone()[0]
            except sqlite3.OperationalError:
                return False
            staged_files = list(tmp_path.rglob("stage_*.tmp"))
            return (
                budget["inflight_bytes"] == 0
                and budget["active_requests"] == 0
                and cache_reservations == 0
                and spool_reservations == 0
                and not staged_files
            )

        wait_until(upload_cleanup_converged)
        with connect(cfg.db_path) as conn:
            artifact = conn.execute(
                "SELECT capture_status, file_path, blob_locator, spool_locator FROM media_artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        assert artifact["capture_status"] == "referenced"
        assert not artifact["file_path"]
        assert not artifact["blob_locator"]
        assert not artifact["spool_locator"]
    finally:
        server.shutdown()
        thread.join(timeout=5)

    stderr = capsys.readouterr().err
    events = [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]
    disconnects = [event for event in events if event.get("route") == "media-blob-put"]
    assert disconnects and disconnects[-1]["status"] == 499
    assert disconnects[-1]["error_code"] == "client_disconnected"
    assert "Traceback" not in stderr


def test_http_media_download_disconnect_stops_stream_and_releases_process_budget(tmp_path, monkeypatch, capsys):
    cfg = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        host="127.0.0.1",
        port=0,
        policy_mode="all",
    )
    cfg = replace(
        cfg,
        media_fetch_on_capture=False,
        max_media_artifact_bytes=1_000_019,
        max_media_inflight_bytes=1_000_019,
    )
    server = make_server(cfg)
    # Keep the accepted socket's kernel send buffer below the artifact size so
    # the coordinated abort must be observed by a later bounded write instead
    # of the entire response being accepted before the reset is processed.
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    allow_second_read = threading.Event()
    try:
        status, captured = request(
            "POST",
            f"{base}/capture",
            body={
                "url": "https://example.org/disconnected-download",
                "title": "Disconnected download",
                "text": "Searchable text remains independent from media delivery.",
                "media_artifacts": [
                    {
                        "media_type": "image",
                        "source_url": "https://example.org/disconnected-download.png",
                        "mime_type": "image/png",
                    }
                ],
            },
        )
        assert status == 201
        artifact_id = captured["media_artifacts"][0]["artifact_id"]
        status, uploaded = binary_request(
            "PUT",
            f"{base}/media-artifacts/{artifact_id}/blob",
            body=b"z" * (256 * 1024 + 7),
            content_type="image/png",
            headers={
                "X-BMD-Document-ID": captured["document_id"],
                "X-BMD-Snapshot-ID": captured["snapshot_id"],
            },
        )
        assert status == 201
        assert uploaded["stored"] is True
        capsys.readouterr()

        second_read_started = threading.Event()
        response_completed = threading.Event()
        completed_responses = []
        original_open = BlobStore.open
        original_complete_request = http_server_module.complete_request

        class CoordinatedReader:
            def __init__(self, handle):
                self._handle = handle
                self._reads = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                self._handle.close()

            def read(self, size=-1):
                self._reads += 1
                if self._reads == 2:
                    second_read_started.set()
                    assert allow_second_read.wait(timeout=5)
                return self._handle.read(size)

        def coordinated_open(self, locator, mode="rb"):
            return CoordinatedReader(original_open(self, locator, mode))

        def observed_complete_request(handler, *, status, error_code=None):
            original_complete_request(handler, status=status, error_code=error_code)
            completed_responses.append((status, error_code))
            response_completed.set()

        monkeypatch.setattr(BlobStore, "open", coordinated_open)
        monkeypatch.setattr(http_server_module, "complete_request", observed_complete_request)
        sock = socket.create_connection(server.server_address, timeout=5)
        sock.sendall(
            (
                f"GET /media-artifacts/{artifact_id} HTTP/1.0\r\n"
                "Host: 127.0.0.1\r\n"
                "Authorization: Bearer test-token\r\n"
                "\r\n"
            ).encode("ascii")
        )
        response_prefix = sock.recv(128 * 1024)
        assert b"HTTP/1.0 200 OK" in response_prefix
        assert second_read_started.wait(timeout=5)
        abort_socket(sock)
        allow_second_read.set()
        assert response_completed.wait(timeout=5)
        assert completed_responses[-1] == (499, "client_disconnected")
        wait_until(
            lambda: media_resource_budget(cfg).snapshot()["inflight_bytes"] == 0
            and media_resource_budget(cfg).snapshot()["active_requests"] == 0
        )
    finally:
        allow_second_read.set()
        server.shutdown()
        thread.join(timeout=5)

    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr


def test_http_raw_media_upload_returns_503_when_global_byte_budget_cannot_admit_body(tmp_path):
    cfg = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        host="127.0.0.1",
        port=0,
        policy_mode="all",
    )
    cfg = replace(
        cfg,
        media_fetch_on_capture=False,
        max_media_artifact_bytes=8,
        max_media_inflight_bytes=8,
        max_media_concurrent_requests=1,
    )
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, capture = request(
            "POST",
            f"{base}/capture",
            body={
                "url": "https://example.org/resource-budget",
                "text": "Text remains committed when a media upload is rejected by its resource budget.",
                "media_artifacts": [
                    {"media_type": "image", "source_url": "https://example.org/resource-budget.png"}
                ],
            },
        )
        assert status == 201
        artifact_id = capture["media_artifacts"][0]["artifact_id"]
        status, _headers, body = error_request(
            "PUT",
            f"{base}/media-artifacts/{artifact_id}/blob",
            raw_body=b"123456789",
            content_type="image/png",
        )
        assert status == 503
        assert body["error"] == "media resource request exceeds configured budget"
        assert body["error_code"] == "resource_unavailable"
        query = urllib.parse.urlencode({"q": "Text remains committed", "limit": "3"})
        status, search = request("GET", f"{base}/search?{query}")
        assert status == 200
        assert search["results"][0]["snapshot_id"] == capture["snapshot_id"]
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_capture_search_forget_round_trip(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="strict")
    cfg = replace(cfg, media_fetch_on_capture=False)
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, health = request("GET", f"{base}/health", token=None)
        assert status == 200
        assert health["ok"] is True

        try:
            request("POST", f"{base}/capture", token="wrong", body={"url": "https://example.com", "text": "x"})
            raise AssertionError("unauthorized request should fail")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401

        status, blocked = request("POST", f"{base}/capture", body={"url": "https://mail.google.com/mail", "text": "private"})
        assert status == 200
        assert blocked["stored"] is False

        status, stored = request("POST", f"{base}/capture", body={
            "visit_id": "http-visit-1",
            "url": "https://example.org/stirling",
            "title": "Synthetic Stirling Article",
            "text": "Low temperature differential Stirling engines are memorable.",
            "media_artifacts": [{"media_type": "image", "source_url": "https://example.org/assets/engine.png", "alt_text": "engine diagram"}],
        })
        assert status == 201
        assert stored["stored"] is True
        assert stored["media_ref_count"] == 1

        status, media = request("POST", f"{base}/media-artifacts", body={
            "document_id": stored["document_id"],
            "snapshot_id": stored["snapshot_id"],
            "visit_id": stored["visit_id"],
            "page_url": "https://example.org/stirling",
            "media_type": "image",
            "role": "content",
            "source_url": "https://example.org/assets/engine.png",
            "mime_type": "image/png",
            "content_base64": "iVBORw0KGgo=",
        })
        assert status == 201
        assert media["stored"] is True
        status, headers, binary = raw_request("GET", f"{base}/media-artifacts/{media['artifact_id']}")
        assert status == 200
        assert headers.get_content_type() == "image/png"
        assert_common_security_headers(headers)
        assert binary == b"\x89PNG\r\n\x1a\n"

        q = urllib.parse.urlencode({"q": "Stirling", "limit": "3"})
        status, found = request("GET", f"{base}/search?{q}")
        assert status == 200
        assert found["results"][0]["title"] == "Synthetic Stirling Article"

        status, event = request("POST", f"{base}/visit-events", body={
            "event_id": "http-event-1",
            "visit_id": "http-visit-1",
            "url": "https://example.org/stirling",
            "event_type": "tab-deactivated",
            "event_started_at": "2026-06-08T12:00:00Z",
            "event_ended_at": "2026-06-08T12:00:25Z",
            "active_seconds": 25,
            "max_scroll_percent": 91,
        })
        assert status == 201
        assert event["dwell_updated"] is True
        assert event["visit_id"] == "http-visit-1"
        assert event["claimed_visit_id"] == "http-visit-1"
        assert event["attachment_method"] == "visit-id"
        assert event["dwell_seconds"] == 25
        status, document = request("GET", f"{base}/documents/{stored['document_id']}")
        assert status == 200
        assert document["visits"][0]["dwell_seconds"] == 25
        assert document["visit_events"][0]["max_scroll_percent"] == 91
        assert document["visit_events"][0]["claimed_visit_id"] == "http-visit-1"
        assert document["visit_events"][0]["attachment_method"] == "visit-id"

        status, blocked_event = request("POST", f"{base}/visit-events", body={
            "visit_id": "blocked-event",
            "url": "https://mail.google.com/mail",
            "event_type": "tab-deactivated",
            "event_ended_at": "2026-06-08T12:00:25Z",
            "active_seconds": 25,
        })
        assert status == 200
        assert blocked_event["stored"] is False

        bad_q = urllib.parse.urlencode({"q": '"unterminated', "limit": "3"})
        status, malformed = request("GET", f"{base}/search?{bad_q}")
        assert status == 200
        assert "results" in malformed

        try:
            request("GET", f"{base}/search?q=x&limit=not-int")
            raise AssertionError("invalid limit should fail")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

        status, _, bad_forget = error_request("POST", f"{base}/forget", body={"domain": "example.org", "url": "https://example.org/stirling"})
        assert status == 400
        assert "exactly one selector" in bad_forget["error"]

        status, preview = request(
            "POST",
            f"{base}/forget",
            body={"domain": "example.org", "dry_run": True, "max_records": 1},
        )
        assert status == 200
        assert preview["dry_run"] is True
        assert preview["counts"]["documents"] == 1
        assert preview["guard"]["within_limit"] is False

        status, found_after_preview = request("GET", f"{base}/search?{q}")
        assert status == 200
        assert len(found_after_preview["results"]) == 1

        status, _, guarded = error_request(
            "POST",
            f"{base}/forget",
            body={"domain": "example.org", "max_records": 1},
        )
        assert status == 400
        assert guarded["error_code"] == "invalid_request"
        assert "exceeds max_records guard" in guarded["error"]

        status, receipt = request(
            "POST",
            f"{base}/forget",
            body={"domain": "example.org", "max_records": preview["guard"]["selected_records"]},
        )
        assert status == 200
        assert receipt["dry_run"] is False
        assert receipt["counts"]["documents"] == 1

        status, found_after = request("GET", f"{base}/search?{q}")
        assert found_after["results"] == []
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_api_contract_errors_methods_and_limits_are_json(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    cfg = replace(cfg, media_fetch_on_capture=False)
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, stored = request(
            "POST",
            f"{base}/capture",
            body={"visit_id": "limit-contract-1", "url": "https://example.org/limits", "title": "Limits", "text": "Limit contract body."},
        )
        assert status == 201

        error_cases = [
            error_request("GET", f"{base}/recent?limit=5", token=None),
            error_request("GET", f"{base}/recent?limit=5", token="wrong"),
            error_request("POST", f"{base}/capture", raw_body=b"{"),
            error_request("POST", f"{base}/capture", body={"url": "not-a-url", "text": "bad"}),
            error_request("GET", f"{base}/does-not-exist"),
            error_request("PATCH", f"{base}/health", raw_body=b"{}"),
        ]
        assert [case[0] for case in error_cases] == [401, 401, 400, 400, 404, 501]
        assert [case[2]["error_code"] for case in error_cases] == [
            "unauthorized",
            "unauthorized",
            "invalid_request",
            "invalid_request",
            "not_found",
            "unsupported_method",
        ]
        for _status, headers, payload in error_cases:
            assert "application/json" in headers.get("Content-Type", "")
            assert set(payload) == {"error", "error_code", "request_id"}
            assert isinstance(payload["error"], str) and payload["error"]
            assert payload["request_id"] == headers["X-Request-ID"]

        status, recent = request("GET", f"{base}/recent?limit=9999")
        assert status == 200
        assert len(recent["results"]) == 1
        status, timeline = request("GET", f"{base}/timeline?limit=9999")
        assert status == 200
        assert timeline["count"] == 1
        status, queue = request("GET", f"{base}/media-artifacts/queue-status?limit=9999")
        assert status == 200
        assert len(queue["recent_nonstored"] or []) <= 200
        assert stored["stored"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_route_catalog_preserves_auth_unknown_route_and_ready_contracts(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def concrete_path(template: str) -> str:
        return (
            template
            .replace("{document_id}", "doc-contract")
            .replace("{snapshot_id}", "snap-contract")
            .replace("{artifact_id}", "media-contract")
            .replace("{rule_id}", "rule-contract")
        )

    try:
        status, ready = request("GET", f"{base}/ready")
        assert status == 200
        assert ready == {"ready": True, "db_path": str(cfg.db_path)}

        for route in ROUTES:
            if not route.auth_required:
                continue
            status, headers, payload = error_request(route.method, f"{base}{concrete_path(route.path)}", token=None)
            assert status == 401, route.name
            assert payload == {
                "error": "unauthorized",
                "error_code": "unauthorized",
                "request_id": headers["X-Request-ID"],
            }, route.name
            assert "application/json" in headers.get("Content-Type", ""), route.name
            assert headers.get("X-Content-Type-Options") == "nosniff", route.name

        for method in ["GET", "POST", "PUT", "DELETE"]:
            status, headers, payload = error_request(method, f"{base}/does-not-exist", raw_body=b"{}" if method in {"POST", "PUT"} else None)
            assert status == 404
            assert payload == {
                "error": "not found",
                "error_code": "not_found",
                "request_id": headers["X-Request-ID"],
            }
            assert "application/json" in headers.get("Content-Type", "")

        status, headers, payload = error_request("PATCH", f"{base}/health", raw_body=b"{}")
        assert status == 501
        assert payload == {
            "error": "Unsupported method ('PATCH')",
            "error_code": "unsupported_method",
            "request_id": headers["X-Request-ID"],
        }
        assert "application/json" in headers.get("Content-Type", "")
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_request_envelope_adds_unique_ids_and_security_headers_to_every_response_kind(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, headers, body = raw_request(
            "GET",
            f"{base}/health",
            token=None,
            headers={"X-Request-ID": "caller-controlled"},
        )
        assert status == 200
        payload = json.loads(body)
        assert payload["ok"] is True
        health_id = assert_common_security_headers(headers)
        assert health_id != "caller-controlled"

        status, headers, payload = error_request("GET", f"{base}/recent", token=None)
        assert status == 401
        error_id = assert_common_security_headers(headers)
        assert payload["request_id"] == error_id
        assert payload["error_code"] == "unauthorized"

        status, headers, payload = error_request("OPTIONS", f"{base}/capture", token=None)
        assert status == 204
        assert payload == {}
        options_id = assert_common_security_headers(headers)

        status, headers, body = raw_request("GET", f"{base}/ui", token=None)
        assert status == 200
        assert b"Browser Memory" in body
        ui_id = assert_common_security_headers(headers)
        assert "script-src 'self' 'unsafe-inline'" in headers["Content-Security-Policy"]

        assert len({health_id, error_id, options_id, ui_id}) == 4
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_structured_request_telemetry_contains_only_redaction_safe_fields(tmp_path, capsys):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        secret_query = "https://private.example/path?token=do-not-log"
        status, _headers, _payload = error_request(
            "GET",
            f"{base}/search?{urllib.parse.urlencode({'q': secret_query})}",
        )
        assert status == 200
        status, _headers, _payload = error_request(
            "GET",
            f"{base}/recent?private=do-not-log",
            token=None,
        )
        assert status == 401
    finally:
        server.shutdown()
        thread.join(timeout=5)

    stderr = capsys.readouterr().err
    events = [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]
    assert len(events) == 2
    assert events[0]["event"] == "http.request"
    assert events[0]["method"] == "GET"
    assert events[0]["route"] == "search"
    assert events[0]["status"] == 200
    assert events[0]["error_code"] is None
    assert re.fullmatch(r"req_[0-9a-f]{32}", events[0]["request_id"])
    assert isinstance(events[0]["latency_ms"], int) and events[0]["latency_ms"] >= 0
    assert events[1]["route"] == "recent"
    assert events[1]["status"] == 401
    assert events[1]["error_code"] == "unauthorized"
    assert set(events[0]) == {"event", "request_id", "method", "route", "status", "latency_ms", "error_code"}
    assert "do-not-log" not in stderr
    assert "private.example" not in stderr
    assert "test-token" not in stderr


def test_http_maps_capture_identity_conflicts_to_stable_conflict_error(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        first = {
            "observation_id": "obs-http-conflict",
            "visit_id": "visit-http-conflict",
            "url": "https://example.org/conflict",
            "title": "Original",
            "text": "Original capture text.",
        }
        status, _stored = request("POST", f"{base}/capture", body=first)
        assert status == 201

        status, headers, conflict = error_request(
            "POST",
            f"{base}/capture",
            body={**first, "title": "Changed", "text": "Changed capture text."},
        )
        assert status == 409
        assert conflict == {
            "error": "observation_id conflicts with an existing capture",
            "error_code": "conflict",
            "request_id": headers["X-Request-ID"],
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_maps_database_busy_and_unexpected_failures_without_leaking_internal_details(tmp_path, monkeypatch):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def database_busy(*_args, **_kwargs):
        raise sqlite3.OperationalError(f"database is locked at {tmp_path}/private.sqlite3")

    def unexpected_failure(*_args, **_kwargs):
        raise RuntimeError(f"token=private-value path={tmp_path}/private.sqlite3")

    try:
        monkeypatch.setattr(application_module, "search_memory", database_busy)
        status, headers, busy = error_request("GET", f"{base}/search?q=test")
        assert status == 503
        assert busy == {
            "error": "database temporarily unavailable",
            "error_code": "database_busy",
            "request_id": headers["X-Request-ID"],
        }

        monkeypatch.setattr(application_module, "search_memory", unexpected_failure)
        status, headers, internal = error_request("GET", f"{base}/search?q=test")
        assert status == 500
        assert internal == {
            "error": "internal server error",
            "error_code": "internal_error",
            "request_id": headers["X-Request-ID"],
        }
        assert "private-value" not in json.dumps(internal)
        assert str(tmp_path) not in json.dumps(internal)
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_policy_rule_duplicate_creation_returns_existing_semantic_rule(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="all")
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, first = request("POST", f"{base}/policy/rules", body={"rule_type": "domain", "pattern": "Example.COM.", "action": "block"})
        assert status == 201
        status, second = request("POST", f"{base}/policy/rules", body={"rule_type": "domain", "pattern": "example.com", "action": "block"})
        assert status == 201
        assert second["rule"]["id"] == first["rule"]["id"]
        assert second["rule"]["pattern"] == "example.com"
        status, rules = request("GET", f"{base}/policy/rules")
        assert status == 200
        assert [rule for rule in rules["rules"] if rule["pattern"] == "example.com"] == [second["rule"]]
    finally:
        server.shutdown()
        thread.join(timeout=5)
