# Establish reliability/performance/coverage baseline

## Status
closed

## Question
What is the current measured baseline for daily-driver reliability, performance, and test coverage, and what explicit budgets should future tickets prove against?

## Type
research

## Inputs / links

- `docs/STATUS.md`
- `docs/TESTS.md`
- `docs/test-plan.md`
- `docs/ARCHITECTURE.md`
- `systemctl --user` service state for `browser-memory-daemon.service` and `browser-memory-media-worker.service`
- `journalctl --user` recent error history
- SQLite aggregate/freshness probes only; do not dump captured content
- Current tests: `BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh`

## Blocks / blocked by

- Blocks: most implementation tickets in this map, especially tickets 003, 009, 012, and 014.
- Blocked by: none.

## Resolution

Resolved 2026-07-03 UTC against repo HEAD on `main`. Probes were redaction-safe: no captured page text, snippets, cookies, tokens, or raw daily-driver URLs are recorded here.

### Current reliability baseline

| Area | Measured baseline | Budget for future tickets |
|---|---:|---|
| Daemon service | `browser-memory-daemon.service` is enabled/active/running; `NRestarts=0`; current process started 2026-07-02 20:19:49 EDT. | Service must be active after verification; no restart-count increase during the verification window unless the ticket explicitly restarts it. |
| Media-worker service | `browser-memory-media-worker.service` is enabled/active/running; `NRestarts=0`; current process started 2026-07-02 20:19:49 EDT. | Same as daemon, plus queue budgets below. |
| Loopback health | `GET /health` returned `ok=true`, `capture_enabled=true`, `policy_mode=all`; elapsed 0.055s for the single probe. | Health must stay `ok=true`; policy mode changes must be explicit. |
| Doctor | CLI `doctor` exited 0 in 3.15s; `ok=true`, SQLite `integrity_check=ok`, `chunks_missing_fts=0`. | Doctor must stay green; integrity and FTS-missing budgets are zero. |
| Journal history, 7 days | Daemon: 2 warnings, 0 errors. Media worker: 919 warning-or-higher lines: 300 errors and 619 warnings. Dominant class was a resolved 2026-06-27 to 2026-06-28 systemd start failure: `No space left on device` / `resources` / `Failed to start Browser Memory Media Worker` (900 lines). | Fresh verification windows should allow 0 new priority 0-3 service errors. Known historical warning debt must not grow. Add a health/preflight budget for storage headroom and service-start failures. |
| Filesystem headroom at measurement | WSL `/`: 755G size, 240G used, 477G free, 34% used. Windows `C:`: 1.7T size, 880G used, 797G free, 53% used. | Health/installer checks should fail or warn before systemd reports no-space service-start failures. Exact thresholds belong in ticket 015 / retention work. |

### Current daily-driver DB and queue baseline

| Area | Measured baseline | Budget for future tickets |
|---|---:|---|
| DB size | 367,779,840 bytes / 350.74 MiB; WAL 0 bytes. | No uncontrolled DB growth in tests; live growth needs ticket 012 retention thresholds before a hard cap. |
| Text/media storage | Clean text: 4,820 files, 23,551,779 bytes / 22.46 MiB. Media: 61,393 files, 12,389,528,151 bytes / 11.54 GiB. | Media cache must remain below configured gates; full DB/text retention budget is deferred to ticket 012. |
| Table counts | documents 1,851; visits 3,945; visit_events 9,697; snapshots 4,820; chunks/chunks_fts 15,651; media_artifacts 117,201; media_fetch_tasks 115,005; audit_events 241,672. | Schema/FTS counts must remain internally consistent; `chunks_missing_fts=0` is a hard budget. |
| Freshness | Latest visit/snapshot 2026-07-03T00:44:25.203Z; latest visit event 2026-07-03T00:44:39.093Z; latest media artifact 2026-07-03 00:40:10; baseline probe timestamp 2026-07-03T00:47:21Z. | Freshness checks should compare against expected operator activity, not wall-clock alone. Ticket 002 should surface this without dumping captured content. |
| Media artifacts by status | stored 60,974; purged 53,389; referenced 1,849; skipped 611; expired 320; retrying 36; failed 22. | Terminal/expected statuses need classification coverage; unexplained `failed` and `retrying` should not grow without an explicit reason. |
| Media tasks by status | succeeded 113,413; skipped 1,518; retrying 35; leased 22; failed 17. Due pending/retrying tasks: 31. Stale leases: 0. | Stale leases budget is zero. Retry/failed/due counts may exist for remote/source failures, but should be trended and classified by tickets 002, 006, and 015. |

### Current performance baseline

These are guardrails from one local WSL/Windows run, not a deterministic benchmark suite. Ticket 009 should replace them with synthetic, repeatable machine-readable budgets.

| Probe | Measured baseline | Interim budget |
|---|---:|---:|
| Full local gate: `BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh` | pass, 45.28s | pass, <= 90s unless environment explains variance |
| Daemon pytest: `/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q` | pass, 59 tests, 26.41s | pass, <= 60s |
| Extension `npm test && npm run build` | pass, 23 tests, 0.43s | pass, <= 2s |
| Real Chrome e2e | pass, 16.83s | pass, <= 45s |
| `/health` live loopback, 7 samples | median 1.10ms; observed p95 1.34ms | p95 <= 50ms |
| `/policy/rules`, 7 samples | median 2.83ms; observed p95 3.03ms | p95 <= 50ms |
| `/search` no-hit, 7 samples | median 14.23ms; observed p95 14.65ms | p95 <= 50ms |
| `/recent?limit=25`, 7 samples | median 373.69ms; observed p95 383.47ms | p95 <= 1s |
| `/timeline?limit=100`, 7 samples | median 1,391.96ms; observed p95 1,404.84ms | p95 <= 3s |
| `/doctor`, 7 samples | median 3,232.69ms; observed p95 3,275.98ms | p95 <= 6s |

### Current coverage baseline

| Area | Measured baseline | Budget for future tickets |
|---|---:|---|
| Static test inventory | 82 test functions across 15 files: 59 daemon pytest tests and 23 extension `node:test` tests. | Inventory must not decrease without a deliberate explanation; behavior changes need focused tests. |
| Source/test line snapshot | Daemon source: 18 files / 4,360 total lines; daemon tests: 10 files / 1,939 total lines. Extension source: 9 files / 2,138 total lines; extension tests: 5 files / 371 total lines. | Use as a coarse shape check only; real measured line/branch coverage is deferred to ticket 014 after first-wave coverage expansion. |
| Requirement trace | `docs/test-plan.md` maps REQ-001 through REQ-022 to current evidence. | New or changed requirements must update `docs/test-plan.md` and `docs/TESTS.md` inventory/gates. |

### Summary decision

The baseline is good enough to unblock targeted durability/performance/coverage work, but not good enough to declare a hard release gate yet. Future tickets should prove against the hard correctness budgets now, use the performance budgets as interim guardrails, and move repeatable benchmarking/coverage enforcement into tickets 009 and 014.

## New tickets / fog updates

- Created [015 — Add storage-headroom and service-start failure budget checks](015-storage-headroom-service-start-budget.md) for the dominant media-worker `No space left on device` / systemd start-failure class.
- Unblocked ticket 012; retention/compaction/backup design now has current DB/media/headroom evidence.
- Ticket 009 remains the path to replace ad hoc live endpoint timings with deterministic synthetic benchmark output.
- Ticket 014 remains blocked by at least one coverage-expansion ticket; this ticket established the inventory baseline but did not add measured line/branch coverage.
