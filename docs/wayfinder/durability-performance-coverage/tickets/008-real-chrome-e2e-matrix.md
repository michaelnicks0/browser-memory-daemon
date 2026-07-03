# Expand real Chrome e2e matrix

## Status
open

## Question
Can the real Chrome for Testing e2e cover the critical policy modes, pause/control states, explicit block rules, media sidecars, and lifecycle surfaces without touching the daily-driver Chrome profile?

## Type
task

## Inputs / links

- `scripts/run-real-chrome-e2e.sh`
- `scripts/real-chrome-e2e.mjs`
- `docs/TESTS.md#policy-mode-verification-matrix`
- `docs/test-plan.md#mode-specific-e2e`
- ADR-0007 real Chrome e2e verification authority

## Blocks / blocked by

- Blocks: release confidence for extension/daemon integration changes.
- Blocked by: none; ticket 001 preferred.

## Resolution

Pending.

## New tickets / fog updates

Pending. If the matrix becomes slow/flaky, create a follow-up ticket to split smoke vs exhaustive e2e gates.
