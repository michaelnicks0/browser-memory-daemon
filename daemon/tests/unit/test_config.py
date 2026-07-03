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
