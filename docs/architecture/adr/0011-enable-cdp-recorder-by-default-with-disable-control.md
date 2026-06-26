---
id: ADR-0011
status: accepted
date: 2026-06-26
decision_date: 2026-06-26
decider: Operator
scope: repo
backfilled: false
supersedes:
  - ADR-0010
superseded_by: []
related:
  - docs/ARCHITECTURE.md
  - docs/USER_GUIDE.md
  - docs/media-artifacts.md
  - extension/src/service_worker.js
  - extension/src/options.js
  - extension/src/popup.js
  - scripts/install-daily-driver.sh
verification:
  - node static source/dist default-on check
  - cd extension && npm test && npm run build
  - uv run --with pytest python -m pytest -q
  - PATH=/tmp/bmd-python-shim:$PATH ./scripts/run-e2e.sh
  - ./scripts/secret-scan.sh
  - git diff --check -- .
---

# ADR-0011: Enable the CDP Recorder by Default with a Disable Control

## Context

ADR-0010 briefly made the Browser Memory Daemon CDP recorder disabled by default to avoid Chrome's native debugging banner. Operator reversed that preference: X/Twitter media completeness is worth the banner, but the options-page disable switch should remain available.

The technical constraint remains unchanged. Chrome intentionally shows a native security banner while an extension is attached through `chrome.debugger`:

> “Browser Memory Daemon started debugging this browser”

The recorder is the path that captures `video.twimg.com` HLS manifests and media segments before X/Twitter pages expose only transient `blob:` player URLs.

## Decision

We will enable the CDP recorder by default and keep the options-page disable control.

A one-time local-storage migration will set `cdpRecorderEnabled=true` on upgraded daily-driver profiles so the recorder resumes even if ADR-0010's default-off migration previously ran. When Operator later disables the recorder through options, the save path records the new migration marker so the service worker preserves that explicit choice.

## Decision drivers

- X/Twitter video recovery is valuable enough to tolerate Chrome's native debugging banner.
- The user still needs a direct control to disable the recorder when banner-free browsing matters more.
- Normal text capture and non-CDP media capture must remain independent of this toggle.
- Chrome does not support hiding the debugging banner while `chrome.debugger` is attached.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Remove the disable control | Maximizes CDP coverage | No quick operator escape hatch for the banner | Rejected |
| Keep recorder disabled by default | Banner-free daily browsing | Loses the media completeness Operator wants | Superseded |
| Enable by default and keep disable control | Restores media completeness while preserving operator control | Chrome banner appears while attached | Chosen |

## Consequences

- Positive: X/Twitter CDP media recovery resumes by default.
- Positive: the options page still lets Operator disable the recorder without removing the feature.
- Positive: prior default-off profiles are migrated back to enabled once.
- Negative: Chrome's “started debugging this browser” banner is expected while the recorder is attached.
- Neutral: disabling the recorder reduces X/Twitter CDP video coverage but does not disable normal text capture, browser lazy media fetch, inline/blob upload, daemon media worker, or HLS backfill.

## Verification / validation

- Verification: `node` static source/dist check passed, proving `cdpRecorderEnabled: true` is present in source, built extension files, and the installed Windows extension artifact.
- Verification: `cd extension && npm test && npm run build` passed: 23/23 extension unit tests.
- Verification: `uv run --with pytest python -m pytest -q` passed: 57 Python tests.
- Verification: `PATH=/tmp/bmd-python-shim:$PATH ./scripts/run-e2e.sh` passed, including real Windows Chrome for Testing e2e, extension build/tests, secret scan, and `git diff --check`.
- Verification: `BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh` installed the daily-driver artifact, restarted WSL services, and verified WSL and Windows `/health` with `ok=true`.
- Validation: reloading the daily Chrome unpacked extension runs the default-on migration and restores CDP recorder attachment on configured X/Twitter tabs; disabling the options checkbox preserves the operator override.

## Revisit triggers

- Supersede this ADR if Chrome provides a supported, user-approved way to hide the debugging banner while keeping an extension debugger attached.
- Supersede this ADR if a non-debugger browser-side media capture path replaces CDP recorder coverage.
- Supersede this ADR if Operator decides banner-free daily browsing is more important than default X/Twitter CDP video recovery.

## References

- `docs/architecture/adr/0010-disable-cdp-recorder-by-default.md`
- `extension/src/service_worker.js`
- `extension/src/options.js`
- `extension/src/popup.js`
- `docs/media-artifacts.md`
- `docs/USER_GUIDE.md`
- `docs/ARCHITECTURE.md`
