import pytest
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.lifecycle import record_visit_event
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.ops import document_detail


def test_visit_lifecycle_event_updates_dwell_and_is_idempotent(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        capture = CapturePayload.from_dict(
            {
                "visit_id": "visit-lifecycle-1",
                "url": "https://example.org/lifecycle",
                "title": "Lifecycle Fixture",
                "text": "Readable lifecycle text that will have dwell time attached.",
                "captured_at": "2026-06-08T12:00:00Z",
                "visit_started_at": "2026-06-08T12:00:00Z",
            }
        )
        stored = ingest_capture(conn, cfg, capture)

        first = record_visit_event(
            conn,
            {
                "event_id": "event-lifecycle-1",
                "visit_id": "visit-lifecycle-1",
                "url": "https://example.org/lifecycle",
                "event_type": "tab-deactivated",
                "event_started_at": "2026-06-08T12:00:05Z",
                "event_ended_at": "2026-06-08T12:00:42Z",
                "active_seconds": 37,
                "max_scroll_percent": 83,
            },
        )
        duplicate = record_visit_event(
            conn,
            {
                "event_id": "event-lifecycle-1",
                "visit_id": "visit-lifecycle-1",
                "url": "https://example.org/lifecycle",
                "event_type": "tab-deactivated",
                "event_started_at": "2026-06-08T12:00:05Z",
                "event_ended_at": "2026-06-08T12:00:42Z",
                "active_seconds": 37,
                "max_scroll_percent": 83,
            },
        )

        assert first["stored"] is True
        assert first["dwell_updated"] is True
        assert duplicate["stored"] is False
        assert duplicate["dwell_updated"] is False

        visit = conn.execute("SELECT dwell_seconds FROM visits WHERE id = ?", ("visit-lifecycle-1",)).fetchone()
        assert visit["dwell_seconds"] == 37
        events = conn.execute("SELECT COUNT(*) AS n FROM visit_events").fetchone()
        assert events["n"] == 1

        detail = document_detail(conn, cfg, stored["document_id"])
        assert detail["visits"][0]["dwell_seconds"] == 37
        assert detail["visit_events"][0]["max_scroll_percent"] == 83


def test_lifecycle_dwell_uses_interval_union_for_overlap_containment_adjacency_and_out_of_order(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "visit_id": "visit-overlap-1",
                    "url": "https://example.org/overlap",
                    "title": "Overlap Fixture",
                    "text": "Readable lifecycle overlap text that should count one active segment.",
                }
            ),
        )
        intervals = [
            ("event-overlap-1", "2026-06-08T12:00:00Z", "2026-06-08T12:00:10Z", 10, 10),
            ("event-overlap-2", "2026-06-08T12:00:05Z", "2026-06-08T12:00:15Z", 10, 15),
            ("event-contained", "2026-06-08T12:00:06Z", "2026-06-08T12:00:08Z", 2, 15),
            ("event-adjacent", "2026-06-08T12:00:15Z", "2026-06-08T12:00:20Z", 5, 20),
            ("event-out-of-order", "2026-06-08T12:00:30Z", "2026-06-08T12:00:40Z", 10, 30),
            ("event-bridge", "2026-06-08T12:00:18Z", "2026-06-08T12:00:32Z", 14, 40),
        ]
        observed_dwell = []
        for event_id, started_at, ended_at, active_seconds, expected_dwell in intervals:
            result = record_visit_event(
                conn,
                {
                    "event_id": event_id,
                    "visit_id": "visit-overlap-1",
                    "url": "https://example.org/overlap",
                    "event_type": "active-segment",
                    "event_started_at": started_at,
                    "event_ended_at": ended_at,
                    "active_seconds": active_seconds,
                },
            )
            observed_dwell.append(result["dwell_seconds"])
            assert result["attachment_method"] == "visit-id"
            assert result["dwell_seconds"] == expected_dwell

        visit = conn.execute(
            "SELECT dwell_seconds FROM visits WHERE id = ?", ("visit-overlap-1",)
        ).fetchone()
        assert observed_dwell == [10, 15, 15, 20, 30, 40]
        assert visit["dwell_seconds"] == 40


def test_legacy_visit_lifecycle_event_without_visit_id_can_attach_by_url(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "visit_id": "visit-lifecycle-url",
                    "url": "https://example.org/lifecycle-by-url?utm_source=test",
                    "title": "Lifecycle URL Fixture",
                    "text": "Readable lifecycle URL text that is used for URL event matching.",
                    "captured_at": "2026-06-08T12:00:00Z",
                }
            ),
        )
        result = record_visit_event(
            conn,
            {
                "event_id": "event-lifecycle-url",
                "url": "https://example.org/lifecycle-by-url",
                "event_type": "tab-closed",
                "event_started_at": "2026-06-08T12:02:48Z",
                "event_ended_at": "2026-06-08T12:03:00Z",
                "active_seconds": 12,
            },
        )
        assert result["stored"] is True
        assert result["visit_id"] == "visit-lifecycle-url"
        assert result["attachment_method"] == "legacy-url-fallback"
        assert result["dwell_updated"] is True


def test_visit_lifecycle_event_without_matching_visit_stores_metadata_only(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        result = record_visit_event(
            conn,
            {
                "event_id": "event-orphan-navigation",
                "visit_id": "visit-not-yet-captured",
                "url": "https://example.org/not-captured-yet",
                "event_type": "navigation-away",
                "event_ended_at": "2026-06-08T12:00:00Z",
                "active_seconds": 0,
            },
        )
        assert result["stored"] is True
        assert result["dwell_updated"] is False
        row = conn.execute("SELECT visit_id, normalized_url FROM visit_events WHERE id = ?", ("event-orphan-navigation",)).fetchone()
        assert row["visit_id"] is None
        assert row["normalized_url"] == "https://example.org/not-captured-yet"


def test_claimed_visit_identity_does_not_fall_back_by_url_and_reconciles_after_delayed_capture(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "visit_id": "visit-existing-tab",
                    "url": "https://example.org/concurrent-tabs",
                    "title": "Existing tab",
                    "text": "Readable content from an existing same URL tab.",
                }
            ),
        )

        mismatched_url = record_visit_event(
            conn,
            {
                "event_id": "event-existing-id-wrong-url",
                "visit_id": "visit-existing-tab",
                "url": "https://example.org/other-navigation",
                "event_type": "active-segment",
                "event_started_at": "2026-06-08T11:59:00Z",
                "event_ended_at": "2026-06-08T11:59:01Z",
                "active_seconds": 1,
            },
        )
        assert mismatched_url["visit_id"] is None
        assert mismatched_url["attachment_method"] == "unmatched"

        before_capture = record_visit_event(
            conn,
            {
                "event_id": "event-delayed-visit",
                "visit_id": "visit-delayed-tab",
                "url": "https://example.org/concurrent-tabs",
                "event_type": "active-segment",
                "event_started_at": "2026-06-08T12:00:00Z",
                "event_ended_at": "2026-06-08T12:00:10Z",
                "active_seconds": 10,
            },
        )
        assert before_capture["visit_id"] is None
        assert before_capture["claimed_visit_id"] == "visit-delayed-tab"
        assert before_capture["attachment_method"] == "unmatched"
        existing = conn.execute(
            "SELECT dwell_seconds FROM visits WHERE id = 'visit-existing-tab'"
        ).fetchone()
        assert existing["dwell_seconds"] in {None, 0}

        delayed = ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "visit_id": "visit-delayed-tab",
                    "url": "https://example.org/concurrent-tabs",
                    "title": "Delayed tab",
                    "text": "Readable content from the delayed same URL tab.",
                }
            ),
        )
        linked = conn.execute(
            """
            SELECT visit_id, document_id, claimed_visit_id, attachment_method
            FROM visit_events WHERE id = 'event-delayed-visit'
            """
        ).fetchone()
        assert dict(linked) == {
            "visit_id": "visit-delayed-tab",
            "document_id": delayed["document_id"],
            "claimed_visit_id": "visit-delayed-tab",
            "attachment_method": "visit-id-delayed",
        }
        delayed_visit = conn.execute(
            "SELECT dwell_seconds FROM visits WHERE id = 'visit-delayed-tab'"
        ).fetchone()
        assert delayed_visit["dwell_seconds"] == 10

        after_capture = record_visit_event(
            conn,
            {
                "event_id": "event-delayed-visit-after",
                "visit_id": "visit-delayed-tab",
                "url": "https://example.org/concurrent-tabs",
                "event_type": "active-segment",
                "event_started_at": "2026-06-08T12:00:08Z",
                "event_ended_at": "2026-06-08T12:00:15Z",
                "active_seconds": 7,
            },
        )
        assert after_capture["visit_id"] == "visit-delayed-tab"
        assert after_capture["attachment_method"] == "visit-id"
        assert after_capture["dwell_seconds"] == 15


def test_visit_lifecycle_event_validates_ranges(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        try:
            record_visit_event(
                conn,
                {
                    "url": "https://example.org/lifecycle",
                    "event_type": "tab-deactivated",
                    "event_ended_at": "2026-06-08T12:00:00Z",
                    "active_seconds": -1,
                },
            )
            raise AssertionError("negative dwell should fail")
        except ValueError as exc:
            assert "active_seconds" in str(exc)

        try:
            record_visit_event(
                conn,
                {
                    "url": "https://example.org/lifecycle",
                    "event_type": "tab-deactivated",
                    "event_ended_at": "2026-06-08T12:00:00Z",
                    "max_scroll_percent": 101,
                },
            )
            raise AssertionError("scroll > 100 should fail")
        except ValueError as exc:
            assert "max_scroll_percent" in str(exc)

        invalid_intervals = [
            (
                {
                    "event_started_at": "2026-06-08T12:00:10Z",
                    "event_ended_at": "2026-06-08T12:00:00Z",
                    "active_seconds": 10,
                },
                "event_ended_at",
            ),
            (
                {
                    "event_ended_at": "2026-06-08T12:00:10Z",
                    "active_seconds": 10,
                },
                "event_started_at",
            ),
            (
                {
                    "event_started_at": "2026-06-08T12:00:00Z",
                    "event_ended_at": "2026-06-08T12:00:10Z",
                    "active_seconds": 25,
                },
                "active_seconds",
            ),
            (
                {
                    "event_started_at": "2026-06-08T12:00:00",
                    "event_ended_at": "2026-06-08T12:00:10",
                    "active_seconds": 10,
                },
                "timezone",
            ),
        ]
        for index, (interval, expected_error) in enumerate(invalid_intervals):
            with pytest.raises(ValueError, match=expected_error):
                record_visit_event(
                    conn,
                    {
                        "event_id": f"invalid-interval-{index}",
                        "visit_id": "visit-validation",
                        "url": "https://example.org/lifecycle",
                        "event_type": "active-segment",
                        **interval,
                    },
                )
