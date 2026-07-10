from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any

from .config import RuntimeConfig
from .db import audit, connect, init_db
from .media import fetch_and_store_media_artifact
from .media_ops import reconcile_cdp_blob_coverage, reconcile_stored_media_tasks
from .media_tasks import claim_media_fetch_tasks, process_media_fetch_task_rows


def run_once(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    worker_id: str | None = None,
    worker_kind: str = "daemon-public",
    limit: int = 25,
) -> dict[str, Any]:
    worker_id = worker_id or f"media-worker-{uuid.uuid4()}"
    with conn:
        reconciled_cdp_blob_coverage = reconcile_cdp_blob_coverage(conn, limit=limit)
        reconciled_stored_tasks = reconcile_stored_media_tasks(conn, worker_kind=worker_kind, limit=limit)
        rows = claim_media_fetch_tasks(conn, worker_id=worker_id, worker_kind=worker_kind, limit=limit)
    results = process_media_fetch_task_rows(
        conn,
        config,
        rows,
        fetch_artifact=fetch_and_store_media_artifact,
    )
    summary = {
        "worker_id": worker_id,
        "worker_kind": worker_kind,
        "reconciled_cdp_blob_coverage": reconciled_cdp_blob_coverage,
        "reconciled_stored_tasks": reconciled_stored_tasks,
        "attempted": len(results),
        "stored": sum(1 for item in results if item.get("stored")),
        "failed": sum(1 for item in results if item.get("capture_status") == "failed"),
        "skipped": sum(1 for item in results if item.get("capture_status") == "skipped"),
        "results": results,
    }
    audit(
        conn,
        "media.worker.run_once",
        {
            key: summary[key]
            for key in (
                "worker_id",
                "worker_kind",
                "reconciled_cdp_blob_coverage",
                "reconciled_stored_tasks",
                "attempted",
                "stored",
                "failed",
                "skipped",
            )
        },
    )
    conn.commit()
    return summary


def run_loop(config: RuntimeConfig, *, interval_seconds: float = 30.0, limit: int = 25, worker_id: str | None = None) -> None:
    worker_id = worker_id or f"media-worker-{uuid.uuid4()}"
    init_db(config)
    while True:
        with connect(config.db_path) as conn:
            run_once(conn, config, worker_id=worker_id, limit=limit)
        time.sleep(max(1.0, float(interval_seconds)))
