---
id: ADR-0059
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes: []
superseded_by: []
related:
  - ADR-0007
implementation_status: implemented
implementation:
  - scripts/chrome-for-testing-lock.json
  - scripts/chrome-for-testing.mjs
  - scripts/real-chrome-e2e.mjs
  - extension/tests/unit/chrome_for_testing.test.js
  - docs/TESTS.md
verification:
  - node --test extension/tests/unit/chrome_for_testing.test.js
  - BMD_REAL_CHROME_ALLOW_DOWNLOAD=0 BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-real-chrome-e2e.sh
---

# Pin and verify Chrome for Testing release evidence

## Context

ADR-0007 makes an isolated real branded browser the extension verification authority. The harness previously fetched Google's `last-known-good` metadata on every run, selected whatever Stable version was current, trusted an existing extracted executable without verification, and downloaded unless `BMD_REAL_CHROME_ALLOW_DOWNLOAD=0` was set. That made release evidence time-dependent and allowed an implicit network side effect.

## Decision

1. `scripts/chrome-for-testing-lock.json` pins one Windows x64 Chrome for Testing version, canonical download URL, archive size/SHA-256, and extracted `chrome.exe` size/SHA-256.
2. A cached executable is accepted only after its size and SHA-256 match the lock. Cached verification performs no metadata or download request.
3. Missing or corrupt cached bytes fail closed unless `BMD_REAL_CHROME_ALLOW_DOWNLOAD=1` is explicitly present.
4. An approved download uses only the pinned canonical URL, writes to a unique staged archive, verifies archive size and SHA-256 before rename/unzip, then verifies the extracted executable before use.
5. `BMD_CHROME_EXE` remains an explicit operator override for a separately managed executable and is reported as such by the harness.
6. Updating the pinned release is a reviewed repository change: download intentionally, compute hashes/sizes from the exact archive and executable, update the lock, run lock unit tests, and run the isolated real-Chrome matrix with downloads disabled.
7. The isolated temporary browser profile and prohibition on the operator's default profile remain unchanged.

## Consequences

### Positive

- Release evidence identifies exact browser bytes rather than a moving Stable channel.
- Routine real-browser validation is network-free when the pinned artifact is cached.
- Cache corruption or substitution fails before browser launch.
- Downloads become explicit and checksum-gated.

### Negative

- Chrome updates require a deliberate lock refresh and review.
- Both archive and executable metadata must be maintained.
- An explicit `BMD_CHROME_EXE` override is outside lock verification and must be treated as operator-supplied evidence.

## Verification

- Node unit tests validate lock schema, cached verification, missing-cache refusal, and corrupt-cache refusal without network access.
- The pinned cached `150.0.7871.115` executable passes the `all` and `strict` isolated-profile real-browser matrix with `BMD_REAL_CHROME_ALLOW_DOWNLOAD=0`.
- Generic fast and broad gates remain network-free and do not invoke real Chrome automatically.
