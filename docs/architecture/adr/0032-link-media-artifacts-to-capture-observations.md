---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0032: Link media artifacts to capture observations

## Context and problem statement

Media artifacts are deduplicated by snapshot and media-reference identity. A single artifact row carries only one legacy `visit_id`, while one snapshot can be observed repeatedly and each observation can expose a different set of media references. Joining artifacts to every observation of a snapshot would invent provenance; retaining only the artifact's first visit would silently omit later evidence.

Phase 2 requires explicit temporal relationships between capture observations and media provenance before detail readers can cut over.

## Decision drivers

- Media provenance must identify the extraction that supplied each reference.
- Repeated observations of one snapshot must not collapse distinct media evidence.
- Historical relationships may be backfilled only when one supported candidate exists.
- The change must remain additive and compatible with the existing media artifact/task model.
- Media decomposition, cache-state redesign, and BlobStore work remain separate phases.

## Considered options

1. **Infer media provenance from `snapshot_id` at read time** — rejected because multiple observations can share one snapshot and expose different media.
2. **Treat the legacy artifact `visit_id` as authoritative** — rejected because one deduplicated artifact may be referenced by more than one observation and the column retains only one visit.
3. **Duplicate media artifact rows per observation** — rejected because it breaks the current stable artifact identity and cache/task relationships.
4. **Add an observation/artifact relation with evidence-bounded backfill** — accepted.

## Decision outcome

Migration version 6 adds `media_artifact_observations`:

- `(artifact_id, observation_id)` is the primary key;
- both identities use cascading foreign keys so existing document/observation forget behavior remains bounded;
- `provenance_quality` is constrained to `observed`, `inferred`, or `ambiguous`;
- `observed_at` preserves the relationship's capture time;
- an observation index supports detail and timeline reads.

New ingest transactions insert one relation for each accepted media reference and capture observation. Exact retries remain idempotent. Two observations that share text/snapshot identity but expose different media references therefore retain distinct artifact relationships.

Version-6 backfill is deliberately conservative:

- exactly one observation matching the artifact's snapshot and legacy visit becomes an `inferred` link;
- when no unique visit match exists but the snapshot has exactly one observation, it becomes an `ambiguous` link;
- multiple candidates remain unlinked rather than being speculatively assigned.

Media detail readers expose the stored observation relationships and their link/observation provenance quality. They do not synthesize links for unresolved historical artifacts.

## Compatibility and rollback

- Version 6 is additive and non-destructive.
- Existing `media_artifacts` columns and endpoint paths remain available.
- A prior application can ignore the relation table; rollback does not drop it.
- No media bytes, tasks, cache states, or artifact identifiers are rewritten.
- Unresolved historical artifacts remain visible through their existing document/snapshot relationships but have an empty observation relationship list.

## Consequences

### Positive

- Media references no longer inherit an invented "latest snapshot" or broad snapshot-level observation association.
- Current capture provenance is exact and retry-safe.
- Historical uncertainty is explicit and bounded.
- Later media decomposition can consume a stable provenance relation without changing artifact identity.

### Negative

- The relation adds rows proportional to distinct observation/artifact pairs.
- Some historical artifacts intentionally remain unlinked.
- Browser-originated post-capture uploads still rely on the relation created during the original capture until extension payloads carry observation identity everywhere.

## Validation

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  -m pytest -q \
  daemon/tests/integration/test_capture_observations.py \
  daemon/tests/integration/test_migrations.py \
  daemon/tests/integration/test_ingest_search_forget.py \
  daemon/tests/integration/test_media_worker.py
```

Required evidence includes exact current-ingest links, distinct media references across observations sharing one snapshot, retry idempotency, unique historical visit/snapshot backfill, unique-snapshot ambiguous fallback, unresolved multi-candidate preservation, schema fingerprint integrity, and foreign-key integrity.

## Supersession and follow-up

This ADR extends ADR-0030 and ADR-0031 for media provenance. Observation-first recent/timeline/document/snapshot reads remain the next cutover slice. Media state-machine decomposition and streaming remain Phase 4 work.
