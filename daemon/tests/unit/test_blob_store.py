import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest
from browser_memory_daemon.blob_store import BlobStore, BlobStoreError


def test_blob_store_stages_streams_verifies_hash_and_commits_atomically(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    content = b"streamed-" + (b"payload" * 1024)
    expected_hash = hashlib.sha256(content).hexdigest()

    staged = store.stage(
        [content[:100], content[100:]],
        expected_size=len(content),
        expected_sha256=expected_hash,
    )

    assert staged.byte_size == len(content)
    assert staged.sha256 == expected_hash
    assert staged.path in store.staged_paths()

    committed = store.commit(staged, "media.bin")

    assert committed == tmp_path / "blobs" / "media.bin"
    assert store.relative_locator(committed) == "media.bin"
    assert store.relative_locator("media.bin") == "media.bin"
    assert store.read_bytes("media.bin") == content
    assert store.stat("media.bin").st_size == len(content)
    assert store.staged_paths() == []
    with pytest.raises(BlobStoreError, match="cannot name the storage root"):
        store.relative_locator(store.root)


def test_blob_store_mismatch_aborts_stage_without_publishing(tmp_path):
    store = BlobStore(tmp_path / "blobs")

    with pytest.raises(BlobStoreError, match="size mismatch"):
        store.stage([b"short"], expected_size=99)
    with pytest.raises(BlobStoreError, match="SHA-256 mismatch"):
        store.stage([b"content"], expected_sha256="0" * 64)

    assert store.exists("target.bin") is False
    assert store.staged_paths() == []


def test_blob_store_rejects_traversal_symlink_escape_and_cross_root_stage(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    store = BlobStore(root)

    assert store.resolve("../outside/file.bin").status == "outside-root"
    assert store.resolve("link/file.bin").status == "outside-root"
    with pytest.raises(BlobStoreError, match="outside-root"):
        store.write_bytes("link/file.bin", b"secret")
    assert not (outside / "file.bin").exists()

    staged = store.stage(b"same-root-only")
    other = BlobStore(tmp_path / "other")
    with pytest.raises(BlobStoreError, match="different root"):
        other.commit(staged, "target.bin")
    store.abort(staged)


def test_blob_store_delete_reports_outcomes_without_touching_outside_paths(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside.bin"
    root.mkdir()
    outside.write_bytes(b"outside")
    store = BlobStore(root)
    store.write_bytes("inside.bin", b"inside")

    assert store.delete("inside.bin").status == "deleted"
    assert store.delete("inside.bin").status == "missing"
    assert store.delete(outside).status == "outside-root"
    assert outside.read_bytes() == b"outside"


def test_blob_store_concurrent_writers_publish_whole_file_and_leave_no_stages(tmp_path):
    store = BlobStore(tmp_path / "root")
    payloads = [f"writer-{index}".encode() * 1000 for index in range(8)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        committed = list(pool.map(lambda payload: store.write_bytes("shared.bin", payload), payloads))

    assert all(path == store.path("shared.bin") for path in committed)
    assert store.read_bytes("shared.bin") in payloads
    assert store.staged_paths() == []
