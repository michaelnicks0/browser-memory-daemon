# Add performance benchmark harness and budgets

## Status
open

## Question
Can the repo measure ingest, search, recent/timeline/detail, media-worker task selection, and docs/test gates on synthetic datasets with explicit local budgets and machine-readable output?

## Type
prototype

## Inputs / links

- `daemon/src/browser_memory_daemon/ingest.py`
- `daemon/src/browser_memory_daemon/search.py`
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/media_worker.py`
- `daemon/tests/`
- `docs/ARCHITECTURE.md#storage-model`

## Blocks / blocked by

- Blocks: ticket 010 query/index optimization and any performance gate.
- Blocked by: ticket 001 baseline.

## Resolution

Pending.

## New tickets / fog updates

Pending. Keep benchmarks synthetic and deterministic; do not use captured live text as fixture input.
