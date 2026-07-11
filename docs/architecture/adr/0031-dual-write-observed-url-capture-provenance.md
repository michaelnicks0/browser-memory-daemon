---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0031: Dual-write observed-URL capture provenance without replacing visits

## Context and problem statement

Version 4 added additive capture-observation and URL-claim tables, but the ingest path still used page-provided canonical URLs for document identity and replaced visit rows on repeated captures. `INSERT OR REPLACE` deletes then reinserts a visit, which can sever lifecycle-event and other foreign-key provenance. Deduplicated snapshots also retain only the visit that first created them.

The daemon must begin writing trustworthy provenance before historical readers can cut over, while keeping legacy document/visit/snapshot columns available for compatibility.

## Decision drivers

- Normalized observed browser URL is the approved identity authority.
- Canonical URLs are untrusted claims and cannot merge documents automatically.
- A visit represents one navigation/session and can contain multiple observations.
- Browser retries must be idempotent, and conflicting reuse of an observation ID must fail.
- Existing historical canonical-derived IDs must remain untouched.
- Lifecycle-event foreign keys must survive recapture.

## Considered options

1. **Continue canonical-derived identity until read cutover** — rejected because every new capture would add more ambiguous history.
2. **Replace visit rows but rely on cascading recreation** — rejected because provenance deletion is the defect.
3. **Rewrite all historical documents around observed URLs now** — rejected because historical evidence is incomplete.
4. **Dual-write new observed-URL documents/observations/claims and conflict-update visits in place** — accepted.

## Decision outcome

### New captures

- `documents.id` is derived from the policy-transformed, normalized observed `url`.
- A differing `canonical_url` becomes a `document_url_claims` row with `identity_effect='none'`; same-origin assessment is recorded, but no automatic merge occurs.
- Claim first/last bounds and latest-observation provenance remain monotonic when delayed observations arrive out of order.
- Every accepted extraction writes one `capture_observations` row linking the visit, observed document, and contemporaneous snapshot.
- Browser-provided observation IDs become the idempotency authority. Until the extension emits them everywhere, the daemon derives a deterministic fallback from visit, capture time, observed URL, document, and snapshot and marks provenance `inferred`.
- Identical observation retries are row-level no-ops that still reconstruct the compatibility response, including URL-claim and media artifact identifiers. Reusing the same observation ID with conflicting stored provenance raises a conflict.

### Visit identity

- Visit insertion uses `INSERT ... ON CONFLICT DO UPDATE`, never `INSERT OR REPLACE`.
- The first visit/document/URL identity remains in place.
- Later observations may update title, latest capture time, earliest known start, bounded dwell, and incognito state without deleting the row.
- Lifecycle-event foreign keys therefore survive repeated capture.
- Reusing one visit ID for a different normalized observed navigation is rejected rather than creating a cross-document visit/observation mismatch.

### Historical data

Migration version 5 performs a one-time, evidence-bounded backfill:

- a snapshot with a surviving visit link becomes an `inferred` historical observation;
- a snapshot without a surviving visit becomes an `ambiguous` observation and does not receive an invented visit;
- each historical document records a `legacy-canonical` claim with `identity_effect='historical-authority'` and ambiguous provenance;
- no document is split or merged.

## Compatibility and rollback

- Existing visit, document, and snapshot columns remain populated.
- Existing read APIs continue using legacy joins in this slice; observation-first read cutover is separate.
- A prior application can ignore the additive tables. It may resume its old canonical-derived behavior after rollback, so rollback is operationally compatible but should be temporary to avoid new ambiguous identity decisions.
- No destructive migration or down-migration is introduced.

## Consequences

### Positive

- New capture history has explicit contemporaneous snapshot provenance.
- Cross-origin canonical claims cannot control identity or deletion scope.
- Repeated extraction no longer destroys visit/event identity.
- Historical ambiguity is visible and bounded.

### Negative

- New observed-URL documents may coexist with older canonical-derived documents until read/backfill reconciliation is complete.
- Derived observation IDs are less authoritative than browser-issued IDs and can collide for indistinguishable captures in the same timestamp bucket.
- Legacy readers still do not consume the richer provenance.

## Validation

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  -m pytest -q \
  daemon/tests/integration/test_capture_observations.py \
  daemon/tests/integration/test_ingest_search_forget.py \
  daemon/tests/integration/test_migrations.py \
  daemon/tests/integration/test_visit_lifecycle.py
```

Required cases include unchanged and changed observations in one visit, multiple visits observing one snapshot, exact retry idempotency, conflicting observation-ID rejection, visit-ID/navigation conflict rejection, out-of-order temporal bounds, cross-origin canonical targeting an existing document, lifecycle FK preservation, concurrent same-URL tabs, and evidence-bounded historical backfill with the surviving visit's normalized observed URL.

## Supersession and follow-up

This ADR implements the dual-write and identity portions of ADR-0030. Observation-first recent/timeline/detail/media reads, lifecycle attachment by visit/navigation identity, and interval-union dwell remain separate cutover decisions.
