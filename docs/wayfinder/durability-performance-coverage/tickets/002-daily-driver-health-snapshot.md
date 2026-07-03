# Add daily-driver health snapshot command

## Status
closed

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
- Ticket 001 baseline: service `active` plus `/doctor ok` still missed 7-day media-worker journal churn from no-space start failures; include journal counts, queue state, and filesystem headroom without dumping captured content.

## Blocks / blocked by

- Blocks: ticket 011 installer consistency; future soak/alerting work.
- Blocked by: ticket 001 preferred, but can proceed independently if scoped to existing health evidence.

## Resolution

Resolved by adding a redaction-safe daily-driver health snapshot surface:

- Added `daily-driver-health` to the Python CLI.
- Added `scripts/daily-driver-health.sh` so the operator can run one command without manually copying the token.
- Snapshot output covers WSL `/health`, optional Windows PowerShell loopback health, systemd user-unit state, sanitized journal warning/error aggregates, read-only SQLite integrity/count/freshness checks, media queue aggregates, storage headroom, and Windows extension artifact/token-default/policy-default checks.
- Output intentionally excludes captured page text, snippets, cookies, bearer token values, raw captured URLs, media source URLs, and extension API token values.
- The command exits non-zero on hard errors (`ok=false`) and supports `--no-fail` for report-only collection.
- Updated `docs/USER_GUIDE.md`, `docs/CLI_UX_CONTRACT.md`, `docs/TESTS.md`, and `scripts/install-daily-driver.sh` to make the snapshot the primary daily-driver check.
- Inspected the ADR index. No ADR was added because this is an additive operator CLI/runbook surface over existing boundaries and data stores, not a change to capture, auth, storage, schema, policy, or component ownership semantics.

Verification evidence:

- `/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/unit/test_daily_driver_health.py daemon/tests/e2e/test_cli_admin.py` passed.
- `/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q` passed.
- `python scripts/generate_test_inventory.py --check` passed after inventory update to 84 tests / 16 files.
- `python3.11 -m py_compile daemon/src/browser_memory_daemon/daily_driver_health.py daemon/src/browser_memory_daemon/cli.py` passed.
- `bash -n scripts/daily-driver-health.sh scripts/install-daily-driver.sh` passed.
- Live smoke: `./scripts/daily-driver-health.sh --journal-since '1 hour ago'` returned exit 0 with `ok=True`, `status=warning`, WSL loopback OK, Windows loopback OK, DB OK, extension artifact OK, and one non-fatal media-queue retry warning.

## New tickets / fog updates

- Ticket 011 can reuse the snapshot checks for installer/token/artifact validation and is no longer waiting on ticket 002.
