from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from browser_memory_daemon.config import RuntimeConfig
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.media_tasks import claim_media_fetch_tasks, ensure_media_fetch_task
from browser_memory_daemon.models import CapturePayload


def _config(root: Path) -> RuntimeConfig:
    cfg = RuntimeConfig(
        api_token="test-token",
        policy_mode="all",
        config_root=root / "config",
        data_root=root,
        state_root=root / "state",
        blob_root=root / "blobs",
        derivative_root=root / "blobs",
        media_root_path=root / "blobs" / "media",
        media_spool_root=None,
    )
    cfg.ensure_dirs()
    return cfg


def _media_task_fixture(tmp_path: Path) -> tuple[RuntimeConfig, str, str]:
    cfg = _config(tmp_path / "runtime")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.test/task-repository",
            "title": "Task repository",
            "text": "Task repository concurrency proof.",
            "media_artifacts": [
                {
                    "media_type": "image",
                    "source_url": "data:image/png;base64,iVBORw0KGgo=",
                    "mime_type": "image/png",
                }
            ],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        stored = ingest_capture(conn, cfg, payload)
        row = conn.execute("SELECT id FROM media_fetch_tasks").fetchone()
        assert row is not None
    return cfg, stored["snapshot_id"], str(row["id"])


def test_media_task_repository_allows_only_one_concurrent_lease_owner(tmp_path):
    cfg, _snapshot_id, task_id = _media_task_fixture(tmp_path)
    barrier = Barrier(2)

    def claim(worker_id: str) -> list[str]:
        with connect(cfg.db_path) as conn:
            barrier.wait(timeout=5)
            with conn:
                return [str(row["task_id"]) for row in claim_media_fetch_tasks(conn, worker_id=worker_id, limit=1)]

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(claim, ["worker-a", "worker-b"]))

    assert sorted(task for tasks in claimed for task in tasks) == [task_id]
    with connect(cfg.db_path) as conn:
        task = conn.execute("SELECT status, lease_owner, lease_until FROM media_fetch_tasks WHERE id = ?", (task_id,)).fetchone()
    assert task is not None
    assert task["status"] == "leased"
    assert task["lease_owner"] in {"worker-a", "worker-b"}
    assert task["lease_until"] is not None


def test_media_task_repository_preserves_terminal_state_unless_force_reset(tmp_path):
    cfg, _snapshot_id, task_id = _media_task_fixture(tmp_path)
    with connect(cfg.db_path) as conn:
        artifact_id = str(conn.execute("SELECT artifact_id FROM media_fetch_tasks WHERE id = ?", (task_id,)).fetchone()[0])
        conn.execute(
            "UPDATE media_fetch_tasks SET status = 'succeeded', attempts = 3, last_error = 'old error' WHERE id = ?",
            (task_id,),
        )
        ensure_media_fetch_task(conn, artifact_id)
        preserved = conn.execute("SELECT status, attempts, last_error FROM media_fetch_tasks WHERE id = ?", (task_id,)).fetchone()
        assert dict(preserved) == {"status": "succeeded", "attempts": 3, "last_error": "old error"}

        ensure_media_fetch_task(conn, artifact_id, force_reset=True)
        reset = conn.execute(
            "SELECT status, attempts, next_attempt_at, lease_owner, lease_until, last_error FROM media_fetch_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    assert dict(reset) == {
        "status": "pending",
        "attempts": 0,
        "next_attempt_at": None,
        "lease_owner": None,
        "lease_until": None,
        "last_error": None,
    }
