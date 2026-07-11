import browser_memory_daemon.media_storage as media_storage_module
import pytest
from browser_memory_daemon.config import load_config
from browser_memory_daemon.media_storage import MEDIA_ROOT_MARKER, media_root_readiness


def test_default_runtime_roots_follow_xdg_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    cfg = load_config(test_mode=True, token="test-token", policy_mode="all")

    assert cfg.config_root == tmp_path / "config" / "browser-memory-daemon"
    assert cfg.data_root == tmp_path / "data" / "browser-memory-daemon"
    assert cfg.state_root == tmp_path / "state" / "browser-memory-daemon"


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
    assert not cfg.clean_text_root.exists()
    assert not cfg.media_root.exists()
    assert not (runtime_root / "blobs").exists()


def test_required_blob_root_mount_degrades_media_without_blocking_local_sqlite(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    blob_root = tmp_path / "nas-blobs"
    monkeypatch.setenv("BMD_REQUIRE_BLOB_ROOT_MOUNT", "1")
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda _path: False)

    cfg = load_config(runtime_root=runtime_root, blob_root=blob_root, test_mode=True, token="test-token", policy_mode="all")

    assert media_root_readiness(cfg).status == "mount-missing"
    assert cfg.db_path.parent.exists()
    assert not blob_root.exists()


def test_required_blob_root_mount_allows_mounted_blob_root(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    blob_root = tmp_path / "mounted" / "browser-memory-daemon" / "blobs"
    monkeypatch.setenv("BMD_REQUIRE_BLOB_ROOT_MOUNT", "1")
    monkeypatch.setenv("BMD_MEDIA_ROOT_IDENTITY", "test-media-root")
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda path: str(path).startswith(str(tmp_path / "mounted")))
    media_root = blob_root / "media"
    media_root.mkdir(parents=True)
    media_root.joinpath(MEDIA_ROOT_MARKER).write_text("test-media-root\n", encoding="utf-8")

    cfg = load_config(runtime_root=runtime_root, blob_root=blob_root, test_mode=True, token="test-token", policy_mode="all")

    assert cfg.require_blob_root_mount is True
    assert media_root_readiness(cfg).ok is True
    assert not cfg.clean_text_root.exists()
    assert cfg.media_root == media_root


def test_explicit_external_media_root_requires_mount_identity_and_marker(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    media_root = tmp_path / "external-media"
    cfg = load_config(
        runtime_root=runtime_root,
        media_root=media_root,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )
    assert media_root_readiness(cfg).status == "mount-missing"
    assert not media_root.exists()

    monkeypatch.setenv("BMD_MEDIA_ROOT_IDENTITY", "external-test")
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda _path: True)
    media_root.mkdir()
    media_root.joinpath(MEDIA_ROOT_MARKER).write_text("wrong-root\n", encoding="utf-8")
    cfg = load_config(
        runtime_root=runtime_root,
        media_root=media_root,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )
    assert media_root_readiness(cfg).status == "identity-mismatch"
    media_root.joinpath(MEDIA_ROOT_MARKER).write_text("external-test\n", encoding="utf-8")
    assert media_root_readiness(cfg).ok is True


def test_media_spool_requires_explicit_local_root_and_positive_cap(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    spool_root = runtime_root / "spool"
    monkeypatch.setenv("BMD_MEDIA_SPOOL_ROOT", str(spool_root))
    with pytest.raises(ValueError, match="must be configured together"):
        load_config(runtime_root=runtime_root, test_mode=True, token="test-token", policy_mode="all")

    monkeypatch.setenv("BMD_MAX_MEDIA_SPOOL_BYTES", "1024")
    cfg = load_config(runtime_root=runtime_root, test_mode=True, token="test-token", policy_mode="all")
    assert cfg.media_spool_enabled is True
    assert cfg.media_spool_root == spool_root
    assert not spool_root.exists()


def test_global_media_resource_budgets_are_positive_and_fit_one_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("BMD_MAX_MEDIA_INFLIGHT_BYTES", "100")
    monkeypatch.setenv("BMD_MAX_MEDIA_ARTIFACT_BYTES", "100")
    monkeypatch.setenv("BMD_MAX_MEDIA_CONCURRENT_REQUESTS", "2")
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    assert cfg.max_media_inflight_bytes == 100
    assert cfg.max_media_concurrent_requests == 2

    monkeypatch.setenv("BMD_MAX_MEDIA_INFLIGHT_BYTES", "99")
    with pytest.raises(ValueError, match="allow at least one"):
        load_config(runtime_root=tmp_path / "invalid", test_mode=True, token="test-token", policy_mode="all")
