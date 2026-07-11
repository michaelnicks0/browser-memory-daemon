from __future__ import annotations

import sqlite3
from typing import Any

from .db import audit
from .media_tasks import ensure_media_fetch_task

_REQUEUE_REASONS: dict[str, tuple[str, ...]] = {
    "snapshot-budget": ("snapshot-media-budget",),
    "storage-budget": ("domain-media-budget", "media-cache-budget"),
    "all-budget": ("snapshot-media-budget", "domain-media-budget", "media-cache-budget"),
}


def reconcile_cdp_blob_coverage(conn: sqlite3.Connection, *, limit: int = 100) -> int:
    selected_limit = max(1, min(int(limit), 1000))
    rows = conn.execute(
        """
        SELECT media_artifacts.id
        FROM media_artifacts
        WHERE media_artifacts.media_type = 'video'
          AND media_artifacts.capture_status = 'referenced'
          AND (media_artifacts.status_reason IS NULL OR media_artifacts.status_reason IN ('', 'opaque-browser-blob'))
          AND media_artifacts.source_url LIKE 'blob:%'
          AND EXISTS (
            SELECT 1
            FROM media_artifacts cdp
            WHERE cdp.media_type = 'video'
              AND cdp.capture_status = 'stored'
              AND (COALESCE(cdp.blob_locator, '') != '' OR COALESCE(cdp.spool_locator, '') != '' OR COALESCE(cdp.file_path, '') != '')
              AND (cdp.id LIKE 'media_cdp_%' OR json_extract(cdp.metadata_json, '$.cdp_recorder') = 1)
              AND (
                cdp.snapshot_id = media_artifacts.snapshot_id
                OR (
                  cdp.document_id = media_artifacts.document_id
                  AND ABS(strftime('%s', cdp.created_at) - strftime('%s', media_artifacts.created_at)) <= 300
                )
              )
          )
        ORDER BY media_artifacts.created_at DESC, media_artifacts.id
        LIMIT ?
        """,
        (selected_limit,),
    ).fetchall()
    artifact_ids = [str(row["id"]) for row in rows]
    if not artifact_ids:
        return 0
    placeholders = ",".join("?" for _ in artifact_ids)
    cursor = conn.execute(
        f"UPDATE media_artifacts SET status_reason = 'covered-by-cdp-recorder' WHERE id IN ({placeholders})",
        artifact_ids,
    )
    return int(cursor.rowcount or 0)


def reconcile_stored_media_tasks(
    conn: sqlite3.Connection,
    *,
    worker_kind: str = "daemon-public",
    limit: int = 100,
) -> int:
    selected_limit = max(1, min(int(limit), 1000))
    rows = conn.execute(
        """
        SELECT t.id
        FROM media_fetch_tasks t
        JOIN media_artifacts m ON m.id = t.artifact_id
        WHERE t.worker_kind = ?
          AND t.status IN ('pending', 'retrying', 'leased')
          AND m.capture_status = 'stored'
          AND (COALESCE(m.blob_locator, '') != '' OR COALESCE(m.spool_locator, '') != '' OR COALESCE(m.file_path, '') != '')
        ORDER BY t.updated_at, t.id
        LIMIT ?
        """,
        (worker_kind, selected_limit),
    ).fetchall()
    task_ids = [str(row["id"]) for row in rows]
    if not task_ids:
        return 0
    placeholders = ",".join("?" for _ in task_ids)
    cursor = conn.execute(
        f"""
        UPDATE media_fetch_tasks
        SET status = 'succeeded', lease_owner = NULL, lease_until = NULL,
            last_error = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
        """,
        task_ids,
    )
    return int(cursor.rowcount or 0)


def _normalized_domain(value: str) -> str:
    domain = str(value or "").strip().rstrip(".").lower()
    if (
        not domain
        or "://" in domain
        or "/" in domain
        or any(character.isspace() for character in domain)
        or any(character in domain for character in ("%", "_"))
    ):
        raise ValueError("media requeue domain must be a literal hostname")
    return domain


def requeue_media_artifacts(
    conn: sqlite3.Connection,
    *,
    reason: str,
    domain: str | None = None,
    document_id: str | None = None,
    snapshot_id: str | None = None,
    limit: int = 100,
    execute: bool = False,
    worker_kind: str = "daemon-public",
) -> dict[str, Any]:
    normalized_reason = str(reason or "").strip().lower()
    reasons = _REQUEUE_REASONS.get(normalized_reason)
    if reasons is None:
        raise ValueError(f"media requeue reason must be one of {sorted(_REQUEUE_REASONS)}")
    if not any(str(value or "").strip() for value in (domain, document_id, snapshot_id)):
        raise ValueError("media requeue requires an explicit domain, document_id, or snapshot_id scope")

    where = ["m.capture_status = 'skipped'"]
    params: list[Any] = []
    placeholders = ",".join("?" for _ in reasons)
    where.append(f"m.status_reason IN ({placeholders})")
    params.extend(reasons)
    scope: dict[str, str] = {}
    if domain:
        selected_domain = _normalized_domain(domain)
        where.append("(lower(d.domain) = ? OR lower(d.domain) LIKE ?)")
        params.extend((selected_domain, f"%.{selected_domain}"))
        scope["domain"] = selected_domain
    if document_id:
        selected_document = str(document_id).strip()
        where.append("m.document_id = ?")
        params.append(selected_document)
        scope["document_id"] = selected_document
    if snapshot_id:
        selected_snapshot = str(snapshot_id).strip()
        where.append("m.snapshot_id = ?")
        params.append(selected_snapshot)
        scope["snapshot_id"] = selected_snapshot

    selected_limit = max(1, min(int(limit), 1000))
    params.append(selected_limit)
    rows = conn.execute(
        f"""
        SELECT m.id, m.capture_status, m.status_reason
        FROM media_artifacts m
        LEFT JOIN documents d ON d.id = m.document_id
        WHERE {' AND '.join(where)}
        ORDER BY m.created_at, m.id
        LIMIT ?
        """,
        params,
    ).fetchall()
    artifact_ids = [str(row["id"]) for row in rows]
    updated = 0
    if execute:
        with conn:
            for artifact_id in artifact_ids:
                changed = int(
                    conn.execute(
                        """
                        UPDATE media_artifacts
                        SET capture_status = 'referenced', status_reason = NULL
                        WHERE id = ? AND capture_status = 'skipped'
                        """,
                        (artifact_id,),
                    ).rowcount
                    or 0
                )
                updated += changed
                if changed:
                    ensure_media_fetch_task(
                        conn,
                        artifact_id,
                        worker_kind=worker_kind,
                        status="pending",
                        force_reset=True,
                    )
            audit(
                conn,
                "media-budget-requeue",
                {
                    "reason": normalized_reason,
                    "scope_kinds": sorted(scope),
                    "selected": len(artifact_ids),
                    "updated": updated,
                    "limit": selected_limit,
                },
            )
    return {
        "dry_run": not execute,
        "reason": normalized_reason,
        "scope": scope,
        "limit": selected_limit,
        "selected": len(artifact_ids),
        "updated": updated,
        "sample_artifact_ids": artifact_ids[:20],
    }


__all__ = ["reconcile_cdp_blob_coverage", "reconcile_stored_media_tasks", "requeue_media_artifacts"]
