from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from .blob_store import BlobStore, BlobStoreError, prefer_relative_locator
from .config import RuntimeConfig
from .db import audit


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunk_candidate(conn: sqlite3.Connection, snapshot_id: str) -> str | None:
    rows = conn.execute(
        "SELECT text FROM chunks WHERE snapshot_id = ? ORDER BY chunk_index, id",
        (snapshot_id,),
    ).fetchall()
    if not rows:
        return None
    return "\n\n".join(row["text"] for row in rows)


def reconcile_snapshot_text_authority(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    execute: bool = False,
    limit: int = 1_000,
) -> dict[str, Any]:
    """Find exact historical text and optionally promote it into SQLite authority."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    rows = conn.execute(
        """
        SELECT id, text_hash, cleaned_text_path, cleaned_text_locator
        FROM snapshots
        WHERE cleaned_text IS NULL
        ORDER BY captured_at, id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    store = BlobStore(config.clean_text_root)
    candidates: list[tuple[str, str, str]] = []
    unresolved: list[dict[str, str]] = []
    from_chunks = 0
    from_sidecars = 0

    for row in rows:
        expected_hash = str(row["text_hash"] or "")
        chunk_text = _chunk_candidate(conn, row["id"])
        if chunk_text is not None and _sha256(chunk_text) == expected_hash:
            candidates.append((row["id"], chunk_text, "chunks-hash-verified"))
            from_chunks += 1
            continue

        locator = prefer_relative_locator(row["cleaned_text_locator"], row["cleaned_text_path"])
        resolution = store.resolve(locator, require_file=True)
        if resolution.path is None:
            unresolved.append({"snapshot_id": row["id"], "reason": f"sidecar-{resolution.status}"})
            continue
        try:
            sidecar_text = store.read_text(resolution.path, encoding="utf-8", errors="strict")
        except (BlobStoreError, OSError, UnicodeError):
            unresolved.append({"snapshot_id": row["id"], "reason": "sidecar-read-failed"})
            continue
        if _sha256(sidecar_text) != expected_hash:
            unresolved.append({"snapshot_id": row["id"], "reason": "sidecar-hash-mismatch"})
            continue
        candidates.append((row["id"], sidecar_text, "sidecar-hash-verified"))
        from_sidecars += 1

    applied = 0
    if execute and candidates:
        with conn:
            for snapshot_id, text, source in candidates:
                applied += conn.execute(
                    """
                    UPDATE snapshots
                    SET cleaned_text = ?, cleaned_text_source = ?
                    WHERE id = ? AND cleaned_text IS NULL
                    """,
                    (text, source, snapshot_id),
                ).rowcount
            audit(
                conn,
                "snapshot-text.reconciled",
                {
                    "scanned": len(rows),
                    "resolved": len(candidates),
                    "applied": applied,
                    "from_chunks": from_chunks,
                    "from_sidecars": from_sidecars,
                    "unresolved": len(unresolved),
                },
            )

    remaining = int(
        conn.execute("SELECT COUNT(*) FROM snapshots WHERE cleaned_text IS NULL").fetchone()[0]
    )
    return {
        "dry_run": not execute,
        "scanned": len(rows),
        "resolved": len(candidates),
        "applied": applied,
        "from_chunks": from_chunks,
        "from_sidecars": from_sidecars,
        "unresolved": unresolved,
        "remaining": remaining,
    }
