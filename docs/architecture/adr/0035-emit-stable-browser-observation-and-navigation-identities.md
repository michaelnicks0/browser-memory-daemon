---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0035: Emit stable browser observation and navigation identities

## Context and problem statement

The daemon capture model accepts browser-provided `observation_id` and `navigation_id`, but the MV3 extension previously emitted only `visit_id`. The daemon therefore had to derive observation identity from capture time/content, and browser queue retries could not prove that repeated delivery represented the same accepted extraction. Navigation identity was implicit in service-worker tab state rather than durable in the capture payload.

Phase 2 requires each browser extraction to carry a stable observation identity and each tab/URL navigation state to carry a stable navigation identity without replatforming the existing queue yet.

## Decision drivers

- Preserve exactly-once daemon observation semantics across HTTP retry and service-worker restart.
- Keep one navigation identity for repeated extractions of one tab/URL state.
- Rotate navigation identity when the observed URL state changes.
- Migrate already queued legacy captures before their next network attempt.
- Avoid changing the content-script-to-localhost boundary or introducing native messaging.
- Keep the Phase 5 IndexedDB outbox migration as a separate rollback domain.

## Decision

The MV3 service worker owns capture identity decoration:

- Every capture payload receives an opaque `observation_<uuid>` unless a caller-supplied observation ID is already present.
- Each persisted tab/URL visit state receives an opaque `navigation_<uuid>` alongside its existing `visit_<uuid>`.
- Repeated extractions for the same tab and exact URL reuse visit/navigation IDs but receive distinct observation IDs.
- URL change closes the prior visit state and creates new visit/navigation IDs.
- The decorated payload is persisted in `captureQueue` before daemon transport, so HTTP retries and service-worker restarts reuse the same IDs.
- Legacy queued captures missing either ID are decorated and re-saved before the next POST.
- Legacy persisted tab state missing `navigationId` is upgraded lazily and saved.

The daemon continues to hash the browser observation ID into its internal observation primary key while preserving a `browser:` idempotency key. No captured text or URL is embedded in these opaque IDs.

## Compatibility and rollback

The payload fields are additive. Older daemons ignore unknown JSON fields; the current daemon consumes them. Older queued captures are upgraded lazily without deleting or reordering them.

Rollback is the prior extension build. Database rows already created from browser IDs remain valid observations; no schema rollback is needed.

This decision does not make `chrome.storage.local` arrays durable enough for Phase 5. Transactional IndexedDB outboxes, byte quotas, and stale-claim recovery remain separate work.

## Consequences

### Positive

- A queued extraction has one stable daemon idempotency identity across retry/restart.
- Multiple observations of one navigation are explicit.
- Navigation changes cannot accidentally reuse the prior navigation ID.
- Real Chrome release evidence can distinguish browser-authored from daemon-derived observations.

### Negative

- Identity decoration is still wrapped by the existing non-transactional `chrome.storage.local` queue.
- A content script that never reaches the service worker has no durable observation record; Phase 5 outbox work addresses that boundary.

## Rejected alternatives

- **Derive identity only in the daemon:** cannot prove browser retry identity across capture-time changes.
- **Use content hash as observation ID:** unchanged repeated observations are distinct temporal evidence.
- **Reuse `visit_id` as navigation and observation identity:** collapses multiple extractions and prevents explicit temporal provenance.
- **Combine with the IndexedDB outbox migration:** violates the separate rollback-domain requirement.

## Validation

- `extension/tests/unit/service_worker.test.js` proves queued retry/restart preserves observation/navigation IDs.
- `extension/tests/unit/service_worker.test.js` proves same-URL extractions reuse navigation identity, distinct extractions receive distinct observations, and URL changes rotate navigation identity.
- `scripts/real-chrome-e2e.mjs` requires browser-authored observation idempotency plus non-empty navigation IDs in the isolated Chrome for Testing database.
- Daemon integration tests continue to prove duplicate observation retry behavior and explicit navigation storage.
