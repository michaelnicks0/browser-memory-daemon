from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import time
import uuid
from typing import Any

from .config import RuntimeConfig
from .db import audit, connect, init_db
from .media import fetch_and_store_media_artifact


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _backoff_seconds(attempts: int) -> int:
    return min(3600, 30 * (2 ** max(0, attempts - 1)))


def claim_media_fetch_tasks(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    worker_kind: str = "daemon-public",
    limit: int = 25,
    lease_seconds: int = 120,
) -> list[sqlite3.Row]:
    now_s = utc_now()
    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
    task_ids = [
        row["id"]
        for row in conn.execute(
            """
            SELECT t.id
            FROM media_fetch_tasks t
            JOIN media_artifacts m ON m.id = t.artifact_id
            WHERE t.worker_kind = ?
              AND t.status IN ('pending', 'retrying', 'leased')
              AND COALESCE(m.file_path, '') = ''
              AND m.capture_status IN ('referenced', 'metadata-only', 'queued', 'retrying', 'failed', 'purged')
              AND (t.next_attempt_at IS NULL OR t.next_attempt_at <= ?)
              AND (t.lease_until IS NULL OR t.lease_until <= ? OR t.lease_owner = ?)
            ORDER BY t.priority DESC, t.created_at ASC, t.id
            LIMIT ?
            """,
            (worker_kind, now_s, now_s, worker_id, max(1, int(limit))),
        ).fetchall()
    ]
    if not task_ids:
        return []
    conn.executemany(
        """
        UPDATE media_fetch_tasks
        SET status = 'leased', lease_owner = ?, lease_until = ?, updated_at = ?
        WHERE id = ?
        """,
        [(worker_id, lease_until, now_s, task_id) for task_id in task_ids],
    )
    placeholders = ",".join("?" for _ in task_ids)
    return conn.execute(
        f"""
        SELECT t.id AS task_id, t.status AS task_status, t.attempts AS task_attempts,
               t.max_attempts AS task_max_attempts, t.worker_kind AS task_worker_kind,
               t.priority AS task_priority, m.*
        FROM media_fetch_tasks t
        JOIN media_artifacts m ON m.id = t.artifact_id
        WHERE t.id IN ({placeholders})
        ORDER BY t.priority DESC, t.created_at ASC, t.id
        """,
        task_ids,
    ).fetchall()


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
        rows = claim_media_fetch_tasks(conn, worker_id=worker_id, worker_kind=worker_kind, limit=limit)
    results: list[dict[str, Any]] = []
    for row in rows:
        artifact_id = row["id"]
        task_id = row["task_id"]
        attempts = int(row["task_attempts"] or 0) + 1
        max_attempts = int(row["task_max_attempts"] or 5)
        try:
            result = fetch_and_store_media_artifact(conn, config, row)
            status = str(result.get("capture_status") or "")
            if result.get("stored"):
                with conn:
                    conn.execute(
                        "UPDATE media_fetch_tasks SET status = 'succeeded', attempts = ?, lease_owner = NULL, lease_until = NULL, last_error = NULL, updated_at = ? WHERE id = ?",
                        (attempts, utc_now(), task_id),
                    )
            elif status == "skipped":
                with conn:
                    conn.execute(
                        "UPDATE media_fetch_tasks SET status = 'skipped', attempts = ?, lease_owner = NULL, lease_until = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                        (attempts, str(result.get("status_reason") or result.get("reason") or "skipped")[:512], utc_now(), task_id),
                    )
            else:
                error = str(result.get("status_reason") or result.get("error") or "fetch failed")[:512]
                next_status = "failed" if attempts >= max_attempts else "retrying"
                next_attempt = None if next_status == "failed" else (datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(attempts))).isoformat().replace("+00:00", "Z")
                with conn:
                    conn.execute(
                        "UPDATE media_fetch_tasks SET status = ?, attempts = ?, next_attempt_at = ?, lease_owner = NULL, lease_until = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                        (next_status, attempts, next_attempt, error, utc_now(), task_id),
                    )
            results.append(result)
        except Exception as exc:
            error = str(exc)[:512]
            next_status = "failed" if attempts >= max_attempts else "retrying"
            next_attempt = None if next_status == "failed" else (datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(attempts))).isoformat().replace("+00:00", "Z")
            with conn:
                conn.execute(
                    "UPDATE media_fetch_tasks SET status = ?, attempts = ?, next_attempt_at = ?, lease_owner = NULL, lease_until = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                    (next_status, attempts, next_attempt, error, utc_now(), task_id),
                )
            results.append({"stored": False, "artifact_id": artifact_id, "capture_status": "failed", "error": error})
    summary = {
        "worker_id": worker_id,
        "worker_kind": worker_kind,
        "attempted": len(results),
        "stored": sum(1 for item in results if item.get("stored")),
        "failed": sum(1 for item in results if item.get("capture_status") == "failed"),
        "skipped": sum(1 for item in results if item.get("capture_status") == "skipped"),
        "results": results,
    }
    audit(conn, "media.worker.run_once", {k: summary[k] for k in ("worker_id", "worker_kind", "attempted", "stored", "failed", "skipped")})
    conn.commit()
    return summary


def run_loop(config: RuntimeConfig, *, interval_seconds: float = 30.0, limit: int = 25, worker_id: str | None = None) -> None:
    worker_id = worker_id or f"media-worker-{uuid.uuid4()}"
    init_db(config)
    while True:
        with connect(config.db_path) as conn:
            run_once(conn, config, worker_id=worker_id, limit=limit)
        time.sleep(max(1.0, float(interval_seconds)))
