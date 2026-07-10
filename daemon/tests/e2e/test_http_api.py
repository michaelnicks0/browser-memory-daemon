import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace

import browser_memory_daemon.app as app_module
import browser_memory_daemon.media_storage as media_storage_module
from browser_memory_daemon.app import make_server
from browser_memory_daemon.config import load_config


def request(method, url, token="test-token", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, json.loads(response.read().decode() or "{}")


def error_request(method, url, token="test-token", body=None, raw_body=None, content_type="application/json"):
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


def raw_request(method, url, token="test-token", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, response.headers, response.read()


def binary_request(method, url, token="test-token", body=b"", content_type="application/octet-stream", headers=None):
    req = urllib.request.Request(url, data=body, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", content_type)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, json.loads(response.read().decode() or "{}")


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


def test_http_upload_get_and_purge_use_bounded_spool_during_media_root_outage(tmp_path, monkeypatch):
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
        assert binary == b"\x89PNG\r\n\x1a\n"

        status, queue_status = request("GET", f"{base}/media-artifacts/queue-status")
        assert status == 200
        assert queue_status["artifacts"]["stored"] == 1
        assert queue_status["bytes"]["stored"] == 8

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

        status, receipt = request("POST", f"{base}/forget", body={"domain": "example.org"})
        assert status == 200
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
        for _status, headers, payload in error_cases:
            assert "application/json" in headers.get("Content-Type", "")
            assert set(payload) == {"error"}
            assert isinstance(payload["error"], str) and payload["error"]

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
