# Build deterministic concurrency stress harness

## Status
open

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
- Blocked by: ticket 001 baseline.

## Resolution

Pending.

## New tickets / fog updates

Pending. If deterministic reproduction is hard, keep the harness as a high-repetition flake amplifier and document reproduction rate.
