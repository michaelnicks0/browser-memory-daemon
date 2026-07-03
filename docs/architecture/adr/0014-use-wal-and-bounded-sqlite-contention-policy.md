---
id: ADR-0014
status: accepted
date: 2026-07-03
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - docs/wayfinder/durability-performance-coverage/tickets/004-sqlite-write-path-hardening.md
  - daemon/src/browser_memory_daemon/db.py
  - daemon/src/browser_memory_daemon/app.py
  - daemon/src/browser_memory_daemon/media.py
  - daemon/src/browser_memory_daemon/concurrency_stress.py
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/unit/test_db.py daemon/tests/e2e/test_concurrency_stress.py
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_media_worker.py::test_concurrent_media_blob_writes_use_distinct_temp_files
  - ./scripts/run-concurrency-stress.sh --captures 24 --reader-rounds 24 --media-worker-runs 8 --max-workers 32 --timeout 60 --no-fail
  - ./scripts/run-concurrency-stress.sh --captures 80 --reader-rounds 80 --media-worker-runs 24 --max-workers 64 --timeout 90 --no-fail
---

# ADR-0014: Use WAL and Bounded SQLite Contention Policy

## Context

Browser Memory Daemon uses SQLite/FTS5 as the authoritative local store. The daily-driver path has multiple writers and near-writers: Chrome capture requests, lifecycle events, media blob uploads, read endpoints that record audit rows, and the daemon-public media worker.

The durability Wayfinder baseline retained SQLite WAL mode as the intended concurrency mode, and ticket 003 added a stress harness that exercises capture, lifecycle, read, media upload, and media-worker work against one SQLite database. Ticket 004 used that harness to harden the implementation instead of leaving WAL and startup behavior as operator lore.

## Decision

We will enforce a boring SQLite contention policy in code:

- initialize Browser Memory databases with `PRAGMA journal_mode = WAL`;
- keep every connection on a 30-second SQLite busy timeout;
- set connection `PRAGMA synchronous = NORMAL`, matching the usual WAL durability/performance tradeoff for a local single-operator daemon;
- avoid request-time schema/backfill DDL after startup by marking the initialized DB path ready inside the daemon process;
- use a bounded larger loopback listen backlog for stress bursts so the contention harness reaches SQLite instead of failing at TCP accept backlog.
- use per-write temporary media blob filenames before atomic replace, so concurrent browser/worker writes for the same artifact do not share one temp path.

This does not change the storage schema, privacy posture, API contract, or local-first boundary. It makes the existing SQLite storage decision explicit and testable.

## Decision drivers

- WAL allows readers and writers to coexist better than rollback journals for this daemon's read-heavy recall path.
- Daily-driver captures should not wait on repeated schema DDL or legacy media-task backfill scans.
- Media-worker and browser requests should wait briefly for a busy writer instead of surfacing transient `database is locked` failures.
- The stress harness should test the database contention boundary, not collapse first at the HTTP server listen queue.
- Browser-side uploads and daemon-worker backfills can race on the same media artifact; file staging must not fail before SQLite can reconcile the final artifact row.
- The policy must remain local, inspectable, and dependency-free.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Leave WAL as manual/operator state | No code change | New DBs can silently use rollback journal mode; future agents cannot rely on the baseline | Rejected |
| Set WAL and busy timeout in code | Local, boring, directly verifiable | WAL creates sidecar `-wal`/`-shm` files that backup/runbooks must tolerate | Chosen |
| Move to a client/server DB | Stronger concurrent writer model | Violates boring local dependency posture and is unnecessary for current load | Rejected |
| Run schema/backfill on every request | Self-heals missing DB state | Adds avoidable write/DDL contention on hot paths | Rejected |

## Consequences

- Positive: new runtime databases consistently enter WAL mode during initialization.
- Positive: request hot paths skip repeated schema/backfill initialization after server startup.
- Positive: the stress harness can run larger bursts without connection resets from the default listen backlog.
- Positive: concurrent media writes for the same artifact no longer collide on a deterministic `.tmp` pathname.
- Positive: busy writers have an explicit wait budget before an operational error surfaces.
- Negative: WAL sidecar files are now an intentional runtime artifact; backup and cleanup tooling must treat `*.sqlite3-wal` and `*.sqlite3-shm` as normal live SQLite companions.
- Neutral: this does not remove SQLite's single-writer model; future write-heavy bottlenecks still need focused measurement before larger storage changes.

## Verification / validation

- Verification: `daemon/tests/unit/test_db.py` checks the busy timeout, `journal_mode=wal`, `foreign_keys=ON`, and `synchronous=NORMAL` on an initialized DB.
- Verification: `daemon/tests/e2e/test_concurrency_stress.py` covers the stress runner and CLI entry point.
- Verification: `daemon/tests/integration/test_media_worker.py::test_concurrent_media_blob_writes_use_distinct_temp_files` covers concurrent same-artifact blob writes.
- Verification: `./scripts/run-concurrency-stress.sh --captures 80 --reader-rounds 80 --media-worker-runs 24 --max-workers 64 --timeout 90 --no-fail` passed with 80 captures, 264 mixed operations, 80 documents, 80 visit events, 80 succeeded media tasks, and SQLite `integrity_check=ok`.
- Validation: Browser Memory can keep using local SQLite/FTS5 under the daily-driver concurrency envelope without introducing a server DB or cloud dependency.

## Revisit triggers

- Supersede this ADR if sustained daily-driver evidence shows SQLite busy waits are still a material reliability bottleneck.
- Supersede this ADR before replacing SQLite/FTS5 with a client/server database or queue-backed write service.
- Revisit backup docs if retention/backup tooling does not correctly handle WAL sidecars.

## References

- `docs/wayfinder/durability-performance-coverage/tickets/004-sqlite-write-path-hardening.md`
- `daemon/src/browser_memory_daemon/db.py`
- `daemon/src/browser_memory_daemon/app.py`
- `daemon/src/browser_memory_daemon/media.py`
- `daemon/src/browser_memory_daemon/concurrency_stress.py`
