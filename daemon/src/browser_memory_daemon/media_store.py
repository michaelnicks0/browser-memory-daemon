from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from .blob_lifecycle import process_blob_tombstones, tombstone_blob
from .config import RuntimeConfig
from .media_storage import media_blob_store_and_locator


def _mime_allowed(config: RuntimeConfig, mime_type: str, media_type: str) -> bool:
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if not mime:
        return True
    if media_type == "image" and not mime.startswith("image/"):
        return False
    if media_type == "video" and not (mime.startswith("video/") or mime.startswith("audio/")):
        return False
    if media_type == "audio" and not mime.startswith("audio/"):
        return False
    allowlist = tuple(item.lower().strip() for item in config.media_mime_allowlist if item.strip())
    if not allowlist:
        return True
    return any(mime.startswith(item) if item.endswith("/") else mime == item for item in allowlist)


def stored_media_bytes(conn: sqlite3.Connection, where_sql: str = "", params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(
        f"SELECT COALESCE(SUM(byte_size), 0) AS n FROM media_artifacts WHERE capture_status IN ('stored', 'purging', 'missing') AND (COALESCE(blob_locator, '') != '' OR COALESCE(spool_locator, '') != '' OR COALESCE(file_path, '') != '') {where_sql}",
        params,
    ).fetchone()
    return int(row["n"] if row else 0)


def _evict_oldest_media_rows(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    rows: list[sqlite3.Row],
    *,
    bytes_to_free: int,
    reason: str,
) -> dict[str, int]:
    selected_bytes = 0
    skipped_paths = 0
    selected: list[tuple[sqlite3.Row, str]] = []
    for row in rows:
        if bytes_to_free > 0 and selected_bytes >= bytes_to_free:
            break
        store, locator, _tier_status = media_blob_store_and_locator(config, dict(row))
        if store is None or not locator:
            skipped_paths += 1
            continue
        resolution = store.resolve(locator, require_file=False)
        if resolution.status in {"outside-root", "invalid", "empty"} or resolution.path is None:
            skipped_paths += 1
            continue
        size = int(row["byte_size"] or 0)
        if store.exists(locator) and size <= 0:
            try:
                size = int(store.stat(locator).st_size)
            except (OSError, RuntimeError):
                size = 0
        selected_bytes += max(0, size)
        selected.append((row, str(locator)))
    operation_id = f"evict-{uuid.uuid4().hex}"
    if selected:
        with conn:
            for row, locator in selected:
                tombstone_blob(
                    conn,
                    operation_id=operation_id,
                    owner_kind="media-artifact",
                    owner_id=str(row["id"]),
                    storage_tier=str(row["storage_tier"] or "media-root"),
                    locator=locator,
                    reason=reason,
                    byte_size=int(row["byte_size"]) if row["byte_size"] is not None else None,
                )
            conn.executemany(
                """
                UPDATE media_artifacts
                SET capture_status = 'purging', status_reason = ?
                WHERE id = ?
                """,
                [(reason, row["id"]) for row, _locator in selected],
            )
    outcome = (
        process_blob_tombstones(conn, config, operation_id=operation_id)
        if selected
        else {"deleted": 0, "missing": 0, "failed": 0, "blocked": 0, "pending": 0}
    )
    completed = {
        str(row["owner_id"]): int(row["byte_size"] or 0)
        for row in conn.execute(
            """
            SELECT owner_id, byte_size FROM blob_storage_records
            WHERE operation_id = ? AND state IN ('deleted', 'missing')
            """,
            (operation_id,),
        ).fetchall()
    }
    return {
        "evicted": len(completed),
        "missing_files": int(outcome["missing"]) + int(outcome["failed"]) + int(outcome["blocked"]),
        "skipped_paths": skipped_paths,
        "bytes": sum(completed.values()),
        "pending_deletions": int(outcome["pending"]),
    }


def _evict_oldest_media_to_fit(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    candidate_bytes: int,
    max_bytes: int,
    reason: str,
    domain: str | None = None,
) -> dict[str, int]:
    if max_bytes <= 0 or candidate_bytes <= 0:
        return {"evicted": 0, "missing_files": 0, "skipped_paths": 0, "bytes": 0, "current": 0, "remaining": 0}
    join_sql = ""
    where = [
        "m.capture_status IN ('stored', 'purging', 'missing')",
        "(COALESCE(m.blob_locator, '') != '' OR COALESCE(m.spool_locator, '') != '' OR COALESCE(m.file_path, '') != '')",
    ]
    params: list[Any] = []
    if domain:
        join_sql = "JOIN documents d ON d.id = m.document_id"
        where.append("d.domain = ?")
        params.append(domain)
    current_row = conn.execute(
        f"""
        SELECT COALESCE(SUM(m.byte_size), 0) AS n
        FROM media_artifacts m
        {join_sql}
        WHERE {' AND '.join(where)}
        """,
        params,
    ).fetchone()
    current = int(current_row["n"] if current_row else 0)
    overflow = current + int(candidate_bytes) - int(max_bytes)
    if overflow <= 0:
        return {"evicted": 0, "missing_files": 0, "skipped_paths": 0, "bytes": 0, "current": current, "remaining": current}
    rows = conn.execute(
        f"""
        SELECT m.id, m.file_path, m.blob_locator, m.storage_tier, m.spool_locator,
               m.byte_size, m.created_at
        FROM media_artifacts m
        {join_sql}
        WHERE {' AND '.join(where)}
        ORDER BY m.created_at ASC, m.id
        """,
        params,
    ).fetchall()
    result = _evict_oldest_media_rows(conn, config, rows, bytes_to_free=overflow, reason=reason)
    result["current"] = current
    result["remaining"] = max(0, current - int(result["bytes"]))
    return result


def media_storage_allowed(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    document_id: str,
    snapshot_id: str,
    media_type: str,
    mime_type: str,
    candidate_bytes: int,
    priority: int = 50,
) -> tuple[bool, str]:
    if candidate_bytes > config.max_media_artifact_bytes:
        return False, "media-too-large"
    if priority < config.media_min_priority_to_store:
        return False, "priority-below-threshold"
    if not _mime_allowed(config, mime_type, media_type):
        return False, "disallowed-mime"
    if config.max_media_bytes_per_snapshot > 0:
        current = stored_media_bytes(conn, "AND snapshot_id = ?", (snapshot_id,))
        if current + candidate_bytes > config.max_media_bytes_per_snapshot:
            return False, "snapshot-media-budget"
    if config.max_media_bytes_per_domain > 0:
        doc = conn.execute("SELECT domain FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc and doc["domain"]:
            domain = str(doc["domain"])
            eviction = _evict_oldest_media_to_fit(
                conn,
                config,
                candidate_bytes=candidate_bytes,
                max_bytes=config.max_media_bytes_per_domain,
                reason="cache-evicted:domain-oldest",
                domain=domain,
            )
            if int(eviction.get("remaining") or 0) + candidate_bytes > config.max_media_bytes_per_domain:
                return False, "domain-media-budget"
    if config.max_media_cache_bytes > 0:
        eviction = _evict_oldest_media_to_fit(
            conn,
            config,
            candidate_bytes=candidate_bytes,
            max_bytes=config.max_media_cache_bytes,
            reason="cache-evicted:global-oldest",
        )
        if int(eviction.get("remaining") or 0) + candidate_bytes > config.max_media_cache_bytes:
            return False, "media-cache-budget"
    return True, ""
