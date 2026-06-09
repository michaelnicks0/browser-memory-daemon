from __future__ import annotations

import re
import sqlite3


def fts_query(raw_query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", raw_query or "")
    return " ".join(tokens)


def search_memory(conn: sqlite3.Connection, query: str, *, limit: int = 10) -> list[dict]:
    safe_query = fts_query(query)
    if not safe_query:
        return []
    limit = max(1, min(int(limit), 50))
    rows = conn.execute(
        """
        SELECT
          chunks_fts.chunk_id,
          chunks_fts.document_id,
          chunks_fts.snapshot_id,
          chunks_fts.title,
          chunks_fts.url,
          snippet(chunks_fts, 5, '[', ']', '…', 24) AS snippet,
          bm25(chunks_fts) AS score,
          documents.domain,
          snapshots.captured_at,
          (SELECT COUNT(*) FROM media_artifacts m WHERE m.snapshot_id = chunks_fts.snapshot_id) AS media_artifact_count
        FROM chunks_fts
        JOIN documents ON documents.id = chunks_fts.document_id
        JOIN snapshots ON snapshots.id = chunks_fts.snapshot_id
        WHERE chunks_fts MATCH ?
        ORDER BY score
        LIMIT ?
        """,
        (safe_query, limit),
    ).fetchall()
    return [dict(row) for row in rows]
