---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0033: Use observation-first historical activity reads

## Context and problem statement

The legacy recent/timeline read path emitted one row per visit and selected the newest snapshot for the document. When one visit produced multiple extractions, every historical row could therefore show the document's latest text instead of the snapshot observed at that time. Conversely, collapsing observations into visits hid repeated unchanged captures and their media provenance.

Version 4 introduced capture observations, version 5 backfilled evidence-supported history, and version 6 linked media artifacts to observations. The read path can now cut over without contracting legacy tables or endpoint paths.

## Decision drivers

- A historical item must show its contemporaneous observed URL, title, snapshot, text snippet, and media references.
- Repeated unchanged extractions must remain separate observations while sharing one deduplicated snapshot.
- Legacy rows without observation evidence must remain readable without pretending their provenance is exact.
- Visit-level dwell and scroll summaries must not multiply when one visit has several observations.
- Existing local API/CLI endpoint paths and legacy fields must remain compatible.

## Considered options

1. **Keep visit-first reads and add observation counts** — rejected because it still substitutes the newest document snapshot.
2. **Return observation rows only** — rejected because partially migrated or deliberately unresolved legacy visits would disappear.
3. **Observation-first rows plus an explicit legacy fallback** — accepted.

## Decision outcome

`recent_captures` and `timeline` now read from an observation-first activity projection:

- each capture observation produces one activity item using its stored observed URL, title, capture time, snapshot, disposition, and provenance quality;
- the text snippet comes only from that observation's snapshot;
- media counts come only from `media_artifact_observations` for that observation;
- `observation_id`, `navigation_id`, capture method/reason/version, `record_source`, and provenance fields are additive response fields.

A visit becomes a `legacy-visit` fallback item only when no capture observation references that visit. The fallback prefers a snapshot whose legacy `visit_id` matches the visit. If none exists, it may use the document's latest snapshot but labels the item `legacy-fallback` with `ambiguous` provenance. It never presents that fallback as an observed relationship.

Timeline returns an additive `summary`:

- `captures` counts returned activity items;
- `observations` counts observation-backed items;
- `visits` counts distinct visit identities;
- dwell is summed once per distinct visit;
- maximum scroll is derived from visit lifecycle events;
- media counts are summed from the activity rows in the bounded response.

Document detail now exposes ordered `observations` and `url_claims`. Snapshot detail exposes the observations that reference that exact snapshot. Media detail continues to expose only stored artifact/observation links from ADR-0032.

Search remains snapshot-centric: every FTS hit already names the exact snapshot containing the matching chunk, so no latest-snapshot substitution occurs there.

## Compatibility and rollback

- `/recent`, `/timeline`, `/documents/{id}`, and `/snapshots/{id}` retain their paths and legacy fields.
- New fields and timeline summary are additive.
- `visits`, legacy snapshot links, and prior read-capable columns remain intact for at least one compatibility release.
- A prior binary can ignore the new tables/fields. Rollback does not require schema contraction.

## Consequences

### Positive

- Historical activity no longer substitutes a document's latest snapshot.
- One visit with several unchanged or changed extractions is represented truthfully.
- URL claims remain separate from observed identity in detail views.
- Legacy uncertainty is visible instead of silently inferred.
- Visit-level dwell is not multiplied by observation count.

### Negative

- Recent/timeline can return more items than before because the unit is now an extraction observation, not a visit.
- The bounded timeline summary describes returned items, not an unbounded aggregate outside the requested limit.
- Legacy fallback rows remain necessarily ambiguous when no visit-linked snapshot survives.

## Validation

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  -m pytest -q \
  daemon/tests/integration/test_observation_reads.py \
  daemon/tests/integration/test_capture_observations.py \
  daemon/tests/integration/test_ingest_search_forget.py \
  daemon/tests/integration/test_visit_lifecycle.py \
  daemon/tests/e2e/test_admin_api.py
```

Required cases include three unchanged observations sharing one snapshot, changed content producing a contemporaneous second snapshot, exact per-observation media counts, URL-claim detail, visit-deduplicated dwell summary, and a legacy visit whose visit-linked snapshot is older than the document's latest snapshot.

## Supersession and follow-up

This ADR completes the read-cutover follow-up from ADR-0030 through ADR-0032. Lifecycle attachment by visit identity and interval-union dwell remain the next Phase 2 slice. Legacy columns/read fallback are retained; no contract migration occurs here.
