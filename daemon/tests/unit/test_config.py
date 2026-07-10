import pytest

import browser_memory_daemon.config as config_module
from browser_memory_daemon.config import load_config


def test_blob_root_can_be_moved_independently_from_runtime_root(tmp_path):
    runtime_root = tmp_path / "runtime"
    blob_root = tmp_path / "nas-blobs"

    cfg = load_config(
        runtime_root=runtime_root,
        blob_root=blob_root,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )

    assert cfg.db_path == runtime_root / "browser-memory.sqlite3"
    assert cfg.blob_root == blob_root
    assert cfg.clean_text_root == blob_root / "clean-text"
    assert cfg.media_root == blob_root / "media"
    assert cfg.clean_text_root.exists()
    assert cfg.media_root.exists()
    assert not (runtime_root / "blobs").exists()


def test_required_blob_root_mount_refuses_unmounted_blob_root(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    blob_root = tmp_path / "nas-blobs"
    monkeypatch.setenv("BMD_REQUIRE_BLOB_ROOT_MOUNT", "1")
    monkeypatch.setattr(config_module, "has_non_root_mount_ancestor", lambda _path: False)

    with pytest.raises(RuntimeError, match="BMD_REQUIRE_BLOB_ROOT_MOUNT=1"):
        load_config(runtime_root=runtime_root, blob_root=blob_root, test_mode=True, token="test-token", policy_mode="all")

    assert not blob_root.exists()
    assert not (blob_root / "clean-text").exists()


def test_required_blob_root_mount_allows_mounted_blob_root(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    blob_root = tmp_path / "mounted" / "browser-memory-daemon" / "blobs"
    monkeypatch.setenv("BMD_REQUIRE_BLOB_ROOT_MOUNT", "1")
    monkeypatch.setattr(config_module, "has_non_root_mount_ancestor", lambda path: str(path).startswith(str(tmp_path / "mounted")))

    cfg = load_config(runtime_root=runtime_root, blob_root=blob_root, test_mode=True, token="test-token", policy_mode="all")

    assert cfg.require_blob_root_mount is True
    assert cfg.clean_text_root.exists()
    assert cfg.media_root.exists()
