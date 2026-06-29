---
id: ADR-0005
status: accepted
date: 2026-06-14
decision_date: 2026-06-09
decider: Operator
scope: repo
backfilled: true
supersedes: []
superseded_by: []
related:
  - docs/ARCHITECTURE.md
  - docs/media-artifacts.md
  - docs/storage-growth-model.md
  - daemon/src/browser_memory_daemon/media.py
  - daemon/src/browser_memory_daemon/media_worker.py
  - extension/src/media_queue.js
  - extension/src/cdp_recorder.js
verification:
  - ADR lint + repo Markdown fence check
  - git diff --check -- .
  - ./scripts/secret-scan.sh
  - BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh with temporary Python 3.11 shim
---

# ADR-0005: Use Durable Lazy Media Sidecars with a Bounded Cache

## Context

This ADR backfills a decision sequence that existed before the ADR workflow was added.

Text recall is the core product, but pages often contain important images, video posters, HLS videos, blob URLs, and transient media references. Capturing media synchronously inside `/capture` would make text recall fragile: slow fetches, signed URLs, service-worker suspension, CORS/cookie constraints, and streaming video edge cases could block or fail the text path.

The architecture therefore needs a media lane that improves byte completeness without making media bytes authoritative for recall correctness.

## Decision

We will use durable lazy media sidecars with a bounded disposable media cache.

The fast `/capture` path stores text, FTS chunks, visit/snapshot rows, and media reference rows first. Browser-side media work runs later from an extension IndexedDB queue and can fetch with Chrome's credential envelope before raw `PUT` upload to the daemon. The daemon-public media worker separately backfills public `http:`, `https:`, and `data:` refs with leases, backoff, HLS handling, and classified terminal statuses. X/Twitter HLS/video cases use a domain-gated CDP recorder.

Text, FTS rows, media refs, hashes, and provenance are durable. Media blob bytes are a bounded cache under per-artifact, per-snapshot, per-domain, and global caps, with purge and best-effort rehydrate controls.

## Decision drivers

- Text/FTS capture must never wait on media bytes.
- Credentialed media fetch should stay inside Chrome; WSL must not receive browser cookies.
- Public media should still be retried/backfilled without relying on Chrome staying alive.
- X/Twitter video often collapses into opaque `blob:` URLs unless HLS/CDP evidence is captured early.
- Media cache growth must be bounded and operationally purgeable.
- Missing media bytes should be classified, not treated as unexplained capture failure.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Store no media | Keeps system simple and small | Loses important page context and video/image provenance | Rejected |
| Block `/capture` until media bytes are fetched | Immediate completeness when it works | Breaks text recall on slow/expired/credentialed/streaming media | Rejected |
| Browser-only media fetch | Has cookies and page context | MV3 worker suspension, limited retries, no daemon-wide queue/ops | Rejected as sole lane |
| Daemon-only media fetch | Durable worker and simple ops | Cannot use Chrome cookies; misses transient blob and credentialed media | Rejected as sole lane |
| Hybrid lazy sidecars with bounded cache | Preserves fast text recall while improving media coverage | More moving parts and status taxonomy | Chosen |

## Decision history

- `b6446d6` (2026-06-09) stored related media artifacts.
- `d8eea55` (2026-06-09) added daemon fetch-pending media artifacts.
- `fa6dc26` (2026-06-09) planned durable media sidecars.
- `04e6482` (2026-06-09) added durable media sidecars.
- `ab38213` (2026-06-11) hardened media sidecar retrieval.
- `77d8f3d` (2026-06-11) added HLS media backfill and normalized video skips.
- `061e490` (2026-06-11) added the CDP recorder for X video media.
- `97b0e81` (2026-06-11) stored HLS audio sidecars and classified blob video refs.
- `969a20d` (2026-06-12) raised media cache caps and added rolling eviction.
- `e85da5b` (2026-06-12) folded the media sidecar design into the architecture docs.

## Consequences

- Positive: fast text recall stays reliable even when media fetches are slow, credentialed, expired, or unsupported.
- Positive: Chrome cookies stay in Chrome; WSL receives raw uploaded blobs, not browser credential material.
- Positive: daemon-public media backfill is durable, leaseable, retryable, and inspectable.
- Positive: media status reasons distinguish `stored`, `referenced`, `skipped`, `expired`, `purged`, and unexpected `failed` cases.
- Negative: media correctness now spans extension queue code, daemon media APIs, worker leases, cache gates, and CDP recorder behavior.
- Negative: some DRM/DASH/MSE/opaque `blob:` cases remain refs only.
- Neutral: media blobs are disposable cache bytes; text/FTS remains the recall source of truth.

## Verification / validation

- Verification: `docs/media-artifacts.md` records the fast capture, browser lazy sidecar, daemon-public worker, HLS/CDP, purge, and cache semantics.
- Verification: `daemon/src/browser_memory_daemon/media.py` implements media refs, fetch tasks, raw blob storage, HLS detection, status classification, rolling eviction, purge, and rehydrate.
- Verification: `extension/src/media_queue.js` and `extension/src/cdp_recorder.js` implement browser queue and CDP-recorder lanes.
- Verification: `scripts/real-chrome-e2e.mjs` verifies public media, cookie-required media, synthetic `blob:` video storage, queue drainage, and all/strict policy media expectations.
- Verification: `daemon/tests/integration/test_media_worker.py`, media-related ingest tests, and extension media queue/CDP tests cover worker and queue behavior.
- Backfill hygiene verification passed on 2026-06-14: ADR lint, repo Markdown fence check, `git diff --check -- .`, `./scripts/secret-scan.sh`, and `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` using a temporary Python 3.11 shim.
- Validation: media improves page reconstruction without compromising the text-first recall path.

## Revisit triggers

- Supersede this ADR if media-derived text/OCR becomes part of search correctness.
- Supersede this ADR before adding DRM/DASH/MSE capture beyond public/readable artifacts.
- Supersede this ADR if browser credential handling changes or cookies leave Chrome.
- Supersede this ADR if media cache semantics become retention semantics rather than disposable cache semantics.

## References

- `docs/ARCHITECTURE.md#durable-media-sidecar-architecture`
- `docs/media-artifacts.md`
- `docs/storage-growth-model.md`
- `daemon/src/browser_memory_daemon/media.py`
- `daemon/src/browser_memory_daemon/media_worker.py`
- `extension/src/media_queue.js`
- `extension/src/cdp_recorder.js`
