# Harden installer, token, and Windows artifact consistency

## Status
closed

## Question
Can the daily-driver install/refresh path be made self-validating and testable: Python runtime, service units, token file permissions, process-arg secrecy, Windows extension artifact contents, and Chrome manual reload guidance?

## Type
task

## Inputs / links

- `scripts/install-daily-driver.sh`
- `docs/USER_GUIDE.md#install-or-refresh-daily-chrome-integration`
- `docs/TESTS.md#daily-driver-smoke-checklist`
- `AGENTS.md` daily-driver refresh command
- Skill guidance from `local-browser-extension-daemon-ops`

## Blocks / blocked by

- Blocks: reliable operator refresh and future token rotation work.
- Blocked by: none. Ticket 002 supplies reusable health/artifact checks.

## Resolution

Closed in this slice. The daily-driver install path now has an explicit non-mutating preview/check surface and the redaction-safe health snapshot verifies the installer/token/artifact invariants called out by the ticket.

Implemented:

- `scripts/install-daily-driver.sh --dry-run` validates inputs and Python 3.11+ runtime, prints the planned config/unit/extension/service actions, and makes no files/service/Chrome artifact changes.
- `scripts/install-daily-driver.sh --check` runs the installed-state health/artifact check without rebuilding, copying, writing units, rotating tokens, or restarting services.
- `scripts/daily-driver-health.sh` no longer passes the bearer token in CLI arguments; it uses `BMD_API_TOKEN` for the short-lived health command.
- Daily-driver health JSON now checks protected token/env files, token-file/env/extension token consistency without printing token values, unit-file `EnvironmentFile`/`ExecStart` expectations, and live service process-argument token secrecy.
- Operator docs now explain dry-run/check mode, manual Chrome reload, token permissions, EnvironmentFile usage, and extension token matching.

Focused evidence:

```bash
bash -n scripts/install-daily-driver.sh scripts/daily-driver-health.sh
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/unit/test_daily_driver_health.py daemon/tests/e2e/test_daily_driver_install.py
# 4 passed

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  BMD_POLICY_MODE=all \
  BMD_WINDOWS_EXTENSION_DIR="$tmp/windows-extension" \
  XDG_CONFIG_HOME="$tmp/config-home" \
  XDG_DATA_HOME="$tmp/data-home" \
  XDG_STATE_HOME="$tmp/state-home" \
  ./scripts/install-daily-driver.sh --dry-run >/tmp/bmd_install_dry_run.txt
# dry_run_exit=0; non_mutating_paths_ok=1
```

## New tickets / fog updates

No new ticket. Do not modify the daily Chrome profile JSON; future installer changes should continue using temp dirs or explicit `--dry-run`/`--check` paths for verification.
