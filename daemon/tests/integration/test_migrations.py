from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import shutil
import sqlite3
from threading import Barrier
from types import SimpleNamespace

import pytest

from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import SCHEMA_PATH, connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.migrations import (
    LATEST_SCHEMA_VERSION,
    MIGRATIONS,
    V1_SCHEMA_FINGERPRINT,
    MigrationCompatibilityError,
    MigrationExecutionError,
    MigrationPreflightError,
    MigrationStep,
    migrate_database,
    migration_checksum,
    migration_status,
    schema_fingerprint,
)
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.search import search_memory


def _config(tmp_path):
    return load_config(
        runtime_root=tmp_path / "runtime",
        blob_root=tmp_path / "blobs",
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )


def _create_unversioned_current_db(cfg, *, with_media_ref: bool = False) -> None:
    cfg.ensure_dirs()
    with sqlite3.connect(cfg.db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO sources(id, source_type, source_name) VALUES ('chrome-extension', 'browser', 'chrome-extension')"
        )
        if with_media_ref:
            conn.execute(
                """
                INSERT INTO documents(
                  id, canonical_url, normalized_url, domain, title, first_seen_at, last_seen_at
                ) VALUES ('doc-legacy', 'https://example.com/legacy', 'https://example.com/legacy',
                          'example.com', 'Legacy', '2026-07-10T00:00:00Z', '2026-07-10T00:00:00Z')
                """
            )
            conn.execute(
                """
                INSERT INTO snapshots(
                  id, document_id, visit_id, captured_at, content_type, extraction_method,
                  text_hash, cleaned_text_path, privacy_class, redaction_count
                ) VALUES ('snap-legacy', 'doc-legacy', NULL, '2026-07-10T00:00:00Z',
                          'text/html', 'dom-text', 'legacy-hash', NULL, 'normal', 0)
                """
            )
            conn.execute(
                """
                INSERT INTO media_artifacts(
                  id, document_id, snapshot_id, visit_id, media_type, role, source_url,
                  normalized_source_url, page_url, capture_status, metadata_json
                ) VALUES ('media-legacy', 'doc-legacy', 'snap-legacy', NULL, 'image', 'content',
                          'https://cdn.example.com/legacy.png', 'https://cdn.example.com/legacy.png',
                          'https://example.com/legacy', 'referenced', '{"priority": 73}')
                """
            )


def _capture(conn, cfg):
    payload = CapturePayload.from_dict(
        {
            "visit_id": "migration-visit",
            "url": "https://example.com/migration-proof",
            "title": "Migration proof",
            "text": "Versioned migration preserves searchable full text.",
        },
        allow_any_url=True,
    )
    return ingest_capture(conn, cfg, payload)


def test_fresh_database_migrates_to_ordered_versioned_ledger_and_preserves_fts(tmp_path):
    cfg = _config(tmp_path)

    before = migration_status(cfg)
    assert before["state"] == "uninitialized"
    assert before["ready"] is False
    assert before["pending_versions"] == [1, 2, 3]
    assert not cfg.db_path.exists()

    result = migrate_database(cfg, execute=True)
    assert result["ready"] is True
    assert result["current_version"] == LATEST_SCHEMA_VERSION == 3
    assert result["applied_versions"] == [1, 2, 3]
    assert result["stamped_versions"] == []

    with connect(cfg.db_path) as conn:
        ledger = conn.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [row["version"] for row in ledger] == [1, 2, 3]
        assert all(row["name"] and len(row["checksum"]) == 64 and row["applied_at"] for row in ledger)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA_VERSION
        assert schema_fingerprint(conn) == V1_SCHEMA_FINGERPRINT
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute(
            "SELECT COUNT(*) FROM sources WHERE id = 'chrome-extension'"
        ).fetchone()[0] == 1
        stored = _capture(conn, cfg)
        conn.commit()
        results = search_memory(conn, "Versioned migration", limit=10)
        assert results and results[0]["snapshot_id"] == stored["snapshot_id"]
        assert conn.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE snapshot_id = ?", (stored["snapshot_id"],)
        ).fetchone()[0] > 0


def test_unversioned_current_schema_is_stamped_then_historical_seed_runs_once(tmp_path):
    cfg = _config(tmp_path)
    _create_unversioned_current_db(cfg, with_media_ref=True)

    before = migration_status(cfg)
    assert before["state"] == "unversioned-current"
    assert before["schema_fingerprint"] == V1_SCHEMA_FINGERPRINT
    with sqlite3.connect(cfg.db_path) as raw:
        assert raw.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()[0] == 0

    result = migrate_database(cfg, execute=True)
    assert result["stamped_versions"] == [1]
    assert result["applied_versions"] == [2, 3]
    with connect(cfg.db_path) as conn:
        task = conn.execute(
            "SELECT status, priority FROM media_fetch_tasks WHERE artifact_id = 'media-legacy'"
        ).fetchone()
        assert dict(task) == {"status": "pending", "priority": 73}
        conn.execute("DELETE FROM media_fetch_tasks WHERE artifact_id = 'media-legacy'")
        conn.commit()

    init_db(cfg)
    with connect(cfg.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM media_fetch_tasks WHERE artifact_id = 'media-legacy'"
        ).fetchone()[0] == 0


def test_repeated_migration_is_a_noop_and_schema_has_no_recurring_repair_dml(tmp_path):
    cfg = _config(tmp_path)
    first = migrate_database(cfg, execute=True)
    with connect(cfg.db_path) as conn:
        ledger_before = [tuple(row) for row in conn.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()]

    second = migrate_database(cfg, execute=True)
    with connect(cfg.db_path) as conn:
        ledger_after = [tuple(row) for row in conn.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()]

    assert first["applied_versions"] == [1, 2, 3]
    assert second["applied_versions"] == []
    assert second["stamped_versions"] == []
    assert ledger_after == ledger_before
    assert "DELETE FROM privacy_rules" not in SCHEMA_PATH.read_text(encoding="utf-8")


def test_concurrent_fresh_migration_applies_each_ledger_step_once(tmp_path):
    cfg = _config(tmp_path)
    barrier = Barrier(2)

    def run_migration():
        barrier.wait(timeout=5)
        return migrate_database(cfg, execute=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_migration), executor.submit(run_migration)]
        results = [future.result(timeout=20) for future in futures]

    assert all(result["ready"] is True for result in results)
    assert sorted(
        version for result in results for version in result["applied_versions"]
    ) == [1, 2, 3]
    with connect(cfg.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 3
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_checksum_mismatch_and_unknown_newer_version_fail_closed(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        conn.execute("UPDATE schema_migrations SET checksum = ? WHERE version = 2", ("0" * 64,))
        conn.commit()
    with pytest.raises(MigrationCompatibilityError, match="checksum mismatch"):
        migration_status(cfg)

    other_cfg = _config(tmp_path / "other")
    init_db(other_cfg)
    with connect(other_cfg.db_path) as conn:
        conn.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 1}")
        conn.commit()
    with pytest.raises(MigrationCompatibilityError, match="newer schema version"):
        migration_status(other_cfg)


def test_unknown_unversioned_schema_is_not_stamped(tmp_path):
    cfg = _config(tmp_path)
    cfg.ensure_dirs()
    with sqlite3.connect(cfg.db_path) as conn:
        conn.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)")

    with pytest.raises(MigrationCompatibilityError, match="unrecognized unversioned schema"):
        migrate_database(cfg, execute=True)
    with sqlite3.connect(cfg.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()[0] == 0


def test_injected_migration_failure_rolls_back_step_and_ledger(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)

    def fail_after_write(conn):
        conn.execute("CREATE TABLE should_rollback(id INTEGER PRIMARY KEY)")
        raise RuntimeError("injected migration failure")

    failing = MigrationStep(
        version=4,
        name="injected_failure",
        checksum=migration_checksum(4, "injected_failure", "fixture-v1"),
        apply=fail_after_write,
    )
    with pytest.raises(MigrationExecutionError, match="injected migration failure"):
        migrate_database(cfg, execute=True, steps=(*MIGRATIONS, failing))

    with connect(cfg.db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 4"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table' AND name = 'should_rollback'"
        ).fetchone()[0] == 0


def test_destructive_migration_creates_online_backup_that_restores_search(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        stored = _capture(conn, cfg)
        conn.commit()

    def fail_destructive_step(conn):
        conn.execute("DELETE FROM chunks_fts")
        raise RuntimeError("destructive fixture failed")

    destructive = MigrationStep(
        version=4,
        name="destructive_fixture",
        checksum=migration_checksum(4, "destructive_fixture", "fixture-v1"),
        apply=fail_destructive_step,
        destructive=True,
    )
    with pytest.raises(MigrationExecutionError, match="destructive fixture failed") as caught:
        migrate_database(
            cfg,
            execute=True,
            allow_destructive=True,
            steps=(*MIGRATIONS, destructive),
        )

    backup_path = caught.value.backup_path
    assert backup_path is not None and backup_path.exists()
    restored_path = tmp_path / "restored.sqlite3"
    shutil.copy2(backup_path, restored_path)
    with connect(restored_path) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert restored.execute("PRAGMA foreign_key_check").fetchall() == []
        results = search_memory(restored, "Versioned migration", limit=10)
        assert results and results[0]["snapshot_id"] == stored["snapshot_id"]


def test_destructive_migration_refuses_insufficient_backup_headroom_before_writes(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    called = False

    def should_not_run(conn):
        nonlocal called
        called = True

    destructive = MigrationStep(
        version=4,
        name="headroom_fixture",
        checksum=migration_checksum(4, "headroom_fixture", "fixture-v1"),
        apply=should_not_run,
        destructive=True,
    )
    with pytest.raises(MigrationPreflightError, match="insufficient disk headroom"):
        migrate_database(
            cfg,
            execute=True,
            allow_destructive=True,
            steps=(*MIGRATIONS, destructive),
            disk_usage_fn=lambda _path: SimpleNamespace(free=0),
        )
    assert called is False
    assert not (cfg.state_root / "migration-backups").exists()
