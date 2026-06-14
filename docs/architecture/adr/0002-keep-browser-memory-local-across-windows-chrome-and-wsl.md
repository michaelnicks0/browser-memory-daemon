---
id: ADR-0002
status: accepted
date: 2026-06-14
decision_date: 2026-06-08
decider: Operator
scope: repo
backfilled: true
supersedes: []
superseded_by: []
related:
  - docs/ARCHITECTURE.md
  - docs/security-model.md
  - docs/api.md
  - daemon/src/browser_memory_daemon/config.py
  - scripts/install-daily-driver.sh
  - scripts/real-chrome-e2e.mjs
verification:
  - ADR lint + repo Markdown fence check
  - git diff --check -- .
  - ./scripts/secret-scan.sh
  - BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh with temporary Python 3.11 shim
---

# ADR-0002: Keep Browser Memory Local Across Windows Chrome and WSL

## Context

This ADR backfills a decision that existed before the ADR workflow was added.

Browser Memory Daemon needs to capture pages from Operator's Windows Chrome daily-driver while keeping durable recall data under WSL. The product goal is local personal recall, not a hosted service, enterprise DLP product, or shared multi-user system.

The architecture has to cross the Windows/WSL boundary because Chrome runs on Windows and the daemon, SQLite database, FTS index, CLI, local UI, and blob stores live in WSL. It also has to avoid treating the Chrome profile itself as the durable memory store.

## Decision

We will keep browser memory local by using a Windows Chrome MV3 extension as the capture surface and a WSL-resident loopback HTTP daemon as the durable storage/search owner.

The current transport is authenticated loopback HTTP on `127.0.0.1:8765`. The daemon owns SQLite, FTS5, clean-text blobs, media blobs, policy evaluation, read APIs, deletion, and diagnostics. Chrome extension storage is used only for transient extension state and queues, not as the source of truth.

Native messaging hardening remains a future lane, but HTTP loopback is the accepted current boundary.

## Decision drivers

- Daily-driver capture must happen where Chrome page/runtime APIs are available.
- Durable data should stay in WSL XDG paths, outside this repo and outside the Chrome profile.
- Search, doctor, forget, media worker, CLI, and local UI should share one daemon-owned data model.
- The system is personal/local-first and should not add cloud storage, cloud embeddings, or hosted processing without explicit approval.
- The bridge must be testable with synthetic real-browser e2e fixtures.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Store everything in Chrome extension storage | Simple browser-only deployment | Weak query model, poor operational tooling, Chrome profile becomes durable memory, hard backup/delete semantics | Rejected |
| Send captures to a cloud service | Easy cross-device story | Violates local-first privacy posture and adds external dependency | Rejected |
| Native messaging as first transport | Stronger browser-host integration | More setup/hardening work before proving the product loop | Deferred |
| Authenticated loopback HTTP to WSL daemon | Simple, testable, local, fits CLI/UI/worker ownership | Must keep daemon loopback-only and tokened | Chosen |

## Decision history

- `2ba4373` (2026-06-08) bootstrapped the browser-memory daemon.
- `2c2b76b` (2026-06-08) added real Windows Chrome extension e2e coverage for the bridge.
- `fb025df` (2026-06-08) added the daily-driver Chrome deployment helper.
- `29410de` (2026-06-08) added local memory UI and ops APIs.
- Current evidence: `docs/ARCHITECTURE.md` defines the Mission/ConOps, storage owner, loopback capture path, and no-cloud boundary; `daemon/src/browser_memory_daemon/config.py` defaults to `127.0.0.1` and XDG runtime roots.

## Consequences

- Positive: one WSL-owned store backs search, detail, timeline, media, doctor, CLI, UI, and deletion.
- Positive: the repo remains code/docs only; live memory artifacts stay under runtime paths.
- Positive: future architecture work can reason about one local system boundary instead of scattered browser-local state.
- Negative: the Windows/WSL boundary adds installation, loopback, token, and service-management complexity.
- Negative: HTTP loopback is not as hardened as a dedicated native messaging bridge.
- Neutral: Chrome is still the only component with access to browser cookies and page-runtime APIs.

## Verification / validation

- Verification: `daemon/src/browser_memory_daemon/config.py` sets `DEFAULT_HOST = "127.0.0.1"`, default port `8765`, and XDG data/config/state roots.
- Verification: `docs/security-model.md` documents loopback bind, bearer auth, WSL XDG storage, and service-worker-owned daemon communication.
- Verification: `scripts/real-chrome-e2e.mjs` starts the WSL daemon, configures a Windows Chrome-family browser, and proves capture/search through the loopback bridge.
- Backfill hygiene verification passed on 2026-06-14: ADR lint, repo Markdown fence check, `git diff --check -- .`, `./scripts/secret-scan.sh`, and `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` using a temporary Python 3.11 shim.
- Validation: Operator can use Windows Chrome as the browser surface while WSL remains the durable local recall system.

## Revisit triggers

- Supersede this ADR if native messaging replaces loopback HTTP.
- Supersede this ADR if durable data ownership moves outside WSL.
- Supersede this ADR if the system becomes multi-user or exposed beyond loopback.
- Supersede this ADR before adding any cloud storage, cloud embedding, or hosted recall path.

## References

- `docs/ARCHITECTURE.md`
- `docs/security-model.md`
- `docs/api.md`
- `daemon/src/browser_memory_daemon/config.py`
- `scripts/install-daily-driver.sh`
- `scripts/real-chrome-e2e.mjs`
