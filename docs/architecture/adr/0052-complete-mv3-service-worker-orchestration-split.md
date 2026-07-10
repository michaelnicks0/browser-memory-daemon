# ADR-0052: Complete MV3 service-worker orchestration split

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0048, ADR-0049, ADR-0051

## Context

ADR-0051 extracted restart-sensitive configuration, visit, injection, and CDP session state, but the MV3 service worker still implemented capture/lifecycle transport, legacy outbox import, media task/blob transport, CDP response correlation, and telemetry writes. That retained a large composition file and made redaction behavior inconsistent across error paths.

## Decision

Complete the extension boundary split without changing message, HTTP, IndexedDB, policy, or quota contracts:

- `capture_bridge.js` owns capture/lifecycle HTTP delivery, transactional outbox import/admission/claim/checkpoint/ack/retry, the one-version legacy fallback, media-enqueue compensation, and outbox status;
- `media_bridge.js` owns credentialed browser fetch, inline/CDP blob upload, specialized media queue draining, retry/backoff, and terminal cleanup;
- `telemetry.js` is the only browser-local telemetry writer for the extracted bridges and CDP controller; it recursively drops payload/text/body/content/URL/token/header fields and redacts URL-shaped error substrings;
- `cdp_session.js` additionally owns CDP recorder enablement, response/request correlation, body retrieval, size gates, detach handling, and media-bridge dispatch;
- `service_worker.js` remains the MV3 composition root and listener/alarm/message registration shell.

Capture/lifecycle and media stores remain separate. Searchable text acceptance remains checkpointed before media admission, and a media admission or upload failure cannot cause the daemon capture POST to repeat.

## Consequences

- Queue and transport behavior has directly testable module ownership while retaining stable service-worker wrappers for characterization tests.
- Service-worker source is reduced to composition, small compatibility delegates, and Chrome listener registration.
- Browser telemetry remains aggregate and redaction-safe even when thrown errors contain page or media URLs.
- No daemon schema, API path, extension permission, queue schema, limit, policy mode, or live installation changes.

## Verification

- `extension/tests/unit/capture_bridge.test.js`
- `extension/tests/unit/media_bridge.test.js`
- `extension/tests/unit/cdp_session.test.js`
- `extension/tests/unit/service_worker.test.js`
- `scripts/run-real-chrome-e2e.sh`
