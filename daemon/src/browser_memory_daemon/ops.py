from __future__ import annotations

from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path
import sqlite3
from typing import Any

from . import __version__
from .config import RuntimeConfig


def _clamp_limit(limit: int | str | None, *, default: int = 25, maximum: int = 100) -> int:
    if limit is None or limit == "":
        return default
    return max(1, min(int(limit), maximum))


def _snippet(text: str | None, *, max_chars: int = 280) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def _parse_date_range(*, day: str | None = None, after: str | None = None, before: str | None = None) -> tuple[str | None, str | None]:
    if day:
        parsed = date.fromisoformat(day)
        start = datetime.combine(parsed, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")
    return after or None, before or None


def recent_captures(conn: sqlite3.Connection, *, limit: int | str | None = 25) -> list[dict[str, Any]]:
    selected_limit = _clamp_limit(limit)
    rows = conn.execute(
        """
        SELECT
          visits.id AS visit_id,
          visits.url,
          visits.normalized_url,
          COALESCE(visits.title, documents.title, '') AS title,
          visits.source_device,
          visits.browser_profile,
          visits.visit_started_at,
          visits.captured_at,
          visits.dwell_seconds,
          documents.id AS document_id,
          documents.domain,
          snapshots.id AS snapshot_id,
          snapshots.privacy_class,
          snapshots.redaction_count,
          chunks.text AS first_chunk
        FROM visits
        JOIN documents ON documents.id = visits.document_id
        LEFT JOIN snapshots ON snapshots.id = (
          SELECT s.id FROM snapshots s
          WHERE s.document_id = documents.id
          ORDER BY s.captured_at DESC, s.created_at DESC
          LIMIT 1
        )
        LEFT JOIN chunks ON chunks.id = (
          SELECT c.id FROM chunks c
          WHERE c.snapshot_id = snapshots.id
          ORDER BY c.chunk_index ASC
          LIMIT 1
        )
        WHERE visits.blocked = 0
        ORDER BY visits.captured_at DESC, visits.created_at DESC
        LIMIT ?
        """,
        (selected_limit,),
    ).fetchall()
    return [_capture_row(row) for row in rows]


def timeline(conn: sqlite3.Connection, *, day: str | None = None, after: str | None = None, before: str | None = None, limit: int | str | None = 100) -> dict[str, Any]:
    selected_limit = _clamp_limit(limit, default=100, maximum=250)
    start, end = _parse_date_range(day=day, after=after, before=before)
    where = ["visits.blocked = 0"]
    params: list[Any] = []
    if start:
        where.append("visits.captured_at >= ?")
        params.append(start)
    if end:
        where.append("visits.captured_at < ?")
        params.append(end)
    params.append(selected_limit)
    rows = conn.execute(
        f"""
        SELECT
          visits.id AS visit_id,
          visits.url,
          visits.normalized_url,
          COALESCE(visits.title, documents.title, '') AS title,
          visits.source_device,
          visits.browser_profile,
          visits.visit_started_at,
          visits.captured_at,
          visits.dwell_seconds,
          documents.id AS document_id,
          documents.domain,
          snapshots.id AS snapshot_id,
          snapshots.privacy_class,
          snapshots.redaction_count,
          chunks.text AS first_chunk
        FROM visits
        JOIN documents ON documents.id = visits.document_id
        LEFT JOIN snapshots ON snapshots.id = (
          SELECT s.id FROM snapshots s
          WHERE s.document_id = documents.id
          ORDER BY s.captured_at DESC, s.created_at DESC
          LIMIT 1
        )
        LEFT JOIN chunks ON chunks.id = (
          SELECT c.id FROM chunks c
          WHERE c.snapshot_id = snapshots.id
          ORDER BY c.chunk_index ASC
          LIMIT 1
        )
        WHERE {' AND '.join(where)}
        ORDER BY visits.captured_at DESC, visits.created_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    items = [_capture_row(row) for row in rows]
    return {"items": items, "range": {"date": day, "after": start, "before": end}, "count": len(items)}


def document_detail(conn: sqlite3.Connection, document_id: str) -> dict[str, Any]:
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not doc:
        raise KeyError("document not found")
    visits = conn.execute(
        """
        SELECT id, url, normalized_url, title, source_device, browser_profile, visit_started_at,
               captured_at, dwell_seconds, is_incognito, blocked, block_reason
        FROM visits
        WHERE document_id = ?
        ORDER BY captured_at DESC, created_at DESC
        """,
        (document_id,),
    ).fetchall()
    snapshots = conn.execute(
        """
        SELECT id, captured_at, content_type, extraction_method, text_hash, privacy_class,
               redaction_count, cleaned_text_path
        FROM snapshots
        WHERE document_id = ?
        ORDER BY captured_at DESC, created_at DESC
        """,
        (document_id,),
    ).fetchall()
    chunks = conn.execute(
        """
        SELECT id, snapshot_id, chunk_index, title, url, text
        FROM chunks
        WHERE document_id = ?
        ORDER BY snapshot_id, chunk_index
        LIMIT 20
        """,
        (document_id,),
    ).fetchall()
    visit_events = conn.execute(
        """
        SELECT id, visit_id, document_id, url, normalized_url, event_type,
               event_started_at, event_ended_at, active_seconds, max_scroll_percent,
               metadata_json, created_at
        FROM visit_events
        WHERE document_id = ?
           OR visit_id IN (SELECT id FROM visits WHERE document_id = ?)
        ORDER BY event_ended_at DESC, created_at DESC
        LIMIT 100
        """,
        (document_id, document_id),
    ).fetchall()
    return {
        "document": dict(doc),
        "visits": [dict(row) for row in visits],
        "visit_events": [dict(row) for row in visit_events],
        "snapshots": [_snapshot_summary(row) for row in snapshots],
        "chunks": [
            {
                "id": row["id"],
                "snapshot_id": row["snapshot_id"],
                "chunk_index": row["chunk_index"],
                "title": row["title"],
                "url": row["url"],
                "snippet": _snippet(row["text"]),
            }
            for row in chunks
        ],
    }


def snapshot_detail(conn: sqlite3.Connection, snapshot_id: str, *, max_text_chars: int = 50_000) -> dict[str, Any]:
    snapshot = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    if not snapshot:
        raise KeyError("snapshot not found")
    document = conn.execute("SELECT * FROM documents WHERE id = ?", (snapshot["document_id"],)).fetchone()
    chunks = conn.execute(
        "SELECT id, chunk_index, title, url, text FROM chunks WHERE snapshot_id = ? ORDER BY chunk_index",
        (snapshot_id,),
    ).fetchall()
    text = ""
    path = snapshot["cleaned_text_path"]
    if path:
        clean_path = Path(path)
        if clean_path.exists():
            text = clean_path.read_text(encoding="utf-8", errors="replace")
    if not text:
        text = "\n\n".join(row["text"] for row in chunks)
    truncated = len(text) > max_text_chars
    return {
        "snapshot": _snapshot_summary(snapshot),
        "document": dict(document) if document else None,
        "text": text[:max_text_chars],
        "text_truncated": truncated,
        "chunks": [
            {"id": row["id"], "chunk_index": row["chunk_index"], "title": row["title"], "url": row["url"], "snippet": _snippet(row["text"])}
            for row in chunks
        ],
    }


def doctor(config: RuntimeConfig, conn: sqlite3.Connection) -> dict[str, Any]:
    tables = [
        "sources",
        "documents",
        "visits",
        "visit_events",
        "snapshots",
        "chunks",
        "chunks_fts",
        "privacy_rules",
        "audit_events",
        "deletion_receipts",
    ]
    counts = {}
    for table in tables:
        counts[table] = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    missing_fts = conn.execute(
        "SELECT COUNT(*) AS n FROM chunks WHERE id NOT IN (SELECT chunk_id FROM chunks_fts)"
    ).fetchone()["n"]
    storage_files = 0
    storage_bytes = 0
    if config.clean_text_root.exists():
        for path in config.clean_text_root.rglob("*"):
            if path.is_file():
                storage_files += 1
                storage_bytes += path.stat().st_size
    return {
        "ok": integrity == "ok" and missing_fts == 0,
        "version": __version__,
        "daemon": {"host": config.host, "port": config.port, "policy_mode": config.policy_mode},
        "paths": {
            "config_root": str(config.config_root),
            "data_root": str(config.data_root),
            "state_root": str(config.state_root),
            "db_path": str(config.db_path),
            "clean_text_root": str(config.clean_text_root),
        },
        "database": {"exists": config.db_path.exists(), "integrity_check": integrity, "counts": counts, "chunks_missing_fts": missing_fts},
        "storage": {"clean_text_files": storage_files, "clean_text_bytes": storage_bytes},
    }


def _capture_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "visit_id": row["visit_id"],
        "document_id": row["document_id"],
        "snapshot_id": row["snapshot_id"],
        "url": row["url"],
        "normalized_url": row["normalized_url"],
        "title": row["title"],
        "domain": row["domain"],
        "source_device": row["source_device"],
        "browser_profile": row["browser_profile"],
        "visit_started_at": row["visit_started_at"],
        "captured_at": row["captured_at"],
        "dwell_seconds": row["dwell_seconds"],
        "privacy_class": row["privacy_class"],
        "redaction_count": row["redaction_count"],
        "snippet": _snippet(row["first_chunk"]),
    }


def _snapshot_summary(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    path = value.pop("cleaned_text_path", None)
    value["has_clean_text"] = bool(path and Path(path).exists())
    return value
