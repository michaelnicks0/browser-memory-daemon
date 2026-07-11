---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0030: Separate capture observations and URL claims

## Context and problem statement

The current schema connects a visit directly to one document and stores `snapshots.visit_id` only when the immutable snapshot is first created. Repeated captures can replace a visit row, deduplicated snapshots can retain an earlier visit, and timeline readers select the latest document snapshot rather than the snapshot observed at that capture time. Page-provided canonical URLs also currently influence document identity.

Phase 2 requires an expand-first authority model that can represent each accepted extraction, the contemporaneous snapshot relationship, and untrusted canonical/alternate claims without speculatively rewriting historical identities.

## Decision drivers

- Observed browser URL must become the future document-identity authority.
- Canonical and alternate URLs are evidence claims, not merge commands.
- Every accepted extraction needs an idempotent temporal record.
- Historical ambiguity must be represented, not guessed away.
- Existing endpoint behavior must remain compatible during dual-write/read cutover.
- Rollback must remain possible by returning to the prior application while retaining additive tables.

## Considered options

1. **Continue inferring observations from visits and snapshots** — rejected because replacement/deduplication has already lost exact relationships.
2. **Rewrite documents immediately around observed URLs** — rejected because ambiguous historical canonical-derived identities cannot be split safely in one migration.
3. **Store canonical aliases directly on documents** — rejected because a claim needs source observation, origin relationship, and explicit non-authoritative effect.
4. **Add observations and claims through an expand migration, then dual-write and cut over reads in later slices** — accepted.

## Decision outcome

Migration version 4 adds two tables without changing existing columns or readers:

### `capture_observations`

One row represents one accepted or historically reconstructed extraction. It carries:

- stable `id` and unique `idempotency_key`;
- optional navigation and visit identity;
- document and optional contemporaneous snapshot relationships;
- authoritative observed URL and its normalized form;
- capture time, reason, method, extraction version, disposition, and provenance quality;
- constrained metadata.

Visit and snapshot foreign keys use `ON DELETE SET NULL`; document deletion cascades the observation. This permits future snapshot lifecycle changes without inventing a replacement relationship while preserving document-scoped forget behavior.

### `document_url_claims`

One row records a canonical, alternate, Open Graph, or explicitly historical canonical claim. It carries:

- document and optional source-observation identity;
- claimed URL, normalized claim, claim origin, and same-origin assessment;
- explicit `identity_effect` (`none`, `same-origin-alias`, or `historical-authority`);
- provenance quality and first/last observation times.

The default identity effect is `none`. A cross-origin claim cannot create or merge a document merely by being stored. Historical rows may later use `historical-authority` only to describe the old identity decision; that label does not authorize new merges.

## Migration and compatibility

- Version 4 is additive and non-destructive.
- Version-1 schema remains immutable; the version-4 step declares the new exact schema fingerprint.
- `schema.sql` mirrors the latest materialized schema for documentation/fixture inspection, while fresh runtime databases continue through the ordered ledger.
- No historical backfill, dual-write, read cutover, or old-column contraction occurs in this slice.
- A prior application can continue using the old tables; rollback does not drop the new tables.

## Consequences

### Positive

- The schema can express visit → observation → contemporaneous snapshot provenance.
- URL claims have origin and authority semantics instead of silently controlling identity.
- Later dual-write/backfill/read-cutover slices have a reversible target.

### Negative

- The new tables are initially empty for existing data.
- Existing canonical-derived document IDs remain authoritative until the later dual-write/cutover migration proves safe relationships.
- Additive storage and indexes increase schema complexity before readers use them.

## Validation

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  -m pytest -q daemon/tests/integration/test_migrations.py
```

Required evidence includes fresh version-4 initialization, an exact version-3 fixture upgrade, schema fingerprint/ledger checks, FK integrity, constrained observation states, and a cross-origin claim whose default `identity_effect` remains `none` without creating another document.

## Supersession and follow-up

This ADR refines the capture/identity portions of ADR-0004 and ADR-0015 without superseding their local-first or idempotency decisions. Later ADRs may record observed-URL read cutover and lifecycle interval-union semantics. Contraction of legacy columns requires a separate compatibility release and decision.
