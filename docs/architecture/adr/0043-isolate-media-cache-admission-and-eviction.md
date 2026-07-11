# ADR-0043: Isolate Media Cache Admission and Eviction in the Artifact Store

- **Status:** accepted
- **Date:** 2026-07-10
- **Decision owners:** Browser Memory Daemon maintainers
- **Related:** ADR-0040, ADR-0042, REQ-036, HRD-006, HRD-011, VAL-006

## Context

Media cache admission was embedded in the `media.py` compatibility facade. The same block counted committed/tombstoned/missing bytes, applied per-artifact/snapshot/domain/global gates, selected oldest rows, created durable tombstones, and processed deletion outcomes. This combined policy, repository, and BlobStore lifecycle work with transport and API compatibility code.

The behavior is concurrency- and failure-sensitive. Moving it requires preserving the existing SQL selection order, status accounting, tombstone-before-delete sequence, and public `media.media_storage_allowed` symbol.

## Decision

1. `media_store.py` owns media byte accounting, MIME/priority/size admission, domain/global oldest-first eviction, BlobStore locator resolution, durable tombstone creation, and deletion-outcome accounting.
2. `media.py` remains the compatibility facade and re-exports `media_storage_allowed` with identical object identity.
3. Admission continues to call the existing `media_storage` tier resolver and `blob_lifecycle` tombstone processor; it does not open, unlink, or trust DB-supplied paths directly.
4. Snapshot limits reject without eviction. Domain and global limits retain the existing oldest-first bounded eviction behavior.
5. Rows in `stored`, `purging`, or `missing` state continue to count while any media/spool/legacy locator remains, so pending or failed deletion cannot silently free capacity.
6. This slice does not change schema, status values, endpoint behavior, cache limits, or live runtime state. Later media-store slices may move publication/read/purge repository code behind the same boundary.

## Alternatives considered

### Leave admission in the compatibility facade

Rejected because it keeps durable state and BlobStore lifecycle behavior coupled to transport/fetch code and prevents a thin facade.

### Make BlobStore choose eviction policy

Rejected because BlobStore is a contained byte boundary; it should not know document domains, snapshots, artifact status, or SQLite policy.

### Replace the logic with a generic cache framework

Rejected because it would add abstraction and dependencies without improving the local SQLite/BlobStore invariants.

## Consequences

### Positive

- Admission and eviction have one explicit owner.
- The facade remains source-compatible.
- Tombstone-before-delete and pending-byte accounting remain intact.
- The boundary is ready to absorb artifact publication/read/purge repository code incrementally.

### Negative

- `media_store.py` still depends on the concrete SQLite schema and BlobStore lifecycle modules.
- Media publication/read/purge logic remains in `media.py` until subsequent slices.
- DB `CHECK` constraints and full transition enforcement remain deferred until historical state normalization is versioned.

## Verification

- `daemon/tests/unit/test_media_store.py` verifies compatibility-facade identity and module ownership.
- `daemon/tests/integration/test_ingest_search_forget.py` verifies global/domain oldest-first eviction behavior.
- `daemon/tests/integration/test_storage_reconcile.py` verifies failed/pending deletion accounting and out-of-root containment.
- `daemon/tests/integration/test_media_worker.py` verifies admission through public fetch and upload paths.
- The hermetic fast gate, broad repository gate, concurrency stress, performance benchmark, and isolated real-Chrome gate remain release authorities.

## Rollback

Move the four admission/accounting helpers back into `media.py` and remove the compatibility re-export. There is no schema or runtime-data rollback.
