from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .blob_store import BlobStore, prefer_relative_locator
from .config import RuntimeConfig
from .media_storage import media_root_readiness

TERMINAL_BLOB_STATES = {"deleted", "missing"}
RETRYABLE_BLOB_STATES = {"tombstoned", "failed", "blocked"}


def _new_id() -> str:
    return f"blob-{uuid.uuid4().hex}"


def _store_for_tier(config: RuntimeConfig, storage_tier: str) -> tuple[BlobStore | None, str]:
    if storage_tier == "derivative":
        return BlobStore(config.clean_text_root), "ready"
    if storage_tier == "spool":
        if config.media_spool_root is None:
            return None, "spool-unconfigured"
        return BlobStore(config.media_spool_root), "ready"
    if storage_tier == "media-root":
        readiness = media_root_readiness(config)
        if not readiness.ok:
            return None, readiness.status
        return BlobStore(config.media_root), "ready"
    return None, "unknown-storage-tier"


def register_committed_blob(
    conn: sqlite3.Connection,
    *,
    owner_kind: str,
    owner_id: str,
    storage_tier: str,
    locator: str,
    byte_size: int | None = None,
    content_sha256: str | None = None,
) -> str:
    normalized_locator = str(locator or "").strip()
    if not normalized_locator:
        raise ValueError("committed blob locator is required")
    row = conn.execute(
        """
        SELECT id FROM blob_storage_records
        WHERE owner_kind = ? AND owner_id = ? AND storage_tier = ? AND locator = ?
        """,
        (owner_kind, owner_id, storage_tier, normalized_locator),
    ).fetchone()
    record_id = str(row["id"]) if row else _new_id()
    conn.execute(
        """
        INSERT INTO blob_storage_records(
          id, owner_kind, owner_id, storage_tier, locator,
          byte_size, content_sha256, state, operation_id, reason,
          attempts, last_error, updated_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'committed', NULL, NULL, 0, NULL,
                  strftime('%Y-%m-%dT%H:%M:%fZ','now'), NULL)
        ON CONFLICT(owner_kind, owner_id, storage_tier, locator) DO UPDATE SET
          byte_size=excluded.byte_size,
          content_sha256=excluded.content_sha256,
          state='committed',
          operation_id=NULL,
          reason=NULL,
          attempts=0,
          last_error=NULL,
          updated_at=excluded.updated_at,
          completed_at=NULL
        """,
        (
            record_id,
            owner_kind,
            owner_id,
            storage_tier,
            normalized_locator,
            byte_size,
            content_sha256 or None,
        ),
    )
    return record_id


def tombstone_blob(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    owner_kind: str,
    owner_id: str,
    storage_tier: str,
    locator: str,
    reason: str,
    byte_size: int | None = None,
    content_sha256: str | None = None,
) -> str:
    normalized_locator = str(locator or "").strip()
    if not normalized_locator:
        raise ValueError("tombstoned blob locator is required")
    row = conn.execute(
        """
        SELECT id FROM blob_storage_records
        WHERE owner_kind = ? AND owner_id = ? AND storage_tier = ? AND locator = ?
        """,
        (owner_kind, owner_id, storage_tier, normalized_locator),
    ).fetchone()
    record_id = str(row["id"]) if row else _new_id()
    conn.execute(
        """
        INSERT INTO blob_storage_records(
          id, operation_id, owner_kind, owner_id, storage_tier, locator,
          byte_size, content_sha256, state, reason, attempts,
          last_error, updated_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'tombstoned', ?, 0, NULL,
                  strftime('%Y-%m-%dT%H:%M:%fZ','now'), NULL)
        ON CONFLICT(owner_kind, owner_id, storage_tier, locator) DO UPDATE SET
          operation_id=excluded.operation_id,
          byte_size=COALESCE(excluded.byte_size, blob_storage_records.byte_size),
          content_sha256=COALESCE(excluded.content_sha256, blob_storage_records.content_sha256),
          state='tombstoned',
          reason=excluded.reason,
          attempts=0,
          last_error=NULL,
          updated_at=excluded.updated_at,
          completed_at=NULL
        """,
        (
            record_id,
            operation_id,
            owner_kind,
            owner_id,
            storage_tier,
            normalized_locator,
            byte_size,
            content_sha256 or None,
            reason,
        ),
    )
    return record_id


def _finalize_media_owner(conn: sqlite3.Connection, record: sqlite3.Row) -> None:
    if record["owner_kind"] != "media-artifact":
        return
    row = conn.execute(
        """
        SELECT capture_status, storage_tier, file_path, blob_locator, spool_locator
        FROM media_artifacts WHERE id = ?
        """,
        (record["owner_id"],),
    ).fetchone()
    if not row or row["capture_status"] != "purging" or row["storage_tier"] != record["storage_tier"]:
        return
    if row["storage_tier"] == "spool":
        current_locator = prefer_relative_locator(row["spool_locator"], row["file_path"])
    else:
        current_locator = prefer_relative_locator(row["blob_locator"], row["file_path"])
    if str(current_locator or "") != str(record["locator"]):
        return
    conn.execute(
        """
        UPDATE media_artifacts
        SET file_path = '', blob_locator = NULL, spool_locator = NULL,
            storage_tier = 'media-root', capture_status = 'purged'
        WHERE id = ? AND capture_status = 'purging'
        """,
        (record["owner_id"],),
    )


def _refresh_receipt(conn: sqlite3.Connection, operation_id: str) -> None:
    receipt = conn.execute(
        "SELECT counts_json FROM deletion_receipts WHERE id = ?",
        (operation_id,),
    ).fetchone()
    if not receipt:
        return
    states = {
        str(row["state"]): int(row["n"])
        for row in conn.execute(
            """
            SELECT state, COUNT(*) AS n FROM blob_storage_records
            WHERE operation_id = ? GROUP BY state
            """,
            (operation_id,),
        ).fetchall()
    }
    counts = json.loads(receipt["counts_json"] or "{}")
    counts["blob_deletions_deleted"] = states.get("deleted", 0)
    counts["blob_deletions_missing"] = states.get("missing", 0)
    counts["blob_deletions_blocked"] = states.get("blocked", 0)
    counts["blob_deletions_failed"] = states.get("failed", 0)
    counts["blob_deletions_pending"] = sum(
        count for state, count in states.items() if state not in TERMINAL_BLOB_STATES
    )
    conn.execute(
        "UPDATE deletion_receipts SET counts_json = ? WHERE id = ?",
        (json.dumps(counts, sort_keys=True), operation_id),
    )


@contextmanager
def _blob_deletion_lock(config: RuntimeConfig) -> Iterator[None]:
    config.state_root.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(config.state_root / "blob-deletion.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _process_blob_tombstones_unlocked(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    operation_id: str | None = None,
    limit: int = 1000,
) -> dict[str, int]:
    where = ["state IN ('tombstoned', 'failed', 'blocked')"]
    params: list[Any] = []
    if operation_id:
        where.append("operation_id = ?")
        params.append(operation_id)
    params.append(max(1, int(limit)))
    rows = conn.execute(
        f"""
        SELECT * FROM blob_storage_records
        WHERE {' AND '.join(where)}
        ORDER BY updated_at, id
        LIMIT ?
        """,
        params,
    ).fetchall()
    result = {"selected": len(rows), "deleted": 0, "missing": 0, "failed": 0, "blocked": 0, "pending": 0}
    touched_operations: set[str] = set()
    for record in rows:
        record_operation = str(record["operation_id"] or "")
        if record_operation:
            touched_operations.add(record_operation)
        store, readiness = _store_for_tier(config, str(record["storage_tier"]))
        state: str
        error: str | None
        if store is None:
            state = "blocked"
            error = readiness
        else:
            outcome = store.delete(str(record["locator"]))
            if outcome.status == "deleted":
                state = "deleted"
                error = None
            elif outcome.status == "missing":
                state = "missing"
                error = None
            elif outcome.status in {"outside-root", "invalid", "empty", "not-file"}:
                state = "blocked"
                error = outcome.status
            else:
                state = "failed"
                error = outcome.status
        with conn:
            conn.execute(
                """
                UPDATE blob_storage_records
                SET state = ?, attempts = attempts + 1, last_error = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                    completed_at = CASE WHEN ? IN ('deleted', 'missing')
                                        THEN strftime('%Y-%m-%dT%H:%M:%fZ','now')
                                        ELSE NULL END
                WHERE id = ?
                """,
                (state, error, state, record["id"]),
            )
            if state in TERMINAL_BLOB_STATES:
                _finalize_media_owner(conn, record)
        result[state] += 1
    with conn:
        for touched_operation in touched_operations:
            _refresh_receipt(conn, touched_operation)
    pending_where = ["state IN ('tombstoned', 'failed', 'blocked')"]
    pending_params: list[Any] = []
    if operation_id:
        pending_where.append("operation_id = ?")
        pending_params.append(operation_id)
    pending = conn.execute(
        f"SELECT COUNT(*) AS n FROM blob_storage_records WHERE {' AND '.join(pending_where)}",
        pending_params,
    ).fetchone()
    result["pending"] = int(pending["n"] if pending else 0)
    return result


def process_blob_tombstones(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    operation_id: str | None = None,
    limit: int = 1000,
) -> dict[str, int]:
    with _blob_deletion_lock(config):
        return _process_blob_tombstones_unlocked(
            conn,
            config,
            operation_id=operation_id,
            limit=limit,
        )


def blob_lifecycle_status(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {
        str(row["state"]): int(row["n"])
        for row in conn.execute(
            "SELECT state, COUNT(*) AS n FROM blob_storage_records GROUP BY state"
        ).fetchall()
    }
    return {
        "records": sum(counts.values()),
        "committed": counts.get("committed", 0),
        "tombstoned": counts.get("tombstoned", 0),
        "failed": counts.get("failed", 0),
        "blocked": counts.get("blocked", 0),
        "missing": counts.get("missing", 0),
        "deleted": counts.get("deleted", 0),
        "pending": sum(counts.get(state, 0) for state in RETRYABLE_BLOB_STATES),
    }
