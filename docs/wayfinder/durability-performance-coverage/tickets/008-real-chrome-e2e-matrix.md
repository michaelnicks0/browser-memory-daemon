# Expand real Chrome e2e matrix

## Status
closed

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

Closed in this slice. `scripts/run-real-chrome-e2e.sh` now runs an isolated Chrome for Testing matrix for `all` and `strict` by default, while preserving `BMD_REAL_CHROME_POLICY_MODE=<mode>` for single-mode debugging and `BMD_REAL_CHROME_MATRIX_MODES=...` for extended local matrices. The wrapper chooses free loopback port bases per matrix leg so sequential runs do not collide with stale local ports.

The real-browser scenario now also proves pause/control and explicit block-rule behavior, not only default capture:

- `capturePaused=true` skips injection/capture and leaves the paused fixture absent from search;
- a daemon URL-prefix block rule prevents an otherwise allowed page from becoming searchable;
- `all` mode still stores sensitive-domain and localhost/private fixtures;
- `strict` mode excludes sensitive-domain and localhost/private fixtures;
- allowed, SPA, public/cookie media, `blob:` media, lifecycle telemetry, and queue drainage remain covered in each matrix leg.

Evidence:

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python BMD_REAL_CHROME_MATRIX_MODES=all ./scripts/run-real-chrome-e2e.sh
# passed: all-mode pause, explicit block, media, lifecycle, queue, and DB-count assertions

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-real-chrome-e2e.sh
# passed: default all + strict Chrome for Testing matrix
```

## New tickets / fog updates

No new ticket. The default two-leg matrix remained stable in focused verification; keep the existing fog item about splitting smoke vs exhaustive e2e only if future runtime/flakiness becomes unacceptable.
