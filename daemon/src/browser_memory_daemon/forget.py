from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from .normalize import domain_from_url, normalize_url
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


def _unlink_existing(paths: list[Path]) -> int:
    unlinked = 0
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            if path.exists():
                path.unlink()
                unlinked += 1
        except OSError:
            continue
    return unlinked


def forget(conn: sqlite3.Connection, *, domain: str | None = None, url: str | None = None) -> dict:
    if not domain and not url:
        raise ValueError("forget requires domain or url")
    normalized_domain = None
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
    counts = {
        "documents": 0,
        "visits": 0,
        "visit_events": 0,
        "snapshots": 0,
        "chunks": 0,
        "blobs": 0,
        "media_artifacts": 0,
        "media_blobs": 0,
        "fts": 0,
        "embeddings": 0,
        "redactions": 0,
        "feedback_events": 0,
    }
    media_paths: list[Path] = []
    clean_text_paths: list[Path] = []
    with conn:
        for document_id in document_ids:
            snapshot_rows = conn.execute("SELECT id, cleaned_text_path FROM snapshots WHERE document_id = ?", (document_id,)).fetchall()
            media_rows = conn.execute("SELECT id, file_path FROM media_artifacts WHERE document_id = ?", (document_id,)).fetchall()
            for media in media_rows:
                if media["file_path"]:
                    media_paths.append(Path(media["file_path"]))
            counts["media_artifacts"] += conn.execute("DELETE FROM media_artifacts WHERE document_id = ?", (document_id,)).rowcount
            chunk_rows = conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,)).fetchall()
            for chunk in chunk_rows:
                counts["embeddings"] += conn.execute("DELETE FROM embeddings WHERE chunk_id = ?", (chunk["id"],)).rowcount
                counts["feedback_events"] += conn.execute("DELETE FROM feedback_events WHERE chunk_id = ?", (chunk["id"],)).rowcount
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk["id"],))
                counts["fts"] += 1
            for snap in snapshot_rows:
                counts["redactions"] += conn.execute("DELETE FROM redactions WHERE snapshot_id = ?", (snap["id"],)).rowcount
                if snap["cleaned_text_path"]:
                    clean_text_paths.append(Path(snap["cleaned_text_path"]))
            counts["chunks"] += conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,)).rowcount
            counts["snapshots"] += conn.execute("DELETE FROM snapshots WHERE document_id = ?", (document_id,)).rowcount
            counts["visit_events"] += conn.execute(
                "DELETE FROM visit_events WHERE document_id = ? OR visit_id IN (SELECT id FROM visits WHERE document_id = ?)",
                (document_id, document_id),
            ).rowcount
            counts["visits"] += conn.execute("DELETE FROM visits WHERE document_id = ?", (document_id,)).rowcount
            counts["feedback_events"] += conn.execute("DELETE FROM feedback_events WHERE document_id = ?", (document_id,)).rowcount
            counts["documents"] += conn.execute("DELETE FROM documents WHERE id = ?", (document_id,)).rowcount
        if domain:
            event_rows = conn.execute("SELECT id, normalized_url FROM visit_events WHERE document_id IS NULL").fetchall()
            for event in event_rows:
                event_domain = domain_from_url(event["normalized_url"])
                if event_domain == normalized_domain or event_domain.endswith(f".{normalized_domain}"):
                    counts["visit_events"] += conn.execute("DELETE FROM visit_events WHERE id = ?", (event["id"],)).rowcount
        else:
            counts["visit_events"] += conn.execute("DELETE FROM visit_events WHERE normalized_url = ?", (scope["url"],)).rowcount
    counts["media_blobs"] = _unlink_existing(media_paths)
    counts["blobs"] = _unlink_existing(clean_text_paths)
    receipt_id = str(uuid.uuid4())
    with conn:
        conn.execute(
            "INSERT INTO deletion_receipts(id, scope_json, counts_json) VALUES (?, ?, ?)",
            (receipt_id, json.dumps(scope, sort_keys=True), json.dumps(counts, sort_keys=True)),
        )
    return {"forgotten": True, "receipt_id": receipt_id, "scope": scope, "counts": counts}
