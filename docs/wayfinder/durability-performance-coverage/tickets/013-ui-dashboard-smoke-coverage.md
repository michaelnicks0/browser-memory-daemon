# Add local UI dashboard smoke coverage

## Status
closed

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

Closed with deterministic local UI smoke coverage:

- `daemon/tests/e2e/test_ui_dashboard_smoke.py` starts the existing daemon test server and verifies `/ui` serves core dashboard panels plus daemon-injected bootstrap JSON.
- Static `/ui/app.js` and `/ui/style.css` are served token-free.
- Static asset path traversal under `/ui/` is rejected instead of serving arbitrary repo files.
- `daemon/tests/e2e/ui_dashboard_smoke_runner.mjs` executes the real `ui/app.js` in a low-dependency mocked DOM/fetch harness, proving bootstrap parsing, initial API calls, empty states, no-token state, and per-panel API error rendering without using Michael's browser profile or adding browser automation dependencies.

Evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_ui_dashboard_smoke.py daemon/tests/e2e/test_admin_api.py
# 6 passed

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
# pytest passed; extension node:test 27/27; extension build; real Chrome for Testing all+strict matrix ok; secret scan passed

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_test_inventory.py --check
# 109 tests / 22 files

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
# 78 rendered docs match source
```

## New tickets / fog updates

Resolved the dashboard-harness fog in favor of a low-dependency DOM/fetch smoke harness for this ticket. Full browser UI automation remains unnecessary unless future dashboard behavior needs layout/browser API coverage.
