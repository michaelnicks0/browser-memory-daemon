from __future__ import annotations

import json
import re
import subprocess
import threading
import urllib.error
import urllib.request

import pytest
from browser_memory_daemon.app import make_server
from browser_memory_daemon.config import load_config


def raw_request(method, url, token: str | None = "test-token", headers: dict[str, str] | None = None):
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, response.headers.get("Content-Type"), response.read().decode()


@pytest.fixture()
def server(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0, policy_mode="strict")
    srv = make_server(cfg)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        thread.join(timeout=5)


def test_ui_dashboard_shell_serves_bootstrap_and_core_panels(server):
    status, content_type, html = raw_request("GET", f"{server}/ui", token=None)

    assert status == 200
    assert "text/html" in content_type
    assert "Browser Memory" in html
    assert "Search captured memory" in html
    assert "Recent captures" in html
    assert "Timeline" in html
    assert "Privacy actions" in html
    assert "Diagnostics" in html
    assert "Results / detail" in html

    match = re.search(r'<script id="bmd-bootstrap" type="application/json">(.*?)</script>', html, re.S)
    assert match, "UI shell should include daemon bootstrap JSON"
    bootstrap = json.loads(match.group(1))
    assert bootstrap["api_token"] == "test-token"
    assert bootstrap["policy_mode"] == "strict"
    assert bootstrap["storage_root"]
    assert bootstrap["blob_root"]

    status, content_type, js = raw_request("GET", f"{server}/ui/app.js", token=None)
    assert status == 200
    assert "application/javascript" in content_type
    assert "test-token" not in js
    assert "bmd-bootstrap" in js
    assert "dry_run: true" in js
    assert "max_records: selectedRecords" in js

    status, content_type, css = raw_request("GET", f"{server}/ui/style.css", token=None)
    assert status == 200
    assert "text/css" in content_type
    assert "test-token" not in css


def test_ui_dashboard_static_asset_path_traversal_is_rejected(server):
    req = urllib.request.Request(f"{server}/ui/../daemon/src/browser_memory_daemon/app.py", method="GET")
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        assert exc.code in {401, 404}
    else:  # pragma: no cover - safety assertion
        raise AssertionError("path traversal should not serve repo files")


def test_ui_dashboard_rejects_non_loopback_host_header(server):
    try:
        raw_request("GET", f"{server}/ui", token=None, headers={"Host": "evil.example"})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        assert exc.code == 403
        assert "loopback-only" in body
    else:  # pragma: no cover - safety assertion
        raise AssertionError("token-bootstrap UI should reject non-loopback Host headers")


def test_ui_dashboard_smoke_runner_executes_bootstrap_empty_and_error_states():
    result = subprocess.run(
        ["node", "daemon/tests/e2e/ui_dashboard_smoke_runner.mjs"],
        check=True,
        cwd=".",
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert "ui dashboard smoke runner passed" in result.stdout
