# Expand HTTP API contract coverage

## Status
closed

## Question
Can every HTTP endpoint have contract tests for auth, malformed input, bounded limits, unsupported routes/methods, stable error shape, and no uncaught server tracebacks?

## Type
task

## Inputs / links

- `docs/api.md`
- `daemon/src/browser_memory_daemon/app.py`
- `daemon/src/browser_memory_daemon/policy_store.py`
- `daemon/tests/e2e/test_http_api.py`
- `daemon/tests/e2e/test_admin_api.py`

## Blocks / blocked by

- Blocks: operational consistency and safer refactors of `app.py`.
- Blocked by: none; ticket 001 preferred for budget language.

## Resolution

Closed in this slice. HTTP contract coverage now exercises stable JSON error behavior and bounded/duplicate contracts across the loopback API:

- Missing and invalid bearer tokens return JSON `401` responses with a top-level `error` string.
- Malformed JSON, invalid capture payloads, unknown routes, and unsupported methods are covered as JSON error responses (`400`, `404`, `501`).
- Limit clamping is covered for `recent`, `timeline`, and media queue status surfaces.
- Duplicate policy-rule creation through HTTP is covered and returns the existing semantic rule added in ticket 016.
- `MemoryHandler.send_error` now converts BaseHTTPRequestHandler unsupported-method errors into the same JSON error shape instead of the default HTML page.

Evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_http_api.py daemon/tests/e2e/test_admin_api.py daemon/tests/unit/test_policy_store.py
# 12 passed

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
# pytest passed; extension node:test 23/23; extension build; real Chrome for Testing e2e ok; secret scan passed
```

## New tickets / fog updates

No new tickets. `docs/api.md` now records stable JSON error shape, common status codes, limit bounds, and duplicate policy-rule semantics.
