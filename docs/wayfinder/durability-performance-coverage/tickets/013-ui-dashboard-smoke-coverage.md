# Add local UI dashboard smoke coverage

## Status
open

## Question
Can the local UI get smoke tests that verify token bootstrap parsing, initial API calls, empty/error states, and core panels without requiring Michael's browser profile?

## Type
task

## Inputs / links

- `ui/`
- `daemon/src/browser_memory_daemon/app.py` UI serving and bootstrap path
- `daemon/tests/e2e/test_admin_api.py`
- `docs/USER_GUIDE.md#search-and-inspect-memory`
- `docs/api.md`

## Blocks / blocked by

- Blocks: UI refactors and operator dashboard consistency.
- Blocked by: none; ticket 001 preferred.

## Resolution

Pending.

## New tickets / fog updates

Pending. Fog remains on whether to use a browser automation dependency or a low-dependency static/DOM harness.
