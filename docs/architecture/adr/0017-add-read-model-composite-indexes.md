---
id: ADR-0017
status: accepted
date: 2026-07-03
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - docs/wayfinder/durability-performance-coverage/tickets/010-read-model-query-performance.md
  - docs/architecture/adr/0016-use-deterministic-synthetic-performance-benchmarks.md
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_read_model_indexes.py daemon/tests/e2e/test_performance_benchmarks.py
  - ./scripts/run-performance-benchmarks.sh --json --runtime-root /tmp/bmd-010-after --captures 1000 --read-repetitions 3 --media-every 10 --media-worker-limit 100 >/tmp/bmd_010_after.json
---

# ADR-0017: Add composite indexes for read-model ordering

## Context

Ticket 009 added deterministic performance benchmark output. Ticket 010 used that output and SQLite query plans to inspect read-model paths. The 1,000-capture synthetic benchmark showed `recent`, `timeline`, and detail reads were still fast, but query plans exposed avoidable scans and temporary order B-trees on hot read paths:

- recent/timeline used `idx_visits_captured_at` and still needed ordering work for `blocked`, `captured_at`, and `created_at`;
- correlated latest-snapshot lookups used `idx_snapshots_document_id` plus a temporary order B-tree;
- first-chunk and snapshot detail paths scanned `chunks` or sorted via temporary B-trees;
- document detail scans/sorts visits, snapshots, chunks, and lifecycle events by document/visit plus time ordering.

## Decision

We will add idempotent composite SQLite indexes that match the read-model filter and order shapes for recent, timeline, document detail, snapshot detail, lifecycle detail, media queue status, and correlated latest-snapshot/first-chunk subqueries.

We will not change API pagination, detail payload limits, or read-audit write semantics in this slice because benchmark evidence showed audit-write overhead was small compared with query-shape costs, and API limit contracts were already bounded.

## Decision drivers

- Query plans should avoid full scans and temporary B-trees for common ordered read paths.
- Existing APIs should preserve response shapes and bounded limit behavior.
- Indexes must be additive and safe for existing local SQLite databases via `CREATE INDEX IF NOT EXISTS`.
- Ticket 010 needs before/after benchmark evidence, not speculative tuning.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Add composite indexes for observed query shapes | Minimal API risk, clear query-plan improvement, automatic for existing DBs. | Adds DB file size and ingest write maintenance cost. | Chosen. |
| Rewrite recent/timeline queries with materialized read models | Could reduce correlated subqueries further. | Larger design/schema change without current benchmark need. | Rejected for this slice. |
| Sample/disable read-audit writes | Could reduce write pressure on read endpoints. | Benchmark overhead was sub-millisecond; changes audit contract. | Rejected for this slice. |
| Add pagination/detail contract changes | Could bound worst-case payloads harder. | Current server-side limits already bound hot endpoints; API contract churn not justified by evidence. | Rejected for this slice. |

## Consequences

- Positive: recent/timeline/detail query plans use targeted indexes instead of avoidable scans/sorts.
- Positive: ticket 010 closes without changing API response contracts or audit semantics.
- Positive: future agents can rerun `scripts/run-performance-benchmarks.sh` to compare read-model changes.
- Neutral / operational: existing databases receive the new indexes at the next DB initialization path.
- Negative: DB size grows modestly because each capture/update maintains more indexes.

## Verification / validation

- Verification: `daemon/tests/e2e/test_read_model_indexes.py` asserts the intended query shapes use the new composite indexes.
- Verification: before/after 1,000-capture synthetic benchmark showed `recent` p95 improve from 2.829 ms to 0.436 ms, `timeline` p95 from 9.534 ms to 1.337 ms, and `document_detail` p95 from 0.420 ms to 0.169 ms on this WSL host.
- Validation: read-audit write behavior and API contracts remained unchanged while the measured read-model bottleneck moved from scans/sorts to indexed lookups.

## Revisit triggers

- Supersede this ADR if daily-driver or larger synthetic benchmarks show doctor/integrity checks, media queue status, or FTS search becoming the limiting read surfaces.
- Supersede this ADR if a materialized read model replaces correlated latest-snapshot/first-chunk lookups.
- Revisit if index maintenance measurably hurts ingest/write contention under concurrency stress.

## References

- `docs/wayfinder/durability-performance-coverage/tickets/010-read-model-query-performance.md`
- `daemon/src/browser_memory_daemon/schema.sql`
- `/tmp/bmd_010_before.json` and `/tmp/bmd_010_after.json` benchmark outputs from the ticket 010 session
