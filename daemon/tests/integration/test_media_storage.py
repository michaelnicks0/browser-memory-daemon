import base64
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import browser_memory_daemon.media_storage as media_storage_module
import browser_memory_daemon.media_store as media_store_module
import pytest
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.media import media_artifact, store_media_artifact
from browser_memory_daemon.media_storage import (
    MEDIA_ROOT_MARKER,
    MediaSpoolFull,
    MediaStorageUnavailable,
    drain_media_spool,
    media_spool_status,
    release_media_spool_reservation,
    reserve_media_spool,
)
from browser_memory_daemon.models import CapturePayload


def _spool_config(tmp_path, monkeypatch, *, cap: int = 64):
    runtime_root = tmp_path / "runtime"
    media_root = tmp_path / "mounted-media"
    spool_root = runtime_root / "media-spool"
    monkeypatch.setenv("BMD_MEDIA_ROOT_IDENTITY", "media-test-root")
    monkeypatch.setenv("BMD_MAX_MEDIA_SPOOL_BYTES", str(cap))
    return load_config(
        runtime_root=runtime_root,
        media_root=media_root,
        media_spool_root=spool_root,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )


def _store_payload(content: bytes) -> dict:
    return {
        "document_id": "doc-spool",
        "snapshot_id": "snap-spool",
        "page_url": "https://example.com/spool",
        "media_type": "image",
        "source_url": "https://cdn.example.com/spool.png",
        "mime_type": "image/png",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def _insert_media_owner(conn):
    conn.execute(
        """
        INSERT INTO documents(id, canonical_url, normalized_url, domain, first_seen_at, last_seen_at)
        VALUES ('doc-spool', 'https://example.com/spool', 'https://example.com/spool',
                'example.com', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    conn.execute(
        """
        INSERT INTO snapshots(
          id, document_id, captured_at, content_type, extraction_method,
          text_hash, privacy_class, redaction_count, cleaned_text, cleaned_text_source
        ) VALUES ('snap-spool', 'doc-spool', CURRENT_TIMESTAMP, 'text/plain',
                  'fixture', 'fixture-hash', 'normal', 0, 'fixture', 'capture')
        """
    )


def test_unavailable_external_media_root_spools_then_drains_with_hash_verification(tmp_path, monkeypatch):
    cfg = _spool_config(tmp_path, monkeypatch)
    init_db(cfg)
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda _path: False)

    with connect(cfg.db_path) as conn:
        conn.execute(
            """
            INSERT INTO documents(id, canonical_url, normalized_url, domain, first_seen_at, last_seen_at)
            VALUES ('doc-spool', 'https://example.com/spool', 'https://example.com/spool',
                    'example.com', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        conn.execute(
            """
            INSERT INTO snapshots(
              id, document_id, captured_at, content_type, extraction_method,
              text_hash, privacy_class, redaction_count, cleaned_text, cleaned_text_source
            ) VALUES ('snap-spool', 'doc-spool', CURRENT_TIMESTAMP, 'text/plain',
                      'fixture', 'fixture-hash', 'normal', 0, 'fixture', 'capture')
            """
        )
        stored = store_media_artifact(conn, cfg, _store_payload(b"durable-spool-bytes"))
        row = conn.execute(
            """
            SELECT storage_tier, spool_locator, blob_locator, file_path, content_sha256
            FROM media_artifacts WHERE id = ?
            """,
            (stored["artifact_id"],),
        ).fetchone()
        assert row["storage_tier"] == "spool"
        assert row["spool_locator"]
        spool_locator = row["spool_locator"]
        assert row["blob_locator"] is None
        assert cfg.media_spool_root.joinpath(row["spool_locator"]).read_bytes() == b"durable-spool-bytes"
        assert not cfg.media_root.exists()
        assert conn.execute("SELECT COUNT(*) FROM media_spool_reservations").fetchone()[0] == 0
        detail = media_artifact(conn, cfg, stored["artifact_id"])
        assert detail["has_file"] is True
        assert detail["file_locator_kind"] == "spool-relative"
        preview = drain_media_spool(conn, cfg, execute=False)
        assert preview["selected"] == 1
        assert preview["media_root"]["status"] == "mount-missing"

    cfg.media_root.mkdir(parents=True)
    cfg.media_root.joinpath(MEDIA_ROOT_MARKER).write_text("media-test-root\n", encoding="utf-8")
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda _path: True)
    with connect(cfg.db_path) as conn:
        preview = drain_media_spool(conn, cfg, execute=False)
        assert preview["selected"] == 1
        assert preview["media_root"]["ok"] is True
        source_path = cfg.media_spool_root.joinpath(spool_locator)
        source_path.write_bytes(b"corrupted-spool")
        mismatch = drain_media_spool(conn, cfg, execute=True)
        assert mismatch["moved"] == 0
        assert mismatch["errors"] == 1
        assert source_path.is_file()
        assert not cfg.media_root.joinpath(spool_locator).exists()
        source_path.write_bytes(b"durable-spool-bytes")
        conn.execute(
            """
            CREATE TRIGGER reject_spool_transition
            BEFORE UPDATE OF storage_tier ON media_artifacts
            WHEN OLD.storage_tier = 'spool' AND NEW.storage_tier = 'media-root'
            BEGIN
              SELECT RAISE(IGNORE);
            END
            """
        )
        rejected = drain_media_spool(conn, cfg, execute=True)
        assert rejected["moved"] == 0
        assert rejected["errors"] == 1
        assert cfg.media_spool_root.joinpath(spool_locator).is_file()
        conn.execute("DROP TRIGGER reject_spool_transition")
        result = drain_media_spool(conn, cfg, execute=True)
        assert result["moved"] == 1
        row = conn.execute(
            "SELECT storage_tier, spool_locator, blob_locator, file_path FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()
        assert row["storage_tier"] == "media-root"
        assert row["spool_locator"] is None
        assert cfg.media_root.joinpath(row["blob_locator"]).read_bytes() == b"durable-spool-bytes"
        assert not cfg.media_spool_root.joinpath(spool_locator).exists()
        assert media_spool_status(conn, cfg)["stored_artifacts"] == 0


def test_failed_first_publication_removes_new_blob_and_spool_reservation(tmp_path, monkeypatch):
    cfg = _spool_config(tmp_path, monkeypatch)
    init_db(cfg)
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda _path: False)
    with connect(cfg.db_path) as conn:
        _insert_media_owner(conn)
        conn.commit()
        conn.execute(
            """
            CREATE TRIGGER reject_media_insert
            BEFORE INSERT ON media_artifacts
            BEGIN
              SELECT RAISE(ABORT, 'injected media insert failure');
            END
            """
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="injected media insert failure"):
            store_media_artifact(conn, cfg, _store_payload(b"must-not-survive"))
        assert conn.execute("SELECT COUNT(*) FROM media_artifacts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM media_spool_reservations").fetchone()[0] == 0

    committed_files = [
        path for path in cfg.media_spool_root.rglob("*") if path.is_file() and ".staging" not in path.parts
    ]
    assert committed_files == []
    assert not cfg.media_root.exists()


def test_failed_write_transaction_start_aborts_stage_and_releases_spool_reservation(tmp_path, monkeypatch):
    cfg = _spool_config(tmp_path, monkeypatch)
    init_db(cfg)
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda _path: False)

    def fail_transaction_start(_conn):
        raise sqlite3.OperationalError("injected write lock failure")

    monkeypatch.setattr(media_store_module, "_start_artifact_transaction", fail_transaction_start)
    with connect(cfg.db_path) as conn:
        _insert_media_owner(conn)
        conn.commit()
        with pytest.raises(sqlite3.OperationalError, match="injected write lock failure"):
            store_media_artifact(conn, cfg, _store_payload(b"candidate"))
        assert conn.execute("SELECT COUNT(*) FROM media_spool_reservations").fetchone()[0] == 0

    assert [path for path in cfg.media_spool_root.rglob("*") if path.is_file()] == []


def test_failed_replacement_preserves_previous_blob_and_removes_candidate(tmp_path):
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        _insert_media_owner(conn)
        first = store_media_artifact(conn, cfg, _store_payload(b"original-bytes"))
        row = conn.execute(
            "SELECT file_path FROM media_artifacts WHERE id = ?",
            (first["artifact_id"],),
        ).fetchone()
        original_path = row["file_path"]
        conn.execute(
            """
            CREATE TRIGGER reject_media_update
            BEFORE UPDATE ON media_artifacts
            BEGIN
              SELECT RAISE(ABORT, 'injected media update failure');
            END
            """
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="injected media update failure"):
            store_media_artifact(conn, cfg, _store_payload(b"replacement-bytes"))

    original = cfg.media_root.joinpath(original_path)
    assert original.read_bytes() == b"original-bytes"
    committed_files = [
        path for path in cfg.media_root.rglob("*") if path.is_file() and ".staging" not in path.parts
    ]
    assert committed_files == [original]


def test_metadata_refresh_reports_the_preserved_stored_state(tmp_path):
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        _insert_media_owner(conn)
        first = store_media_artifact(conn, cfg, _store_payload(b"authoritative-bytes"))
        refreshed = store_media_artifact(conn, cfg, _store_payload(b""))
        row = conn.execute(
            "SELECT capture_status, byte_size, file_path FROM media_artifacts WHERE id = ?",
            (first["artifact_id"],),
        ).fetchone()

    assert refreshed["stored"] is True
    assert refreshed["capture_status"] == row["capture_status"] == "stored"
    assert refreshed["byte_size"] == row["byte_size"] == len(b"authoritative-bytes")
    assert Path(row["file_path"]).read_bytes() == b"authoritative-bytes"


def test_replacement_admission_excludes_current_artifact_and_preserves_it_on_row_failure(tmp_path):
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, max_media_cache_bytes=len(b"old-data"))
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        _insert_media_owner(conn)
        first = store_media_artifact(conn, cfg, _store_payload(b"old-data"))
        row = conn.execute(
            "SELECT file_path FROM media_artifacts WHERE id = ?",
            (first["artifact_id"],),
        ).fetchone()
        original = Path(row["file_path"])
        conn.execute(
            """
            CREATE TRIGGER reject_stored_replacement
            BEFORE UPDATE ON media_artifacts
            WHEN NEW.capture_status = 'stored' AND NEW.file_path != OLD.file_path
            BEGIN
              SELECT RAISE(ABORT, 'injected replacement row failure');
            END
            """
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="injected replacement row failure"):
            store_media_artifact(conn, cfg, _store_payload(b"new-data"))
        persisted = conn.execute(
            "SELECT capture_status, file_path FROM media_artifacts WHERE id = ?",
            (first["artifact_id"],),
        ).fetchone()

    assert persisted["capture_status"] == "stored"
    assert Path(persisted["file_path"]) == original
    assert original.read_bytes() == b"old-data"
    assert [path for path in cfg.media_root.rglob("*") if path.is_file() and ".staging" not in path.parts] == [
        original
    ]


def test_spool_reservations_serialize_concurrent_cap_checks(tmp_path, monkeypatch):
    cfg = _spool_config(tmp_path, monkeypatch, cap=10)
    init_db(cfg)
    barrier = Barrier(2)

    def reserve(artifact_id: str) -> str:
        with connect(cfg.db_path) as conn:
            barrier.wait(timeout=5)
            reserve_media_spool(conn, cfg, artifact_id=artifact_id, reserved_bytes=8)
            return artifact_id

    outcomes: list[str] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reserve, "media-reserve-a"), executor.submit(reserve, "media-reserve-b")]
        for future in futures:
            try:
                outcomes.append(future.result(timeout=10))
            except MediaSpoolFull:
                outcomes.append("full")

    assert outcomes.count("full") == 1
    with connect(cfg.db_path) as conn:
        assert conn.execute("SELECT COALESCE(SUM(reserved_bytes), 0) FROM media_spool_reservations").fetchone()[0] == 8


def test_spool_capacity_accounts_for_existing_files_and_exact_headroom(tmp_path, monkeypatch):
    cfg = _spool_config(tmp_path, monkeypatch, cap=10)
    init_db(cfg)
    cfg.media_spool_root.mkdir(parents=True)
    cfg.media_spool_root.joinpath("orphan.bin").write_bytes(b"123456")

    with connect(cfg.db_path) as conn:
        accepted = reserve_media_spool(conn, cfg, artifact_id="exact-fit", reserved_bytes=4)
        assert accepted["projected_bytes"] == 10
        release_media_spool_reservation(conn, str(accepted["reservation_id"]))
        with pytest.raises(MediaSpoolFull):
            reserve_media_spool(conn, cfg, artifact_id="one-byte-over", reserved_bytes=5)
        status = media_spool_status(conn, cfg)
        assert status["filesystem_bytes"] == 6
        assert status["accounted_bytes"] == 6
        assert status["available_bytes"] == 4


def test_concurrent_same_artifact_writers_hold_distinct_reservations(tmp_path, monkeypatch):
    cfg = _spool_config(tmp_path, monkeypatch, cap=16)
    init_db(cfg)
    barrier = Barrier(2)

    def reserve() -> str:
        with connect(cfg.db_path) as conn:
            barrier.wait(timeout=5)
            result = reserve_media_spool(conn, cfg, artifact_id="same-artifact", reserved_bytes=8)
            return str(result["reservation_id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reserve), executor.submit(reserve)]
        reservation_ids = [future.result(timeout=10) for future in futures]

    assert len(set(reservation_ids)) == 2
    with connect(cfg.db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS reservation_count, SUM(reserved_bytes) AS reserved_bytes FROM media_spool_reservations"
        ).fetchone()
        assert int(row["reservation_count"]) == 2
        assert int(row["reserved_bytes"]) == 16
        with pytest.raises(MediaSpoolFull):
            reserve_media_spool(conn, cfg, artifact_id="other-artifact", reserved_bytes=1)


def test_text_and_provenance_commit_when_external_media_has_no_spool(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    media_root = tmp_path / "missing-external-media"
    monkeypatch.setenv("BMD_MEDIA_ROOT_IDENTITY", "media-test-root")
    cfg = load_config(
        runtime_root=runtime_root,
        media_root=media_root,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )
    init_db(cfg)
    monkeypatch.setattr(media_storage_module, "has_non_root_mount_ancestor", lambda _path: False)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/text-first",
            "title": "Text first",
            "text": "Authoritative text survives unavailable media storage.",
            "media_artifacts": [
                {
                    "media_type": "image",
                    "role": "content",
                    "source_url": "https://cdn.example.com/text-first.png",
                    "mime_type": "image/png",
                }
            ],
        }
    )

    with connect(cfg.db_path) as conn:
        captured = ingest_capture(conn, cfg, payload)
        row = conn.execute(
            """
            SELECT id, document_id, snapshot_id, page_url, media_type, role, source_url, mime_type
            FROM media_artifacts
            WHERE snapshot_id = ?
            """,
            (captured["snapshot_id"],),
        ).fetchone()
        upload = dict(row)
        upload["artifact_id"] = upload.pop("id")
        upload["content_base64"] = base64.b64encode(b"cannot-store").decode("ascii")
        with pytest.raises(MediaStorageUnavailable):
            store_media_artifact(conn, cfg, upload)

        snapshot = conn.execute(
            "SELECT cleaned_text, cleaned_text_source FROM snapshots WHERE id = ?",
            (captured["snapshot_id"],),
        ).fetchone()
        artifact = conn.execute(
            "SELECT capture_status, file_path, blob_locator, spool_locator FROM media_artifacts WHERE id = ?",
            (upload["artifact_id"],),
        ).fetchone()
        assert snapshot["cleaned_text"] == payload.text
        assert snapshot["cleaned_text_source"] == "capture"
        assert artifact["capture_status"] == "referenced"
        assert not artifact["file_path"]
        assert artifact["blob_locator"] is None
        assert artifact["spool_locator"] is None
        assert not media_root.exists()
