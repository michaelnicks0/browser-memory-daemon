from __future__ import annotations

import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import SCHEMA_PATH, connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.migration_steps import (
    v0001_baseline_schema,
    v0004_capture_observations_and_url_claims,
)
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


def _drop_claimed_visit_identity(conn: sqlite3.Connection) -> None:
    conn.execute("DROP INDEX IF EXISTS idx_visit_events_claimed_visit")
    conn.execute("ALTER TABLE visit_events DROP COLUMN attachment_method")
    conn.execute("ALTER TABLE visit_events DROP COLUMN claimed_visit_id")


def _drop_relative_blob_locators(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE media_artifacts DROP COLUMN blob_locator")
    conn.execute("ALTER TABLE snapshots DROP COLUMN cleaned_text_locator")


def _drop_snapshot_text_authority(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE snapshots DROP COLUMN cleaned_text_source")
    conn.execute("ALTER TABLE snapshots DROP COLUMN cleaned_text")


def _drop_media_storage_tiers(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS blob_storage_records")
    conn.execute("DROP TABLE IF EXISTS media_cache_reservations")
    conn.execute("DROP TABLE media_spool_reservations")
    conn.execute("ALTER TABLE media_artifacts DROP COLUMN spool_locator")
    conn.execute("ALTER TABLE media_artifacts DROP COLUMN storage_tier")


def _create_unversioned_current_db(cfg, *, with_media_ref: bool = False) -> None:
    cfg.ensure_dirs()
    with sqlite3.connect(cfg.db_path) as conn:
        conn.executescript(v0001_baseline_schema.SQL)
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
    expected_versions = list(range(1, LATEST_SCHEMA_VERSION + 1))

    before = migration_status(cfg)
    assert before["state"] == "uninitialized"
    assert before["ready"] is False
    assert before["pending_versions"] == expected_versions
    assert not cfg.db_path.exists()

    result = migrate_database(cfg, execute=True)
    assert result["ready"] is True
    assert result["current_version"] == LATEST_SCHEMA_VERSION
    assert result["applied_versions"] == expected_versions
    assert result["stamped_versions"] == []

    with connect(cfg.db_path) as conn:
        ledger = conn.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [row["version"] for row in ledger] == expected_versions
        assert all(row["name"] and len(row["checksum"]) == 64 and row["applied_at"] for row in ledger)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA_VERSION
        expected_fingerprint = next(
            step.schema_fingerprint for step in reversed(MIGRATIONS) if step.schema_fingerprint
        )
        assert schema_fingerprint(conn) == expected_fingerprint
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
    assert result["applied_versions"] == list(range(2, LATEST_SCHEMA_VERSION + 1))
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


def test_version_twelve_normalizes_historical_media_state_once(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        conn.execute(
            """
            INSERT INTO documents(id, canonical_url, normalized_url, domain, first_seen_at, last_seen_at)
            VALUES ('doc-media-v12', 'https://example.com/media-v12', 'https://example.com/media-v12',
                    'example.com', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        conn.execute(
            """
            INSERT INTO snapshots(id, document_id, captured_at, content_type, extraction_method,
                                  text_hash, privacy_class, redaction_count, cleaned_text)
            VALUES ('snap-media-v12', 'doc-media-v12', CURRENT_TIMESTAMP, 'text/html', 'fixture',
                    'hash-media-v12', 'normal', 0, 'fixture text')
            """
        )
        artifacts = [
            ("legacy-blob", "video", "blob:https://example.com/legacy", "skipped", "unsupported-media-url-scheme", "{}", None),
            ("legacy-hls", "video", "https://cdn.example/master.m3u8", "skipped", "unsupported-media-url-scheme", "{}", None),
            ("legacy-audio", "video", "https://cdn.example/mp4a/audio.m3u8", "referenced", "hls-audio-rendition", "{}", None),
            ("failed-404", "image", "https://cdn.example/missing.png", "failed", "fetch-status-404", "{}", None),
            ("failed-429", "image", "https://cdn.example/rate.png", "failed", "fetch-status-429", "{}", None),
            ("video-html", "video", "https://cdn.example/player", "skipped", "non-media-content-type", "{}", None),
            ("opaque-blob", "video", "blob:https://example.com/opaque", "referenced", None, "{}", None),
            ("covered-blob", "video", "blob:https://example.com/covered", "referenced", None, "{}", None),
            ("media_cdp_fixture", "video", "https://video.twimg.com/segment.ts", "stored", None, '{"cdp_recorder": true}', "media/cdp.bin"),
        ]
        conn.executemany(
            """
            INSERT INTO media_artifacts(
              id, document_id, snapshot_id, media_type, role, source_url,
              normalized_source_url, page_url, capture_status, status_reason,
              metadata_json, blob_locator, byte_size
            ) VALUES (?, 'doc-media-v12', 'snap-media-v12', ?, 'content', ?, ?,
                      'https://example.com/media-v12', ?, ?, ?, ?, CASE WHEN ? IS NULL THEN 0 ELSE 4 END)
            """,
            [
                (artifact_id, media_type, source_url, source_url, status, reason, metadata, locator, locator)
                for artifact_id, media_type, source_url, status, reason, metadata, locator in artifacts
            ],
        )
        task_rows = [
            (f"task-{index}", artifact_id, "pending" if artifact_id == "media_cdp_fixture" else "failed")
            for index, (artifact_id, *_rest) in enumerate(artifacts)
            if artifact_id not in {"opaque-blob", "covered-blob"}
        ]
        conn.executemany(
            """
            INSERT INTO media_fetch_tasks(
              id, artifact_id, worker_kind, status, priority, attempts, max_attempts, updated_at
            ) VALUES (?, ?, 'daemon-public', ?, 50, 3, 5, CURRENT_TIMESTAMP)
            """,
            task_rows,
        )
        conn.execute("DROP TABLE media_cache_reservations")
        conn.execute("DELETE FROM schema_migrations WHERE version >= 12")
        conn.execute("PRAGMA user_version = 11")
        conn.commit()

    result = migrate_database(cfg, execute=True)
    assert result["applied_versions"] == [12, 13]
    with connect(cfg.db_path) as conn:
        statuses = {
            row["id"]: (row["capture_status"], row["status_reason"])
            for row in conn.execute(
                "SELECT id, capture_status, status_reason FROM media_artifacts WHERE snapshot_id = 'snap-media-v12'"
            )
        }
        assert statuses["legacy-blob"] == ("referenced", "covered-by-cdp-recorder")
        assert statuses["legacy-hls"] == ("referenced", None)
        assert statuses["legacy-audio"] == ("referenced", None)
        assert statuses["failed-404"] == ("expired", "fetch-status-404")
        assert statuses["failed-429"] == ("retrying", "fetch-status-429")
        assert statuses["video-html"] == ("referenced", "non-media-content-type")
        assert statuses["opaque-blob"] == ("referenced", "covered-by-cdp-recorder")
        assert statuses["covered-blob"] == ("referenced", "covered-by-cdp-recorder")
        task_statuses = {
            row["artifact_id"]: (row["status"], row["attempts"])
            for row in conn.execute(
                "SELECT artifact_id, status, attempts FROM media_fetch_tasks WHERE artifact_id IN ('legacy-hls', 'legacy-audio', 'failed-404', 'failed-429', 'media_cdp_fixture')"
            )
        }
        assert task_statuses["legacy-hls"] == ("pending", 0)
        assert task_statuses["legacy-audio"] == ("pending", 0)
        assert task_statuses["failed-404"] == ("skipped", 3)
        assert task_statuses["failed-429"] == ("retrying", 3)
        assert task_statuses["media_cdp_fixture"] == ("succeeded", 3)

    repeated = migrate_database(cfg, execute=True)
    assert repeated["applied_versions"] == []


def test_version_thirteen_adds_cache_reservations_from_exact_prior_schema(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        conn.execute("DROP TABLE media_cache_reservations")
        conn.execute("DELETE FROM schema_migrations WHERE version = 13")
        conn.execute("PRAGMA user_version = 12")
        conn.commit()

    before = migration_status(cfg)
    assert before["current_version"] == 12
    assert before["pending_versions"] == [13]
    result = migrate_database(cfg, execute=True)
    assert result["applied_versions"] == [13]
    with connect(cfg.db_path) as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(media_cache_reservations)").fetchall()
        }
        assert columns == {
            "reservation_id",
            "artifact_id",
            "document_id",
            "snapshot_id",
            "domain",
            "reserved_bytes",
            "owner_pid",
            "owner_start_token",
            "expires_at",
            "created_at",
        }
        foreign_keys = {
            row["from"]: (row["table"], row["on_delete"])
            for row in conn.execute("PRAGMA foreign_key_list(media_cache_reservations)")
        }
        assert foreign_keys == {
            "document_id": ("documents", "CASCADE"),
            "snapshot_id": ("snapshots", "CASCADE"),
        }
        assert schema_fingerprint(conn) == MIGRATIONS[-1].schema_fingerprint


def test_capture_observation_and_url_claim_schema_enforces_expand_contract(tmp_path):
    cfg = _config(tmp_path)
    assert (
        v0004_capture_observations_and_url_claims.SQL.strip()
        in SCHEMA_PATH.read_text(encoding="utf-8")
    )
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        stored = _capture(conn, cfg)
        conn.execute(
            """
            INSERT INTO capture_observations(
              id, idempotency_key, navigation_id, visit_id, document_id, snapshot_id,
              observed_url, normalized_observed_url, title, captured_at,
              capture_reason, capture_method, extraction_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "obs-schema-proof",
                "idem-schema-proof",
                "nav-schema-proof",
                stored["visit_id"],
                stored["document_id"],
                stored["snapshot_id"],
                "https://example.com/migration-proof",
                "https://example.com/migration-proof",
                "Migration proof",
                "2026-07-10T00:00:00Z",
                "test",
                "fixture",
                "fixture-v1",
            ),
        )
        conn.execute(
            """
            INSERT INTO document_url_claims(
              id, document_id, observation_id, claim_type, claimed_url,
              normalized_claimed_url, claim_origin, same_origin,
              first_observed_at, last_observed_at
            ) VALUES (?, ?, ?, 'canonical', ?, ?, ?, 0, ?, ?)
            """,
            (
                "claim-cross-origin",
                stored["document_id"],
                "obs-schema-proof",
                "https://other.example/target",
                "https://other.example/target",
                "https://other.example",
                "2026-07-10T00:00:00Z",
                "2026-07-10T00:00:00Z",
            ),
        )
        claim = conn.execute(
            "SELECT same_origin, identity_effect, provenance_quality FROM document_url_claims"
        ).fetchone()
        assert dict(claim) == {
            "same_origin": 0,
            "identity_effect": "none",
            "provenance_quality": "observed",
        }
        assert conn.execute(
            "SELECT COUNT(*) FROM documents WHERE normalized_url = 'https://other.example/target'"
        ).fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE capture_observations SET disposition = 'invalid' WHERE id = 'obs-schema-proof'"
            )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_version_three_fixture_upgrades_once_to_capture_model_expand_schema(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        _drop_media_storage_tiers(conn)
        _drop_snapshot_text_authority(conn)
        _drop_relative_blob_locators(conn)
        _drop_claimed_visit_identity(conn)
        conn.execute("DROP TABLE media_artifact_observations")
        conn.execute("DROP TABLE document_url_claims")
        conn.execute("DROP TABLE capture_observations")
        conn.execute("DELETE FROM schema_migrations WHERE version >= 4")
        conn.execute("PRAGMA user_version = 3")
        conn.commit()

    before = migration_status(cfg)
    assert before["current_version"] == 3
    assert before["pending_versions"] == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    result = migrate_database(cfg, execute=True)
    assert result["applied_versions"] == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    with connect(cfg.db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "capture_observations",
            "document_url_claims",
            "media_artifact_observations",
        } <= tables
        assert schema_fingerprint(conn) == MIGRATIONS[-1].schema_fingerprint


def test_version_five_backfills_only_evidence_supported_historical_relationships(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        _drop_media_storage_tiers(conn)
        _drop_snapshot_text_authority(conn)
        _drop_relative_blob_locators(conn)
        _drop_claimed_visit_identity(conn)
        conn.execute("DELETE FROM document_url_claims")
        conn.execute("DELETE FROM capture_observations")
        conn.execute("DROP TABLE media_artifact_observations")
        conn.execute("DELETE FROM schema_migrations WHERE version >= 5")
        conn.execute("PRAGMA user_version = 4")
        conn.execute(
            """
            INSERT INTO documents(id, canonical_url, normalized_url, domain, title, first_seen_at, last_seen_at)
            VALUES ('doc-legacy', 'https://canonical.example/item', 'https://canonical.example/item',
                    'canonical.example', 'Legacy document', '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO visits(
              id, document_id, source_id, url, normalized_url, title,
              source_device, browser_profile, visit_started_at, captured_at,
              dwell_seconds, is_incognito, blocked
            ) VALUES ('visit-legacy', 'doc-legacy', 'chrome-extension',
                      'https://observed.example/item', 'https://observed.example/item',
                      'Observed legacy title', 'legacy-device', 'Default',
                      '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 0, 0, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO snapshots(
              id, document_id, visit_id, captured_at, content_type, extraction_method,
              text_hash, cleaned_text_path, privacy_class, redaction_count
            ) VALUES ('snap-with-visit', 'doc-legacy', 'visit-legacy', '2026-01-01T00:00:00Z',
                      'text/plain', 'legacy-v1', 'hash-with-visit', '/legacy/with-visit.txt', 'legacy', 0)
            """
        )
        conn.execute(
            """
            INSERT INTO snapshots(
              id, document_id, visit_id, captured_at, content_type, extraction_method,
              text_hash, cleaned_text_path, privacy_class, redaction_count
            ) VALUES ('snap-ambiguous', 'doc-legacy', NULL, '2026-01-02T00:00:00Z',
                      'text/plain', 'legacy-v1', 'hash-ambiguous', '/legacy/ambiguous.txt', 'legacy', 0)
            """
        )

    pending = migration_status(cfg, steps=MIGRATIONS[:5])
    assert pending["current_version"] == 4
    assert pending["pending_versions"] == [5]
    result = migrate_database(cfg, execute=True, steps=MIGRATIONS[:5])
    assert result["applied_versions"] == [5]

    with connect(cfg.db_path) as conn:
        observations = conn.execute(
            """
            SELECT snapshot_id, visit_id, observed_url, normalized_observed_url,
                   disposition, provenance_quality
            FROM capture_observations
            ORDER BY snapshot_id
            """
        ).fetchall()
        assert [dict(row) for row in observations] == [
            {
                "snapshot_id": "snap-ambiguous",
                "visit_id": None,
                "observed_url": "https://canonical.example/item",
                "normalized_observed_url": "https://canonical.example/item",
                "disposition": "historical-ambiguous",
                "provenance_quality": "ambiguous",
            },
            {
                "snapshot_id": "snap-with-visit",
                "visit_id": "visit-legacy",
                "observed_url": "https://observed.example/item",
                "normalized_observed_url": "https://observed.example/item",
                "disposition": "historical-inferred",
                "provenance_quality": "inferred",
            },
        ]
        claim = dict(
            conn.execute(
                """
                SELECT claim_type, claimed_url, identity_effect, provenance_quality, same_origin
                FROM document_url_claims
                WHERE document_id = 'doc-legacy'
                """
            ).fetchone()
        )
        assert claim == {
            "claim_type": "legacy-canonical",
            "claimed_url": "https://canonical.example/item",
            "identity_effect": "historical-authority",
            "provenance_quality": "ambiguous",
            "same_origin": None,
        }
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    assert migrate_database(cfg, execute=True, steps=MIGRATIONS[:5])["applied_versions"] == []


def test_version_six_backfills_only_unambiguous_media_observation_links(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)

    def capture(*, suffix: str, observation_id: str, visit_id: str, captured_at: str):
        return ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "url": f"https://example.com/{suffix}",
                    "title": suffix,
                    "text": f"Stable text for {suffix}.",
                    "visit_id": visit_id,
                    "navigation_id": visit_id,
                    "observation_id": observation_id,
                    "captured_at": captured_at,
                    "media_artifacts": [
                        {
                            "media_type": "image",
                            "role": "content",
                            "source_url": f"https://cdn.example.com/{suffix}.png",
                        }
                    ],
                }
            ),
        )

    with connect(cfg.db_path) as conn:
        exact = capture(
            suffix="exact-media-link",
            observation_id="observation-exact-media",
            visit_id="visit-exact-media",
            captured_at="2026-01-03T00:00:00Z",
        )
        no_visit = capture(
            suffix="no-visit-media-link",
            observation_id="observation-no-visit-media",
            visit_id="visit-no-visit-media",
            captured_at="2026-01-04T00:00:00Z",
        )
        ambiguous_first = capture(
            suffix="ambiguous-media-link",
            observation_id="observation-ambiguous-media-1",
            visit_id="visit-ambiguous-media",
            captured_at="2026-01-05T00:00:00Z",
        )
        capture(
            suffix="ambiguous-media-link",
            observation_id="observation-ambiguous-media-2",
            visit_id="visit-ambiguous-media",
            captured_at="2026-01-05T00:05:00Z",
        )
        conn.execute(
            "UPDATE media_artifacts SET visit_id = NULL WHERE id = ?",
            (no_visit["media_artifacts"][0]["artifact_id"],),
        )
        _drop_media_storage_tiers(conn)
        _drop_snapshot_text_authority(conn)
        _drop_relative_blob_locators(conn)
        _drop_claimed_visit_identity(conn)
        conn.execute("DROP TABLE media_artifact_observations")
        conn.execute("DELETE FROM schema_migrations WHERE version >= 6")
        conn.execute("PRAGMA user_version = 5")

    pending = migration_status(cfg, steps=MIGRATIONS[:6])
    assert pending["current_version"] == 5
    assert pending["pending_versions"] == [6]
    result = migrate_database(cfg, execute=True, steps=MIGRATIONS[:6])
    assert result["applied_versions"] == [6]

    with connect(cfg.db_path) as conn:
        links = {
            row["artifact_id"]: dict(row)
            for row in conn.execute(
                """
                SELECT artifact_id, observation_id, provenance_quality, observed_at
                FROM media_artifact_observations
                ORDER BY artifact_id
                """
            ).fetchall()
        }
        exact_artifact_id = exact["media_artifacts"][0]["artifact_id"]
        no_visit_artifact_id = no_visit["media_artifacts"][0]["artifact_id"]
        ambiguous_artifact_id = ambiguous_first["media_artifacts"][0]["artifact_id"]
        assert links[exact_artifact_id] == {
            "artifact_id": exact_artifact_id,
            "observation_id": exact["observation_id"],
            "provenance_quality": "inferred",
            "observed_at": "2026-01-03T00:00:00Z",
        }
        assert links[no_visit_artifact_id] == {
            "artifact_id": no_visit_artifact_id,
            "observation_id": no_visit["observation_id"],
            "provenance_quality": "ambiguous",
            "observed_at": "2026-01-04T00:00:00Z",
        }
        assert ambiguous_artifact_id not in links
        assert schema_fingerprint(conn) == MIGRATIONS[5].schema_fingerprint
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_version_seven_preserves_claimed_visit_identity_for_historical_events(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        capture = ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "visit_id": "visit-v7-history",
                    "url": "https://example.org/v7-history",
                    "title": "Version seven history",
                    "text": "Readable historical lifecycle fixture for migration version seven.",
                }
            ),
        )
        conn.execute(
            """
            INSERT INTO visit_events(
              id, visit_id, document_id, source_id, url, normalized_url, event_type,
              event_started_at, event_ended_at, active_seconds, metadata_json
            ) VALUES (?, ?, ?, 'chrome-extension', ?, ?, 'active-segment', ?, ?, 10, '{}')
            """,
            (
                "event-v7-history",
                "visit-v7-history",
                capture["document_id"],
                "https://example.org/v7-history",
                "https://example.org/v7-history",
                "2026-01-06T00:00:00Z",
                "2026-01-06T00:00:10Z",
            ),
        )
        _drop_media_storage_tiers(conn)
        _drop_snapshot_text_authority(conn)
        _drop_relative_blob_locators(conn)
        _drop_claimed_visit_identity(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version >= 7")
        conn.execute("PRAGMA user_version = 6")

    pending = migration_status(cfg, steps=MIGRATIONS[:7])
    assert pending["current_version"] == 6
    assert pending["pending_versions"] == [7]
    result = migrate_database(cfg, execute=True, steps=MIGRATIONS[:7])
    assert result["applied_versions"] == [7]

    with connect(cfg.db_path) as conn:
        event = conn.execute(
            """
            SELECT visit_id, claimed_visit_id, attachment_method
            FROM visit_events WHERE id = 'event-v7-history'
            """
        ).fetchone()
        assert dict(event) == {
            "visit_id": "visit-v7-history",
            "claimed_visit_id": "visit-v7-history",
            "attachment_method": "historical",
        }
        assert schema_fingerprint(conn) == MIGRATIONS[6].schema_fingerprint
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_version_eight_adds_nullable_relative_locators(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        legacy = _capture(conn, cfg)
        _drop_media_storage_tiers(conn)
        _drop_snapshot_text_authority(conn)
        _drop_relative_blob_locators(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version >= 8")
        conn.execute("PRAGMA user_version = 7")

    pending = migration_status(cfg, steps=MIGRATIONS[:8])
    assert pending["current_version"] == 7
    assert pending["pending_versions"] == [8]
    result = migrate_database(cfg, execute=True, steps=MIGRATIONS[:8])
    assert result["applied_versions"] == [8]

    with connect(cfg.db_path) as conn:
        legacy_row = conn.execute(
            "SELECT cleaned_text_path, cleaned_text_locator FROM snapshots WHERE id = ?",
            (legacy["snapshot_id"],),
        ).fetchone()
        assert dict(legacy_row) == {
            "cleaned_text_path": None,
            "cleaned_text_locator": None,
        }
        media_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(media_artifacts)").fetchall()
        }
        assert "blob_locator" in media_columns
        assert schema_fingerprint(conn) == MIGRATIONS[7].schema_fingerprint
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_version_nine_backfills_hash_verified_chunks_and_new_ingest_uses_sqlite_authority(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        legacy = _capture(conn, cfg)
        _drop_media_storage_tiers(conn)
        _drop_snapshot_text_authority(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version >= 9")
        conn.execute("PRAGMA user_version = 8")

    pending = migration_status(cfg, steps=MIGRATIONS[:9])
    assert pending["current_version"] == 8
    assert pending["pending_versions"] == [9]
    result = migrate_database(cfg, execute=True, steps=MIGRATIONS[:9])
    assert result["applied_versions"] == [9]

    with connect(cfg.db_path) as conn:
        legacy_row = conn.execute(
            "SELECT cleaned_text, cleaned_text_source FROM snapshots WHERE id = ?",
            (legacy["snapshot_id"],),
        ).fetchone()
        assert dict(legacy_row) == {
            "cleaned_text": "Versioned migration preserves searchable full text.",
            "cleaned_text_source": "chunks-hash-verified",
        }
        stored = ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "visit_id": "migration-v9-new-visit",
                    "url": "https://example.com/migration-v9-new",
                    "title": "Migration v9 new write",
                    "text": "New captures commit complete cleaned text to local SQLite.",
                },
                allow_any_url=True,
            ),
        )
        new_row = conn.execute(
            """
            SELECT cleaned_text, cleaned_text_source, cleaned_text_path, cleaned_text_locator
            FROM snapshots WHERE id = ?
            """,
            (stored["snapshot_id"],),
        ).fetchone()
        assert dict(new_row) == {
            "cleaned_text": "New captures commit complete cleaned text to local SQLite.",
            "cleaned_text_source": "capture",
            "cleaned_text_path": None,
            "cleaned_text_locator": None,
        }
        assert schema_fingerprint(conn) == MIGRATIONS[8].schema_fingerprint
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_version_ten_adds_media_storage_tiers_and_spool_reservations(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        capture = _capture(conn, cfg)
        conn.execute(
            """
            INSERT INTO media_artifacts(
              id, document_id, snapshot_id, media_type, role, source_url,
              normalized_source_url, page_url, capture_status, metadata_json
            ) VALUES ('media-v10-legacy', ?, ?, 'image', 'content',
                      'https://cdn.example.com/v10.png', 'https://cdn.example.com/v10.png',
                      'https://example.org/migration', 'referenced', '{}')
            """,
            (capture["document_id"], capture["snapshot_id"]),
        )
        _drop_media_storage_tiers(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version >= 10")
        conn.execute("PRAGMA user_version = 9")

    pending = migration_status(cfg, steps=MIGRATIONS[:10])
    assert pending["pending_versions"] == [10]
    result = migrate_database(cfg, execute=True, steps=MIGRATIONS[:10])
    assert result["applied_versions"] == [10]
    with connect(cfg.db_path) as conn:
        row = conn.execute(
            "SELECT storage_tier, spool_locator FROM media_artifacts WHERE id = 'media-v10-legacy'"
        ).fetchone()
        assert dict(row) == {"storage_tier": "media-root", "spool_locator": None}
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table' AND name = 'media_spool_reservations'"
        ).fetchone()[0] == 1
        reservation_columns = {
            column["name"]: int(column["pk"])
            for column in conn.execute("PRAGMA table_info(media_spool_reservations)").fetchall()
        }
        assert reservation_columns == {
            "reservation_id": 1,
            "artifact_id": 0,
            "reserved_bytes": 0,
            "created_at": 0,
        }
        assert schema_fingerprint(conn) == MIGRATIONS[9].schema_fingerprint
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_version_eleven_adds_and_backfills_blob_lifecycle_records(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        capture = _capture(conn, cfg)
        conn.execute(
            """
            UPDATE snapshots
            SET cleaned_text_path = '/legacy/clean.txt', cleaned_text_locator = 'clean.txt'
            WHERE id = ?
            """,
            (capture["snapshot_id"],),
        )
        conn.execute(
            """
            INSERT INTO media_artifacts(
              id, document_id, snapshot_id, media_type, role, source_url,
              normalized_source_url, page_url, byte_size, content_sha256,
              file_path, blob_locator, storage_tier, capture_status, metadata_json
            ) VALUES ('media-v11-legacy', ?, ?, 'image', 'content',
                      'https://cdn.example.com/v11.png', 'https://cdn.example.com/v11.png',
                      'https://example.org/migration', 12, 'abc', '/legacy/media.bin',
                      'media.bin', 'media-root', 'stored', '{}')
            """,
            (capture["document_id"], capture["snapshot_id"]),
        )
        conn.execute("DROP TABLE blob_storage_records")
        conn.execute("DROP TABLE media_cache_reservations")
        conn.execute("DELETE FROM schema_migrations WHERE version >= 11")
        conn.execute("PRAGMA user_version = 10")

    pending = migration_status(cfg)
    assert pending["pending_versions"] == [11, 12, 13]
    result = migrate_database(cfg, execute=True)
    assert result["applied_versions"] == [11, 12, 13]
    with connect(cfg.db_path) as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT owner_kind, owner_id, storage_tier, locator, state
                FROM blob_storage_records ORDER BY owner_kind
                """
            ).fetchall()
        ]
        assert rows == [
            {
                "owner_kind": "media-artifact",
                "owner_id": "media-v11-legacy",
                "storage_tier": "media-root",
                "locator": "media.bin",
                "state": "committed",
            },
            {
                "owner_kind": "snapshot-derivative",
                "owner_id": capture["snapshot_id"],
                "storage_tier": "derivative",
                "locator": "clean.txt",
                "state": "committed",
            },
        ]
        assert schema_fingerprint(conn) == MIGRATIONS[-1].schema_fingerprint
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


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

    assert first["applied_versions"] == list(range(1, LATEST_SCHEMA_VERSION + 1))
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
    ) == list(range(1, LATEST_SCHEMA_VERSION + 1))
    with connect(cfg.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == LATEST_SCHEMA_VERSION
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
    next_version = LATEST_SCHEMA_VERSION + 1

    def fail_after_write(conn):
        conn.execute("CREATE TABLE should_rollback(id INTEGER PRIMARY KEY)")
        raise RuntimeError("injected migration failure")

    failing = MigrationStep(
        version=next_version,
        name="injected_failure",
        checksum=migration_checksum(next_version, "injected_failure", "fixture-v1"),
        apply=fail_after_write,
    )
    with pytest.raises(MigrationExecutionError, match="injected migration failure"):
        migrate_database(cfg, execute=True, steps=(*MIGRATIONS, failing))

    with connect(cfg.db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA_VERSION
        assert conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (next_version,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table' AND name = 'should_rollback'"
        ).fetchone()[0] == 0


def test_destructive_migration_creates_online_backup_that_restores_search(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    next_version = LATEST_SCHEMA_VERSION + 1
    with connect(cfg.db_path) as conn:
        stored = _capture(conn, cfg)
        conn.commit()

    def fail_destructive_step(conn):
        conn.execute("DELETE FROM chunks_fts")
        raise RuntimeError("destructive fixture failed")

    destructive = MigrationStep(
        version=next_version,
        name="destructive_fixture",
        checksum=migration_checksum(next_version, "destructive_fixture", "fixture-v1"),
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
    next_version = LATEST_SCHEMA_VERSION + 1
    called = False

    def should_not_run(conn):
        nonlocal called
        called = True

    destructive = MigrationStep(
        version=next_version,
        name="headroom_fixture",
        checksum=migration_checksum(next_version, "headroom_fixture", "fixture-v1"),
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
