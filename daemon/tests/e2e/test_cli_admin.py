import json
import threading

import pytest

import browser_memory_daemon.cli as cli_module
from browser_memory_daemon.app import make_server
from browser_memory_daemon.cli import main
from browser_memory_daemon.config import load_config


@pytest.fixture()
def cli_server(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0)
    srv = make_server(cfg)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()
        thread.join(timeout=5)


def _base_args(port):
    return ["--host", "127.0.0.1", "--port", str(port), "--token", "test-token"]


def _last_json(capsys):
    out = capsys.readouterr().out
    return json.loads(out)


def test_cli_admin_commands(cli_server, capsys, monkeypatch):
    assert main(_base_args(cli_server) + [
        "capture-fixture",
        "--url",
        "https://cli.example/stirling",
        "--title",
        "CLI Stirling",
        "--text",
        "CLI admin command fixture text.",
    ]) == 0
    stored = _last_json(capsys)
    assert stored["stored"] is True

    assert main(_base_args(cli_server) + ["recent", "--limit", "1"]) == 0
    recent = _last_json(capsys)
    assert recent["results"][0]["title"] == "CLI Stirling"

    assert main(_base_args(cli_server) + ["document", stored["document_id"]]) == 0
    document = _last_json(capsys)
    assert document["document"]["title"] == "CLI Stirling"

    assert main(_base_args(cli_server) + ["snapshot", stored["snapshot_id"]]) == 0
    snapshot = _last_json(capsys)
    assert "CLI admin command fixture text" in snapshot["text"]

    assert main(_base_args(cli_server) + ["doctor"]) == 0
    doctor = _last_json(capsys)
    assert doctor["ok"] is True
    assert doctor["storage"]["census_mode"] == "db-derived"

    assert main(_base_args(cli_server) + ["doctor", "--storage-census"]) == 0
    full_doctor = _last_json(capsys)
    assert full_doctor["ok"] is True
    assert full_doctor["storage"]["census_mode"] == "filesystem"

    assert main(_base_args(cli_server) + ["policy-rules", "--block-domain", "cli-block.example"]) == 0
    rule = _last_json(capsys)
    assert rule["rule"]["pattern"] == "cli-block.example"

    assert main(_base_args(cli_server) + ["policy-rules", "--block-url-prefix", "http://127.0.0.1:32400/"]) == 0
    prefix_rule = _last_json(capsys)
    assert prefix_rule["rule"]["rule_type"] == "url-prefix"
    assert prefix_rule["rule"]["pattern"] == "http://127.0.0.1:32400/"

    def fake_daily_driver_health_snapshot(cfg, *, extension_dir, journal_since, include_windows_loopback, powershell):
        assert cfg.api_token == "test-token"
        assert extension_dir == "/tmp/bmd-extension"
        assert journal_since == "24 hours ago"
        assert include_windows_loopback is False
        assert powershell is None
        return {"ok": True, "summary": {"status": "ok", "errors": [], "warnings": []}}

    monkeypatch.setattr(cli_module, "daily_driver_health_snapshot", fake_daily_driver_health_snapshot)
    assert main(_base_args(cli_server) + ["daily-driver-health", "--skip-windows-loopback", "--extension-dir", "/tmp/bmd-extension"]) == 0
    daily_driver_health = _last_json(capsys)
    assert daily_driver_health["ok"] is True
