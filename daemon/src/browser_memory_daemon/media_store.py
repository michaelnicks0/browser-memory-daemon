from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from .blob_lifecycle import process_blob_tombstones, register_committed_blob, tombstone_blob
from .blob_store import BlobStore, StagedBlob, prefer_relative_locator
from .config import RuntimeConfig
from .media_storage import (
    choose_media_blob_destination,
    media_blob_store_and_locator,
    release_media_spool_reservation,
    reserve_media_spool,
)
from .media_tasks import ensure_media_fetch_task, mark_media_fetch_task
from .storage_paths import storage_stem, validate_media_artifact_id


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


def stored_media_bytes(
    conn: sqlite3.Connection,
    where_sql: str = "",
    params: tuple[Any, ...] = (),
    *,
    exclude_artifact_id: str | None = None,
) -> int:
    exclusion = " AND id != ?" if exclude_artifact_id else ""
    query_params = (*params, exclude_artifact_id) if exclude_artifact_id else params
    row = conn.execute(
        f"SELECT COALESCE(SUM(byte_size), 0) AS n FROM media_artifacts WHERE capture_status IN ('stored', 'purging', 'missing') AND (COALESCE(blob_locator, '') != '' OR COALESCE(spool_locator, '') != '' OR COALESCE(file_path, '') != '') {where_sql}{exclusion}",
        query_params,
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
    exclude_artifact_id: str | None = None,
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
    if exclude_artifact_id:
        where.append("m.id != ?")
        params.append(exclude_artifact_id)
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
    artifact_id: str | None = None,
) -> tuple[bool, str]:
    if candidate_bytes > config.max_media_artifact_bytes:
        return False, "media-too-large"
    if priority < config.media_min_priority_to_store:
        return False, "priority-below-threshold"
    if not _mime_allowed(config, mime_type, media_type):
        return False, "disallowed-mime"
    if config.max_media_bytes_per_snapshot > 0:
        current = stored_media_bytes(
            conn,
            "AND snapshot_id = ?",
            (snapshot_id,),
            exclude_artifact_id=artifact_id,
        )
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
                exclude_artifact_id=artifact_id,
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
            exclude_artifact_id=artifact_id,
        )
        if int(eviction.get("remaining") or 0) + candidate_bytes > config.max_media_cache_bytes:
            return False, "media-cache-budget"
    return True, ""


@dataclass(frozen=True)
class MediaArtifactWrite:
    artifact_id: str
    generated_artifact_id: str
    artifact_id_provided: bool
    document_id: str
    snapshot_id: str
    visit_id: str | None
    media_type: str
    role: str
    source_url: str
    normalized_source_url: str
    page_url: str
    alt_text: str
    title: str
    mime_type: str
    width: int | None
    height: int | None
    duration_seconds: float | None
    capture_status: str
    status_reason: str
    metadata_json: str
    priority: int
    content: bytes
    file_extension: str
    fetch_supported: bool


@dataclass(frozen=True)
class _PreparedMediaBlob:
    store: BlobStore
    staged: StagedBlob
    locator: str
    tier: str
    reservation_id: str | None


def media_fetch_supported(source_url: str) -> bool:
    try:
        return urlsplit(source_url).scheme in {"http", "https", "data"}
    except Exception:
        return False


def _existing_media_artifact(conn: sqlite3.Connection, artifact_id: str) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        conn.execute(
            """
            SELECT document_id, snapshot_id, source_url, byte_size, file_path, blob_locator,
                   storage_tier, spool_locator, capture_status
            FROM media_artifacts
            WHERE id = ?
            """,
            (artifact_id,),
        ).fetchone(),
    )


def _validate_media_owner(
    conn: sqlite3.Connection,
    write: MediaArtifactWrite,
    existing: sqlite3.Row | None,
) -> None:
    snap = conn.execute("SELECT id, document_id FROM snapshots WHERE id = ?", (write.snapshot_id,)).fetchone()
    if not snap:
        raise KeyError("snapshot not found")
    if snap["document_id"] != write.document_id:
        raise ValueError("document_id does not match snapshot")
    if write.artifact_id_provided and not existing and write.artifact_id != write.generated_artifact_id:
        raise ValueError("artifact_id does not match media reference")
    if existing:
        if existing["capture_status"] == "purging":
            raise ValueError("media artifact deletion is pending")
        if existing["document_id"] != write.document_id or existing["snapshot_id"] != write.snapshot_id:
            raise ValueError("artifact_id ownership mismatch")
        if existing["source_url"] and existing["source_url"] != write.source_url:
            raise ValueError("artifact_id source mismatch")


def _prepare_media_blob(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    artifact_id: str,
    content: bytes,
    file_extension: str,
) -> _PreparedMediaBlob:
    artifact_id = validate_media_artifact_id(artifact_id)
    if not file_extension.startswith(".") or "/" in file_extension or "\\" in file_extension:
        raise ValueError("invalid media file extension")
    destination = choose_media_blob_destination(config)
    reservation_id: str | None = None
    if destination.tier == "spool":
        reservation = reserve_media_spool(conn, config, artifact_id=artifact_id, reserved_bytes=len(content))
        reservation_id = str(reservation["reservation_id"])
    try:
        staged = destination.store.stage(content, expected_size=len(content))
    except BaseException:
        if reservation_id is not None:
            release_media_spool_reservation(conn, reservation_id)
        raise
    locator = f"{storage_stem('media', artifact_id)}-{uuid.uuid4().hex}{file_extension}"
    return _PreparedMediaBlob(destination.store, staged, locator, destination.tier, reservation_id)


def _start_artifact_transaction(conn: sqlite3.Connection) -> str | None:
    if conn.in_transaction:
        savepoint = f"media_artifact_{uuid.uuid4().hex}"
        conn.execute(f"SAVEPOINT {savepoint}")
        return savepoint
    conn.execute("BEGIN IMMEDIATE")
    return None


def _finish_artifact_transaction(conn: sqlite3.Connection, savepoint: str | None) -> None:
    if savepoint is None:
        conn.commit()
    else:
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")


def _rollback_artifact_transaction(conn: sqlite3.Connection, savepoint: str | None) -> None:
    if savepoint is None:
        conn.rollback()
    else:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")


def _release_failed_reservation(conn: sqlite3.Connection, reservation_id: str | None) -> None:
    if reservation_id is None:
        return
    try:
        release_media_spool_reservation(conn, reservation_id)
    except sqlite3.Error:
        pass


def persist_media_artifact(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    write: MediaArtifactWrite,
) -> dict[str, Any]:
    artifact_id = validate_media_artifact_id(write.artifact_id)
    existing = _existing_media_artifact(conn, artifact_id)
    _validate_media_owner(conn, write, existing)

    content = write.content
    status = write.capture_status
    reason = write.status_reason
    if content:
        allowed, gate_reason = media_storage_allowed(
            conn,
            config,
            document_id=write.document_id,
            snapshot_id=write.snapshot_id,
            media_type=write.media_type,
            mime_type=write.mime_type,
            candidate_bytes=len(content),
            priority=write.priority,
            artifact_id=artifact_id,
        )
        if not allowed:
            content = b""
            status = "skipped"
            reason = gate_reason
        else:
            status = "stored"
    elif status == "stored":
        status = "metadata-only"

    prepared = (
        _prepare_media_blob(
            conn,
            config,
            artifact_id=artifact_id,
            content=content,
            file_extension=write.file_extension,
        )
        if content
        else None
    )
    target_path: Path | None = None
    replacement_operation: str | None = None
    result_tier = str(existing["storage_tier"] or "media-root") if existing else "media-root"
    result_status = status
    result_reason = reason
    result_byte_size = len(content) if content else 0
    had_transaction = conn.in_transaction
    savepoint: str | None = None
    transaction_started = False
    try:
        savepoint = _start_artifact_transaction(conn)
        transaction_started = True
        existing = _existing_media_artifact(conn, artifact_id)
        _validate_media_owner(conn, write, existing)
        previous_locator: str | None = None
        previous_tier = "media-root"
        if prepared is not None and existing:
            previous_tier = str(existing["storage_tier"] or "media-root")
            previous_locator = (
                prefer_relative_locator(existing["spool_locator"], existing["file_path"])
                if previous_tier == "spool"
                else prefer_relative_locator(existing["blob_locator"], existing["file_path"])
            )
        file_path = ""
        blob_locator = ""
        spool_locator = ""
        content_sha256 = ""
        byte_size = len(content) if content else None
        storage_tier = "media-root"
        if prepared is not None:
            target_path = prepared.store.commit(prepared.staged, prepared.locator)
            content_sha256 = prepared.staged.sha256
            file_path = str(target_path)
            storage_tier = prepared.tier
            result_tier = storage_tier
            if storage_tier == "spool":
                spool_locator = prepared.locator
            else:
                blob_locator = prepared.locator
            if previous_locator and (previous_tier != storage_tier or str(previous_locator) != prepared.locator):
                replacement_operation = f"replace-{uuid.uuid4().hex}"

        conn.execute(
            """
            INSERT INTO media_artifacts(
              id, document_id, snapshot_id, visit_id, media_type, role, source_url,
              normalized_source_url, page_url, alt_text, title, mime_type, width, height,
              duration_seconds, byte_size, content_sha256, file_path, blob_locator, storage_tier,
              spool_locator, capture_status, status_reason, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              visit_id=COALESCE(excluded.visit_id, media_artifacts.visit_id),
              alt_text=excluded.alt_text,
              title=excluded.title,
              mime_type=COALESCE(NULLIF(excluded.mime_type, ''), media_artifacts.mime_type),
              width=COALESCE(excluded.width, media_artifacts.width),
              height=COALESCE(excluded.height, media_artifacts.height),
              duration_seconds=COALESCE(excluded.duration_seconds, media_artifacts.duration_seconds),
              byte_size=COALESCE(excluded.byte_size, media_artifacts.byte_size),
              content_sha256=COALESCE(NULLIF(excluded.content_sha256, ''), media_artifacts.content_sha256),
              file_path=CASE WHEN excluded.file_path != '' THEN excluded.file_path ELSE media_artifacts.file_path END,
              blob_locator=CASE
                WHEN excluded.file_path != '' THEN NULLIF(excluded.blob_locator, '')
                ELSE media_artifacts.blob_locator
              END,
              storage_tier=CASE
                WHEN excluded.file_path != '' THEN excluded.storage_tier
                ELSE media_artifacts.storage_tier
              END,
              spool_locator=CASE
                WHEN excluded.file_path != '' THEN NULLIF(excluded.spool_locator, '')
                ELSE media_artifacts.spool_locator
              END,
              capture_status=CASE
                WHEN media_artifacts.capture_status = 'stored' AND excluded.capture_status != 'stored' THEN media_artifacts.capture_status
                ELSE excluded.capture_status
              END,
              status_reason=CASE
                WHEN media_artifacts.capture_status = 'stored' AND excluded.capture_status != 'stored' THEN media_artifacts.status_reason
                ELSE excluded.status_reason
              END,
              metadata_json=excluded.metadata_json
            """,
            (
                artifact_id,
                write.document_id,
                write.snapshot_id,
                write.visit_id,
                write.media_type,
                write.role,
                write.source_url,
                write.normalized_source_url,
                write.page_url,
                write.alt_text,
                write.title,
                write.mime_type,
                write.width,
                write.height,
                write.duration_seconds,
                byte_size,
                content_sha256,
                file_path,
                blob_locator or None,
                storage_tier,
                spool_locator or None,
                status,
                reason or None,
                write.metadata_json,
            ),
        )
        persisted = conn.execute(
            "SELECT capture_status, status_reason, byte_size, storage_tier FROM media_artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
        if persisted is None:
            raise RuntimeError("media artifact persistence did not produce a row")
        result_status = str(persisted["capture_status"])
        result_reason = str(persisted["status_reason"] or "")
        result_byte_size = int(persisted["byte_size"] or 0)
        result_tier = str(persisted["storage_tier"] or "media-root")
        if prepared is not None and prepared.reservation_id is not None:
            conn.execute(
                "DELETE FROM media_spool_reservations WHERE reservation_id = ?",
                (prepared.reservation_id,),
            )
        if prepared is not None:
            current_locator = spool_locator if storage_tier == "spool" else blob_locator
            register_committed_blob(
                conn,
                owner_kind="media-artifact",
                owner_id=artifact_id,
                storage_tier=storage_tier,
                locator=current_locator,
                byte_size=byte_size,
                content_sha256=content_sha256,
            )
            if replacement_operation and previous_locator:
                tombstone_blob(
                    conn,
                    operation_id=replacement_operation,
                    owner_kind="media-artifact",
                    owner_id=artifact_id,
                    storage_tier=previous_tier,
                    locator=str(previous_locator),
                    reason="media-replaced",
                )
        if result_status == "stored":
            mark_media_fetch_task(conn, artifact_id, worker_kind="daemon-public", status="succeeded")
            mark_media_fetch_task(conn, artifact_id, worker_kind="browser", status="succeeded")
        elif result_status in {"skipped", "expired"}:
            mark_media_fetch_task(
                conn,
                artifact_id,
                worker_kind="daemon-public",
                status="skipped",
                error=result_reason,
            )
        elif result_status in {"referenced", "metadata-only", "queued", "retrying"} and write.fetch_supported:
            ensure_media_fetch_task(
                conn,
                artifact_id,
                worker_kind="daemon-public",
                priority=write.priority,
            )
        _finish_artifact_transaction(conn, savepoint)
    except BaseException:
        if transaction_started:
            _rollback_artifact_transaction(conn, savepoint)
        elif not had_transaction and conn.in_transaction:
            conn.rollback()
        if prepared is not None:
            if target_path is not None or prepared.store.exists(prepared.locator):
                prepared.store.delete(prepared.locator)
            else:
                try:
                    prepared.store.abort(prepared.staged)
                except RuntimeError:
                    pass
        if prepared is not None:
            _release_failed_reservation(conn, prepared.reservation_id)
        raise

    if replacement_operation:
        process_blob_tombstones(conn, config, operation_id=replacement_operation)
    return {
        "stored": result_status == "stored",
        "artifact_id": artifact_id,
        "snapshot_id": write.snapshot_id,
        "document_id": write.document_id,
        "media_type": write.media_type,
        "role": write.role,
        "capture_status": result_status,
        "status_reason": result_reason,
        "byte_size": result_byte_size,
        "storage_tier": result_tier,
    }


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _purge_scope_sql(scope: dict[str, Any]) -> tuple[list[str], list[Any], str]:
    rehydrate_only = bool(scope.get("rehydrate_only") or scope.get("rehydrateOnly"))
    where = (
        [
            "m.capture_status = 'purged'",
            "COALESCE(m.blob_locator, '') = '' AND COALESCE(m.spool_locator, '') = '' AND COALESCE(m.file_path, '') = ''",
        ]
        if rehydrate_only
        else [
            "COALESCE(m.blob_locator, '') != '' OR COALESCE(m.spool_locator, '') != '' OR COALESCE(m.file_path, '') != ''"
        ]
    )
    params: list[Any] = []
    labels: list[str] = []
    domain = str(scope.get("domain") or "").lower().strip().lstrip(".")
    if domain:
        where.append("(lower(d.domain) = ? OR lower(d.domain) LIKE ?)")
        params.extend([domain, f"%.{domain}"])
        labels.append(f"domain:{domain}")
    document_id = str(scope.get("document_id") or scope.get("documentId") or "").strip()
    if document_id:
        where.append("m.document_id = ?")
        params.append(document_id)
        labels.append(f"document:{document_id}")
    snapshot_id = str(scope.get("snapshot_id") or scope.get("snapshotId") or "").strip()
    if snapshot_id:
        where.append("m.snapshot_id = ?")
        params.append(snapshot_id)
        labels.append(f"snapshot:{snapshot_id}")
    older_than = str(scope.get("older_than") or scope.get("olderThan") or "").strip()
    if older_than:
        where.append("m.created_at < ?")
        params.append(older_than)
        labels.append(f"older-than:{older_than}")
    if not labels:
        labels.append("all")
    return where, params, ";".join(labels)


def purge_media_cache(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    scope: dict[str, Any],
) -> dict[str, Any]:
    dry_run = bool(scope.get("dry_run") if "dry_run" in scope else scope.get("dryRun", True))
    rehydrate = bool(scope.get("rehydrate") or False)
    rehydrate_only = bool(scope.get("rehydrate_only") or scope.get("rehydrateOnly"))
    max_bytes_to_purge = _optional_nonnegative_int(
        scope.get("max_bytes_to_purge") or scope.get("maxBytesToPurge")
    )
    where, params, label = _purge_scope_sql(scope)
    rows = conn.execute(
        f"""
        SELECT m.id, m.file_path, m.blob_locator, m.storage_tier, m.spool_locator,
               m.byte_size, m.source_url, m.capture_status
        FROM media_artifacts m
        LEFT JOIN documents d ON d.id = m.document_id
        WHERE {' AND '.join(where)}
        ORDER BY m.created_at ASC, m.id
        """,
        params,
    ).fetchall()
    selected: list[tuple[sqlite3.Row, BlobStore | None, str, int]] = []
    selected_bytes = 0
    skipped_out_of_root = 0
    skipped_out_of_root_ids: list[str] = []
    for row in rows:
        if rehydrate_only:
            selected.append((row, None, "", 0))
            continue
        store, locator, _tier_status = media_blob_store_and_locator(config, dict(row))
        if store is None or not locator:
            skipped_out_of_root += 1
            if len(skipped_out_of_root_ids) < 20:
                skipped_out_of_root_ids.append(str(row["id"]))
            continue
        resolution = store.resolve(locator, require_file=False)
        if resolution.status in {"outside-root", "invalid", "empty"} or resolution.path is None:
            skipped_out_of_root += 1
            if len(skipped_out_of_root_ids) < 20:
                skipped_out_of_root_ids.append(str(row["id"]))
            continue
        try:
            size = int(row["byte_size"] or (store.stat(locator).st_size if store.exists(locator) else 0))
        except (OSError, RuntimeError):
            size = int(row["byte_size"] or 0)
        if max_bytes_to_purge is not None and selected_bytes + size > max_bytes_to_purge:
            break
        selected.append((row, store, str(locator), size))
        selected_bytes += size
    purged = 0
    missing = 0
    pending_deletions = 0
    operation_id = f"purge-{uuid.uuid4().hex}"
    if not dry_run:
        with conn:
            for row, selected_store, raw_path, _size in selected:
                if rehydrate_only:
                    if media_fetch_supported(str(row["source_url"] or "")):
                        ensure_media_fetch_task(
                            conn,
                            str(row["id"]),
                            worker_kind="daemon-public",
                            status="pending",
                            force_reset=True,
                        )
                    continue
                if selected_store is None:
                    continue
                tombstone_blob(
                    conn,
                    operation_id=operation_id,
                    owner_kind="media-artifact",
                    owner_id=str(row["id"]),
                    storage_tier=str(row["storage_tier"] or "media-root"),
                    locator=raw_path,
                    reason=f"cache-purged:{label}",
                    byte_size=int(row["byte_size"]) if row["byte_size"] is not None else None,
                )
                conn.execute(
                    """
                    UPDATE media_artifacts
                    SET capture_status = 'purging', status_reason = ?
                    WHERE id = ?
                    """,
                    (f"cache-purged:{label}", row["id"]),
                )
        if not rehydrate_only and selected:
            outcome = process_blob_tombstones(conn, config, operation_id=operation_id)
            purged = int(outcome["deleted"])
            missing = int(outcome["missing"]) + int(outcome["failed"]) + int(outcome["blocked"])
            pending_deletions = int(outcome["pending"])
            if rehydrate:
                with conn:
                    for row, _store, _path, _size in selected:
                        current = conn.execute(
                            "SELECT capture_status FROM media_artifacts WHERE id = ?",
                            (row["id"],),
                        ).fetchone()
                        if (
                            current
                            and current["capture_status"] == "purged"
                            and media_fetch_supported(str(row["source_url"] or ""))
                        ):
                            ensure_media_fetch_task(
                                conn,
                                str(row["id"]),
                                worker_kind="daemon-public",
                                status="pending",
                                force_reset=True,
                            )
    return {
        "dry_run": dry_run,
        "rehydrate": rehydrate,
        "rehydrate_only": rehydrate_only,
        "scope": scope,
        "selected": len(selected),
        "purged": purged,
        "missing_files": missing,
        "pending_deletions": pending_deletions,
        "skipped_out_of_root": skipped_out_of_root,
        "bytes": selected_bytes,
        "sample_artifact_ids": [row["id"] for row, _store, _path, _size in selected[:20]],
        "sample_out_of_root_artifact_ids": skipped_out_of_root_ids,
    }


def _media_file_resolution(
    config: RuntimeConfig | None,
    row: dict[str, Any],
) -> tuple[Path | None, str, str]:
    if not config:
        return None, "config-required", "unresolved"
    if str(row.get("capture_status") or "") in {"purging", "purged", "missing"}:
        return None, str(row.get("capture_status")), "unavailable"
    store, locator, tier_status = media_blob_store_and_locator(config, row)
    if store is None:
        return None, tier_status, "unresolved"
    resolution = store.resolve(locator, require_file=True)
    tier = str(row.get("storage_tier") or "media-root")
    if tier == "spool":
        kind = "spool-relative" if row.get("spool_locator") not in {None, ""} else "legacy-absolute"
    else:
        kind = "relative" if row.get("blob_locator") not in {None, ""} else "legacy-absolute"
    return resolution.path, resolution.status, kind


def _media_observation_provenance(
    conn: sqlite3.Connection,
    artifact_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT mao.observation_id, mao.provenance_quality AS link_provenance_quality,
               mao.observed_at, o.navigation_id, o.visit_id, o.observed_url,
               o.capture_reason, o.capture_method, o.extraction_version,
               o.provenance_quality AS observation_provenance_quality
        FROM media_artifact_observations mao
        JOIN capture_observations o ON o.id = mao.observation_id
        WHERE mao.artifact_id = ?
        ORDER BY mao.observed_at, mao.observation_id
        """,
        (artifact_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def media_artifact(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    artifact_id: str,
) -> dict[str, Any]:
    artifact_id = validate_media_artifact_id(artifact_id)
    row = conn.execute("SELECT * FROM media_artifacts WHERE id = ?", (artifact_id,)).fetchone()
    if not row:
        raise KeyError("media artifact not found")
    value = dict(row)
    resolved, status, kind = _media_file_resolution(config, value)
    value["has_file"] = resolved is not None
    value["file_path_status"] = status
    value["file_locator_kind"] = kind
    if resolved is not None:
        value["resolved_file_path"] = str(resolved)
    value["observations"] = _media_observation_provenance(conn, artifact_id)
    return value


def _artifact_list_item(
    conn: sqlite3.Connection,
    config: RuntimeConfig | None,
    row: sqlite3.Row,
) -> dict[str, Any]:
    item = dict(row)
    resolved, status, kind = _media_file_resolution(config, item)
    item.pop("file_path", None)
    item.pop("blob_locator", None)
    item.pop("spool_locator", None)
    item["has_file"] = resolved is not None
    item["file_path_status"] = status
    item["file_locator_kind"] = kind
    if item["has_file"]:
        item["content_url"] = f"/media-artifacts/{item['id']}"
    item["observations"] = _media_observation_provenance(conn, str(item["id"]))
    return item


def media_artifacts_for_snapshot(
    conn: sqlite3.Connection,
    snapshot_id: str,
    config: RuntimeConfig | None = None,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, document_id, snapshot_id, visit_id, page_url,
               media_type, role, source_url, normalized_source_url, alt_text, title, mime_type,
               width, height, duration_seconds, byte_size, capture_status, status_reason,
               file_path, blob_locator, storage_tier, spool_locator, created_at
        FROM media_artifacts
        WHERE snapshot_id = ?
        ORDER BY media_type, role, created_at, id
        """,
        (snapshot_id,),
    ).fetchall()
    return [_artifact_list_item(conn, config, row) for row in rows]


def media_artifacts_for_document(
    conn: sqlite3.Connection,
    document_id: str,
    config: RuntimeConfig | None = None,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, document_id, snapshot_id, visit_id, page_url,
               media_type, role, source_url, normalized_source_url, alt_text, title,
               mime_type, width, height, duration_seconds, byte_size, capture_status, status_reason,
               file_path, blob_locator, storage_tier, spool_locator, created_at
        FROM media_artifacts
        WHERE document_id = ?
        ORDER BY created_at DESC, id
        LIMIT ?
        """,
        (document_id, limit),
    ).fetchall()
    return [_artifact_list_item(conn, config, row) for row in rows]
