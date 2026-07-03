# Add performance benchmark harness and budgets

## Status
closed

## Question
Can the repo measure ingest, search, recent/timeline/detail, media-worker task selection, and docs/test gates on synthetic datasets with explicit local budgets and machine-readable output?

## Type
prototype

## Inputs / links

- `daemon/src/browser_memory_daemon/ingest.py`
- `daemon/src/browser_memory_daemon/search.py`
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/media_worker.py`
- `daemon/src/browser_memory_daemon/app.py` read endpoints that synchronously write audit rows
- `daemon/tests/`
- `docs/ARCHITECTURE.md#storage-model`

## Blocks / blocked by

- Blocks: ticket 010 query/index optimization and any performance gate.
- Blocked by: none. Ticket 001 provides interim live-system guardrails; this ticket should replace them with deterministic synthetic benchmark output.

## Resolution

Closed in this slice. Added a deterministic, local-only synthetic benchmark harness:

- `daemon/src/browser_memory_daemon/performance_benchmarks.py` generates synthetic captures and measures ingest, search, recent, timeline, document detail, snapshot detail, media queue status, doctor, media-worker task selection, media-worker `run_once`, and DB/WAL/blob sidecar growth.
- `scripts/run-performance-benchmarks.sh` runs the harness with Python 3.11 when `BMD_PYTHON` is not set, keeping repo Python requirements intact on hosts where `python3` is older.
- `--json` emits machine-readable output; default output is a compact human summary.
- The benchmark records endpoint-style read-audit write overhead estimates by measuring direct read calls separately from read calls followed by `audit(...)` + commit.
- Budgets are explicit and advisory only; ADR-0016 records the rationale for not making them hard gates yet.

Evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_performance_benchmarks.py
# 2 passed

./scripts/run-performance-benchmarks.sh --small --json >/tmp/bmd_benchmark.json
# ok=True captures=40 chunks=40 media_stored=20 media_failed=0 media_bytes=355 failed_budgets=0

./scripts/run-performance-benchmarks.sh --small
# emitted compact human summary with ingest/read/media-worker/storage/advisory-budget lines
```

## New tickets / fog updates

Ticket 010 is unblocked. Keep the existing fog item about whether performance budgets should become hard gates; ADR-0016 says budgets stay advisory until measured evidence supports hard thresholds.
