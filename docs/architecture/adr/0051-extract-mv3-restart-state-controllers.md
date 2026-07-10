# ADR-0051: Extract MV3 restart-state controllers from the service worker

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0007, ADR-0048, ADR-0049, ADR-0050

## Context

The MV3 service worker owned configuration migration, visit/navigation state, script injection, debugger attachment state, queue orchestration, media transport, and listener registration in one file. IndexedDB made accepted queue work durable, but CDP capture provenance and debugger attachment knowledge remained process-local. Worker restart could therefore lose the document/snapshot context required for an in-flight CDP response or mistake a still-attached debugger target for an attach failure.

## Decision

Extract current restart-sensitive responsibilities behind explicit browser-side modules while preserving the existing runtime-message and daemon HTTP contracts:

- `config_store.js` owns typed defaults, the existing CDP default-on migration, durable visit state, and a minimal per-tab CDP capture-context map;
- `visit_tracker.js` owns navigation/visit identity, active segments, deterministic lifecycle-event identity, and capture decoration;
- `injection.js` owns active-tab reconstruction and ordered idempotent injection of extractor, digest, and content scripts; ordinary worker re-evaluation reinjects without rewriting active lifecycle state, while browser startup/installation may mark active tabs;
- `cdp_session.js` owns debugger commands/attach/detach, extension-owned attachment reconciliation, transient request state, and durable recovery of document/snapshot/visit/page URL context.

The service worker remains the listener/orchestration and daemon-transport composition root. Capture/lifecycle outbox and specialized media queue ownership remain separate. Capture and media bridge extraction may proceed in later reversible slices; this decision does not change endpoint payloads or queue schemas.

CDP context persistence is intentionally minimal. It excludes page text, title, media bodies, cookies, tokens, and request headers. A tab URL mismatch clears recovered context before CDP recording resumes so a reused tab ID cannot attribute bytes to an older page.

If `chrome.debugger.attach` reports an existing attachment after worker restart, the session controller accepts recovery only when `chrome.debugger.getTargets` shows the same tab as attached; it then re-enables the Network domain. Other attach failures remain visible.

## Consequences

- Restart-sensitive state has directly testable ownership and no longer depends only on service-worker memory.
- Startup revisits all active tabs and idempotently reinjects the complete ordered content-script set.
- Minimal observed page URLs remain in local extension storage while their CDP capture context is current; tab close or URL change removes that context.
- The service worker is smaller but is not yet orchestration-only: capture and media transport/drain code remains for later extraction.
- No daemon schema, HTTP endpoint, extension permission, policy mode, or live installation changes.

## Verification

- `extension/tests/unit/config_store.test.js`
- `extension/tests/unit/visit_tracker.test.js`
- `extension/tests/unit/injection.test.js`
- `extension/tests/unit/cdp_session.test.js`
- `extension/tests/unit/service_worker.test.js`
- `scripts/run-real-chrome-e2e.sh`
