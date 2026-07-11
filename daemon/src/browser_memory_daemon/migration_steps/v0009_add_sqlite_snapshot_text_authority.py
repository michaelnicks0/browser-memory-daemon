"""Add SQLite authority for complete cleaned snapshot text."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

NAME = "add_sqlite_snapshot_text_authority"
SCHEMA_FINGERPRINT = "13638abcfc6cdc9fd689f96f5217dc770310d52306df15994dfdb5a3c45ecc91"
SQL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
CHECKSUM_PAYLOAD = SQL + "\n-- apply implementation --\n" + Path(__file__).read_text(encoding="utf-8")


def apply(conn: sqlite3.Connection) -> None:
    """Backfill only chunk reconstructions that match the stored capture hash."""
    snapshots = conn.execute(
        "SELECT id, text_hash FROM snapshots WHERE cleaned_text IS NULL ORDER BY id"
    ).fetchall()
    for snapshot in snapshots:
        chunks = conn.execute(
            "SELECT text FROM chunks WHERE snapshot_id = ? ORDER BY chunk_index, id",
            (snapshot["id"],),
        ).fetchall()
        if not chunks:
            continue
        candidate = "\n\n".join(row["text"] for row in chunks)
        candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        if candidate_hash != snapshot["text_hash"]:
            continue
        conn.execute(
            """
            UPDATE snapshots
            SET cleaned_text = ?, cleaned_text_source = 'chunks-hash-verified'
            WHERE id = ? AND cleaned_text IS NULL
            """,
            (candidate, snapshot["id"]),
        )
