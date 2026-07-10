from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_install_daily_driver_dry_run_is_non_mutating(tmp_path):
    config_home = tmp_path / "config-home"
    data_home = tmp_path / "data-home"
    blob_root = tmp_path / "nas-blobs"
    state_home = tmp_path / "state-home"
    extension_dir = tmp_path / "windows-extension"
    env = {
        **os.environ,
        "BMD_PYTHON": sys.executable,
        "BMD_POLICY_MODE": "all",
        "BMD_BLOB_ROOT": str(blob_root),
        "BMD_WINDOWS_EXTENSION_DIR": str(extension_dir),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_DATA_HOME": str(data_home),
        "XDG_STATE_HOME": str(state_home),
    }

    result = subprocess.run(
        [str(ROOT / "scripts" / "install-daily-driver.sh"), "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Daily-driver install dry run" in result.stdout
    assert "Python:" in result.stdout
    assert f"Blob dir: {blob_root}" in result.stdout
    assert "Require media mount: 0" in result.stdout
    assert "verify the configured media root mount and identity marker" in result.stdout
    assert "write systemd user units that read the EnvironmentFile" in result.stdout
    assert "chrome://extensions" in result.stdout
    assert not config_home.exists()
    assert not data_home.exists()
    assert not blob_root.exists()
    assert not state_home.exists()
    assert not extension_dir.exists()


def test_install_daily_driver_required_mount_guard_fails_before_writes(tmp_path):
    config_home = tmp_path / "config-home"
    data_home = tmp_path / "data-home"
    state_home = tmp_path / "state-home"
    extension_dir = tmp_path / "windows-extension"
    blob_root = Path("/definitely-not-mounted-bmd-test-root/blobs")
    env = {
        **os.environ,
        "BMD_PYTHON": sys.executable,
        "BMD_BLOB_ROOT": str(blob_root),
        "BMD_REQUIRE_BLOB_ROOT_MOUNT": "1",
        "BMD_MEDIA_ROOT_IDENTITY": "test-media-root",
        "BMD_WINDOWS_EXTENSION_DIR": str(extension_dir),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_DATA_HOME": str(data_home),
        "XDG_STATE_HOME": str(state_home),
    }

    result = subprocess.run(
        [str(ROOT / "scripts" / "install-daily-driver.sh"), "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "media root has no non-root mounted ancestor" in result.stderr
    assert str(blob_root / "media") in result.stderr
    assert not config_home.exists()
    assert not data_home.exists()
    assert not state_home.exists()
    assert not extension_dir.exists()
