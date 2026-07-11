from __future__ import annotations

import hashlib
import inspect
import sqlite3
from datetime import UTC, datetime

NAME = "normalize-historical-media-state"
SQL = ""
DESTRUCTIVE = False
SCHEMA_FINGERPRINT = "ab5053b91c27082493d59f15391c2245c1e0d2719c06837fc7866b20e88b7139"

_PERMANENT_SKIP_REASONS = {
    "unsupported-media-url-scheme",
    "invalid-data-url",
    "invalid-data-url-payload",
    "media-too-large",
    "non-media-content-type",
    "disallowed-mime",
    "snapshot-media-budget",
    "domain-media-budget",
    "media-cache-budget",
    "priority-below-threshold",
    "fetch-blocked-private-address",
    "fetch-blocked-private-host",
    "fetch-blocked-reserved-address",
    "fetch-blocked-url-scheme",
    "fetch-redirect-loop",
    "fetch-redirect-missing-location",
    "fetch-too-many-redirects",
}


def _task_id(artifact_id: str, worker_kind: str = "daemon-public") -> str:
    digest = hashlib.sha256(f"{worker_kind}:{artifact_id}".encode()).hexdigest()[:32]
    return f"mtask_{digest}"


def _historical_status(reason: str, *, source_url: str, media_type: str) -> str:
    normalized = str(reason or "").strip()
    lower = normalized.lower()
    source_scheme = source_url.split(":", 1)[0].lower() if ":" in source_url else ""
    if normalized in _PERMANENT_SKIP_REASONS:
        if lower == "non-media-content-type" and media_type.lower() == "video":
            return "referenced"
        return "skipped"
    if source_scheme == "data" and lower in {"failed to fetch", "invalid-data-url", "invalid-data-url-payload"}:
        return "skipped"
    if lower.startswith(("fetch-status-401", "fetch-status-403", "fetch-status-404", "fetch-status-410")):
        return "expired"
    if lower.startswith(("fetch-status-429", "fetch-timeout", "fetch-error-")):
        return "retrying"
    if lower.startswith("hls-"):
        return "referenced"
    if lower in {"empty-media-response", "failed to fetch"}:
        return "retrying"
    return "failed"


def _reset_task(conn: sqlite3.Connection, artifact_id: str, *, priority: int = 50) -> None:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    updated = conn.execute(
        """
        UPDATE media_fetch_tasks
        SET status = 'pending', priority = MAX(priority, ?), attempts = 0,
            next_attempt_at = NULL, lease_owner = NULL, lease_until = NULL,
            last_error = NULL, updated_at = ?
        WHERE artifact_id = ? AND worker_kind = 'daemon-public'
        """,
        (priority, now, artifact_id),
    )
    if int(updated.rowcount or 0) > 0:
        return
    conn.execute(
        """
        INSERT INTO media_fetch_tasks(
          id, artifact_id, worker_kind, status, priority, attempts, max_attempts,
          next_attempt_at, lease_owner, lease_until, last_error, updated_at
        ) VALUES (?, ?, 'daemon-public', 'pending', ?, 0, 5, NULL, NULL, NULL, NULL, ?)
        """,
        (_task_id(artifact_id), artifact_id, priority, now),
    )


def apply(conn: sqlite3.Connection) -> None:
    failed_rows = conn.execute(
        """
        SELECT id, source_url, media_type, status_reason
        FROM media_artifacts
        WHERE capture_status = 'failed'
        """
    ).fetchall()
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for row in failed_rows:
        reason = str(row["status_reason"] or "")
        status = _historical_status(
            reason,
            source_url=str(row["source_url"] or ""),
            media_type=str(row["media_type"] or ""),
        )
        if status == "failed":
            continue
        conn.execute(
            "UPDATE media_artifacts SET capture_status = ?, status_reason = COALESCE(status_reason, ?) WHERE id = ?",
            (status, reason or status, row["id"]),
        )
        conn.execute(
            """
            UPDATE media_fetch_tasks
            SET status = ?, next_attempt_at = NULL, lease_owner = NULL, lease_until = NULL,
                last_error = NULLIF(?, ''), updated_at = ?
            WHERE artifact_id = ? AND worker_kind = 'daemon-public'
            """,
            ("retrying" if status == "retrying" else "skipped", reason or status, now, row["id"]),
        )

    conn.execute(
        """
        UPDATE media_artifacts
        SET capture_status = 'referenced', status_reason = NULL
        WHERE media_type = 'video'
          AND capture_status = 'skipped'
          AND status_reason = 'unsupported-media-url-scheme'
          AND source_url LIKE 'blob:%'
        """
    )

    requeue_rows = conn.execute(
        """
        SELECT id, COALESCE(json_extract(metadata_json, '$.priority'), 50) AS priority
        FROM media_artifacts
        WHERE (
          media_type = 'video'
          AND capture_status = 'skipped'
          AND status_reason IN ('non-media-content-type', 'media-too-large', 'unsupported-media-url-scheme')
          AND lower(source_url) LIKE '%.m3u8%'
        ) OR (
          media_type = 'video'
          AND capture_status = 'referenced'
          AND status_reason = 'hls-audio-rendition'
          AND lower(source_url) LIKE '%.m3u8%'
        ) OR (
          media_type = 'video'
          AND capture_status = 'referenced'
          AND (status_reason IS NULL OR status_reason = '')
          AND lower(source_url) LIKE '%.m3u8%'
          AND (id LIKE 'media_cdp_%' OR json_extract(metadata_json, '$.cdp_recorder') = 1)
        )
        """
    ).fetchall()
    for row in requeue_rows:
        artifact_id = str(row["id"])
        conn.execute(
            "UPDATE media_artifacts SET capture_status = 'referenced', status_reason = NULL WHERE id = ?",
            (artifact_id,),
        )
        _reset_task(conn, artifact_id, priority=int(row["priority"] or 50))

    conn.execute(
        """
        UPDATE media_artifacts
        SET capture_status = 'referenced'
        WHERE media_type = 'video'
          AND capture_status = 'skipped'
          AND status_reason = 'non-media-content-type'
        """
    )

    conn.execute(
        """
        UPDATE media_artifacts
        SET status_reason = 'covered-by-cdp-recorder'
        WHERE media_type = 'video'
          AND capture_status = 'referenced'
          AND (status_reason IS NULL OR status_reason IN ('', 'opaque-browser-blob'))
          AND source_url LIKE 'blob:%'
          AND EXISTS (
            SELECT 1 FROM media_artifacts cdp
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
        """
    )
    conn.execute(
        """
        UPDATE media_artifacts
        SET status_reason = 'opaque-browser-blob'
        WHERE media_type = 'video'
          AND capture_status = 'referenced'
          AND (status_reason IS NULL OR status_reason = '')
          AND source_url LIKE 'blob:%'
        """
    )
    conn.execute(
        """
        UPDATE media_fetch_tasks
        SET status = 'succeeded', lease_owner = NULL, lease_until = NULL,
            last_error = NULL, updated_at = ?
        WHERE status IN ('pending', 'retrying', 'leased')
          AND artifact_id IN (
            SELECT id FROM media_artifacts
            WHERE capture_status = 'stored'
              AND (COALESCE(blob_locator, '') != '' OR COALESCE(spool_locator, '') != '' OR COALESCE(file_path, '') != '')
          )
        """,
        (now,),
    )


CHECKSUM_PAYLOAD = SQL + "\n" + inspect.getsource(_task_id) + inspect.getsource(_historical_status) + inspect.getsource(_reset_task) + inspect.getsource(apply)
