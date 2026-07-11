import pytest

from browser_memory_daemon.storage_paths import (
    StoragePathError,
    contained_child_path,
    contained_existing_file,
    resolve_db_path_under,
    storage_stem,
    validate_media_artifact_id,
    validate_snapshot_id,
)


def test_storage_identifier_grammars_and_server_stems_are_stable():
    assert validate_media_artifact_id("media_abc-123.v1") == "media_abc-123.v1"
    assert validate_snapshot_id("snap_0123456789abcdef0123456789abcdef") == "snap_0123456789abcdef0123456789abcdef"
    assert storage_stem("media", "caller-controlled") == storage_stem("media", "caller-controlled")

    for invalid in ["", "artifact", "media_../escape", "media_a/b", "media_a\\b", "media_%2fescape"]:
        with pytest.raises(ValueError):
            validate_media_artifact_id(invalid)
    for invalid in ["", "snap_short", "snap_0123456789ABCDEF0123456789ABCDEF"]:
        with pytest.raises(ValueError):
            validate_snapshot_id(invalid)


def test_contained_child_path_rejects_unsafe_parts_and_symlink_escape(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    assert contained_child_path(root, "safe", "file.bin") == root / "safe" / "file.bin"
    for unsafe in ["", ".", "..", "a/b", "a\\b", "a b", "nul\x00byte"]:
        with pytest.raises(StoragePathError, match="invalid storage path"):
            contained_child_path(root, unsafe)
    with pytest.raises(StoragePathError, match="escapes configured root"):
        contained_child_path(root, "link", "escape.bin")


def test_contained_child_path_create_root_is_explicit(tmp_path):
    root = tmp_path / "created"
    path = contained_child_path(root, "safe.bin", create_root=True)
    assert root.is_dir()
    assert path == root / "safe.bin"


def test_resolve_db_path_reports_empty_invalid_outside_missing_and_ok(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    stored = root / "stored.bin"
    stored.write_bytes(b"fixture")

    assert resolve_db_path_under(root, None).status == "empty"
    assert resolve_db_path_under(root, "   ").status == "empty"
    assert resolve_db_path_under(root, "bad\x00path").status == "invalid"
    assert resolve_db_path_under(root, tmp_path / "outside.bin").status == "outside-root"

    missing = contained_existing_file(root, "missing.bin")
    assert missing.status == "missing"
    assert missing.path == root / "missing.bin"

    relative = contained_existing_file(root, "stored.bin")
    absolute = contained_existing_file(root, stored)
    assert relative.status == absolute.status == "ok"
    assert relative.path == absolute.path == stored


def test_resolve_db_path_rejects_symlinked_file_outside_root(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside.bin"
    root.mkdir()
    outside.write_bytes(b"outside")
    (root / "linked.bin").symlink_to(outside)

    resolution = contained_existing_file(root, root / "linked.bin")
    assert resolution.path is None
    assert resolution.status == "outside-root"
