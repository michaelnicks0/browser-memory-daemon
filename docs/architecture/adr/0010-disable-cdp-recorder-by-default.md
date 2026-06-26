---
id: ADR-0010
status: accepted
date: 2026-06-26
decision_date: 2026-06-26
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - docs/ARCHITECTURE.md
  - docs/USER_GUIDE.md
  - docs/media-artifacts.md
  - extension/src/service_worker.js
  - extension/src/options.js
  - extension/src/popup.js
verification:
  - node static source/dist default-off check
  - cd extension && npm test && npm run build
  - uv run --with pytest python -m pytest -q
  - PATH=/tmp/bmd-python-shim:$PATH ./scripts/run-e2e.sh
  - ./scripts/secret-scan.sh
  - git diff --check -- .
---

# ADR-0010: Disable the CDP Recorder by Default

## Context

The Browser Memory Daemon extension includes an optional CDP recorder for X/Twitter video recovery. It attaches to matching tabs through Chrome's `chrome.debugger` API so it can observe `video.twimg.com` network responses before X collapses them into opaque `blob:` player URLs.

Chrome intentionally shows a native security banner while an extension is attached through `chrome.debugger`:

> “Browser Memory Daemon started debugging this browser”

That banner is useful security UX for arbitrary extensions, but it is noisy for Operator's daily-driver browser. Text recall, ordinary page capture, browser lazy media fetch, inline/blob upload, daemon public backfill, and HLS assembly do not require long-lived debugger attachment.

## Decision

We will keep the CDP recorder implemented, but make it opt-in and disabled by default.

The extension will also run a one-time local-storage migration that turns off previously-default-enabled CDP recorder state. After that migration, Operator can explicitly re-enable the recorder from the options page when X/Twitter video recovery is worth the Chrome debugging banner.

## Decision drivers

- Daily-driver browser UX should not carry a persistent Chrome debugging banner.
- Normal text and non-CDP media capture should continue without debugger attachment.
- X/Twitter video recovery remains valuable, but it is a situational recovery lane rather than a default daily-driver lane.
- Chrome's native debugging banner cannot be hidden while `chrome.debugger` is attached; the durable fix is to avoid attaching by default.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep CDP recorder enabled by default | Best X/Twitter video completeness | Persistent Chrome debugging banner in daily browsing | Rejected |
| Remove CDP recorder and `debugger` permission entirely | No banner path remains | Loses a known useful X/Twitter video recovery mechanism | Rejected |
| Detach after short idle windows | Reduces banner dwell time | Still produces recurring banners and can miss late media responses | Rejected for default UX |
| Keep CDP recorder opt-in, default off | Removes banner from normal browsing while preserving recovery option | X/Twitter CDP video coverage requires explicit enablement | Chosen |

## Consequences

- Positive: daily Chrome should stop showing the Browser Memory Daemon debugging banner after the extension reloads and the migration runs.
- Positive: normal capture, search recall, lazy media queueing, inline/blob upload, daemon media worker, and HLS backfill remain active.
- Positive: X/Twitter CDP capture can still be enabled from options for targeted sessions.
- Negative: default capture may miss some X/Twitter videos that only CDP could recover.
- Neutral: the manifest still requests `debugger` permission because the opt-in feature remains present.

## Verification / validation

- Verification: `node` static source/dist check passed, proving `cdpRecorderEnabled: false` is present in source and built extension files and the service-worker migration marker exists.
- Verification: `cd extension && npm test && npm run build` passed: 23/23 extension unit tests.
- Verification: `uv run --with pytest python -m pytest -q` passed: 57 Python tests.
- Verification: `PATH=/tmp/bmd-python-shim:$PATH ./scripts/run-e2e.sh` passed, including real Windows Chrome for Testing e2e, extension build/tests, secret scan, and `git diff --check`.
- Verification: `./scripts/secret-scan.sh` passed.
- Verification: `git diff --check -- .` passed.
- Validation: Chrome's banner is tied to active `chrome.debugger` attachment, so default-off configuration prevents the attachment path during normal browsing while preserving explicit opt-in recovery.

## Revisit triggers

- Supersede this ADR if Chrome provides a supported, user-approved way to hide the debugging banner while keeping an extension debugger attached.
- Supersede this ADR if X/Twitter media capture becomes more important than banner-free daily browsing.
- Supersede this ADR if the CDP recorder is replaced by a non-debugger browser-side media capture mechanism.

## References

- `extension/src/service_worker.js`
- `extension/src/options.js`
- `extension/src/popup.js`
- `docs/media-artifacts.md`
- `docs/USER_GUIDE.md`
- `docs/ARCHITECTURE.md`
