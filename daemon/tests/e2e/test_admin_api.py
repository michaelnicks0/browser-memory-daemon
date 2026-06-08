import json
import threading
import urllib.parse
import urllib.request

import pytest

from browser_memory_daemon.app import make_server
from browser_memory_daemon.config import load_config


def request(method, url, token: str | None = "test-token", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as response:
        text = response.read().decode()
        return response.status, json.loads(text or "{}")


def raw_request(method, url, token: str | None = "test-token"):
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, response.headers.get("Content-Type"), response.read().decode()


@pytest.fixture()
def server(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0)
    srv = make_server(cfg)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        thread.join(timeout=5)


def capture(base, url, title, text, captured_at):
    status, payload = request(
        "POST",
        f"{base}/capture",
        body={"url": url, "title": title, "text": text, "captured_at": captured_at},
    )
    assert status == 201
    assert payload["stored"] is True
    return payload


def test_admin_read_apis_and_ui_assets(server):
    first = capture(
        server,
        "https://docs.example.org/articles/stirling",
        "Stirling Notes",
        "Readable dashboard fixture text about low temperature engines.",
        "2026-06-08T12:00:00Z",
    )
    capture(
        server,
        "https://docs.example.org/articles/rankine",
        "Rankine Notes",
        "Second dashboard fixture text about steam cycles.",
        "2026-06-09T12:00:00Z",
    )

    status, content_type, html = raw_request("GET", f"{server}/", token=None)
    assert status == 200
    assert "text/html" in content_type
    assert "Browser Memory" in html

    status, content_type, js = raw_request("GET", f"{server}/ui/app.js", token=None)
    assert status == 200
    assert "application/javascript" in content_type
    assert "function escapeHtml" in js

    status, recent = request("GET", f"{server}/recent?limit=5")
    assert status == 200
    assert [row["title"] for row in recent["results"]] == ["Rankine Notes", "Stirling Notes"]
    assert recent["results"][0]["snippet"]

    q = urllib.parse.urlencode({"date": "2026-06-08", "limit": "10"})
    status, day = request("GET", f"{server}/timeline?{q}")
    assert status == 200
    assert day["count"] == 1
    assert day["items"][0]["title"] == "Stirling Notes"

    status, document = request("GET", f"{server}/documents/{first['document_id']}")
    assert status == 200
    assert document["document"]["title"] == "Stirling Notes"
    assert document["visits"][0]["url"] == "https://docs.example.org/articles/stirling"
    assert document["chunks"][0]["snippet"].startswith("Readable dashboard fixture")

    status, snapshot = request("GET", f"{server}/snapshots/{first['snapshot_id']}")
    assert status == 200
    assert "low temperature engines" in snapshot["text"]
    assert snapshot["snapshot"]["has_clean_text"] is True

    status, doctor = request("GET", f"{server}/doctor")
    assert status == 200
    assert doctor["ok"] is True
    assert doctor["database"]["counts"]["documents"] == 2
    assert doctor["storage"]["clean_text_files"] == 2


def test_policy_rule_blocks_future_capture_and_can_be_deleted(server):
    status, created = request(
        "POST",
        f"{server}/policy/rules",
        body={"rule_type": "domain", "pattern": "blocked.example", "action": "block"},
    )
    assert status == 201
    rule_id = created["rule"]["id"]

    status, rules = request("GET", f"{server}/policy/rules")
    assert status == 200
    assert rules["rules"][0]["pattern"] == "blocked.example"

    q = urllib.parse.urlencode({"url": "https://sub.blocked.example/article"})
    status, decision = request("GET", f"{server}/policy/evaluate?{q}")
    assert status == 200
    assert decision["allowed"] is False
    assert decision["reason"] == "policy-rule:block-domain:blocked.example"

    status, blocked = request(
        "POST",
        f"{server}/capture",
        body={"url": "https://sub.blocked.example/article", "title": "Blocked", "text": "Should not store."},
    )
    assert status == 200
    assert blocked["stored"] is False
    assert blocked["reason"] == "policy-rule:block-domain:blocked.example"

    status, deleted = request("DELETE", f"{server}/policy/rules/{rule_id}")
    assert status == 200
    assert deleted["deleted"] is True

    stored = capture(
        server,
        "https://sub.blocked.example/after-delete",
        "Allowed After Delete",
        "The policy rule was deleted so this fixture stores.",
        "2026-06-08T13:00:00Z",
    )
    assert stored["stored"] is True
