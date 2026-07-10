from __future__ import annotations

import json
import sqlite3

import pytest
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.media_ops import requeue_media_artifacts
from browser_memory_daemon.models import CapturePayload


def _capture_with_media(conn: sqlite3.Connection, cfg, *, url: str, source_urls: list[str]) -> dict:
    return ingest_capture(
        conn,
        cfg,
        CapturePayload.from_dict(
            {
                "url": url,
                "title": "Media requeue fixture",
                "text": "Scoped media requeue fixture text.",
                "media_artifacts": [
                    {"media_type": "image", "source_url": source_url}
                    for source_url in source_urls
                ],
            },
            allow_any_url=True,
        ),
    )


def test_media_requeue_is_scoped_and_dry_run_first(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        selected = _capture_with_media(
            conn,
            cfg,
            url="https://selected.example/page",
            source_urls=["https://cdn.example/a.png", "https://cdn.example/b.png"],
        )
        _capture_with_media(
            conn,
            cfg,
            url="https://other.example/page",
            source_urls=["https://cdn.example/other.png"],
        )
        rows = conn.execute(
            "SELECT id FROM media_artifacts WHERE snapshot_id = ? ORDER BY id",
            (selected["snapshot_id"],),
        ).fetchall()
        conn.execute(
            "UPDATE media_artifacts SET capture_status = 'skipped', status_reason = 'snapshot-media-budget' WHERE id = ?",
            (rows[0]["id"],),
        )
        conn.execute(
            "UPDATE media_artifacts SET capture_status = 'skipped', status_reason = 'domain-media-budget' WHERE id = ?",
            (rows[1]["id"],),
        )
        conn.execute(
            "UPDATE media_fetch_tasks SET status = 'skipped', attempts = 4, last_error = 'budget' WHERE artifact_id IN (?, ?)",
            (rows[0]["id"], rows[1]["id"]),
        )
        conn.execute(
            "UPDATE media_artifacts SET capture_status = 'skipped', status_reason = 'media-cache-budget' WHERE snapshot_id != ?",
            (selected["snapshot_id"],),
        )
        conn.commit()

        preview = requeue_media_artifacts(
            conn,
            reason="all-budget",
            snapshot_id=selected["snapshot_id"],
            limit=10,
            execute=False,
        )
        assert preview["dry_run"] is True
        assert preview["selected"] == 2
        assert preview["updated"] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM media_artifacts WHERE snapshot_id = ? AND capture_status = 'skipped'",
            (selected["snapshot_id"],),
        ).fetchone()[0] == 2

        applied = requeue_media_artifacts(
            conn,
            reason="all-budget",
            snapshot_id=selected["snapshot_id"],
            limit=10,
            execute=True,
        )
        assert applied["dry_run"] is False
        assert applied["selected"] == applied["updated"] == 2
        refreshed = conn.execute(
            "SELECT capture_status, status_reason FROM media_artifacts WHERE snapshot_id = ?",
            (selected["snapshot_id"],),
        ).fetchall()
        assert {tuple(row) for row in refreshed} == {("referenced", None)}
        tasks = conn.execute(
            "SELECT status, attempts, last_error FROM media_fetch_tasks WHERE artifact_id IN (?, ?)",
            (rows[0]["id"], rows[1]["id"]),
        ).fetchall()
        assert {tuple(row) for row in tasks} == {("pending", 0, None)}
        event = conn.execute(
            "SELECT event_type, metadata_json FROM audit_events WHERE event_type = 'media-budget-requeue'"
        ).fetchone()
        assert event["event_type"] == "media-budget-requeue"
        assert json.loads(event["metadata_json"]) == {
            "limit": 10,
            "reason": "all-budget",
            "scope_kinds": ["snapshot_id"],
            "selected": 2,
            "updated": 2,
        }
        assert "example.com" not in event["metadata_json"]
        assert conn.execute(
            "SELECT COUNT(*) FROM media_artifacts WHERE snapshot_id != ? AND capture_status = 'skipped'",
            (selected["snapshot_id"],),
        ).fetchone()[0] == 1


def test_media_requeue_requires_explicit_scope(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        with pytest.raises(ValueError, match="scope"):
            requeue_media_artifacts(conn, reason="all-budget", execute=False)
