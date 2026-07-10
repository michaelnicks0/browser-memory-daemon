from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .blob_store import BlobStore
from .config import RuntimeConfig
from .media import media_artifacts_for_document, media_artifacts_for_snapshot, media_queue_status


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


_ACTIVITY_CTE = """
WITH observation_activity AS (
  SELECT
    o.id AS observation_id,
    o.navigation_id,
    'observation' AS record_source,
    o.capture_reason,
    o.capture_method,
    o.extraction_version,
    o.disposition,
    o.provenance_quality,
    o.visit_id,
    o.observed_url AS url,
    o.normalized_observed_url AS normalized_url,
    o.title,
    v.source_device,
    v.browser_profile,
    v.visit_started_at,
    o.captured_at,
    COALESCE(v.dwell_seconds, 0) AS dwell_seconds,
    COALESCE((
      SELECT MAX(ve.max_scroll_percent) FROM visit_events ve
      WHERE ve.visit_id = o.visit_id
    ), 0) AS max_scroll_percent,
    o.document_id,
    d.domain,
    o.snapshot_id,
    s.privacy_class,
    s.redaction_count,
    c.text AS first_chunk,
    (
      SELECT COUNT(*) FROM media_artifact_observations mao
      WHERE mao.observation_id = o.id
    ) AS media_artifact_count,
    o.created_at AS created_sort
  FROM capture_observations o
  JOIN documents d ON d.id = o.document_id
  LEFT JOIN visits v ON v.id = o.visit_id
  LEFT JOIN snapshots s ON s.id = o.snapshot_id
  LEFT JOIN chunks c ON c.id = (
    SELECT c2.id FROM chunks c2
    WHERE c2.snapshot_id = o.snapshot_id
    ORDER BY c2.chunk_index ASC
    LIMIT 1
  )
  WHERE COALESCE(v.blocked, 0) = 0
),
legacy_activity AS (
  SELECT
    NULL AS observation_id,
    NULL AS navigation_id,
    'legacy-visit' AS record_source,
    NULL AS capture_reason,
    NULL AS capture_method,
    NULL AS extraction_version,
    'legacy-fallback' AS disposition,
    'ambiguous' AS provenance_quality,
    v.id AS visit_id,
    v.url,
    v.normalized_url,
    COALESCE(v.title, d.title, '') AS title,
    v.source_device,
    v.browser_profile,
    v.visit_started_at,
    v.captured_at,
    COALESCE(v.dwell_seconds, 0) AS dwell_seconds,
    COALESCE((
      SELECT MAX(ve.max_scroll_percent) FROM visit_events ve
      WHERE ve.visit_id = v.id
    ), 0) AS max_scroll_percent,
    d.id AS document_id,
    d.domain,
    s.id AS snapshot_id,
    s.privacy_class,
    s.redaction_count,
    c.text AS first_chunk,
    (SELECT COUNT(*) FROM media_artifacts m WHERE m.snapshot_id = s.id) AS media_artifact_count,
    v.created_at AS created_sort
  FROM visits v
  JOIN documents d ON d.id = v.document_id
  LEFT JOIN snapshots s ON s.id = COALESCE(
    (
      SELECT s2.id FROM snapshots s2
      WHERE s2.visit_id = v.id
      ORDER BY s2.captured_at DESC, s2.created_at DESC
      LIMIT 1
    ),
    (
      SELECT s3.id FROM snapshots s3
      WHERE s3.document_id = d.id
      ORDER BY s3.captured_at DESC, s3.created_at DESC
      LIMIT 1
    )
  )
  LEFT JOIN chunks c ON c.id = (
    SELECT c2.id FROM chunks c2
    WHERE c2.snapshot_id = s.id
    ORDER BY c2.chunk_index ASC
    LIMIT 1
  )
  WHERE v.blocked = 0
    AND NOT EXISTS (
      SELECT 1 FROM capture_observations o WHERE o.visit_id = v.id
    )
),
activity AS (
  SELECT * FROM observation_activity
  UNION ALL
  SELECT * FROM legacy_activity
)
"""


def _activity_rows(
    conn: sqlite3.Connection,
    *,
    start: str | None,
    end: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    where: list[str] = []
    params: list[Any] = []
    if start:
        where.append("captured_at >= ?")
        params.append(start)
    if end:
        where.append("captured_at < ?")
        params.append(end)
    params.append(limit)
    predicate = f"WHERE {' AND '.join(where)}" if where else ""
    return conn.execute(
        f"""
        {_ACTIVITY_CTE}
        SELECT * FROM activity
        {predicate}
        ORDER BY captured_at DESC, created_sort DESC, observation_id DESC, visit_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def recent_captures(conn: sqlite3.Connection, *, limit: int | str | None = 25) -> list[dict[str, Any]]:
    selected_limit = _clamp_limit(limit)
    return [
        _capture_row(row)
        for row in _activity_rows(conn, start=None, end=None, limit=selected_limit)
    ]


def _activity_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    visits: dict[str, dict[str, Any]] = {}
    for item in items:
        visit_id = item.get("visit_id")
        if visit_id and visit_id not in visits:
            visits[visit_id] = item
    return {
        "visits": len(visits),
        "observations": sum(item.get("observation_id") is not None for item in items),
        "captures": len(items),
        "total_dwell_seconds": sum(int(item.get("dwell_seconds") or 0) for item in visits.values()),
        "max_scroll_percent": max((int(item.get("max_scroll_percent") or 0) for item in items), default=0),
        "media_artifacts": sum(int(item.get("media_artifact_count") or 0) for item in items),
    }


def timeline(conn: sqlite3.Connection, *, day: str | None = None, after: str | None = None, before: str | None = None, limit: int | str | None = 100) -> dict[str, Any]:
    selected_limit = _clamp_limit(limit, default=100, maximum=250)
    start, end = _parse_date_range(day=day, after=after, before=before)
    rows = _activity_rows(conn, start=start, end=end, limit=selected_limit)
    items = [_capture_row(row) for row in rows]
    return {
        "items": items,
        "range": {"date": day, "after": start, "before": end},
        "count": len(items),
        "summary": _activity_summary(items),
    }


def _observation_details(
    conn: sqlite3.Connection,
    *,
    document_id: str | None = None,
    snapshot_id: str | None = None,
) -> list[dict[str, Any]]:
    if (document_id is None) == (snapshot_id is None):
        raise ValueError("exactly one observation detail selector is required")
    column = "o.document_id" if document_id is not None else "o.snapshot_id"
    value = document_id if document_id is not None else snapshot_id
    rows = conn.execute(
        f"""
        SELECT o.id AS observation_id, o.navigation_id, o.visit_id,
               o.document_id, o.snapshot_id, o.observed_url,
               o.normalized_observed_url, o.title, o.captured_at,
               o.capture_reason, o.capture_method, o.extraction_version,
               o.disposition, o.provenance_quality,
               (SELECT COUNT(*) FROM media_artifact_observations mao
                WHERE mao.observation_id = o.id) AS media_artifact_count
        FROM capture_observations o
        WHERE {column} = ?
        ORDER BY o.captured_at DESC, o.created_at DESC, o.id DESC
        """,
        (value,),
    ).fetchall()
    return [dict(row) for row in rows]


def document_detail(conn: sqlite3.Connection, config: RuntimeConfig, document_id: str) -> dict[str, Any]:
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
        SELECT id, visit_id, claimed_visit_id, attachment_method,
               document_id, url, normalized_url, event_type,
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
    url_claims = conn.execute(
        """
        SELECT id, observation_id, claim_type, claimed_url, normalized_claimed_url,
               claim_origin, same_origin, identity_effect, provenance_quality,
               first_observed_at, last_observed_at, created_at
        FROM document_url_claims
        WHERE document_id = ?
        ORDER BY first_observed_at, id
        """,
        (document_id,),
    ).fetchall()
    return {
        "document": dict(doc),
        "observations": _observation_details(conn, document_id=document_id),
        "url_claims": [dict(row) for row in url_claims],
        "visits": [dict(row) for row in visits],
        "visit_events": [dict(row) for row in visit_events],
        "snapshots": [_snapshot_summary(row, config) for row in snapshots],
        "media_artifacts": media_artifacts_for_document(conn, document_id, config),
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


def snapshot_detail(conn: sqlite3.Connection, config: RuntimeConfig, snapshot_id: str, *, max_text_chars: int = 50_000) -> dict[str, Any]:
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
        store = BlobStore(config.clean_text_root)
        resolution = store.resolve(path, require_file=True)
        if resolution.path is not None:
            text = store.read_text(path, encoding="utf-8", errors="replace")
    if not text:
        text = "\n\n".join(row["text"] for row in chunks)
    truncated = len(text) > max_text_chars
    return {
        "snapshot": _snapshot_summary(snapshot, config),
        "document": dict(document) if document else None,
        "observations": _observation_details(conn, snapshot_id=snapshot_id),
        "text": text[:max_text_chars],
        "text_truncated": truncated,
        "media_artifacts": media_artifacts_for_snapshot(conn, snapshot_id, config),
        "chunks": [
            {"id": row["id"], "chunk_index": row["chunk_index"], "title": row["title"], "url": row["url"], "snippet": _snippet(row["text"])}
            for row in chunks
        ],
    }


def doctor(config: RuntimeConfig, conn: sqlite3.Connection, *, storage_census: bool = False) -> dict[str, Any]:
    tables = [
        "sources",
        "documents",
        "visits",
        "capture_observations",
        "document_url_claims",
        "media_artifact_observations",
        "visit_events",
        "snapshots",
        "chunks",
        "chunks_fts",
        "media_artifacts",
        "media_fetch_tasks",
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
    storage = _doctor_storage(config, conn, storage_census=storage_census)
    return {
        "ok": integrity == "ok" and missing_fts == 0,
        "version": __version__,
        "daemon": {"host": config.host, "port": config.port, "policy_mode": config.policy_mode},
        "paths": {
            "config_root": str(config.config_root),
            "data_root": str(config.data_root),
            "blob_root": str(config.blob_root),
            "state_root": str(config.state_root),
            "db_path": str(config.db_path),
            "clean_text_root": str(config.clean_text_root),
            "media_root": str(config.media_root),
        },
        "database": {"exists": config.db_path.exists(), "integrity_check": integrity, "counts": counts, "chunks_missing_fts": missing_fts},
        "storage": storage,
        "media_queue": media_queue_status(conn, config, limit=25),
    }


def _doctor_storage(config: RuntimeConfig, conn: sqlite3.Connection, *, storage_census: bool) -> dict[str, Any]:
    if not storage_census:
        clean = conn.execute(
            """
            SELECT COUNT(DISTINCT cleaned_text_path) AS files,
                   COALESCE(SUM(LENGTH(text)), 0) AS bytes
            FROM snapshots
            LEFT JOIN chunks ON chunks.snapshot_id = snapshots.id
            WHERE COALESCE(cleaned_text_path, '') != ''
            """
        ).fetchone()
        media = conn.execute(
            """
            SELECT COUNT(DISTINCT file_path) AS files,
                   COALESCE(SUM(byte_size), 0) AS bytes
            FROM media_artifacts
            WHERE COALESCE(file_path, '') != ''
            """
        ).fetchone()
        return {
            "census_mode": "db-derived",
            "clean_text_files": int(clean["files"] or 0),
            "clean_text_bytes": int(clean["bytes"] or 0),
            "media_files": int(media["files"] or 0),
            "media_bytes": int(media["bytes"] or 0),
        }
    clean_files, clean_bytes = _filesystem_census(config.clean_text_root)
    media_files, media_bytes = _filesystem_census(config.media_root)
    return {
        "census_mode": "filesystem",
        "clean_text_files": clean_files,
        "clean_text_bytes": clean_bytes,
        "media_files": media_files,
        "media_bytes": media_bytes,
    }


def _filesystem_census(root: Path) -> tuple[int, int]:
    files = 0
    bytes_total = 0
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file():
                files += 1
                bytes_total += path.stat().st_size
    return files, bytes_total


def _capture_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "observation_id": row["observation_id"],
        "navigation_id": row["navigation_id"],
        "record_source": row["record_source"],
        "capture_reason": row["capture_reason"],
        "capture_method": row["capture_method"],
        "extraction_version": row["extraction_version"],
        "disposition": row["disposition"],
        "provenance_quality": row["provenance_quality"],
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
        "max_scroll_percent": row["max_scroll_percent"],
        "privacy_class": row["privacy_class"],
        "redaction_count": row["redaction_count"],
        "media_artifact_count": row["media_artifact_count"],
        "snippet": _snippet(row["first_chunk"]),
    }


def _snapshot_summary(row: sqlite3.Row, config: RuntimeConfig | None = None) -> dict[str, Any]:
    value = dict(row)
    path = value.pop("cleaned_text_path", None)
    if config:
        resolution = BlobStore(config.clean_text_root).resolve(path, require_file=True)
        value["has_clean_text"] = resolution.path is not None
        value["clean_text_path_status"] = resolution.status
    else:
        value["has_clean_text"] = bool(path and Path(path).exists())
        value["clean_text_path_status"] = "legacy-unchecked"
    return value
