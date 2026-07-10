from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.ops import document_detail, recent_captures, snapshot_detail, timeline


def _config(tmp_path):
    return load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")


def _payload(*, observation_id: str, captured_at: str, text: str, title: str, media_url: str | None = None):
    media_artifacts = []
    if media_url:
        media_artifacts.append(
            {
                "media_type": "image",
                "role": "content",
                "source_url": media_url,
            }
        )
    return CapturePayload.from_dict(
        {
            "url": "https://example.test/activity",
            "canonical_url": "https://canonical.other.test/activity",
            "title": title,
            "text": text,
            "visit_id": "visit-activity",
            "navigation_id": "navigation-activity",
            "observation_id": observation_id,
            "captured_at": captured_at,
            "capture_reason": "test",
            "capture_method": "fixture",
            "extraction_version": "fixture-v1",
            "media_artifacts": media_artifacts,
        }
    )


def test_observation_first_reads_preserve_contemporaneous_snapshots_and_unique_visit_summary(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    payloads = [
        _payload(
            observation_id="observation-read-1",
            captured_at="2026-06-08T12:00:00Z",
            text="UNCHANGED_OBSERVATION_TEXT",
            title="First observation",
            media_url="https://cdn.example.test/first.png",
        ),
        _payload(
            observation_id="observation-read-2",
            captured_at="2026-06-08T12:05:00Z",
            text="UNCHANGED_OBSERVATION_TEXT",
            title="Second observation",
            media_url="https://cdn.example.test/second.png",
        ),
        _payload(
            observation_id="observation-read-3",
            captured_at="2026-06-08T12:10:00Z",
            text="UNCHANGED_OBSERVATION_TEXT",
            title="Third observation",
        ),
        _payload(
            observation_id="observation-read-4",
            captured_at="2026-06-08T12:15:00Z",
            text="CHANGED_OBSERVATION_TEXT",
            title="Changed observation",
        ),
    ]

    with connect(cfg.db_path) as conn:
        results = [ingest_capture(conn, cfg, payload) for payload in payloads]
        conn.execute("UPDATE visits SET dwell_seconds = 12 WHERE id = 'visit-activity'")
        conn.execute(
            """
            INSERT INTO visit_events(
              id, visit_id, document_id, source_id, url, normalized_url,
              event_type, event_ended_at, active_seconds, max_scroll_percent
            ) VALUES (
              'event-activity-scroll', 'visit-activity', ?, 'chrome-extension',
              'https://example.test/activity', 'https://example.test/activity',
              'heartbeat', '2026-06-08T12:15:00Z', 12, 64
            )
            """,
            (results[0]["document_id"],),
        )

        recent = recent_captures(conn, limit=10)
        day = timeline(conn, day="2026-06-08", limit=10)
        document = document_detail(conn, cfg, results[0]["document_id"])
        unchanged_snapshot = snapshot_detail(conn, cfg, results[0]["snapshot_id"])
        changed_snapshot = snapshot_detail(conn, cfg, results[3]["snapshot_id"])

    assert [item["observation_id"] for item in recent] == [
        results[3]["observation_id"],
        results[2]["observation_id"],
        results[1]["observation_id"],
        results[0]["observation_id"],
    ]
    assert [item["title"] for item in recent] == [
        "Changed observation",
        "Third observation",
        "Second observation",
        "First observation",
    ]
    assert [item["record_source"] for item in recent] == ["observation"] * 4
    assert [item["snapshot_id"] for item in recent[1:]] == [results[0]["snapshot_id"]] * 3
    assert recent[0]["snapshot_id"] == results[3]["snapshot_id"]
    assert recent[0]["snippet"] == "CHANGED_OBSERVATION_TEXT"
    assert recent[1]["snippet"] == "UNCHANGED_OBSERVATION_TEXT"
    assert [item["media_artifact_count"] for item in recent] == [0, 0, 1, 1]

    assert day["summary"] == {
        "visits": 1,
        "observations": 4,
        "captures": 4,
        "total_dwell_seconds": 12,
        "max_scroll_percent": 64,
        "media_artifacts": 2,
    }
    assert [item["observation_id"] for item in document["observations"]] == [
        results[3]["observation_id"],
        results[2]["observation_id"],
        results[1]["observation_id"],
        results[0]["observation_id"],
    ]
    assert document["url_claims"][0]["claimed_url"] == "https://canonical.other.test/activity"
    assert [item["observation_id"] for item in unchanged_snapshot["observations"]] == [
        results[2]["observation_id"],
        results[1]["observation_id"],
        results[0]["observation_id"],
    ]
    assert [item["observation_id"] for item in changed_snapshot["observations"]] == [
        results[3]["observation_id"]
    ]
    assert {
        item["source_url"]: [link["observation_id"] for link in item["observations"]]
        for item in unchanged_snapshot["media_artifacts"]
    } == {
        "https://cdn.example.test/first.png": [results[0]["observation_id"]],
        "https://cdn.example.test/second.png": [results[1]["observation_id"]],
    }


def test_legacy_visit_fallback_is_explicit_and_uses_its_linked_snapshot_not_latest_document_snapshot(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    current = _payload(
        observation_id="observation-current",
        captured_at="2026-06-09T12:00:00Z",
        text="CURRENT_OBSERVATION_TEXT",
        title="Current observation",
    )

    with connect(cfg.db_path) as conn:
        current_result = ingest_capture(conn, cfg, current)
        conn.execute(
            """
            INSERT INTO visits(
              id, document_id, source_id, url, normalized_url, title,
              source_device, browser_profile, captured_at, dwell_seconds,
              is_incognito, blocked
            ) VALUES (
              'visit-legacy-read', ?, 'chrome-extension',
              'https://example.test/activity', 'https://example.test/activity', 'Legacy visit',
              'legacy-device', 'Legacy', '2026-06-09T10:00:00Z', 7, 0, 0
            )
            """,
            (current_result["document_id"],),
        )
        conn.execute(
            """
            INSERT INTO snapshots(
              id, document_id, visit_id, captured_at, content_type, extraction_method,
              text_hash, cleaned_text_path, privacy_class, redaction_count
            ) VALUES (
              'snapshot-legacy-read', ?, 'visit-legacy-read', '2026-06-09T10:00:00Z',
              'text/plain', 'legacy-v1', 'legacy-read-hash', '/legacy/read.txt', 'legacy', 0
            )
            """,
            (current_result["document_id"],),
        )
        conn.execute(
            """
            INSERT INTO chunks(id, snapshot_id, document_id, chunk_index, text, title, url)
            VALUES (
              'chunk-legacy-read', 'snapshot-legacy-read', ?, 0,
              'LEGACY_LINKED_SNAPSHOT_TEXT', 'Legacy visit', 'https://example.test/activity'
            )
            """,
            (current_result["document_id"],),
        )

        recent = recent_captures(conn, limit=10)
        day = timeline(conn, day="2026-06-09", limit=10)

    legacy = next(item for item in recent if item["record_source"] == "legacy-visit")
    assert legacy["observation_id"] is None
    assert legacy["provenance_quality"] == "ambiguous"
    assert legacy["snapshot_id"] == "snapshot-legacy-read"
    assert legacy["snapshot_id"] != current_result["snapshot_id"]
    assert legacy["snippet"] == "LEGACY_LINKED_SNAPSHOT_TEXT"
    assert day["summary"]["visits"] == 2
    assert day["summary"]["observations"] == 1
    assert day["summary"]["captures"] == 2
    assert day["summary"]["total_dwell_seconds"] == 7
