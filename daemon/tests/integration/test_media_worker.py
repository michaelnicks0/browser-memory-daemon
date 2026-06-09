from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.media import media_artifacts_for_snapshot, purge_media_cache
from browser_memory_daemon.media_worker import run_once
from browser_memory_daemon.models import CapturePayload


def test_media_worker_processes_data_url_task_and_marks_success(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/worker-media",
            "title": "Worker Media",
            "text": "Readable worker media body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
        assert summary["attempted"] == 1
        assert summary["stored"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "stored"
        task = conn.execute("SELECT status FROM media_fetch_tasks").fetchone()
        assert task["status"] == "succeeded"


def test_media_worker_tasks_are_seeded_when_existing_unresolved_refs_have_no_task(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/seed-task",
            "title": "Seed Task",
            "text": "Readable seed task body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        conn.execute("DELETE FROM media_fetch_tasks")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM media_fetch_tasks").fetchone()[0] == 0
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        task = conn.execute("SELECT status FROM media_fetch_tasks").fetchone()
        assert task["status"] == "pending"


def test_media_worker_rehydrates_purged_cache_when_source_still_fetchable(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/worker-rehydrate",
            "title": "Worker Rehydrate",
            "text": "Readable worker rehydrate body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert run_once(conn, cfg, worker_id="test-worker", limit=10)["stored"] == 1
        purged = purge_media_cache(conn, cfg, {"domain": "example.com", "dry_run": False, "rehydrate": True})
        assert purged["purged"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "purged"
        assert media["has_file"] is False
        summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
        assert summary["stored"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "stored"
        assert media["has_file"] is True
