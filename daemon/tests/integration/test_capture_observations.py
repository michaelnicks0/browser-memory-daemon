import pytest
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.lifecycle import record_visit_event
from browser_memory_daemon.media import media_artifacts_for_snapshot
from browser_memory_daemon.models import CapturePayload


def _config(tmp_path):
    return load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )


def _payload(**overrides):
    data = {
        "visit_id": "visit-observation-1",
        "navigation_id": "navigation-observation-1",
        "observation_id": "observation-1",
        "url": "https://example.test/article",
        "title": "Observation Article",
        "text": "Stable observation text.",
        "captured_at": "2026-06-08T12:00:00Z",
        "capture_reason": "initial",
        "extraction_method": "dom-visible-text",
        "extraction_version": "extractor-v2",
    }
    data.update(overrides)
    return CapturePayload.from_dict(data)


def test_same_visit_records_multiple_unchanged_observations_without_replacing_visit(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    first = _payload()
    second = _payload(
        observation_id="observation-2",
        captured_at="2026-06-08T12:05:00Z",
        capture_reason="delayed",
        title="Observation Article Updated",
    )

    with connect(cfg.db_path) as conn:
        first_result = ingest_capture(conn, cfg, first)
        second_result = ingest_capture(conn, cfg, second)
        counts = dict(
            conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM visits) AS visits,
                  (SELECT COUNT(*) FROM capture_observations) AS observations,
                  (SELECT COUNT(*) FROM snapshots) AS snapshots
                """
            ).fetchone()
        )
        rows = conn.execute(
            """
            SELECT id, visit_id, snapshot_id, capture_reason, capture_method,
                   extraction_version, disposition, provenance_quality
            FROM capture_observations
            ORDER BY captured_at
            """
        ).fetchall()
        visit = conn.execute(
            "SELECT id, document_id, captured_at, title FROM visits WHERE id = ?",
            (first.visit_id,),
        ).fetchone()

    assert counts == {"visits": 1, "observations": 2, "snapshots": 1}
    assert first_result["snapshot_id"] == second_result["snapshot_id"]
    assert first_result["observation_id"] != second_result["observation_id"]
    assert [row["disposition"] for row in rows] == ["accepted", "duplicate"]
    assert [row["capture_reason"] for row in rows] == ["initial", "delayed"]
    assert all(row["capture_method"] == "dom-visible-text" for row in rows)
    assert all(row["extraction_version"] == "extractor-v2" for row in rows)
    assert all(row["provenance_quality"] == "observed" for row in rows)
    assert visit["document_id"] == first_result["document_id"]
    assert visit["captured_at"] == "2026-06-08T12:05:00Z"
    assert visit["title"] == "Observation Article Updated"


def test_same_visit_changed_content_links_each_observation_to_contemporaneous_snapshot(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    first = _payload()
    second = _payload(
        observation_id="observation-2",
        captured_at="2026-06-08T12:05:00Z",
        text="Changed observation text.",
        capture_reason="mutation",
    )

    with connect(cfg.db_path) as conn:
        first_result = ingest_capture(conn, cfg, first)
        second_result = ingest_capture(conn, cfg, second)
        observations = conn.execute(
            "SELECT snapshot_id FROM capture_observations ORDER BY captured_at"
        ).fetchall()

    assert first_result["snapshot_id"] != second_result["snapshot_id"]
    assert [row["snapshot_id"] for row in observations] == [
        first_result["snapshot_id"],
        second_result["snapshot_id"],
    ]


def test_multiple_visits_can_observe_one_deduplicated_snapshot(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    first = _payload()
    second = _payload(
        visit_id="visit-observation-2",
        navigation_id="navigation-observation-2",
        observation_id="observation-2",
        captured_at="2026-06-08T13:00:00Z",
    )

    with connect(cfg.db_path) as conn:
        first_result = ingest_capture(conn, cfg, first)
        second_result = ingest_capture(conn, cfg, second)
        observations = conn.execute(
            "SELECT visit_id, snapshot_id FROM capture_observations ORDER BY captured_at"
        ).fetchall()
        snapshot_visit_id = conn.execute(
            "SELECT visit_id FROM snapshots WHERE id = ?",
            (first_result["snapshot_id"],),
        ).fetchone()[0]

    assert first_result["snapshot_id"] == second_result["snapshot_id"]
    assert [dict(row) for row in observations] == [
        {"visit_id": first.visit_id, "snapshot_id": first_result["snapshot_id"]},
        {"visit_id": second.visit_id, "snapshot_id": first_result["snapshot_id"]},
    ]
    assert snapshot_visit_id == first.visit_id


def test_out_of_order_observations_preserve_temporal_bounds_and_latest_claim_provenance(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    later = _payload(
        title="Later title",
        canonical_url="https://canonical.example.test/article",
        captured_at="2026-06-08T14:00:00Z",
        visit_started_at="2026-06-08T13:55:00Z",
    )
    earlier = _payload(
        observation_id="observation-earlier",
        title="Earlier title",
        canonical_url="https://canonical.example.test/article",
        captured_at="2026-06-08T12:00:00Z",
        visit_started_at="2026-06-08T11:55:00Z",
    )

    with connect(cfg.db_path) as conn:
        later_result = ingest_capture(conn, cfg, later)
        ingest_capture(conn, cfg, earlier)
        document = dict(
            conn.execute("SELECT title, first_seen_at, last_seen_at FROM documents").fetchone()
        )
        visit = dict(
            conn.execute("SELECT title, visit_started_at, captured_at FROM visits").fetchone()
        )
        claim = dict(
            conn.execute(
                """
                SELECT observation_id, first_observed_at, last_observed_at
                FROM document_url_claims
                """
            ).fetchone()
        )

    assert document == {
        "title": "Later title",
        "first_seen_at": earlier.captured_at,
        "last_seen_at": later.captured_at,
    }
    assert visit == {
        "title": "Later title",
        "visit_started_at": earlier.visit_started_at,
        "captured_at": later.captured_at,
    }
    assert claim == {
        "observation_id": later_result["observation_id"],
        "first_observed_at": earlier.captured_at,
        "last_observed_at": later.captured_at,
    }


def test_media_references_keep_their_capture_observation_provenance(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    first = _payload(
        media_artifacts=[
            {
                "media_type": "image",
                "role": "content",
                "source_url": "https://cdn.example.test/first.png",
            }
        ]
    )
    second = _payload(
        observation_id="observation-media-2",
        captured_at="2026-06-08T12:05:00Z",
        media_artifacts=[
            {
                "media_type": "image",
                "role": "content",
                "source_url": "https://cdn.example.test/second.png",
            }
        ],
    )

    with connect(cfg.db_path) as conn:
        first_result = ingest_capture(conn, cfg, first)
        second_result = ingest_capture(conn, cfg, second)
        rows = conn.execute(
            """
            SELECT m.source_url, mao.observation_id, mao.provenance_quality
            FROM media_artifacts m
            JOIN media_artifact_observations mao ON mao.artifact_id = m.id
            ORDER BY m.source_url
            """
        ).fetchall()
        media = media_artifacts_for_snapshot(conn, first_result["snapshot_id"], cfg)

    assert [dict(row) for row in rows] == [
        {
            "source_url": "https://cdn.example.test/first.png",
            "observation_id": first_result["observation_id"],
            "provenance_quality": "observed",
        },
        {
            "source_url": "https://cdn.example.test/second.png",
            "observation_id": second_result["observation_id"],
            "provenance_quality": "observed",
        },
    ]
    assert {
        item["source_url"]: [link["observation_id"] for link in item["observations"]]
        for item in media
    } == {
        "https://cdn.example.test/first.png": [first_result["observation_id"]],
        "https://cdn.example.test/second.png": [second_result["observation_id"]],
    }


def test_observation_retry_is_idempotent_and_conflicting_reuse_fails(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    payload = _payload(
        canonical_url="https://example.test/canonical-article",
        media_artifacts=[
            {
                "media_type": "image",
                "role": "content",
                "source_url": "https://cdn.example.test/retry-proof.png",
            }
        ],
    )

    with connect(cfg.db_path) as conn:
        first = ingest_capture(conn, cfg, payload)
        retry = ingest_capture(conn, cfg, payload)
        assert retry["observation_id"] == first["observation_id"]
        assert retry["observation_created"] is False
        assert retry["url_claim_ids"] == first["url_claim_ids"]
        assert retry["media_ref_count"] == first["media_ref_count"] == 1
        assert [item["artifact_id"] for item in retry["media_artifacts"]] == [
            item["artifact_id"] for item in first["media_artifacts"]
        ]
        assert conn.execute("SELECT COUNT(*) FROM capture_observations").fetchone()[0] == 1
        link = dict(
            conn.execute(
                """
                SELECT artifact_id, observation_id, provenance_quality
                FROM media_artifact_observations
                """
            ).fetchone()
        )
        assert link == {
            "artifact_id": first["media_artifacts"][0]["artifact_id"],
            "observation_id": first["observation_id"],
            "provenance_quality": "observed",
        }

        with pytest.raises(ValueError, match="observation_id conflicts"):
            ingest_capture(
                conn,
                cfg,
                _payload(text="Conflicting text under the same browser observation id."),
            )
        with pytest.raises(ValueError, match="observation_id conflicts"):
            ingest_capture(conn, cfg, _payload(capture_reason="conflicting-reason"))
        assert conn.execute("SELECT COUNT(*) FROM capture_observations").fetchone()[0] == 1


def test_cross_origin_canonical_is_a_non_authoritative_claim_and_visit_fk_survives_recapture(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        target = ingest_capture(
            conn,
            cfg,
            _payload(
                visit_id="visit-target",
                navigation_id="navigation-target",
                observation_id="observation-target",
                url="https://target.example/item",
                text="Target document body.",
            ),
        )
        hostile = ingest_capture(
            conn,
            cfg,
            _payload(
                canonical_url="https://target.example/item",
                url="https://evil.example/page",
                text="Hostile canonical claimant body.",
            ),
        )
        record_visit_event(
            conn,
            {
                "event_id": "event-before-recapture",
                "visit_id": "visit-observation-1",
                "url": "https://evil.example/page",
                "event_type": "tab-deactivated",
                "event_started_at": "2026-06-08T12:00:00Z",
                "event_ended_at": "2026-06-08T12:00:05Z",
                "active_seconds": 5,
            },
        )
        recapture = ingest_capture(
            conn,
            cfg,
            _payload(
                observation_id="observation-evil-recapture",
                captured_at="2026-06-08T12:05:00Z",
                canonical_url="https://target.example/item",
                url="https://evil.example/page",
                text="Hostile canonical claimant changed body.",
            ),
        )
        claim = dict(
            conn.execute(
                """
                SELECT document_id, claimed_url, same_origin, identity_effect, provenance_quality
                FROM document_url_claims
                WHERE claim_type = 'canonical' AND document_id = ?
                """,
                (hostile["document_id"],),
            ).fetchone()
        )
        event_count = conn.execute(
            "SELECT COUNT(*) FROM visit_events WHERE visit_id = 'visit-observation-1'"
        ).fetchone()[0]
        visit_count = conn.execute(
            "SELECT COUNT(*) FROM visits WHERE id = 'visit-observation-1'"
        ).fetchone()[0]

    assert hostile["document_id"] != target["document_id"]
    assert recapture["document_id"] == hostile["document_id"]
    assert claim == {
        "document_id": hostile["document_id"],
        "claimed_url": "https://target.example/item",
        "same_origin": 0,
        "identity_effect": "none",
        "provenance_quality": "observed",
    }
    assert visit_count == 1
    assert event_count == 1


def test_visit_id_cannot_be_reused_for_a_different_observed_navigation(tmp_path):
    cfg = _config(tmp_path)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        first = ingest_capture(conn, cfg, _payload())
        with pytest.raises(ValueError, match="visit_id conflicts"):
            ingest_capture(
                conn,
                cfg,
                _payload(
                    observation_id="observation-other-navigation",
                    navigation_id="navigation-other",
                    url="https://other.example.test/article",
                ),
            )
        counts = dict(
            conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM documents) AS documents,
                  (SELECT COUNT(*) FROM visits) AS visits,
                  (SELECT COUNT(*) FROM capture_observations) AS observations,
                  (SELECT COUNT(*) FROM snapshots) AS snapshots
                """
            ).fetchone()
        )

    assert first["stored"] is True
    assert counts == {"documents": 1, "visits": 1, "observations": 1, "snapshots": 1}
