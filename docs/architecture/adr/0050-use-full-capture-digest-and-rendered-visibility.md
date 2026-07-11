# ADR-0050: Use full capture digests and a conservative rendered-visibility contract

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0007, ADR-0015, ADR-0035, ADR-0048, REQ-037, REQ-039

## Context

The content script suppressed repeated captures with URL, title, text length, the first and last 256 text characters, and only the first 20 media references. Different page states could therefore collide when changes occurred in the middle of text or late in the media list.

DOM extraction skipped explicit `hidden`, `aria-hidden`, and inline-style cases, but did not consult computed CSS. Class rules, responsive media queries, and hidden ancestors could leak non-rendered text. The service worker also trusted an ephemeral in-memory injected-tab map, which could outlive the document it described and prevent recovery injection.

## Decision

1. Compute a SHA-256 digest over deterministic JSON containing the complete cleaned text, complete ordered media-reference list, authoritative observed URL, title, canonical claim, policy mode, and extraction method.
2. Exclude volatile capture time, capture reason, and scroll percentage so retries and delayed observations of unchanged content retain one digest.
3. Prefer Web Crypto SHA-256. Use an embedded, standard-vector-tested SHA-256 implementation when `crypto.subtle` is unavailable on an ordinary insecure HTTP page.
4. Carry the digest in the capture payload and use it as the content-script duplicate key. Record it as successful only after the service worker accepts the capture into its durable path; failed admission remains retryable with the same digest.
5. Define rendered text conservatively. Exclude a subtree when the element or any light-DOM ancestor has `hidden`, `aria-hidden=true`, inline or computed `display:none`, `visibility:hidden|collapse`, `content-visibility:hidden`, or `opacity:0`. Continue excluding forms, editable controls, scripts, styles, and noscript content in every policy mode.
6. Include offscreen and zero-layout text when CSS does not mark it hidden. Geometry is viewport-dependent and is not part of this contract.
7. Traverse the light DOM only. Open and closed shadow roots and pseudo-element generated content are outside the extraction contract until an explicit composed-tree policy is designed and tested.
8. Re-run idempotent script injection on each relevant service-worker event instead of trusting process-memory tab/document state. The content-script installation guard prevents duplicate listener installation and requests a fresh capture when the current document is already initialized.
9. Identify the new extractor behavior as `dom-rendered-text-v2` or `dom-all-rendered-text-v2`.

## Consequences

- Middle-text and late-media changes cannot collide with the former prefix/suffix fingerprint.
- Digest calculation is linear in the complete bounded capture payload and does not require network or daemon availability.
- Privacy-sensitive hidden surfaces are excluded according to computed CSS and ancestor state in real Chrome.
- Deliberately transparent text is omitted even though it may remain selectable or accessibility-visible; this is the conservative local-capture boundary.
- Shadow-DOM content is explicitly absent rather than inconsistently traversed.
- Repeated injection performs small extra extension work but repairs stale service-worker injection state without relying on live profile mutation.

## Verification

- `extension/tests/unit/capture_digest.test.js::portable SHA-256 fallback matches the standard vector`
- `extension/tests/unit/capture_digest.test.js::capture digest detects middle-text and complete media-list changes missed by the legacy fingerprint`
- `extension/tests/unit/content_script.test.js::content capture retries the same full digest until admission succeeds and then suppresses duplicates`
- `extension/tests/unit/extractor.test.js::computed rendered visibility excludes class, responsive, and ancestor-hidden content`
- `extension/tests/unit/extractor.test.js::document traversal excludes computed-hidden subtrees and does not cross shadow roots`
- `extension/tests/unit/service_worker.test.js::service worker injection respects stale token, pause, and strict URL controls`
- `scripts/run-real-chrome-e2e.sh` verifies class, responsive, ancestor, opacity, content-visibility, ARIA, inline, form, editable, and shadow-root exclusions in isolated Chrome for Testing.
