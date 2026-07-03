# Optimize read-model query and index performance

## Status
closed

## Question
Given benchmark output and query plans, which read-model paths need indexes, pagination, bounded detail payloads, query rewrites, or reduced synchronous audit writes to remain fast as the SQLite DB grows?

## Type
task

## Inputs / links

- Ticket 009 benchmark harness output
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/search.py`
- `daemon/src/browser_memory_daemon/schema.sql`
- `docs/api.md`

## Scope notes from late ticket-004 audit

- Search, recent, timeline, detail, doctor, and queue/status reads synchronously insert audit rows today. Benchmark and decide whether read-audit writes should be sampled, disabled for high-frequency reads, or moved to an async/batched writer.

## Blocks / blocked by

- Blocks: long-term daily-driver performance and UI responsiveness.
- Blocked by: none; ticket 009 is closed and provides synthetic benchmark output.

## Resolution

Closed in this slice. Used ticket 009's synthetic benchmark harness plus SQLite `EXPLAIN QUERY PLAN` output to target read-model index gaps without changing API contracts.

Added composite read-path indexes in `schema.sql`:

- `idx_visits_blocked_captured_created` for `/recent` and `/timeline` filter/order shape;
- `idx_visits_document_captured_created` for document detail visit ordering;
- `idx_snapshots_document_captured_created` for latest-snapshot and document detail snapshot ordering;
- `idx_chunks_snapshot_chunk_index` and `idx_chunks_document_snapshot_chunk_index` for first-chunk, snapshot detail, and document chunk ordering;
- `idx_visit_events_visit_ended_created` and `idx_visit_events_document_ended_created` for lifecycle detail ordering;
- `idx_media_artifacts_status_created` for ordered media queue status checks.

No API pagination/detail semantics changed. Read-audit writes stayed synchronous because benchmark evidence showed sub-millisecond overhead estimates; the measured issue was scan/sort query shape, not audit insertion.

Before/after evidence on a 1,000-capture synthetic dataset:

| Surface | Before p95 | After p95 | Notes |
|---|---:|---:|---|
| `recent` with audit | 2.829 ms | 0.436 ms | now uses `idx_visits_blocked_captured_created` plus indexed subqueries |
| `timeline` with audit | 9.534 ms | 1.337 ms | now uses the same blocked/time index |
| `document_detail` with audit | 0.420 ms | 0.169 ms | visits/snapshots/chunks use document-order indexes |
| `snapshot_detail` with audit | 0.217 ms | 0.150 ms | chunks use `idx_chunks_snapshot_chunk_index` |
| `search` with audit | 0.829 ms | 0.809 ms | FTS path was already fine |
| `media_queue_status` with audit | 0.355 ms | 0.346 ms | no material bottleneck |
| `doctor` with audit | 29.355 ms | 31.336 ms | integrity/storage sweep, not a hot UI read path |

Query-plan evidence after indexing:

```text
recent: SEARCH visits USING INDEX idx_visits_blocked_captured_created (blocked=?)
timeline: SEARCH visits USING INDEX idx_visits_blocked_captured_created (blocked=? AND captured_at>? AND captured_at<?)
latest snapshot: SEARCH snapshots USING INDEX idx_snapshots_document_captured_created (document_id=?)
first/snapshot chunks: SEARCH chunks USING INDEX idx_chunks_snapshot_chunk_index (snapshot_id=?)
document visits: SEARCH visits USING INDEX idx_visits_document_captured_created (document_id=?)
document chunks: SEARCH chunks USING INDEX idx_chunks_document_snapshot_chunk_index (document_id=?)
```

Evidence commands:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_read_model_indexes.py daemon/tests/e2e/test_performance_benchmarks.py
# 3 passed

./scripts/run-performance-benchmarks.sh --json --runtime-root /tmp/bmd-010-before --captures 1000 --read-repetitions 3 --media-every 10 --media-worker-limit 100 >/tmp/bmd_010_before.json
./scripts/run-performance-benchmarks.sh --json --runtime-root /tmp/bmd-010-after --captures 1000 --read-repetitions 3 --media-every 10 --media-worker-limit 100 >/tmp/bmd_010_after.json
```

Recorded ADR-0017 for the additive schema/index decision.

## New tickets / fog updates

No new ticket. API pagination contracts did not change. Keep read-audit sampling/async writes as future fog only if larger benchmarks or daily-driver evidence show audit writes becoming a measurable bottleneck.
