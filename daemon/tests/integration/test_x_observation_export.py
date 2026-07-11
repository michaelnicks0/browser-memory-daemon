from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.x_observation_export import (
    XObservationCompatibilityError,
    XObservationCursorError,
    decode_cursor,
    export_x_observations,
)


def _config(tmp_path):
    return load_config(
        runtime_root=tmp_path / "runtime",
        blob_root=tmp_path / "blobs",
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )


def _capture(conn, cfg, *, observation_id: str, url: str, text: str, captured_at: str):
    return ingest_capture(
        conn,
        cfg,
        CapturePayload.from_dict(
            {
                "observation_id": observation_id,
                "navigation_id": f"nav-{observation_id}",
                "visit_id": f"visit-{observation_id}",
                "url": url,
                "title": f"Title secret {observation_id}",
                "text": text,
                "captured_at": captured_at,
                "capture_reason": "navigation-settled",
                "extraction_method": "dom-text",
                "extraction_version": "fixture-v1",
            },
            allow_any_url=True,
        ),
    )


def _logical_state(cfg):
    with connect(cfg.db_path) as conn:
        return {
            "audit": conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0],
            "observations": conn.execute("SELECT COUNT(*) FROM capture_observations").fetchone()[0],
            "sequences": conn.execute("SELECT COUNT(*) FROM observation_ingest_sequences").fetchone()[0],
            "changes": conn.total_changes,
        }


def _file_hashes(cfg):
    paths = [cfg.db_path, cfg.db_path.with_name(cfg.db_path.name + "-wal")]
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.exists()
    }


def test_export_is_query_only_body_safe_and_losslessly_pages_late_delivery(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        first = _capture(
            conn,
            cfg,
            observation_id="browser-export-a",
            url="https://x.com/alice/status/111?utm_source=fixture",
            text="SECRET-FIRST-BODY",
            captured_at="2026-07-11T10:00:00Z",
        )
        _capture(
            conn,
            cfg,
            observation_id="browser-export-hold",
            url="https://example.com/no-x",
            text="SECRET-NON-X-BODY",
            captured_at="2026-07-11T11:00:00Z",
        )
        late = _capture(
            conn,
            cfg,
            observation_id="browser-export-b",
            url="https://example.com/container",
            text="Late mention https://twitter.com/bob/status/222 and SECRET-LATE-BODY",
            captured_at="2026-07-10T10:00:00Z",
        )
        conn.commit()

    before_state = _logical_state(cfg)
    before_hashes = _file_hashes(cfg)

    def frozen():
        return datetime(2026, 7, 11, 12, 0, tzinfo=UTC)

    page_one = export_x_observations(cfg.db_path, limit=1, now=frozen, build_revision="fixture")
    page_two = export_x_observations(
        cfg.db_path,
        cursor=page_one["next_cursor"],
        limit=10,
        now=frozen,
        build_revision="fixture",
    )

    assert [row["observation_id"] for row in page_one["records"]] == [first["observation_id"]]
    assert [row["observation_id"] for row in page_two["records"]] == [late["observation_id"]]
    assert page_two["holds"]["without_discovered_x_url"] == 1
    assert page_two["exhausted"] is True
    assert decode_cursor(page_two["next_cursor"])[0] > decode_cursor(page_one["next_cursor"])[0]
    record = page_one["records"][0]
    assert record["discovered_x_urls"] == [
        {
            "url": "https://x.com/alice/status/111",
            "kind": "status",
            "status_id": "111",
            "handle_hint": "alice",
            "discovery_source": "observed_url",
            "provenance_quality": "observed",
        }
    ]
    assert record["identity_hints"][0]["quality"] == "alias_only"
    assert record["collection_evidence"]["classification"] == "none"
    assert record["text"]["body_included"] is False
    serialized = json.dumps([page_one, page_two], sort_keys=True)
    for secret in ["SECRET-FIRST-BODY", "SECRET-NON-X-BODY", "SECRET-LATE-BODY", "Title secret"]:
        assert secret not in serialized
    assert _logical_state(cfg) == before_state
    assert _file_hashes(cfg) == before_hashes


def test_export_cursor_survives_deleted_sequence_gap_and_replay_is_stable(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        first = _capture(
            conn,
            cfg,
            observation_id="browser-delete-a",
            url="https://x.com/a/status/101",
            text="first",
            captured_at="2026-07-11T00:00:00Z",
        )
        second = _capture(
            conn,
            cfg,
            observation_id="browser-delete-b",
            url="https://x.com/b/status/202",
            text="second",
            captured_at="2026-07-11T00:00:00Z",
        )
        conn.commit()

    def frozen():
        return datetime(2026, 7, 11, 12, 0, tzinfo=UTC)

    first_page = export_x_observations(cfg.db_path, limit=1, now=frozen)
    replay = export_x_observations(cfg.db_path, limit=1, now=frozen)
    assert replay == first_page
    assert first_page["records"][0]["observation_id"] == first["observation_id"]

    with connect(cfg.db_path) as conn:
        conn.execute("DELETE FROM capture_observations WHERE id = ?", (first["observation_id"],))
        conn.commit()

    next_page = export_x_observations(cfg.db_path, cursor=first_page["next_cursor"], limit=10, now=frozen)
    assert [row["observation_id"] for row in next_page["records"]] == [second["observation_id"]]
    assert next_page["exhausted"] is True


def test_export_fails_closed_for_malformed_cursor_and_schema_drift(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)

    with pytest.raises(XObservationCursorError):
        export_x_observations(cfg.db_path, cursor="not-a-valid-cursor")

    with connect(cfg.db_path) as conn:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.execute(f"PRAGMA user_version = {current - 1}")
    with pytest.raises(XObservationCompatibilityError, match="older"):
        export_x_observations(cfg.db_path)

    with connect(cfg.db_path) as conn:
        conn.execute(f"PRAGMA user_version = {current + 1}")
    with pytest.raises(XObservationCompatibilityError, match="newer"):
        export_x_observations(cfg.db_path)


def test_producer_golden_fixture_matches_current_contract_output(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        stored = ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "observation_id": "browser-golden-v1",
                    "navigation_id": "nav-golden-v1",
                    "visit_id": "visit-golden-v1",
                    "url": "https://x.com/alice/status/111?utm_source=fixture",
                    "title": "Golden fixture title",
                    "text": "Golden fixture body https://twitter.com/bob/status/222",
                    "captured_at": "2026-07-11T10:00:00Z",
                    "capture_reason": "navigation-settled",
                    "extraction_method": "dom-text",
                    "extraction_version": "fixture-v1",
                },
                allow_any_url=True,
            ),
        )
        assert stored["stored"] is True
        conn.commit()

    def frozen():
        return datetime(2026, 7, 11, 12, 0, tzinfo=UTC)

    actual = export_x_observations(
        cfg.db_path,
        limit=100,
        now=frozen,
        build_revision="fixture",
    )
    fixture = Path(__file__).parents[1] / "fixtures" / "x_observations" / "v1-page.json"
    assert actual == json.loads(fixture.read_text(encoding="utf-8"))
