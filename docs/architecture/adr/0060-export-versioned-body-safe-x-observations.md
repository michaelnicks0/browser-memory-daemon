---
id: ADR-0060
status: accepted
date: 2026-07-11
decision_date: 2026-07-11
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - ADR-0030
  - ADR-0035
  - ADR-0038
  - ADR-0040
  - ADR-0056
verification:
  - daemon/tests/integration/test_x_observation_export.py
---

# ADR-0060: Export versioned body-safe X observations

## Context

Birdclaw backfill needs a passive discovery/provenance feed from Browser Memory Daemon without turning normal read APIs into an implicit integration contract. Existing `recent`, `timeline`, document, and snapshot use cases may initialize/migrate the database, write audit events, return bounded compatibility views, and omit a durable continuation cursor.

The browser extension can deliver an observation after a delay. Browser `captured_at` is therefore evidence time, not a lossless ingestion watermark. Pagination by `(captured_at, observation_id)` can skip a late-delivered observation whose capture time is behind an already-committed consumer cursor.

BMD observation data is browser evidence. It does not, by itself, prove structured X tweet authorship, external user identity, or bookmark/like collection membership.

## Decision

BMD owns contract **`bmd.x-observations` major version `1`** and the canonical JSON Schema and invented golden fixture under `contracts/` and `daemon/tests/fixtures/x_observations/`.

### Mutation boundary

The export implementation will:

- open the existing SQLite file with URI `mode=ro`;
- set `PRAGMA query_only=ON` before contract queries;
- use no readiness initializer, migration executor, audit writer, filesystem materializer, or implicit repair path;
- fail closed when the migration ledger, schema version, schema fingerprint, required tables/columns, cursor, or contract is incompatible;
- expose the pure query through a CLI and an authenticated HTTP route, with both adapters calling the same query module.

The request performs no database mutation. Starting the normal daemon remains a separate lifecycle action that may apply approved startup migrations; the standalone export CLI does not start the daemon.

### Identity and cursor

- Every v1 record requires the producer's stable `observation_id`.
- BMD assigns an immutable monotonic `ingest_sequence` in the same transaction that first inserts the observation.
- Retry of the same observation reuses its sequence.
- The exclusive ascending cursor tuple is `(ingest_sequence, observation_id)`.
- Deleted observations create sequence gaps; continuation never requires the cursor row to exist.
- `captured_at` remains required evidence time and never controls continual-watermark progress.
- The cursor is opaque, versioned, shape-validated, and bound to this contract major.

### Body and authority safety

Default v1 output contains no page body, excerpt, raw title, raw HTML, cookie, token, request header, GraphQL payload, profile path, local filesystem path, or idempotency key.

The contract distinguishes:

- observed page URL from discovered canonical X URLs;
- text hash/length/completeness/authority from text body ownership;
- URL-derived handle hints (`alias_only`) from authoritative external X user identity;
- direct collection proof from caller intent or normal browsing.

Current BMD observations emit `collection_evidence.classification = "none"` unless BMD later stores a direct structured source-surface/operation relationship. A viewed status, URL mention, or consumer-selected collection kind is never collection proof.

### Compatibility

Within v1, BMD may add optional fields and enum values only when consumers preserve or ignore unknown values safely. Removing required fields, changing identity/cursor semantics, weakening body safety, or changing authority semantics requires a new major.

Consumers must reject:

- unknown major versions;
- missing or invalid required fields;
- malformed, wrong-contract, or future-version cursors;
- duplicate observation identities with unequal canonical content;
- impossible text completeness/hash combinations.

### Retention boundary

Export does not register a deletion subscriber. After a separate explicit reviewed Birdclaw import, Birdclaw is an independently retained derivative. BMD forget does not silently mutate Birdclaw. Any future cross-store revocation preview or apply workflow is separate approval-gated work.

## Decision drivers

- Passive extraction must not mutate or migrate its source.
- Continual pull must not skip late extension delivery.
- Producer and consumer need executable compatibility fixtures.
- Browser evidence must remain weaker than structured X GraphQL authority.
- Deletion behavior must not become an implicit cross-database mutation channel.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Reuse `/recent` or `/timeline` | No new API | Audit writes, readiness/migration behavior, bounded views, no cursor | Rejected |
| Paginate by capture time | No schema change | Can skip late-delivered observations | Rejected |
| Paginate by SQLite `rowid` | Available immediately | Not an explicit durable contract; may change under table rebuild/VACUUM | Rejected |
| Add immutable ingestion sequence | Lossless commit order, stable gaps/retry semantics | Requires an additive migration and ingest change | Chosen |
| Propagate BMD forget automatically | Strong coupling | Violates independent apply/backup approval and creates silent mutation | Rejected |

## Consequences

- Positive: BMD exposes one stable, body-safe producer contract rather than incidental operator views.
- Positive: the consumer can checkpoint and replay deterministically without relying on capture time or export order.
- Positive: collection, identity, and text authority are explicit and testable.
- Negative: schema migration 14 and an ingest-sequence allocation write are required during normal capture ingest.
- Negative: databases below the supported schema fail closed until an explicitly approved migration occurs.
- Neutral: full-body export is not part of v1; any future local-only body mode needs a separate decision and approval boundary.

## Verification / validation

- JSON Schema and golden-fixture structure checks.
- Migration tests proving deterministic backfill and idempotent retry sequence allocation.
- Export tests with an SQLite authorizer plus logical/file checksum comparison before and after.
- Equal-time, late-delivery, overlap, retry, deletion-gap, malformed-cursor, older-schema, and newer-schema cases.
- Authenticated loopback HTTP tests proving the route wraps the pure query and creates no audit event.
- Cross-repository producer → consumer → temporary Birdclaw replay gate.

## Revisit triggers

Supersede this ADR before adding raw bodies, changing cursor/identity semantics, accepting BMD evidence as native structured X authority, or introducing automatic deletion propagation.

## References

- Backfill canonical review: `birdclaw-x-backfill/docs/reviews/2026-07-11-bmd-backfill-integration-rereview.md`
- `docs/architecture/adr/0035-emit-stable-browser-observation-and-navigation-identities.md`
- `docs/architecture/adr/0038-make-sqlite-authoritative-for-cleaned-snapshot-text.md`
- `docs/architecture/adr/0040-use-durable-deletion-intents-and-reconciliation.md`
