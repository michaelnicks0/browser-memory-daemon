import json
from pathlib import Path

from browser_memory_daemon.config import load_config
from browser_memory_daemon.daily_driver_health import CommandResult, daily_driver_health_snapshot
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.models import CapturePayload


class FakeHealthResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({"ok": True, "capture_enabled": True, "policy_mode": "all", "storage_root": "/tmp/runtime", "version": "0.1.0"}).encode()

    def getcode(self):
        return self.status


def write_install_artifacts(cfg, tmp_path, *, token="test-token"):
    token_file = cfg.config_root / "token"
    token_file.write_text(f"{token}\n")
    token_file.chmod(0o600)
    env_file = cfg.config_root / "env"
    env_file.write_text(
        "\n".join(
            [
                "BMD_HOST=127.0.0.1",
                "BMD_PORT=8765",
                f"BMD_API_TOKEN={token}",
                "BMD_POLICY_MODE=all",
                "PYTHONPATH=/repo/daemon/src",
                "",
            ]
        )
    )
    env_file.chmod(0o600)
    unit_dir = tmp_path / "systemd-user"
    unit_dir.mkdir()
    (unit_dir / "browser-memory-daemon.service").write_text(
        "\n".join(
            [
                "[Service]",
                "EnvironmentFile=%h/.config/browser-memory-daemon/env",
                "ExecStart=/usr/bin/python3.11 -m browser_memory_daemon --host ${BMD_HOST} --port ${BMD_PORT} serve",
                "",
            ]
        )
    )
    (unit_dir / "browser-memory-media-worker.service").write_text(
        "\n".join(
            [
                "[Service]",
                "EnvironmentFile=%h/.config/browser-memory-daemon/env",
                "ExecStart=/usr/bin/python3.11 -m browser_memory_daemon media-worker --loop --interval ${BMD_MEDIA_WORKER_INTERVAL} --limit ${BMD_MEDIA_WORKER_LIMIT}",
                "",
            ]
        )
    )
    return unit_dir


def test_daily_driver_health_snapshot_is_aggregate_and_redaction_safe(tmp_path):
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    unit_dir = write_install_artifacts(cfg, tmp_path)
    secret_text = "PRIVATE-SNAPSHOT-TEXT-DO-NOT-LEAK"
    secret_url = "https://sensitive.example/private/path?token=URLSECRET000000000000"
    with connect(cfg.db_path) as conn:
        ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "url": secret_url,
                    "title": "Private Fixture",
                    "text": secret_text,
                    "media_artifacts": [
                        {"media_type": "image", "source_url": "https://cdn.sensitive.example/private/image.png", "alt_text": "private image"}
                    ],
                }
            ),
        )

    extension_dir = tmp_path / "extension"
    (extension_dir / "src").mkdir(parents=True)
    (extension_dir / "manifest.json").write_text(json.dumps({"manifest_version": 3, "name": "Browser Memory Daemon", "version": "0.1.0"}))
    for rel in ("src/service_worker.js", "src/options.js", "src/popup.js"):
        (extension_dir / rel).write_text("const defaults = { apiToken: 'test-token', policyMode: 'all' };\n")

    def fake_runner(args, timeout):
        if args[:3] == ["systemctl", "--user", "show"]:
            unit = args[3]
            return CommandResult(args, 0, f"Id={unit}\nLoadState=loaded\nActiveState=active\nSubState=running\nNRestarts=0\nExecMainStatus=0\n")
        if args[:3] == ["systemctl", "--user", "is-enabled"]:
            return CommandResult(args, 0, "enabled")
        if args[:3] == ["systemctl", "--user", "is-active"]:
            return CommandResult(args, 0, "active")
        if args[:3] == ["journalctl", "--user", "-u"]:
            row = {
                "PRIORITY": "3",
                "MESSAGE": "failed fetching https://secret.example/path/to/blob with Bearer shortrawtoken",
                "__REALTIME_TIMESTAMP": "1783037077783420",
            }
            return CommandResult(args, 0, json.dumps(row))
        raise AssertionError(args)

    snapshot = daily_driver_health_snapshot(
        cfg,
        base_url="http://127.0.0.1:8765",
        extension_dir=extension_dir,
        unit_dir=unit_dir,
        include_windows_loopback=False,
        runner=fake_runner,
        urlopen=lambda *args, **kwargs: FakeHealthResponse(),
    )

    assert snapshot["loopback"]["ok"] is True
    assert snapshot["systemd"]["units"]["browser-memory-daemon.service"]["ok"] is True
    assert snapshot["database"]["ok"] is True
    assert snapshot["database"]["counts"]["documents"] == 1
    assert snapshot["database"]["chunks_missing_fts"] == 0
    assert snapshot["database"]["media_queue"]["artifact_status_counts"] == {"referenced": 1}
    assert snapshot["install"]["token_file"]["owner_only_permissions"] is True
    assert snapshot["install"]["env_file"]["matches_token_file"] is True
    assert snapshot["extension"]["api_token_configured"] is True
    assert snapshot["extension"]["api_token_matches_token_file"] is True
    assert snapshot["extension"]["policy_mode_defaults"]["src/service_worker.js"] == "all"

    rendered = json.dumps(snapshot, sort_keys=True)
    assert secret_text not in rendered
    assert "URLSECRET" not in rendered
    assert "cdn.sensitive.example" not in rendered
    assert "test-token" not in rendered
    assert "Bearer shortrawtoken" not in rendered
    assert "https://secret.example/path/to/blob" not in rendered
    assert "<url>" in rendered
    assert "Bearer <redacted>" in rendered


def test_daily_driver_health_detects_missing_extension_token(tmp_path):
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    unit_dir = write_install_artifacts(cfg, tmp_path)
    extension_dir = tmp_path / "extension"
    (extension_dir / "src").mkdir(parents=True)
    (extension_dir / "manifest.json").write_text(json.dumps({"manifest_version": 3, "name": "Browser Memory Daemon", "version": "0.1.0"}))
    for rel in ("src/service_worker.js", "src/options.js", "src/popup.js"):
        (extension_dir / rel).write_text("const defaults = { apiToken: '', policyMode: 'all' };\n")

    def quiet_runner(args, timeout):
        if args[:3] == ["systemctl", "--user", "show"]:
            return CommandResult(args, 0, "LoadState=loaded\nActiveState=active\nSubState=running\nNRestarts=0\nExecMainStatus=0\n")
        if args[:3] == ["systemctl", "--user", "is-enabled"]:
            return CommandResult(args, 0, "enabled")
        if args[:3] == ["systemctl", "--user", "is-active"]:
            return CommandResult(args, 0, "active")
        if args[:3] == ["journalctl", "--user", "-u"]:
            return CommandResult(args, 0, "")
        raise AssertionError(args)

    snapshot = daily_driver_health_snapshot(
        cfg,
        extension_dir=extension_dir,
        unit_dir=unit_dir,
        include_windows_loopback=False,
        runner=quiet_runner,
        urlopen=lambda *args, **kwargs: FakeHealthResponse(),
    )

    assert snapshot["ok"] is False
    assert "Windows extension artifact does not have a configured API token default" in snapshot["summary"]["errors"]


def test_daily_driver_health_detects_insecure_token_permissions_and_process_args(tmp_path):
    token = "process-secret-token"
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token=token, policy_mode="all")
    init_db(cfg)
    unit_dir = write_install_artifacts(cfg, tmp_path, token=token)
    (cfg.config_root / "token").chmod(0o644)

    extension_dir = tmp_path / "extension"
    (extension_dir / "src").mkdir(parents=True)
    (extension_dir / "manifest.json").write_text(json.dumps({"manifest_version": 3, "name": "Browser Memory Daemon", "version": "0.1.0"}))
    for rel in ("src/service_worker.js", "src/options.js", "src/popup.js"):
        (extension_dir / rel).write_text(f"const defaults = {{ apiToken: {json.dumps(token)}, policyMode: 'all' }};\n")

    def runner(args, timeout):
        if args[:3] == ["systemctl", "--user", "show"]:
            unit = args[3]
            return CommandResult(args, 0, f"Id={unit}\nLoadState=loaded\nActiveState=active\nSubState=running\nNRestarts=0\nExecMainStatus=0\nMainPID=123\n")
        if args[:3] == ["systemctl", "--user", "is-enabled"]:
            return CommandResult(args, 0, "enabled")
        if args[:3] == ["systemctl", "--user", "is-active"]:
            return CommandResult(args, 0, "active")
        if args[:3] == ["journalctl", "--user", "-u"]:
            return CommandResult(args, 0, "")
        if args[:3] == ["ps", "-p", "123"]:
            return CommandResult(args, 0, f"python -m browser_memory_daemon --token {token} serve")
        raise AssertionError(args)

    snapshot = daily_driver_health_snapshot(
        cfg,
        extension_dir=extension_dir,
        unit_dir=unit_dir,
        include_windows_loopback=False,
        runner=runner,
        urlopen=lambda *args, **kwargs: FakeHealthResponse(),
    )

    assert snapshot["ok"] is False
    assert "daily-driver token file permissions are not owner-only" in snapshot["summary"]["errors"]
    assert "browser-memory-daemon.service appears to expose token material in process arguments" in snapshot["summary"]["errors"]
    assert token not in json.dumps(snapshot, sort_keys=True)
