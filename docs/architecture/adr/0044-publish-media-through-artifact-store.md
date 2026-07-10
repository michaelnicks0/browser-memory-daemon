# ADR-0044: Publish and read media through the artifact store

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0036, ADR-0037, ADR-0039, ADR-0040, ADR-0042, ADR-0043

## Context

ADR-0043 moved cache accounting, admission, eviction, locator containment, and deletion outcomes into `media_store.py`, but `media.py` still directly published artifacts, updated artifact rows, registered lifecycle state, resolved reads, and implemented purge/rehydration. That split left the compatibility facade responsible for the most failure-sensitive database/filesystem transition.

The former replacement path reused one final locator per artifact. A database failure after publication could therefore leave a new blob without matching row metadata or overwrite the previously committed bytes before the row update succeeded. Spool reservations also needed explicit compensation when publication failed.

## Decision

`media_store.py` owns the complete artifact repository and `BlobStore` publication boundary:

1. `media.py` remains the stable compatibility facade. It validates and normalizes caller payloads into `MediaArtifactWrite`; stream buffering and fetch/HLS transport remain there for later slices.
2. Each byte-bearing write stages through `BlobStore` and targets a unique server-generated candidate locator. A replacement never overwrites the currently committed locator in place.
3. Admission accounting excludes the artifact being replaced from snapshot, domain, and global byte totals and from eviction candidates. The current committed bytes therefore remain intact until the replacement row transition succeeds.
4. The store revalidates snapshot/artifact ownership inside the final write transaction. It publishes the candidate, advances the artifact row, releases a spool reservation, registers committed lifecycle state, and tombstones the prior locator as one repository operation.
5. If the database operation fails, the transaction is rolled back, the candidate blob is removed, and any spool reservation is released. The prior row and bytes remain authoritative.
6. Concurrent writers serialize the final owner re-read and row transition with `BEGIN IMMEDIATE` when the caller does not already own a transaction; callers with an existing transaction receive an isolated savepoint.
7. Artifact detail/list resolution and cache purge/rehydration move into `media_store.py`. `browser_memory_daemon.media` re-exports those public functions unchanged.
8. Successful replacement and purge continue to use durable tombstones and the existing storage reconciler. A process failure after candidate publication but before the SQLite commit can leave only a contained unreferenced candidate, which reconciliation classifies as an orphan.

No schema migration or API change is introduced.

## Consequences

### Positive

- A failed replacement cannot corrupt the previously committed artifact.
- Failed first publication does not leak committed candidate bytes or spool reservations during handled failures.
- Artifact rows, contained locators, lifecycle registration, reads, and purge now have one repository owner.
- The public `media.py` import surface remains compatible while becoming thinner.

### Tradeoffs and deferred work

- Unique candidate locators consume a new filename for each replacement until the old tombstone is processed.
- Media-root admission is still an estimate rather than a durable global in-flight-byte reservation. Global worker/request/byte budgets remain Phase 4.5 work under REQ-036.
- `store_media_blob_stream` still buffers the bounded payload before repository publication; transport streaming remains deferred to Phase 4.5.
- Guarded fetch and HLS transport remain in `media.py` until the next reversible extraction.

## Verification

Repository evidence includes:

- `daemon/tests/unit/test_media_store.py`
- `daemon/tests/integration/test_media_storage.py::test_failed_first_publication_removes_new_blob_and_spool_reservation`
- `daemon/tests/integration/test_media_storage.py::test_failed_write_transaction_start_aborts_stage_and_releases_spool_reservation`
- `daemon/tests/integration/test_media_storage.py::test_failed_replacement_preserves_previous_blob_and_removes_candidate`
- `daemon/tests/integration/test_media_storage.py::test_metadata_refresh_reports_the_preserved_stored_state`
- `daemon/tests/integration/test_media_storage.py::test_replacement_admission_excludes_current_artifact_and_preserves_it_on_row_failure`
- `daemon/tests/integration/test_media_worker.py::test_concurrent_media_blob_writes_use_distinct_temp_files`
- focused media/storage/worker, Ruff, Mypy, architecture, generated-document, and broad repository gates recorded with the implementing commit.
