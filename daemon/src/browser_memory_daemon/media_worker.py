from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any

from .config import RuntimeConfig
from .db import audit, connect, init_db
from .media import fetch_and_store_media_artifact
from .media_ops import reconcile_cdp_blob_coverage, reconcile_stored_media_tasks
from .media_storage import MediaStorageUnavailable, drain_media_spool, media_root_readiness
from .media_tasks import claim_media_fetch_tasks, process_media_fetch_task_rows


def _automatic_spool_drain(conn: sqlite3.Connection, config: RuntimeConfig, *, limit: int) -> dict[str, Any]:
    readiness = media_root_readiness(config)
    base: dict[str, Any] = {
        "enabled": config.media_spool_enabled,
        "attempted": False,
        "status": "disabled" if not config.media_spool_enabled else "deferred",
        "media_root_status": readiness.status,
        "selected": 0,
        "selected_bytes": 0,
        "moved": 0,
        "moved_bytes": 0,
        "missing": 0,
        "invalid": 0,
        "source_cleanup_failed": 0,
        "errors": 0,
    }
    if not config.media_spool_enabled or not readiness.ok:
        return base
    try:
        result = drain_media_spool(conn, config, limit=limit, execute=True)
    except MediaStorageUnavailable:
        base["media_root_status"] = media_root_readiness(config).status
        return base
    incomplete = any(
        int(result[key]) > 0
        for key in ("missing", "invalid", "source_cleanup_failed", "errors")
    )
    return {
        **base,
        "attempted": True,
        "status": "partial" if incomplete else "complete",
        **{
            key: int(result[key])
            for key in (
                "selected",
                "selected_bytes",
                "moved",
                "moved_bytes",
                "missing",
                "invalid",
                "source_cleanup_failed",
                "errors",
            )
        },
    }


def run_once(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    worker_id: str | None = None,
    worker_kind: str = "daemon-public",
    limit: int = 25,
) -> dict[str, Any]:
    worker_id = worker_id or f"media-worker-{uuid.uuid4()}"
    selected_limit = max(1, int(limit))
    spool_drain = _automatic_spool_drain(conn, config, limit=min(selected_limit, 10_000))
    with conn:
        reconciled_cdp_blob_coverage = reconcile_cdp_blob_coverage(conn, limit=selected_limit)
        reconciled_stored_tasks = reconcile_stored_media_tasks(conn, worker_kind=worker_kind, limit=selected_limit)
    results: list[dict[str, Any]] = []
    for _ in range(selected_limit):
        with conn:
            rows = claim_media_fetch_tasks(conn, worker_id=worker_id, worker_kind=worker_kind, limit=1)
        if not rows:
            break
        results.extend(
            process_media_fetch_task_rows(
                conn,
                config,
                rows,
                fetch_artifact=fetch_and_store_media_artifact,
            )
        )
    summary = {
        "worker_id": worker_id,
        "worker_kind": worker_kind,
        "spool_drain": spool_drain,
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
                "spool_drain",
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
