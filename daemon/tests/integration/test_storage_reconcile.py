from __future__ import annotations

import base64
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from browser_memory_daemon.blob_lifecycle import process_blob_tombstones
from browser_memory_daemon.blob_store import BlobDeleteResult, BlobStore
from browser_memory_daemon.config import RuntimeConfig, load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.forget import forget
from browser_memory_daemon.media import (
    media_artifact,
    media_storage_allowed,
    purge_media_cache,
    store_media_artifact,
)
from browser_memory_daemon.ops import doctor
from browser_memory_daemon.storage_reconcile import reconcile_storage


def _stored_media(tmp_path: Path) -> tuple[RuntimeConfig, dict, Path]:
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        conn.execute(
            """
            INSERT INTO documents(id, canonical_url, normalized_url, domain, first_seen_at, last_seen_at)
            VALUES ('doc-reconcile', 'https://example.org/reconcile', 'https://example.org/reconcile',
                    'example.org', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        conn.execute(
            """
            INSERT INTO snapshots(
              id, document_id, captured_at, content_type, extraction_method,
              text_hash, privacy_class, redaction_count, cleaned_text, cleaned_text_source
            ) VALUES ('snap-reconcile', 'doc-reconcile', CURRENT_TIMESTAMP, 'text/plain',
                      'fixture', 'fixture-hash', 'normal', 0, 'fixture', 'capture')
            """
        )
        stored = store_media_artifact(
            conn,
            cfg,
            {
                "document_id": "doc-reconcile",
                "snapshot_id": "snap-reconcile",
                "media_type": "image",
                "role": "content",
                "source_url": "https://cdn.example.org/reconcile.png",
                "mime_type": "image/png",
                "content_base64": base64.b64encode(b"reconcile-bytes").decode("ascii"),
            },
        )
        row = conn.execute(
            "SELECT file_path FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()
    return cfg, stored, Path(row["file_path"])


def test_forget_persists_retryable_tombstone_before_database_cascade(tmp_path, monkeypatch):
    cfg, stored, media_path = _stored_media(tmp_path)
    real_delete = BlobStore.delete

    def fail_delete(self, locator):
        return BlobDeleteResult("error", self.resolve(locator, require_file=False).path)

    monkeypatch.setattr(BlobStore, "delete", fail_delete)
    with connect(cfg.db_path) as conn:
        result = forget(conn, cfg, domain="example.org")
        assert result["forgotten"] is False
        assert result["database_forgotten"] is True
        assert result["deletion"]["pending"] == 1
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        tombstone = conn.execute(
            "SELECT state, owner_kind, owner_id, locator FROM blob_storage_records"
        ).fetchone()
        assert dict(tombstone) == {
            "state": "failed",
            "owner_kind": "media-artifact",
            "owner_id": stored["artifact_id"],
            "locator": media_path.name,
        }
        receipt = conn.execute(
            "SELECT counts_json FROM deletion_receipts WHERE id = ?",
            (result["receipt_id"],),
        ).fetchone()
        assert '"blob_deletions_pending": 1' in receipt["counts_json"]
        health = doctor(cfg, conn)
        assert health["ok"] is False
        assert health["blob_lifecycle"]["pending"] == 1
    assert media_path.is_file()

    monkeypatch.setattr(BlobStore, "delete", real_delete)
    with connect(cfg.db_path) as conn:
        reconciled = reconcile_storage(conn, cfg, execute=True)
        assert reconciled["tombstones"]["deleted"] == 1
        assert reconciled["tombstones"]["pending"] == 0
        assert conn.execute("SELECT state FROM blob_storage_records").fetchone()[0] == "deleted"
        receipt = conn.execute(
            "SELECT counts_json FROM deletion_receipts WHERE id = ?",
            (result["receipt_id"],),
        ).fetchone()
        assert '"blob_deletions_pending": 0' in receipt["counts_json"]
        assert doctor(cfg, conn)["ok"] is True
    assert not media_path.exists()


def test_media_purge_remains_pending_until_tombstoned_bytes_are_deleted(tmp_path, monkeypatch):
    cfg, stored, media_path = _stored_media(tmp_path)
    cfg = replace(cfg, max_media_cache_bytes=16, max_media_bytes_per_domain=0)
    real_delete = BlobStore.delete
    monkeypatch.setattr(
        BlobStore,
        "delete",
        lambda self, locator: BlobDeleteResult("error", self.resolve(locator, require_file=False).path),
    )

    with connect(cfg.db_path) as conn:
        purged = purge_media_cache(conn, cfg, {"domain": "example.org", "dry_run": False})
        assert purged["purged"] == 0
        assert purged["pending_deletions"] == 1
        row = conn.execute(
            "SELECT capture_status, file_path, blob_locator FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()
        assert row["capture_status"] == "purging"
        assert row["file_path"]
        assert row["blob_locator"]
        assert media_artifact(conn, cfg, stored["artifact_id"])["has_file"] is False
        with pytest.raises(ValueError, match="deletion is pending"):
            store_media_artifact(
                conn,
                cfg,
                {
                    "artifact_id": stored["artifact_id"],
                    "document_id": "doc-reconcile",
                    "snapshot_id": "snap-reconcile",
                    "media_type": "image",
                    "role": "content",
                    "source_url": "https://cdn.example.org/reconcile.png",
                    "mime_type": "image/png",
                    "content_base64": base64.b64encode(b"replacement").decode("ascii"),
                },
            )
        allowed, reason = media_storage_allowed(
            conn,
            cfg,
            document_id="doc-reconcile",
            snapshot_id="snap-reconcile",
            media_type="image",
            mime_type="image/png",
            candidate_bytes=2,
        )
        assert allowed is False
        assert reason == "media-cache-budget"
    assert media_path.is_file()

    monkeypatch.setattr(BlobStore, "delete", real_delete)
    with connect(cfg.db_path) as conn:
        reconciled = reconcile_storage(conn, cfg, execute=True)
        assert reconciled["tombstones"]["deleted"] == 1
        row = conn.execute(
            "SELECT capture_status, file_path, blob_locator FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()
        assert dict(row) == {"capture_status": "purged", "file_path": "", "blob_locator": None}
    assert not media_path.exists()


def test_concurrent_tombstone_processors_delete_once_and_converge(tmp_path, monkeypatch):
    cfg, _stored, media_path = _stored_media(tmp_path)
    real_delete = BlobStore.delete
    monkeypatch.setattr(
        BlobStore,
        "delete",
        lambda self, locator: BlobDeleteResult("error", self.resolve(locator, require_file=False).path),
    )
    with connect(cfg.db_path) as conn:
        purge_media_cache(conn, cfg, {"domain": "example.org", "dry_run": False})
        operation_id = conn.execute(
            "SELECT operation_id FROM blob_storage_records WHERE state = 'failed'"
        ).fetchone()[0]
    monkeypatch.setattr(BlobStore, "delete", real_delete)

    barrier = Barrier(2)

    def process() -> dict[str, int]:
        with connect(cfg.db_path) as worker_conn:
            barrier.wait(timeout=5)
            return process_blob_tombstones(
                worker_conn,
                cfg,
                operation_id=operation_id,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(process), executor.submit(process)]
        results = [future.result(timeout=10) for future in futures]

    assert sum(result["deleted"] for result in results) == 1
    assert not media_path.exists()
    with connect(cfg.db_path) as conn:
        assert conn.execute(
            "SELECT state FROM blob_storage_records WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == "deleted"


def test_storage_reconcile_reports_and_repairs_missing_orphan_and_stale_stage(tmp_path):
    cfg, stored, media_path = _stored_media(tmp_path)
    media_path.unlink()
    orphan = cfg.media_root / "orphan.bin"
    orphan.write_bytes(b"orphan")
    stage_dir = cfg.media_root / ".staging"
    stage_dir.mkdir(exist_ok=True)
    stale_stage = stage_dir / "stale.stage"
    stale_stage.write_bytes(b"stale")
    stale_time = time.time() - 7200
    os.utime(stale_stage, (stale_time, stale_time))

    with connect(cfg.db_path) as conn:
        preview = reconcile_storage(conn, cfg, execute=False, stale_stage_seconds=3600)
        assert preview["missing"]["count"] == 1
        assert preview["orphans"]["count"] == 1
        assert preview["stale_stages"]["count"] == 1
        assert conn.execute(
            "SELECT capture_status FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()[0] == "stored"
        assert orphan.is_file()
        assert stale_stage.is_file()

        applied = reconcile_storage(conn, cfg, execute=True, stale_stage_seconds=3600)
        assert applied["missing"]["marked"] == 1
        assert applied["orphans"]["deleted"] == 1
        assert applied["stale_stages"]["deleted"] == 1
        row = conn.execute(
            "SELECT capture_status, status_reason FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()
        assert dict(row) == {
            "capture_status": "missing",
            "status_reason": "storage-reconcile:missing",
        }
    assert not orphan.exists()
    assert not stale_stage.exists()

    media_path.write_bytes(b"wrong-bytes")
    with connect(cfg.db_path) as conn:
        preview = reconcile_storage(conn, cfg, execute=False)
        assert preview["corrupt"]["count"] == 1
        assert preview["recovered"]["count"] == 0
        corrupt = reconcile_storage(conn, cfg, execute=True)
        assert corrupt["missing"]["marked"] == 1
        row = conn.execute(
            "SELECT capture_status, status_reason FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()
        assert dict(row) == {
            "capture_status": "missing",
            "status_reason": "storage-reconcile:corrupt",
        }

    media_path.write_bytes(b"reconcile-bytes")
    with connect(cfg.db_path) as conn:
        preview = reconcile_storage(conn, cfg, execute=False)
        assert preview["recovered"]["count"] == 1
        recovered = reconcile_storage(conn, cfg, execute=True)
        assert recovered["recovered"]["marked"] == 1
        row = conn.execute(
            "SELECT capture_status, status_reason FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()
        assert dict(row) == {"capture_status": "stored", "status_reason": None}
