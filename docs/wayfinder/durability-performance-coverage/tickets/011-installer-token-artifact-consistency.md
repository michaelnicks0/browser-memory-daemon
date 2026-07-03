# Harden installer, token, and Windows artifact consistency

## Status
open

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

Pending.

## New tickets / fog updates

Pending. Do not modify the daily Chrome profile JSON; test with temp dirs or explicit dry-run/check mode.
