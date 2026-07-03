# Expand media-worker lifecycle invariant coverage

## Status
closed

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

Closed in this slice. Media fetch task leasing is now the single coordination path for worker, manual `/media-artifacts/fetch-pending`, and `media_fetch_on_capture=True` background fetches:

- `fetch_pending_media_artifacts` seeds missing `media_fetch_tasks`, atomically claims due tasks with the same guarded lease path as `media_worker.run_once`, and processes only rows owned by the caller's lease.
- Task claiming now revalidates status, lease freshness, and artifact filters at update time, so concurrent workers/manual calls cannot process an actively leased task; stale leases remain recoverable.
- Shared task processing records attempts/backoff, clears leases on success/terminal/retry outcomes, and preserves `status_reason` in media API results for stable retry diagnostics.
- Integration coverage now proves active lease isolation, stale lease recovery, retry/backoff release semantics, idempotent already-stored cleanup without duplicate blob writes, and the `media_fetch_on_capture=True` app path.

Evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_media_worker.py
# 19 passed

/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_media_worker.py daemon/tests/e2e/test_concurrency_stress.py daemon/tests/e2e/test_http_api.py
# 24 passed

./scripts/run-concurrency-stress.sh --captures 24 --reader-rounds 24 --media-worker-runs 8 --max-workers 32 --timeout 60 --no-fail
# ok=true; captures 24/24; mixed 80/80; integrity_check=ok; media_task_statuses={"succeeded": 24}
```

## Scope notes from late ticket-004 audit

- Direct/background media fetches launched from `app.py` bypass the `media_fetch_tasks` lease model and can race with browser uploads, manual fetch controls, and `media_worker.run_once`.
- Media-worker startup/run currently performs broad normalization and task claiming in one write transaction; separate bounded maintenance from hot-path claim/fetch if tests show lock pressure.
- If normalization is moved out of the broad transaction, task claim should become explicitly atomic (`BEGIN IMMEDIATE`/guarded `UPDATE ... RETURNING` or equivalent rowcount-verified claim).
- Coverage should include `media_fetch_on_capture=True`, not only the stress harness default path that disables per-capture daemon fetches.

## New tickets / fog updates

No new tickets. Task-state semantics now better enforce ADR-0005's durable lazy sidecar intent without changing storage/schema boundaries, so no superseding ADR was needed.
