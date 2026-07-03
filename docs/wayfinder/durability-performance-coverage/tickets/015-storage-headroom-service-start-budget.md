# Add storage-headroom and service-start failure budget checks

## Status
open

## Question
Can Browser Memory Daemon detect low filesystem/runtime headroom and service-start failure churn before the daily-driver media worker reaches systemd `No space left on device` / `resources` failures?

## Type
task

## Inputs / links

- Ticket 001 baseline: 7-day media-worker journal history contained 919 warning-or-higher lines, dominated by 900 resolved systemd start-failure lines from 2026-06-27 to 2026-06-28.
- `scripts/install-daily-driver.sh`
- `docs/TESTS.md#daily-driver-smoke-checklist`
- `docs/USER_GUIDE.md`
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/cli.py`
- Current runtime locations: WSL data/state/config roots and Windows extension artifact root.

## Blocks / blocked by

- Blocks: hard operational alerting budgets, installer safety, and long-running soak gates.
- Blocked by: none. Coordinate with ticket 002 if the health snapshot command is implemented first.

## Resolution

Pending.

## New tickets / fog updates

Pending. If this chooses hard disk thresholds, reconcile with ticket 012 retention/compaction/backup design and consider whether an ADR is needed for operator-facing failure semantics.
