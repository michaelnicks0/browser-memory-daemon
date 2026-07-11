from __future__ import annotations

from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.migrations import LATEST_SCHEMA_VERSION, migrate_database
from browser_memory_daemon.models import CapturePayload


def _config(tmp_path):
    return load_config(
        runtime_root=tmp_path / "runtime",
        blob_root=tmp_path / "blobs",
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )


def _payload(observation_id: str, captured_at: str, url: str) -> CapturePayload:
    return CapturePayload.from_dict(
        {
            "observation_id": observation_id,
            "navigation_id": "nav-fixture",
            "visit_id": f"visit-{observation_id}",
            "url": url,
            "title": "Fixture",
            "text": f"Fixture text for {observation_id}",
            "captured_at": captured_at,
        },
        allow_any_url=True,
    )


def test_ingest_sequence_is_monotonic_idempotent_and_independent_of_capture_time(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)

    with connect(cfg.db_path) as conn:
        first = _payload("browser-observation-a", "2026-07-11T10:00:00Z", "https://x.com/alice/status/111")
        late = _payload("browser-observation-b", "2026-07-10T10:00:00Z", "https://x.com/bob/status/222")

        first_result = ingest_capture(conn, cfg, first)
        conn.commit()
        retry_result = ingest_capture(conn, cfg, first)
        conn.commit()
        late_result = ingest_capture(conn, cfg, late)
        conn.commit()

        rows = conn.execute(
            "SELECT sequence, observation_id FROM observation_ingest_sequences ORDER BY sequence"
        ).fetchall()

    assert first_result["observation_id"] == retry_result["observation_id"]
    assert [row["observation_id"] for row in rows] == [first_result["observation_id"], late_result["observation_id"]]
    assert [row["sequence"] for row in rows] == [1, 2]


def test_migration_backfills_existing_observations_deterministically(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)

    with connect(cfg.db_path) as conn:
        for payload in [
            _payload("browser-observation-z", "2026-07-11T00:00:00Z", "https://x.com/z/status/999"),
            _payload("browser-observation-a", "2026-07-11T00:00:00Z", "https://x.com/a/status/111"),
        ]:
            ingest_capture(conn, cfg, payload)
        conn.execute("UPDATE capture_observations SET created_at = '2026-07-11 00:00:00'")
        conn.execute("DROP TABLE observation_ingest_sequences")
        conn.execute("DELETE FROM schema_migrations WHERE version = ?", (LATEST_SCHEMA_VERSION,))
        conn.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION - 1}")
        conn.commit()

    result = migrate_database(cfg, execute=True)

    assert result["applied_versions"] == [LATEST_SCHEMA_VERSION]
    with connect(cfg.db_path) as conn:
        rows = conn.execute(
            "SELECT sequence, observation_id FROM observation_ingest_sequences ORDER BY sequence"
        ).fetchall()
        expected_ids = sorted(row["observation_id"] for row in rows)
    assert [row["observation_id"] for row in rows] == expected_ids
    assert [row["sequence"] for row in rows] == [1, 2]
