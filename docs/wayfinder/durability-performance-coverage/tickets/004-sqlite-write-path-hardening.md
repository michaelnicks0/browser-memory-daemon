# Harden SQLite write-path policy

## Status
blocked

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
- Blocked by: ticket 003.

## Resolution

Pending.

## New tickets / fog updates

Pending. If WAL/pragma policy becomes a durable architecture decision, create or supersede an ADR.
