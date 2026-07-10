from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import RuntimeConfig
from .media_models import media_capture_status_for_fetch_reason, normalize_task_status

FetchArtifact = Callable[[sqlite3.Connection, RuntimeConfig, sqlite3.Row], dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def media_fetch_task_id(artifact_id: str, worker_kind: str) -> str:
    digest = hashlib.sha256(f"{worker_kind}:{artifact_id}".encode()).hexdigest()[:32]
    return f"mtask_{digest}"


def ensure_media_fetch_task(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    worker_kind: str = "daemon-public",
    priority: int = 50,
    status: str = "pending",
    last_error: str = "",
    force_reset: bool = False,
) -> str:
    task_id = media_fetch_task_id(artifact_id, worker_kind)
    normalized_status = normalize_task_status(status)
    now = _utc_now()
    force = bool(force_reset)
    conn.execute(
        """
        INSERT INTO media_fetch_tasks(
          id, artifact_id, worker_kind, status, priority, attempts, max_attempts,
          next_attempt_at, lease_owner, lease_until, last_error, updated_at
        ) VALUES (?, ?, ?, ?, ?, 0, 5, NULL, NULL, NULL, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          priority=MAX(media_fetch_tasks.priority, excluded.priority),
          status=CASE
            WHEN ? THEN excluded.status
            WHEN media_fetch_tasks.status IN ('succeeded', 'skipped') THEN media_fetch_tasks.status
            WHEN media_fetch_tasks.status = 'leased' AND media_fetch_tasks.lease_until IS NOT NULL THEN media_fetch_tasks.status
            ELSE excluded.status
          END,
          attempts=CASE WHEN ? THEN 0 ELSE media_fetch_tasks.attempts END,
          next_attempt_at=CASE WHEN ? THEN NULL ELSE media_fetch_tasks.next_attempt_at END,
          lease_owner=CASE WHEN ? THEN NULL ELSE media_fetch_tasks.lease_owner END,
          lease_until=CASE WHEN ? THEN NULL ELSE media_fetch_tasks.lease_until END,
          last_error=CASE WHEN ? THEN NULL ELSE COALESCE(NULLIF(excluded.last_error, ''), media_fetch_tasks.last_error) END,
          updated_at=excluded.updated_at
        """,
        (
            task_id,
            artifact_id,
            worker_kind,
            normalized_status,
            int(priority),
            None if force else (last_error or None),
            now,
            force,
            force,
            force,
            force,
            force,
            force,
        ),
    )
    return task_id


def mark_media_fetch_task(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    worker_kind: str = "daemon-public",
    status: str,
    error: str = "",
) -> None:
    conn.execute(
        """
        UPDATE media_fetch_tasks
        SET status = ?, last_error = NULLIF(?, ''), lease_owner = NULL, lease_until = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (normalize_task_status(status), error[:512], _utc_now(), media_fetch_task_id(artifact_id, worker_kind)),
    )


def _backoff_seconds(attempts: int) -> int:
    return int(min(3600, 30 * (2 ** max(0, attempts - 1))))


def _retryable_media_error(error: str) -> bool:
    return media_capture_status_for_fetch_reason(error) == "retrying"


def _pending_media_artifact_filters(
    *,
    snapshot_id: str | None = None,
    document_id: str | None = None,
    domain: str | None = None,
) -> tuple[list[str], list[Any]]:
    where = [
        "m.capture_status IN ('referenced', 'metadata-only', 'queued', 'retrying', 'failed', 'purged')",
        "COALESCE(m.blob_locator, '') = '' AND COALESCE(m.spool_locator, '') = '' AND COALESCE(m.file_path, '') = ''",
    ]
    params: list[Any] = []
    if snapshot_id:
        where.append("m.snapshot_id = ?")
        params.append(snapshot_id)
    if document_id:
        where.append("m.document_id = ?")
        params.append(document_id)
    if domain:
        normalized_domain = domain.lower().strip()
        where.append("(lower(d.domain) = ? OR lower(m.page_url) LIKE ? OR lower(m.source_url) LIKE ?)")
        params.extend([normalized_domain, f"%://{normalized_domain}/%", f"%{normalized_domain}%"])
    return where, params


def claim_media_fetch_tasks(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    worker_kind: str = "daemon-public",
    limit: int = 25,
    lease_seconds: int = 120,
    snapshot_id: str | None = None,
    document_id: str | None = None,
    domain: str | None = None,
) -> list[sqlite3.Row]:
    """Atomically lease due media tasks and return the rows this worker owns."""
    now_s = _utc_now()
    lease_until = (datetime.now(UTC) + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
    where, artifact_params = _pending_media_artifact_filters(
        snapshot_id=snapshot_id,
        document_id=document_id,
        domain=domain,
    )
    artifact_filter_sql = " AND ".join(where)
    candidates = [
        row["id"]
        for row in conn.execute(
            f"""
            SELECT t.id
            FROM media_fetch_tasks t
            JOIN media_artifacts m ON m.id = t.artifact_id
            LEFT JOIN documents d ON d.id = m.document_id
            WHERE t.worker_kind = ?
              AND t.status IN ('pending', 'retrying', 'leased')
              AND {artifact_filter_sql}
              AND (t.next_attempt_at IS NULL OR t.next_attempt_at <= ?)
              AND (t.lease_until IS NULL OR t.lease_until <= ? OR t.lease_owner = ?)
            ORDER BY t.priority DESC, t.created_at ASC, t.id
            LIMIT ?
            """,
            [worker_kind, *artifact_params, now_s, now_s, worker_id, max(1, int(limit))],
        ).fetchall()
    ]
    claimed_ids: list[str] = []
    for task_id in candidates:
        cursor = conn.execute(
            f"""
            UPDATE media_fetch_tasks
            SET status = 'leased', lease_owner = ?, lease_until = ?, updated_at = ?
            WHERE id = ?
              AND worker_kind = ?
              AND status IN ('pending', 'retrying', 'leased')
              AND artifact_id IN (
                SELECT m.id
                FROM media_artifacts m
                LEFT JOIN documents d ON d.id = m.document_id
                WHERE {artifact_filter_sql}
              )
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
              AND (lease_until IS NULL OR lease_until <= ? OR lease_owner = ?)
            """,
            [worker_id, lease_until, now_s, task_id, worker_kind, *artifact_params, now_s, now_s, worker_id],
        )
        if cursor.rowcount:
            claimed_ids.append(task_id)
    if not claimed_ids:
        return []
    placeholders = ",".join("?" for _ in claimed_ids)
    return conn.execute(
        f"""
        SELECT t.id AS task_id, t.status AS task_status, t.attempts AS task_attempts,
               t.max_attempts AS task_max_attempts, t.worker_kind AS task_worker_kind,
               t.priority AS task_priority, m.*
        FROM media_fetch_tasks t
        JOIN media_artifacts m ON m.id = t.artifact_id
        WHERE t.id IN ({placeholders})
          AND t.lease_owner = ?
        ORDER BY t.priority DESC, t.created_at ASC, t.id
        """,
        [*claimed_ids, worker_id],
    ).fetchall()


def process_media_fetch_task_rows(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    rows: list[sqlite3.Row],
    *,
    fetch_artifact: FetchArtifact,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in rows:
        artifact_id = row["id"]
        task_id = row["task_id"]
        attempts = int(row["task_attempts"] or 0) + 1
        max_attempts = int(row["task_max_attempts"] or 5)
        try:
            result = fetch_artifact(conn, config, row)
            status = str(result.get("capture_status") or "")
            if result.get("stored"):
                with conn:
                    conn.execute(
                        "UPDATE media_fetch_tasks SET status = 'succeeded', attempts = ?, lease_owner = NULL, lease_until = NULL, last_error = NULL, updated_at = ? WHERE id = ?",
                        (attempts, _utc_now(), task_id),
                    )
            elif status in {"skipped", "expired", "referenced"}:
                with conn:
                    conn.execute(
                        "UPDATE media_fetch_tasks SET status = 'skipped', attempts = ?, lease_owner = NULL, lease_until = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                        (attempts, str(result.get("status_reason") or result.get("reason") or status)[:512], _utc_now(), task_id),
                    )
            else:
                error = str(result.get("status_reason") or result.get("error") or "fetch failed")[:512]
                next_status = "retrying" if status == "retrying" or _retryable_media_error(error) or attempts < max_attempts else "failed"
                next_attempt = (
                    None
                    if next_status == "failed"
                    else (datetime.now(UTC) + timedelta(seconds=_backoff_seconds(attempts))).isoformat().replace("+00:00", "Z")
                )
                with conn:
                    conn.execute(
                        "UPDATE media_fetch_tasks SET status = ?, attempts = ?, next_attempt_at = ?, lease_owner = NULL, lease_until = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                        (next_status, attempts, next_attempt, error, _utc_now(), task_id),
                    )
            results.append(result)
        except Exception as exc:
            error = str(exc)[:512]
            next_status = "retrying" if _retryable_media_error(error) or attempts < max_attempts else "failed"
            next_attempt = (
                None
                if next_status == "failed"
                else (datetime.now(UTC) + timedelta(seconds=_backoff_seconds(attempts))).isoformat().replace("+00:00", "Z")
            )
            with conn:
                conn.execute(
                    "UPDATE media_fetch_tasks SET status = ?, attempts = ?, next_attempt_at = ?, lease_owner = NULL, lease_until = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                    (next_status, attempts, next_attempt, error, _utc_now(), task_id),
                )
            results.append({"stored": False, "artifact_id": artifact_id, "capture_status": "failed", "error": error})
    return results
