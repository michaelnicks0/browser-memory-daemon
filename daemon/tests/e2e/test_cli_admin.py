import json
import threading

import browser_memory_daemon.cli as cli_module
import pytest
from browser_memory_daemon.app import make_server
from browser_memory_daemon.cli import main
from browser_memory_daemon.config import load_config
from browser_memory_daemon.migrations import LATEST_SCHEMA_VERSION


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

    with pytest.raises(SystemExit):
        main(_base_args(cli_server) + ["forget"])
    with pytest.raises(SystemExit):
        main(_base_args(cli_server) + ["forget", "--domain", "cli.example", "--url", "https://cli.example/stirling"])

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


def test_cli_migrate_check_is_read_only_then_execute_applies_pending_steps(tmp_path, capsys):
    runtime_root = tmp_path / "runtime"
    blob_root = tmp_path / "blobs"
    base = [
        "--runtime-root",
        str(runtime_root),
        "--blob-root",
        str(blob_root),
        "--token",
        "test-token",
    ]

    assert main(base + ["migrate", "--check"]) == 2
    pending = _last_json(capsys)
    assert pending["state"] == "uninitialized"
    assert pending["pending_versions"] == list(range(1, LATEST_SCHEMA_VERSION + 1))
    assert not (runtime_root / "data" / "memory.sqlite3").exists()

    assert main(base + ["migrate", "--execute"]) == 0
    executed = _last_json(capsys)
    assert executed["ready"] is True
    assert executed["applied_versions"] == list(range(1, LATEST_SCHEMA_VERSION + 1))

    assert main(base + ["migrate", "--check"]) == 0
    current = _last_json(capsys)
    assert current["ready"] is True
    assert current["current_version"] == LATEST_SCHEMA_VERSION


def test_cli_media_requeue_defaults_to_scoped_dry_run(tmp_path, capsys):
    base = [
        "--runtime-root",
        str(tmp_path / "runtime"),
        "--blob-root",
        str(tmp_path / "blobs"),
        "--token",
        "test-token",
    ]
    assert main(base + ["media-cache", "requeue", "--reason", "all-budget", "--snapshot-id", "missing-snapshot"]) == 0
    preview = _last_json(capsys)
    assert preview["dry_run"] is True
    assert preview["scope"] == {"snapshot_id": "missing-snapshot"}
    assert preview["selected"] == preview["updated"] == 0


def test_cli_snapshot_text_reconcile_defaults_to_dry_run(tmp_path, capsys):
    runtime_root = tmp_path / "runtime"
    base = [
        "--runtime-root",
        str(runtime_root),
        "--blob-root",
        str(tmp_path / "blobs"),
        "--token",
        "test-token",
    ]
    assert main(base + ["migrate", "--execute"]) == 0
    _last_json(capsys)

    assert main(base + ["snapshot-text", "reconcile"]) == 0
    preview = _last_json(capsys)
    assert preview["dry_run"] is True
    assert preview["scanned"] == 0

    assert main(base + ["snapshot-text", "reconcile", "--execute"]) == 0
    applied = _last_json(capsys)
    assert applied["dry_run"] is False
    assert applied["applied"] == 0


def test_cli_media_spool_status_and_drain_are_dry_run_safe(tmp_path, capsys):
    base = [
        "--runtime-root",
        str(tmp_path),
        "--token",
        "test-token",
        "--policy-mode",
        "all",
    ]
    assert main(base + ["media-spool", "status"]) == 0
    status = _last_json(capsys)
    assert status["enabled"] is False
    assert status["stored_artifacts"] == 0

    assert main(base + ["media-spool", "drain"]) == 0
    preview = _last_json(capsys)
    assert preview["dry_run"] is True
    assert preview["selected"] == 0


def test_cli_storage_reconcile_defaults_to_dry_run(tmp_path, capsys):
    base = [
        "--runtime-root",
        str(tmp_path / "runtime"),
        "--token",
        "test-token",
        "--policy-mode",
        "all",
    ]
    assert main(base + ["storage", "reconcile"]) == 0
    preview = _last_json(capsys)
    assert preview["dry_run"] is True
    assert preview["tombstones"]["pending"] == 0

    assert main(base + ["storage", "reconcile", "--execute"]) == 0
    applied = _last_json(capsys)
    assert applied["dry_run"] is False
    assert applied["tombstones"]["pending"] == 0


def test_cli_backup_create_and_restore_validate_then_execute(tmp_path, capsys):
    runtime_root = tmp_path / "runtime"
    base = ["--runtime-root", str(runtime_root), "--token", "test-token", "--policy-mode", "all"]
    assert main(base + ["migrate", "--execute"]) == 0
    _last_json(capsys)

    bundle = tmp_path / "bundle"
    assert main(base + ["backup", "create", "--destination", str(bundle)]) == 0
    assert _last_json(capsys)["dry_run"] is True
    assert not bundle.exists()
    assert main(base + ["backup", "create", "--destination", str(bundle), "--execute"]) == 0
    assert _last_json(capsys)["dry_run"] is False

    destination = tmp_path / "restored"
    restore_args = ["backup", "restore", "--source", str(bundle), "--destination", str(destination)]
    assert main(base + restore_args) == 0
    preview = _last_json(capsys)
    assert preview["dry_run"] is True
    assert preview["database"]["ready"] is True
    assert not destination.exists()
    assert main(base + [*restore_args, "--execute"]) == 0
    assert _last_json(capsys)["dry_run"] is False
    assert (destination / "browser-memory.sqlite3").is_file()
