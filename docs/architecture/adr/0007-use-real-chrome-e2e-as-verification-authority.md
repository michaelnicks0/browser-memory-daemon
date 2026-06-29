---
id: ADR-0007
status: accepted
date: 2026-06-14
decision_date: 2026-06-08
decider: Operator
scope: repo
backfilled: true
supersedes: []
superseded_by: []
related:
  - docs/TESTS.md
  - docs/test-plan.md
  - docs/ARCHITECTURE.md
  - scripts/run-e2e.sh
  - scripts/run-real-chrome-e2e.sh
  - scripts/real-chrome-e2e.mjs
  - extension/tests/unit/
  - daemon/tests/
verification:
  - ADR lint + repo Markdown fence check
  - git diff --check -- .
  - ./scripts/secret-scan.sh
  - BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh with temporary Python 3.11 shim
---

# ADR-0007: Use Real Chrome E2E as the Verification Authority

## Context

This ADR backfills a decision that existed before the ADR workflow was added.

Browser Memory Daemon depends on behavior that unit tests and mocked DOM tests cannot fully prove: MV3 service-worker messaging, extension injection, Chrome permissions, page runtime behavior, storage/queue drainage, Windows/WSL loopback, Chrome cookie behavior, SPA navigation, hidden/form/editable DOM skips, and synthetic media/blob capture.

The project needs fast unit/integration tests, but the browser boundary must be validated in a real Chrome-family runtime.

## Decision

We will treat real Windows Chrome-family e2e as the verification authority for extension-to-WSL behavior.

The primary gate remains `./scripts/run-e2e.sh`, which runs daemon tests, extension unit tests/build, real Chrome e2e unless explicitly skipped, secret scan, and whitespace checks. `scripts/run-real-chrome-e2e.sh` / `scripts/real-chrome-e2e.mjs` use Chrome for Testing by default because branded Chrome can ignore command-line unpacked-extension automation. Non-all policy modes remain separately smokeable with `BMD_REAL_CHROME_POLICY_MODE`.

## Decision drivers

- MV3 behavior can pass unit tests while failing in real Chrome.
- Windows Chrome to WSL loopback must be proven end-to-end, not inferred.
- Cookie-required media and `blob:` media need browser-runtime evidence.
- The default `all` policy must be validated against real hidden/form/editable skips and sensitive/local fixture behavior.
- A repeatable synthetic profile is safer than testing against Operator's default Chrome profile.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Unit/integration tests only | Fast and deterministic | Cannot prove Chrome extension/runtime/WSL behavior | Rejected |
| Test against Operator's daily Chrome profile | Most realistic environment | Unsafe, stateful, hard to reproduce, risks personal profile data | Rejected |
| Branded Chrome automation only | Uses familiar installed Chrome | Chrome 137+ can ignore command-line unpacked-extension automation | Rejected as sole gate |
| Chrome for Testing with synthetic fixtures | Reproducible, isolated, real browser/runtime | Slower and needs Windows/browser tooling | Chosen |

## Decision history

- `2c2b76b` (2026-06-08) added real Windows Chrome extension e2e.
- `a384d41` (2026-06-08) documented Chrome CDP/profile caveats.
- `dfeb585` (2026-06-08) recorded daily-driver Chrome install results.
- Current evidence: `docs/TESTS.md` makes real Chrome e2e a primary gate and documents the Chrome for Testing caveat.
- Current evidence: `scripts/real-chrome-e2e.mjs` installs/uses Chrome for Testing, synthetic profile/runtime roots, and end-to-end DB/media assertions.

## Consequences

- Positive: verification covers the highest-risk boundary: real Chrome extension to WSL daemon to SQLite/blob storage.
- Positive: tests prove both browser-side and daemon-side media lanes with public, cookie-required, and `blob:` fixtures.
- Positive: policy-mode behavior is validated in a browser, not only in daemon/extension units.
- Negative: full e2e is slower and can depend on Windows/Chrome/WSL environment health.
- Negative: Chrome for Testing download/cache behavior is another operational dependency.
- Neutral: developers can set `BMD_SKIP_REAL_CHROME_E2E=1` for constrained runs, but that is not equivalent evidence.

## Verification / validation

- Verification: `scripts/run-e2e.sh` runs daemon pytest through `BMD_PYTHON`/Python 3.11+, extension `npm test` and `npm run build`, real Chrome e2e by default, secret scan, and `git diff --check -- .`.
- Verification: `scripts/real-chrome-e2e.mjs` asserts real search hits, hidden/form/editable absence, all-mode sensitive/local fixtures, SPA route capture, media storage, queue drainage, DB counts, and lifecycle telemetry.
- Verification: `docs/TESTS.md` and `docs/test-plan.md` list the primary gates and requirement coverage.
- Backfill hygiene verification passed on 2026-06-14: ADR lint, repo Markdown fence check, `git diff --check -- .`, `./scripts/secret-scan.sh`, and `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` using a temporary Python 3.11 shim.
- Validation: architecture-impacting browser/daemon changes can be accepted only after the real boundary is exercised or an explicit skip/blocker is reported.

## Revisit triggers

- Supersede this ADR if Chrome extension architecture is replaced by native capture or another browser runtime.
- Supersede this ADR if Chrome for Testing stops being reliable for unpacked-extension automation.
- Supersede this ADR if a new deterministic browser harness provides stronger evidence.
- Supersede this ADR if CI/headless constraints require a split between required and operator-local gates.

## References

- `docs/TESTS.md`
- `docs/test-plan.md`
- `scripts/run-e2e.sh`
- `scripts/run-real-chrome-e2e.sh`
- `scripts/real-chrome-e2e.mjs`
- `daemon/tests/`
- `extension/tests/`
