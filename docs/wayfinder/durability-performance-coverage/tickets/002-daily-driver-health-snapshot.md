# Add daily-driver health snapshot command

## Status
open

## Question
Can the repo provide one redaction-safe command that proves the daily-driver stack is healthy without manually stitching together systemd, Windows loopback, DB freshness, queue, and extension-artifact checks?

## Type
task

## Inputs / links

- `docs/USER_GUIDE.md#daily-driver-state-checks`
- `docs/TESTS.md#daily-driver-smoke-checklist`
- `scripts/install-daily-driver.sh`
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/cli.py`
- Recent operational finding: service `active` was insufficient; journal/restart churn and `database is locked` had to be checked.

## Blocks / blocked by

- Blocks: ticket 011 installer consistency; future soak/alerting work.
- Blocked by: ticket 001 preferred, but can proceed independently if scoped to existing health evidence.

## Resolution

Pending.

## New tickets / fog updates

Pending. If this becomes an API/CLI contract change, inspect ADRs and decide whether an ADR update is needed.
