# Establish reliability/performance/coverage baseline

## Status
open

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

Pending.

## New tickets / fog updates

Pending. If the baseline reveals a dominant failure class not represented in the map, create a new ticket instead of expanding this one.
