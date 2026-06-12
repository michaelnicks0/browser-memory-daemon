from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import time
import uuid
from typing import Any

from .config import RuntimeConfig
from .db import audit, connect, init_db
from .media import fetch_and_store_media_artifact, media_capture_status_for_fetch_reason, ensure_media_fetch_task


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


def _retryable_media_error(error: str) -> bool:
    return media_capture_status_for_fetch_reason(error) == "retrying"


def normalize_terminal_failed_artifacts(conn: sqlite3.Connection, *, worker_kind: str = "daemon-public") -> int:
    """Move permanent or transient terminal failures out of the failed artifact bucket.

    `failed` is reserved for unexpected bugs after classification. Permanent remote
    conditions become `skipped`/`expired`; transient remote conditions remain
    `retrying` so the worker can keep probing with backoff.
    """
    rows = conn.execute(
        """
        SELECT id, source_url, media_type, status_reason
        FROM media_artifacts
        WHERE capture_status = 'failed'
        """
    ).fetchall()
    changed = 0
    now_s = utc_now()
    for row in rows:
        reason = row["status_reason"] or ""
        status = media_capture_status_for_fetch_reason(reason, source_url=row["source_url"] or "", media_type=row["media_type"] or "")
        if status == "failed":
            continue
        changed += 1
        conn.execute(
            "UPDATE media_artifacts SET capture_status = ?, status_reason = COALESCE(status_reason, ?) WHERE id = ?",
            (status, reason or status, row["id"]),
        )
        if status == "retrying":
            conn.execute(
                """
                UPDATE media_fetch_tasks
                SET status = 'retrying', next_attempt_at = NULL, lease_owner = NULL, lease_until = NULL,
                    last_error = NULLIF(?, ''), updated_at = ?
                WHERE artifact_id = ? AND worker_kind = ?
                """,
                (reason, now_s, row["id"], worker_kind),
            )
        else:
            conn.execute(
                """
                UPDATE media_fetch_tasks
                SET status = 'skipped', next_attempt_at = NULL, lease_owner = NULL, lease_until = NULL,
                    last_error = NULLIF(?, ''), updated_at = ?
                WHERE artifact_id = ? AND worker_kind = ?
                """,
                (reason or status, now_s, row["id"], worker_kind),
            )
    return changed


def normalize_legacy_blob_video_skips(conn: sqlite3.Connection) -> int:
    """Reclassify legacy daemon-unsupported blob videos as references.

    A blob URL is not fetchable by the daemon after the renderer page is gone, so
    older browser-side `unsupported-media-url-scheme` rows are references, not a
    durable decision to skip a retrievable video. New extension builds either
    upload blob-backed bytes from the page context or keep MSE/blob streams as
    references.
    """
    cursor = conn.execute(
        """
        UPDATE media_artifacts
        SET capture_status = 'referenced', status_reason = NULL
        WHERE media_type = 'video'
          AND capture_status = 'skipped'
          AND status_reason = 'unsupported-media-url-scheme'
          AND source_url LIKE 'blob:%'
        """
    )
    return int(cursor.rowcount or 0)


def normalize_hls_video_skips(conn: sqlite3.Connection, *, worker_kind: str = "daemon-public") -> int:
    """Requeue HLS playlists that were skipped as non-media content.

    HLS manifests use `application/x-mpegURL`, which is not itself a `video/*`
    MIME. Those rows are retrievable by the daemon HLS assembler, so old skipped
    rows should become referenced work again.
    """
    rows = conn.execute(
        """
        SELECT id
        FROM media_artifacts
        WHERE media_type = 'video'
          AND capture_status = 'skipped'
          AND status_reason IN ('non-media-content-type', 'media-too-large', 'unsupported-media-url-scheme')
          AND lower(source_url) LIKE '%.m3u8%'
        """
    ).fetchall()
    if not rows:
        return 0
    artifact_ids = [row["id"] for row in rows]
    placeholders = ",".join("?" for _ in artifact_ids)
    conn.execute(
        f"UPDATE media_artifacts SET capture_status = 'referenced', status_reason = NULL WHERE id IN ({placeholders})",
        artifact_ids,
    )
    for artifact_id in artifact_ids:
        ensure_media_fetch_task(conn, artifact_id, worker_kind=worker_kind, force_reset=True)
    return len(artifact_ids)


def normalize_video_nonmedia_skips(conn: sqlite3.Connection) -> int:
    """Reclassify non-playlist video non-media responses as references.

    Signed player URLs can expire or return HTML/error bodies when replayed by
    the browser-side fetch path. That is not an intentional skip decision; it is
    a reference-only video surface unless a later direct/HLS/blob path appears.
    """
    cursor = conn.execute(
        """
        UPDATE media_artifacts
        SET capture_status = 'referenced'
        WHERE media_type = 'video'
          AND capture_status = 'skipped'
          AND status_reason = 'non-media-content-type'
        """
    )
    return int(cursor.rowcount or 0)


def mark_already_stored_tasks_succeeded(conn: sqlite3.Connection, *, worker_kind: str = "daemon-public") -> int:
    """Close stale work items when the artifact row already has durable bytes."""
    cursor = conn.execute(
        """
        UPDATE media_fetch_tasks
        SET status = 'succeeded', lease_owner = NULL, lease_until = NULL, last_error = NULL,
            updated_at = ?
        WHERE worker_kind = ?
          AND status IN ('pending', 'retrying', 'leased')
          AND artifact_id IN (
            SELECT id
            FROM media_artifacts
            WHERE capture_status = 'stored'
              AND COALESCE(file_path, '') != ''
          )
        """,
        (utc_now(), worker_kind),
    )
    return int(cursor.rowcount or 0)


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
        normalized_legacy_blob_videos = normalize_legacy_blob_video_skips(conn)
        normalized_hls_videos = normalize_hls_video_skips(conn, worker_kind=worker_kind)
        normalized_video_nonmedia = normalize_video_nonmedia_skips(conn)
        normalized_terminal = normalize_terminal_failed_artifacts(conn, worker_kind=worker_kind)
        already_stored = mark_already_stored_tasks_succeeded(conn, worker_kind=worker_kind)
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
            elif status in {"skipped", "expired", "referenced"}:
                with conn:
                    conn.execute(
                        "UPDATE media_fetch_tasks SET status = 'skipped', attempts = ?, lease_owner = NULL, lease_until = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                        (attempts, str(result.get("status_reason") or result.get("reason") or status)[:512], utc_now(), task_id),
                    )
            else:
                error = str(result.get("status_reason") or result.get("error") or "fetch failed")[:512]
                next_status = "retrying" if status == "retrying" or _retryable_media_error(error) or attempts < max_attempts else "failed"
                next_attempt = None if next_status == "failed" else (datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(attempts))).isoformat().replace("+00:00", "Z")
                with conn:
                    conn.execute(
                        "UPDATE media_fetch_tasks SET status = ?, attempts = ?, next_attempt_at = ?, lease_owner = NULL, lease_until = NULL, last_error = ?, updated_at = ? WHERE id = ?",
                        (next_status, attempts, next_attempt, error, utc_now(), task_id),
                    )
            results.append(result)
        except Exception as exc:
            error = str(exc)[:512]
            next_status = "retrying" if _retryable_media_error(error) or attempts < max_attempts else "failed"
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
        "normalized_legacy_blob_videos": normalized_legacy_blob_videos,
        "normalized_hls_videos": normalized_hls_videos,
        "normalized_video_nonmedia": normalized_video_nonmedia,
        "normalized_terminal": normalized_terminal,
        "already_stored": already_stored,
        "attempted": len(results),
        "stored": sum(1 for item in results if item.get("stored")),
        "failed": sum(1 for item in results if item.get("capture_status") == "failed"),
        "skipped": sum(1 for item in results if item.get("capture_status") == "skipped"),
        "results": results,
    }
    audit(conn, "media.worker.run_once", {k: summary[k] for k in ("worker_id", "worker_kind", "normalized_legacy_blob_videos", "normalized_hls_videos", "normalized_video_nonmedia", "normalized_terminal", "already_stored", "attempted", "stored", "failed", "skipped")})
    conn.commit()
    return summary


def run_loop(config: RuntimeConfig, *, interval_seconds: float = 30.0, limit: int = 25, worker_id: str | None = None) -> None:
    worker_id = worker_id or f"media-worker-{uuid.uuid4()}"
    init_db(config)
    while True:
        with connect(config.db_path) as conn:
            run_once(conn, config, worker_id=worker_id, limit=limit)
        time.sleep(max(1.0, float(interval_seconds)))
