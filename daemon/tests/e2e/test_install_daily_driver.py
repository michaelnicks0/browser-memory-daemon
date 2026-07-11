from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import init_db

REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = REPO_ROOT / "scripts" / "install-daily-driver.sh"


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        del format, args
        return


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_fake_systemctl(bin_dir: Path) -> Path:
    state = bin_dir.parent / "systemctl-state"
    state.mkdir()
    script = bin_dir / "systemctl"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$BMD_TEST_SYSTEMCTL_LOG"
command_name="${2:-}"
service="${*: -1}"
if [ "${BMD_TEST_FAIL_ROLLBACK:-0}" = "1" ] \\
   && [ "$command_name" = "restart" ] \\
   && [ "$service" = "browser-memory-daemon.service" ] \\
   && [ -e "$BMD_TEST_SYSTEMCTL_STATE/readiness-failed" ]; then
  exit 1
fi
if [ "$command_name" = "restart" ] && [ "$service" = "browser-memory-media-worker.service" ]; then
  : > "$BMD_TEST_SYSTEMCTL_STATE/worker-restarted"
fi
if [ "$command_name" = "is-active" ]; then
  if [ "${BMD_TEST_FAIL_WORKER_READINESS:-0}" = "1" ] \\
     && [ "$service" = "browser-memory-media-worker.service" ] \\
     && [ -e "$BMD_TEST_SYSTEMCTL_STATE/worker-restarted" ] \\
     && [ ! -e "$BMD_TEST_SYSTEMCTL_STATE/readiness-failed" ]; then
    : > "$BMD_TEST_SYSTEMCTL_STATE/readiness-failed"
    exit 1
  fi
  exit 0
fi
if [ "$command_name" = "is-enabled" ]; then
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return state


def _fixture(tmp_path: Path) -> tuple[dict[str, str], dict[Path, bytes], Path, Path]:
    home = tmp_path / "home"
    config_home = home / ".config"
    data_home = home / ".local" / "share"
    state_home = home / ".local" / "state"
    config = config_home / "browser-memory-daemon"
    data = data_home / "browser-memory-daemon"
    state = state_home / "browser-memory-daemon"
    units = home / ".config" / "systemd" / "user"
    extension = tmp_path / "windows" / "browser-memory-daemon" / "extension"
    fake_bin = tmp_path / "bin"
    for path in (home, config, data, state, units, extension, fake_bin):
        path.mkdir(parents=True, exist_ok=True)

    originals = {
        config / "token": b"existing-token\n",
        config / "env": b"OLD_ENV=1\n",
        units / "browser-memory-daemon.service": b"old daemon unit\n",
        units / "browser-memory-media-worker.service": b"old worker unit\n",
        extension / "old-marker.txt": b"old extension\n",
    }
    for path, content in originals.items():
        path.write_bytes(content)

    systemctl_state = _write_fake_systemctl(fake_bin)
    systemctl_log = tmp_path / "systemctl.log"
    port = _free_port()
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_DATA_HOME": str(data_home),
            "XDG_STATE_HOME": str(state_home),
            "BMD_PYTHON": sys.executable,
            "BMD_WINDOWS_USER": "test-user",
            "BMD_WINDOWS_EXTENSION_DIR": str(extension),
            "BMD_BLOB_ROOT": str(data / "blobs"),
            "BMD_DERIVATIVE_ROOT": str(data / "derivatives"),
            "BMD_MEDIA_ROOT": str(data / "media"),
            "BMD_HOST": "127.0.0.1",
            "BMD_PORT": str(port),
            "BMD_POLICY_MODE": "strict",
            "BMD_POWERSHELL": str(tmp_path / "missing-powershell"),
            "BMD_TEST_SYSTEMCTL_LOG": str(systemctl_log),
            "BMD_TEST_SYSTEMCTL_STATE": str(systemctl_state),
            "PATH": f"{fake_bin}:{env['PATH']}",
        }
    )
    return env, originals, extension, systemctl_log


def _run_with_health(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    server = ThreadingHTTPServer(("127.0.0.1", int(env["BMD_PORT"])), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        return subprocess.run(
            ["bash", str(INSTALLER)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _assert_no_installer_staging(extension: Path, env: dict[str, str]) -> None:
    state = Path(env["XDG_STATE_HOME"]) / "browser-memory-daemon"
    assert not list(state.glob("install-stage.*"))
    assert not list(extension.parent.glob("extension.stage.*"))
    assert not list(extension.parent.glob("extension.backup.*"))


def test_installer_stages_validates_swaps_and_restarts_services_in_order(tmp_path):
    env, originals, extension, systemctl_log = _fixture(tmp_path)
    cfg = load_config(
        runtime_root=Path(env["XDG_DATA_HOME"]) / "browser-memory-daemon",
        token="existing-token",
        policy_mode="strict",
        test_mode=True,
    )
    init_db(cfg)

    result = _run_with_health(env)

    assert result.returncode == 0, result.stderr
    assert not (extension / "old-marker.txt").exists()
    assert json.loads((extension / "manifest.json").read_text(encoding="utf-8"))["manifest_version"] == 3
    popup = (extension / "src" / "popup.js").read_text(encoding="utf-8")
    assert 'apiToken: "existing-token",' in popup
    assert 'policyMode: "strict"' in popup
    config = Path(env["XDG_CONFIG_HOME"]) / "browser-memory-daemon"
    assert (config / "token").read_bytes() == originals[config / "token"]
    assert b"BMD_POLICY_MODE=strict" in (config / "env").read_bytes()
    history = list((Path(env["XDG_STATE_HOME"]) / "browser-memory-daemon" / "install-history").glob("*.json"))
    assert len(history) == 1
    evidence_text = history[0].read_text(encoding="utf-8")
    assert "existing-token" not in evidence_text
    evidence = json.loads(evidence_text)
    assert evidence["result"] == "ready"
    assert evidence["extension_files"] > 0

    commands = systemctl_log.read_text(encoding="utf-8").splitlines()
    daemon_restart = commands.index("--user restart browser-memory-daemon.service")
    daemon_ready = commands.index("--user is-active --quiet browser-memory-daemon.service", daemon_restart)
    worker_restart = commands.index("--user restart browser-memory-media-worker.service")
    worker_ready = commands.index("--user is-active --quiet browser-memory-media-worker.service", worker_restart)
    assert daemon_restart < daemon_ready < worker_restart < worker_ready
    _assert_no_installer_staging(extension, env)


def test_installer_readiness_failure_restores_prior_artifacts_and_service_state(tmp_path):
    env, originals, extension, systemctl_log = _fixture(tmp_path)
    env["BMD_ROTATE_TOKEN"] = "1"
    env["BMD_TEST_FAIL_WORKER_READINESS"] = "1"

    result = _run_with_health(env)

    assert result.returncode != 0
    assert "restoring prior daily-driver artifacts" in result.stderr
    assert "Rollback completed" in result.stderr
    for path, content in originals.items():
        assert path.read_bytes() == content
    assert not (Path(env["XDG_STATE_HOME"]) / "browser-memory-daemon" / "install-history").exists()
    commands = systemctl_log.read_text(encoding="utf-8").splitlines()
    failed_check = commands.index("--user is-active --quiet browser-memory-media-worker.service", 4)
    assert "--user daemon-reload" in commands[failed_check + 1 :]
    assert "--user restart browser-memory-daemon.service" in commands[failed_check + 1 :]
    assert "--user restart browser-memory-media-worker.service" in commands[failed_check + 1 :]
    _assert_no_installer_staging(extension, env)


def test_installer_blocks_incompatible_database_before_publication(tmp_path):
    env, originals, extension, systemctl_log = _fixture(tmp_path)
    database = Path(env["XDG_DATA_HOME"]) / "browser-memory-daemon" / "browser-memory.sqlite3"
    database.write_bytes(b"not-a-sqlite-database")

    result = _run_with_health(env)

    assert result.returncode != 0
    assert "Database schema preflight failed or has pending migrations" in result.stderr
    assert "failed before publication" in result.stderr
    for path, content in originals.items():
        assert path.read_bytes() == content
    assert not any(" restart " in f" {line} " for line in systemctl_log.read_text(encoding="utf-8").splitlines())
    _assert_no_installer_staging(extension, env)


def test_installer_dry_run_rejects_unsafe_extension_destination_without_writes(tmp_path):
    unsafe = Path("/")
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "BMD_PYTHON": sys.executable,
            "BMD_WINDOWS_USER": "test-user",
            "BMD_WINDOWS_EXTENSION_DIR": str(unsafe),
        }
    )

    result = subprocess.run(
        ["bash", str(INSTALLER), "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "cannot be a filesystem root or direct child" in result.stderr
    assert not Path(env["XDG_CONFIG_HOME"]).exists()
    assert not Path(env["XDG_DATA_HOME"]).exists()
    assert not Path(env["XDG_STATE_HOME"]).exists()


def test_installer_surfaces_incomplete_rollback_when_prior_service_cannot_restart(tmp_path):
    env, originals, extension, _systemctl_log = _fixture(tmp_path)
    env["BMD_TEST_FAIL_WORKER_READINESS"] = "1"
    env["BMD_TEST_FAIL_ROLLBACK"] = "1"

    result = _run_with_health(env)

    assert result.returncode == 70
    assert "ROLLBACK INCOMPLETE" in result.stderr
    for path, content in originals.items():
        assert path.read_bytes() == content
    _assert_no_installer_staging(extension, env)
