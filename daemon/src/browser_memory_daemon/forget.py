from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from .normalize import normalize_url
from .policy import redact_url


def _document_ids_for_url(conn: sqlite3.Connection, url: str) -> list[str]:
    safe_url, _, _ = redact_url(url)
    normalized = normalize_url(safe_url)
    rows = conn.execute(
        """
        SELECT id FROM documents WHERE normalized_url = ? OR canonical_url = ?
        UNION
        SELECT document_id AS id FROM visits WHERE normalized_url = ? OR url = ?
        """,
        (normalized, normalized, normalized, safe_url),
    ).fetchall()
    return [row["id"] for row in rows if row["id"]]


def forget(conn: sqlite3.Connection, *, domain: str | None = None, url: str | None = None) -> dict:
    if not domain and not url:
        raise ValueError("forget requires domain or url")
    if domain:
        normalized_domain = domain.lower().strip().lstrip(".")
        doc_rows = conn.execute(
            "SELECT id FROM documents WHERE domain = ? OR domain LIKE ?",
            (normalized_domain, f"%.{normalized_domain}"),
        ).fetchall()
        document_ids = [row["id"] for row in doc_rows]
        scope = {"domain": normalized_domain}
    else:
        document_ids = _document_ids_for_url(conn, url or "")
        scope = {"url": normalize_url(redact_url(url or "")[0])}
    counts = {"documents": 0, "visits": 0, "snapshots": 0, "chunks": 0, "blobs": 0, "fts": 0, "embeddings": 0, "redactions": 0, "feedback_events": 0}
    with conn:
        for document_id in document_ids:
            snapshot_rows = conn.execute("SELECT id, cleaned_text_path FROM snapshots WHERE document_id = ?", (document_id,)).fetchall()
            chunk_rows = conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,)).fetchall()
            for chunk in chunk_rows:
                counts["embeddings"] += conn.execute("DELETE FROM embeddings WHERE chunk_id = ?", (chunk["id"],)).rowcount
                counts["feedback_events"] += conn.execute("DELETE FROM feedback_events WHERE chunk_id = ?", (chunk["id"],)).rowcount
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk["id"],))
                counts["fts"] += 1
            for snap in snapshot_rows:
                counts["redactions"] += conn.execute("DELETE FROM redactions WHERE snapshot_id = ?", (snap["id"],)).rowcount
                if snap["cleaned_text_path"]:
                    path = Path(snap["cleaned_text_path"])
                    if path.exists():
                        path.unlink()
                        counts["blobs"] += 1
            counts["chunks"] += conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,)).rowcount
            counts["snapshots"] += conn.execute("DELETE FROM snapshots WHERE document_id = ?", (document_id,)).rowcount
            counts["visits"] += conn.execute("DELETE FROM visits WHERE document_id = ?", (document_id,)).rowcount
            counts["feedback_events"] += conn.execute("DELETE FROM feedback_events WHERE document_id = ?", (document_id,)).rowcount
            counts["documents"] += conn.execute("DELETE FROM documents WHERE id = ?", (document_id,)).rowcount
        receipt_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO deletion_receipts(id, scope_json, counts_json) VALUES (?, ?, ?)",
            (receipt_id, json.dumps(scope, sort_keys=True), json.dumps(counts, sort_keys=True)),
        )
    return {"forgotten": True, "receipt_id": receipt_id, "scope": scope, "counts": counts}
