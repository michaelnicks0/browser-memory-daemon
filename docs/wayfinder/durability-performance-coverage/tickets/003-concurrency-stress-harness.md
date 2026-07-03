# Build deterministic concurrency stress harness

## Status
closed

## Question
Can we create a deterministic stress harness that reproduces daily-driver contention classes: concurrent captures, lifecycle events, search/detail reads, media blob uploads, and media-worker passes against the same SQLite DB?

## Type
prototype

## Inputs / links

- `daemon/src/browser_memory_daemon/app.py`
- `daemon/src/browser_memory_daemon/db.py`
- `daemon/src/browser_memory_daemon/media_worker.py`
- `daemon/tests/e2e/test_http_api.py`
- `daemon/tests/integration/test_media_worker.py`
- Recent fix commit `2a0d4b2 fix: reduce sqlite lock contention`

## Blocks / blocked by

- Blocks: ticket 004 SQLite write-path hardening.
- Blocked by: none. Ticket 001 baseline is complete.

## Resolution

Resolved by adding a bounded deterministic stress harness:

- Added `daemon/src/browser_memory_daemon/concurrency_stress.py` with an isolated-runtime runner that starts the loopback daemon on an ephemeral port and drives one SQLite database from multiple concurrent work classes.
- Added `scripts/run-concurrency-stress.sh` as the operator/dev entry point. By default it uses a temporary runtime root and synthetic data, so it does not mutate daily-driver storage.
- The harness covers concurrent `/capture` writes, `/visit-events` lifecycle writes, `/search` + `/recent` + `/documents/{id}` + queue-status reads, raw media blob uploads, and direct media-worker `run_once` passes through separate SQLite connections.
- The JSON report exits non-zero if any operation fails, SQLite `PRAGMA integrity_check` is not `ok`, chunks are missing FTS rows, expected synthetic documents/visit events are absent, or operation phases fail.
- Added e2e coverage for the Python runner and CLI-style module entry point.
- Updated `docs/TESTS.md` with stress-harness purpose, command, knobs, and the warning not to point it at daily-driver runtime data unless intentional.
- Inspected the ADR index. No ADR was added because this is an additive verification harness over existing HTTP/SQLite/media-worker boundaries, not a change to the canonical verification authority, interfaces, schema, storage, or privacy posture.

Verification evidence:

- `/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_concurrency_stress.py` passed.
- `./scripts/run-concurrency-stress.sh --captures 4 --reader-rounds 4 --media-worker-runs 2 --max-workers 8 --timeout 20` passed with `ok=True`, `status=ok`, 4 captures, 14 mixed operations, 4 documents, 4 visit events, and SQLite `integrity_check=ok`.
- `python3.11 -m py_compile daemon/src/browser_memory_daemon/concurrency_stress.py` passed.
- `bash -n scripts/run-concurrency-stress.sh` passed.
- `python scripts/generate_test_inventory.py --check` passed after inventory update to 86 tests / 17 files.

## New tickets / fog updates

- Ticket 004 is unblocked and should use `./scripts/run-concurrency-stress.sh` as the focused red/green gate for SQLite write-path hardening.
