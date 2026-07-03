# Expand media-worker lifecycle invariant coverage

## Status
open

## Question
Can the media worker be covered by explicit invariants for task claim/release, stale lease recovery, retry/backoff, terminal classifications, idempotent reprocessing, and no duplicate blob side effects?

## Type
task

## Inputs / links

- `daemon/src/browser_memory_daemon/media_worker.py`
- `daemon/src/browser_memory_daemon/media.py`
- `daemon/tests/integration/test_media_worker.py`
- `docs/media-artifacts.md`
- `docs/ARCHITECTURE.md#durable-media-sidecar-architecture`

## Blocks / blocked by

- Blocks: worker durability and performance work.
- Blocked by: none; ticket 001 preferred.

## Resolution

Pending.

## New tickets / fog updates

Pending. If task-state semantics change, inspect ADR-0005 and decide whether to supersede/update docs.
