# Harden SQLite write-path policy

## Status
closed

## Question
After a stress harness exists, which SQLite write paths still need transaction-boundary changes, WAL/busy-timeout policy, idempotent startup/backfill handling, or background-worker isolation to eliminate lock failures under daily-driver load?

## Type
task

## Inputs / links

- `daemon/src/browser_memory_daemon/db.py`
- `daemon/src/browser_memory_daemon/app.py`
- `daemon/src/browser_memory_daemon/ingest.py`
- `daemon/src/browser_memory_daemon/media.py`
- `daemon/src/browser_memory_daemon/media_worker.py`
- Ticket 003 stress harness output

## Blocks / blocked by

- Blocks: high-confidence durability claim for the daily-driver path.
- Blocked by: none. Ticket 003 added `./scripts/run-concurrency-stress.sh` as the focused red/green harness.

## Resolution

Resolved by making the SQLite contention policy explicit and executable:

- `daemon/src/browser_memory_daemon/db.py` now initializes runtime DBs with `PRAGMA journal_mode = WAL`, keeps the 30-second busy timeout, enables foreign keys, and sets `PRAGMA synchronous = NORMAL` on connections.
- `daemon/src/browser_memory_daemon/app.py` now marks DB paths initialized after daemon startup so hot request handlers do not rerun schema creation or legacy media-task backfill. If a DB path is not ready/missing, handlers still lazily initialize it with `seed_media_tasks=False` under a process lock.
- The loopback server now uses a bounded larger request backlog (`REQUEST_QUEUE_SIZE = 128`) and daemon request threads, preventing high-burst stress runs from failing at TCP accept backlog before reaching SQLite.
- `daemon/src/browser_memory_daemon/media.py` now uses a unique temporary file name for each media blob write before atomic replace, preventing concurrent browser-upload/daemon-worker writes for the same artifact from colliding on one deterministic temp path.
- `daemon/tests/unit/test_db.py` now verifies WAL, busy timeout, foreign keys, and synchronous mode on initialized DBs.
- `daemon/tests/integration/test_media_worker.py` now covers concurrent same-artifact media blob writes.
- `docs/architecture/adr/0014-use-wal-and-bounded-sqlite-contention-policy.md` records the WAL/busy-timeout/startup-initialization decision. `docs/ARCHITECTURE.md` now treats SQLite WAL sidecars as expected runtime artifacts.

Evidence gathered:

- Pre-hardening stress with `./scripts/run-concurrency-stress.sh --captures 24 --reader-rounds 24 --media-worker-runs 8 --max-workers 32 --timeout 60 --no-fail` reported connection resets before all captures reached the daemon, proving the harness could fail before exercising SQLite.
- After hardening, the same 24-capture stress passed with `ok=True`, 24 captures, 80 mixed operations, 24 documents, 24 visit events, 24 succeeded media tasks, and SQLite `integrity_check=ok`.
- A higher 80-capture stress passed with `ok=True`, 80 captures, 264 mixed operations, 80 documents, 80 visit events, 80 succeeded media tasks, and SQLite `integrity_check=ok`.
- Focused tests passed: `/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/unit/test_db.py daemon/tests/e2e/test_http_api.py::test_http_capture_skips_request_time_db_initialization_after_startup daemon/tests/e2e/test_concurrency_stress.py daemon/tests/integration/test_media_worker.py::test_concurrent_media_blob_writes_use_distinct_temp_files`.

## New tickets / fog updates

- No new ticket. Ticket 012 should include WAL sidecar handling when it designs backup/retention posture.
