# Expand HTTP API contract coverage

## Status
open

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

Pending.

## New tickets / fog updates

Pending. If endpoint behavior is underspecified, update `docs/api.md` with the contract proven by tests. Include duplicate policy-rule creation semantics if this ticket touches rule endpoints; a late ticket-004 audit noted concurrent identical creates can duplicate rows without a semantic uniqueness constraint.
