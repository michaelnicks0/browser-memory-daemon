# Expand media-worker lifecycle invariant coverage

## Status
open

## Question
Can the media worker be covered by explicit invariants for task claim/release, stale lease recovery, retry/backoff, terminal classifications, idempotent reprocessing, and no duplicate blob side effects?

## Type
task

## Inputs / links

- Subagent audit `deleg_26f18a8a`, 2026-07-02
- `daemon/src/browser_memory_daemon/media_worker.py`
- `daemon/src/browser_memory_daemon/media.py`
- `daemon/src/browser_memory_daemon/app.py` (`fetch_pending_media_artifacts` call paths)
- `daemon/tests/integration/test_media_worker.py`
- `daemon/tests/e2e/test_concurrency_stress.py`
- `docs/media-artifacts.md`
- `docs/ARCHITECTURE.md#durable-media-sidecar-architecture`

## Blocks / blocked by

- Blocks: worker durability and performance work.
- Blocked by: none; ticket 001 preferred.

## Resolution

Pending.

## Scope notes from late ticket-004 audit

- Direct/background media fetches launched from `app.py` bypass the `media_fetch_tasks` lease model and can race with browser uploads, manual fetch controls, and `media_worker.run_once`.
- Media-worker startup/run currently performs broad normalization and task claiming in one write transaction; separate bounded maintenance from hot-path claim/fetch if tests show lock pressure.
- If normalization is moved out of the broad transaction, task claim should become explicitly atomic (`BEGIN IMMEDIATE`/guarded `UPDATE ... RETURNING` or equivalent rowcount-verified claim).
- Coverage should include `media_fetch_on_capture=True`, not only the stress harness default path that disables per-capture daemon fetches.

## New tickets / fog updates

Pending. If task-state semantics change, inspect ADR-0005 and decide whether to supersede/update docs.
