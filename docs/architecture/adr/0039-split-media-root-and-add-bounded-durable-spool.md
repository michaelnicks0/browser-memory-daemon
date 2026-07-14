---
status: superseded
superseded_by: [ADR-0061]
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0039: Split derivative and media roots with a bounded durable spool

## Context and problem statement

A common blob root coupled local text recall to external media availability and made a missing mount capable of becoming a writable shadow directory. SQLite now owns complete cleaned text, so text derivatives and media bytes can have distinct availability and retention characteristics. Media uploads still need a durable, bounded path during an external-root outage without silently falling back to an unbounded local directory.

## Decision drivers

- text/provenance capture must remain local when media or NAS storage is unavailable;
- external media writes must prove the intended mount and identity;
- outage buffering must be explicit, local, durable, and hard-capped under concurrency;
- stored media must remain readable while it is spooled;
- draining must stream and verify bytes before changing authority;
- legacy `BMD_BLOB_ROOT` deployments need a compatibility path;
- every mutation needs a dry-run or reversible boundary.

## Considered options

### Keep one blob root and rely on startup mount checks

Rejected. It blocks text recall during media outages and does not protect a long-running daemon after a mount disappears.

### Fall back automatically to an uncapped local media directory

Rejected. It can fill local storage and hides the loss of the intended media root.

### Split roots and use an explicitly configured bounded spool

Accepted. It preserves local text authority while making degraded media behavior visible and bounded.

## Decision

1. **Separate roots**
   - `BMD_DERIVATIVE_ROOT` owns reconstructible local derivatives such as legacy clean-text sidecars.
   - `BMD_MEDIA_ROOT` owns final disposable media bytes.
   - `BMD_BLOB_ROOT` remains a compatibility parent when `BMD_MEDIA_ROOT` is absent.
2. **Do not create external roots during startup.** Config initialization creates only local config/data/state directories. Derivative, media, and spool roots are opened lazily by the operations that need them.
3. **Guard external media roots on every media access.** Explicit external roots and mount-guarded legacy roots require a non-root mount plus `.bmd-media-root-id` whose content exactly matches `BMD_MEDIA_ROOT_IDENTITY`. A failed guard never writes a shadow media tree.
4. **Make the spool opt-in and bounded.** `BMD_MEDIA_SPOOL_ROOT` and positive `BMD_MAX_MEDIA_SPOOL_BYTES` must be configured together. The spool must be contained under the local data root and may not overlap the media root.
5. **Serialize spool capacity with distinct SQLite reservations.** Migration v10 adds `media_spool_reservations`, `media_artifacts.storage_tier`, and `media_artifacts.spool_locator`. Every in-flight writer receives a unique reservation ID, including concurrent writers for the same artifact. Admission counts final/orphaned files already present beneath the spool plus all reservations; existing bytes are preserved when the cap rejects a new write.
6. **Serve spooled artifacts as stored media.** `storage_tier='spool'` selects the spool root and `spool_locator`; `storage_tier='media-root'` selects the guarded media root and `blob_locator`. Raw locators remain internal.
7. **Drain explicitly.** `memory media-spool status` is read-only. `memory media-spool drain` is dry-run by default; `--execute` streams each file into the verified media root with expected size and SHA-256, performs a compare-and-switch SQLite transition to `media-root`, then removes the spool source only when the transition committed. A failed cleanup remains visible in filesystem capacity accounting.
8. **Verify migration targets.** Blob-root migration now targets configured derivative/media roots separately, excludes spooled artifacts, and refuses to adopt an existing destination whose size or SHA-256 mismatches SQLite evidence.
9. **Degrade media without disabling text capture.** Daemon startup no longer fails solely because a guarded media root is unavailable. Health reports the degraded media-root status; an enabled spool makes it a warning, while no spool makes it an error.

## Consequences

### Positive

- local SQLite text/provenance commits do not touch media or NAS roots;
- an absent or wrong external mount cannot become a silent media shadow tree;
- local outage buffering has a transactional hard cap;
- spooled bytes remain retrievable and can be drained without loading whole files into memory;
- operators can distinguish final and spooled bytes from SQLite and health output;
- existing legacy blob-root layouts remain readable and migratable.

### Negative

- external media-root deployments must provision and preserve an identity marker;
- spool capacity can reject new media while preserving old bytes;
- the schema and every media read/delete path must understand storage tiers;
- crash-left reservations and orphaned files require the reconciliation slice in ADR-0040.

### Neutral

- this decision does not change media eligibility, cache, or URL policy;
- the spool is durable buffering, not an additional source of truth for searchable text;
- no live daily-driver environment or external root is changed by this repository slice.

## Verification

Required evidence:

- fresh and v9 migration coverage for schema v10;
- external-root marker and wrong-mount rejection tests;
- media writes during root outage land in the local spool and remain readable;
- concurrent distinct-artifact and same-artifact reservations prove the cap cannot be exceeded;
- orphan spool files consume capacity, and a lost drain transition preserves the source;
- dry-run and execute drain tests prove streamed size/hash verification and DB tier switch;
- existing corrupted migration destinations are rejected without DB rewrites;
- focused media, forget, API, CLI, health, installer, and concurrency gates;
- real Windows Chrome e2e confirms normal media lands in the final media tier.

## Related decisions

- [ADR-0036](0036-route-blob-operations-through-contained-blobstore.md)
- [ADR-0037](0037-expand-blob-references-with-relative-locators.md)
- [ADR-0038](0038-make-sqlite-authoritative-for-cleaned-snapshot-text.md)
