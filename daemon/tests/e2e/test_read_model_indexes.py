from __future__ import annotations

import sqlite3

from browser_memory_daemon.performance_benchmarks import BenchmarkOptions, run_benchmark


def _plan_details(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[str]:
    return [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()]


def test_read_model_ordered_queries_use_schema_indexes(tmp_path):
    runtime_root = tmp_path / "read-model-plans"
    result = run_benchmark(
        BenchmarkOptions(
            captures=8,
            read_repetitions=1,
            media_every=0,
            media_worker_limit=4,
            runtime_root=runtime_root,
        )
    )
    document_id = result["benchmarks"]["ingest"]["first_document_id"]
    snapshot_id = result["benchmarks"]["ingest"]["first_snapshot_id"]

    conn = sqlite3.connect(runtime_root / "data" / "browser-memory.sqlite3")
    try:
        recent = _plan_details(
            conn,
            """
            SELECT id
            FROM visits
            WHERE blocked = 0
            ORDER BY captured_at DESC, created_at DESC
            LIMIT 25
            """,
        )
        snapshot_lookup = _plan_details(
            conn,
            """
            SELECT id
            FROM snapshots
            WHERE document_id = ?
            ORDER BY captured_at DESC, created_at DESC
            LIMIT 1
            """,
            (document_id,),
        )
        document_visits = _plan_details(
            conn,
            """
            SELECT id
            FROM visits
            WHERE document_id = ?
            ORDER BY captured_at DESC, created_at DESC
            """,
            (document_id,),
        )
        document_chunks = _plan_details(
            conn,
            """
            SELECT id
            FROM chunks
            WHERE document_id = ?
            ORDER BY snapshot_id, chunk_index
            LIMIT 20
            """,
            (document_id,),
        )
        snapshot_chunks = _plan_details(
            conn,
            """
            SELECT id
            FROM chunks
            WHERE snapshot_id = ?
            ORDER BY chunk_index
            """,
            (snapshot_id,),
        )

        assert any("idx_visits_blocked_captured_created" in item for item in recent)
        assert any("idx_snapshots_document_captured_created" in item for item in snapshot_lookup)
        assert any("idx_visits_document_captured_created" in item for item in document_visits)
        assert any("idx_chunks_document_snapshot_chunk_index" in item for item in document_chunks)
        assert any("idx_chunks_snapshot_chunk_index" in item for item in snapshot_chunks)
    finally:
        conn.close()
