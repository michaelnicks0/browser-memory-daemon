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


def test_overlapping_lifecycle_events_do_not_double_count_dwell(tmp_path):
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
        first = record_visit_event(
            conn,
            {
                "event_id": "event-overlap-1",
                "visit_id": "visit-overlap-1",
                "url": "https://example.org/overlap",
                "event_type": "tab-deactivated",
                "event_started_at": "2026-06-08T12:00:00Z",
                "event_ended_at": "2026-06-08T12:00:10Z",
                "active_seconds": 10,
            },
        )
        second = record_visit_event(
            conn,
            {
                "event_id": "event-overlap-2",
                "visit_id": "visit-overlap-1",
                "url": "https://example.org/overlap",
                "event_type": "window-blurred",
                "event_started_at": "2026-06-08T12:00:00Z",
                "event_ended_at": "2026-06-08T12:00:11Z",
                "active_seconds": 11,
            },
        )
        visit = conn.execute("SELECT dwell_seconds FROM visits WHERE id = ?", ("visit-overlap-1",)).fetchone()
        assert first["dwell_updated"] is True
        assert second["stored"] is True
        assert second["dwell_updated"] is False
        assert visit["dwell_seconds"] == 10


def test_visit_lifecycle_event_can_attach_to_latest_visit_by_url(tmp_path):
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
                "event_ended_at": "2026-06-08T12:03:00Z",
                "active_seconds": 12,
            },
        )
        assert result["stored"] is True
        assert result["visit_id"] == "visit-lifecycle-url"
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
