---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0036: Route blob filesystem operations through one contained BlobStore

## Context and problem statement

Phase 0 centralized path validation, but application modules still performed their own write, replace, read, stat, copy, and unlink operations after resolving a path. That duplicated atomic-publication and cleanup behavior and left the safety boundary spread across ingestion, media, forget, read models, HTTP download, and blob-root migration.

Phase 3 needs a deep storage module before relative locators, reservations, durable blob states, reconciliation, or SQLite-authoritative text can be added safely.

## Decision

Introduce `browser_memory_daemon.blob_store.BlobStore` as the only application boundary for current blob filesystem operations.

The first slice retains existing absolute database locators and current directory layout. `BlobStore` provides:

- contained path generation and resolution under one configured root;
- unique same-root staging files;
- chunked/streaming writes with incremental byte and SHA-256 accounting;
- optional expected-size and expected-hash verification before publication;
- flush and file `fsync` before commit;
- atomic `os.replace` plus parent-directory `fsync`;
- contained binary open/read, text read, stat, existence, abort, and delete operations;
- explicit delete and resolution outcomes for missing, invalid, out-of-root, and failed paths.

Ingestion, media storage/eviction/purge, forget, snapshot reads, media HTTP download, and blob-root migration route through this boundary. A caller that omits `RuntimeConfig` can still inspect media metadata but receives `file_path_status = "config-required"`; it cannot perform unchecked filesystem access.

## Safety and compatibility rules

1. A DB locator is never opened, copied, replaced, statted, or deleted before containment validation.
2. Staged blobs can commit only through the `BlobStore` that created them and only from that root's `.staging` directory.
3. Size/hash mismatch removes the staged file and publishes no target.
4. Commit failure attempts staged-file cleanup and raises a typed `BlobStoreError`.
5. Concurrent writers use unique stages; every published target is a complete atomic file. Reservation and ownership policy arrive in a later Phase 3 slice.
6. Existing absolute locators and endpoint paths remain compatible. Relative locator dual-write is deliberately separate.
7. Required-mount and storage-identity validation remains a configuration/startup prerequisite; this module does not silently reinterpret an absent external mount as a local store.

## Consequences

### Positive

- Application modules no longer directly operate on DB-supplied blob paths.
- Clean-text and media publication share one streaming, hash-aware, atomic path.
- Blob-root migration no longer uses whole-file `shutil.copy2`; it streams through verified staging.
- Out-of-root legacy rows remain visible as status evidence and are never touched.
- The boundary is ready for relative locators, durable staged/committed/tombstoned states, and reconciliation.

### Negative

- HTTP media download still buffers the complete artifact after the contained read; bounded HTTP streaming remains Phase 6.
- Existing-target blob migration still trusts target presence in this slice; source/target hash comparison arrives with the migration/reconciliation slice.
- File publication and its SQLite row are not yet one recoverable state machine. Staging/tombstone reconciliation remains open.

## Alternatives rejected

### Keep path helpers and duplicate filesystem operations

Rejected because containment alone does not centralize publication, cleanup, verification, or future state transitions.

### Introduce a generic storage-provider framework

Rejected. The system needs one boring local/NAS filesystem boundary, not cloud abstraction or dependency injection.

### Change locators and blob state in the same commit

Rejected. Relative-locator migration and durable state require independent expand/backfill/read-switch rollback domains.

## Verification

- `test_blob_store.py` covers streaming stage/commit, expected size/hash mismatch, traversal, symlink escape, cross-root staged commits, delete outcomes, concurrent atomic writers, and stage cleanup.
- Existing ingestion/media/forget/blob-migration/HTTP tests prove endpoint behavior and absolute locator compatibility.
- The fast and broad hermetic gates must pass with no writes outside explicit fixture roots.

## Follow-up

1. Add relative locators alongside legacy absolute paths and dual-read them.
2. Add reservations and durable staged/committed/tombstoned/missing/deleted states.
3. Reconcile stale stages, missing files, orphans, wrong-root locators, and DB/filesystem divergence.
4. Store authoritative full snapshot text in SQLite and make clean-text files optional derivatives.
5. Split local text/derivative, NAS media, and optional bounded local media-spool roots.
