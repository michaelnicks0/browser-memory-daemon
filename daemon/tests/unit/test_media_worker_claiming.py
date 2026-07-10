import sqlite3

import browser_memory_daemon.media as media
import browser_memory_daemon.media_worker as media_worker
from browser_memory_daemon.config import load_config


def test_worker_claims_each_task_immediately_before_processing(tmp_path, monkeypatch):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    pending = [{"id": "artifact-1"}, {"id": "artifact-2"}, {"id": "artifact-3"}]
    claim_limits: list[int] = []
    processed: list[str] = []

    monkeypatch.setattr(media_worker, "reconcile_cdp_blob_coverage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(media_worker, "reconcile_stored_media_tasks", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(media_worker, "audit", lambda *_args, **_kwargs: "audit")

    def claim(*_args, limit, **_kwargs):
        claim_limits.append(limit)
        return [pending.pop(0)] if pending else []

    def process(_conn, _config, rows, *, fetch_artifact):
        del fetch_artifact
        assert len(rows) == 1
        processed.append(rows[0]["id"])
        return [{"artifact_id": rows[0]["id"], "stored": True, "capture_status": "stored"}]

    monkeypatch.setattr(media_worker, "claim_media_fetch_tasks", claim)
    monkeypatch.setattr(media_worker, "process_media_fetch_task_rows", process)

    with sqlite3.connect(":memory:") as conn:
        summary = media_worker.run_once(conn, cfg, worker_id="test-worker", limit=3)

    assert claim_limits == [1, 1, 1]
    assert processed == ["artifact-1", "artifact-2", "artifact-3"]
    assert summary["attempted"] == 3


def test_synchronous_fetch_claims_each_task_immediately_before_processing(tmp_path, monkeypatch):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    pending = [{"id": "artifact-1"}, {"id": "artifact-2"}]
    claim_limits: list[int] = []

    monkeypatch.setattr(media, "_seed_media_fetch_tasks_for_pending_artifacts", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(media, "_count_pending_media_artifacts", lambda *_args, **_kwargs: 0)

    def claim(*_args, limit, **_kwargs):
        claim_limits.append(limit)
        return [pending.pop(0)] if pending else []

    def process(_conn, _config, rows):
        assert len(rows) == 1
        return [{"artifact_id": rows[0]["id"], "stored": True, "capture_status": "stored"}]

    monkeypatch.setattr(media, "claim_media_fetch_tasks", claim)
    monkeypatch.setattr(media, "process_media_fetch_task_rows", process)

    with sqlite3.connect(":memory:") as conn:
        summary = media.fetch_pending_media_artifacts(conn, cfg, limit=2, worker_id="test-worker")

    assert claim_limits == [1, 1]
    assert summary["claimed"] == 2
    assert summary["stored"] == 2
