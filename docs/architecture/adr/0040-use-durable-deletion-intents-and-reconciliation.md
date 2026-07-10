---
id: ADR-0040
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes:
  - ADR-0006
superseded_by: []
related:
  - ADR-0031
  - ADR-0037
  - ADR-0039
  - docs/ARCHITECTURE.md
  - docs/CLI_UX_CONTRACT.md
  - docs/api.md
  - docs/security-model.md
  - daemon/src/browser_memory_daemon/blob_lifecycle.py
  - daemon/src/browser_memory_daemon/storage_reconcile.py
  - daemon/src/browser_memory_daemon/forget.py
  - daemon/src/browser_memory_daemon/media.py
verification:
  - daemon/tests/integration/test_storage_reconcile.py
  - daemon/tests/integration/test_ingest_search_forget.py
  - daemon/tests/integration/test_migrations.py
  - daemon/tests/e2e/test_cli_admin.py
  - python -m ruff check --select F,I
  - python -m mypy
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-fast-gate.sh
---

# ADR-0040: Use Durable Deletion Intents and Retryable Storage Reconciliation

## Context

ADR-0006 established physical forget cascades and deletion receipts, but its implementation removed database rows before deleting their referenced bytes. A crash or unlink failure after the database transaction could therefore leave sensitive bytes with no durable retry record. Media purge and cache eviction had the same split-brain failure: rows were marked purged before filesystem deletion, and failed bytes could disappear from cache accounting.

Phase 3 now has contained `BlobStore` operations, SQLite-authoritative text, distinct media tiers, and an explicitly bounded spool. Those boundaries make it possible to record deletion intent before destructive filesystem work and to retry failures without retaining deleted recall content.

## Decision

We will use SQLite-backed blob lifecycle records and retryable deletion intents for derivative and media bytes.

1. Migration v11 adds `blob_storage_records`. Each record identifies an owner, storage tier, contained locator, expected size/hash when known, lifecycle state, operation, attempts, and failure detail.
2. Supported lifecycle states are `staged`, `committed`, `tombstoned`, `missing`, `deleted`, `blocked`, and `failed`.
3. New media publication and blob-root migration register a `committed` record in the same SQLite transaction that publishes the owning locator.
4. Forget writes blob tombstones and its deletion receipt in the same transaction as the relational cascade. Only after that commit may the processor delete bytes.
5. Media purge and cache eviction set the artifact to `purging`, retain its locator for retry, and tombstone the blob before deletion. `purging`, `purged`, and `missing` artifacts are not served.
6. A deletion is complete only in `deleted` or `missing`. `failed` and `blocked` remain pending, continue to count against media budgets, degrade doctor status, and are retried by reconciliation.
7. Filesystem deletion always resolves through the configured tier's contained `BlobStore`. Wrong-root, invalid, and unavailable-root records fail closed and remain pending.
8. Tombstone processors are serialized by a local state-root file lock so concurrent CLI, daemon, and worker attempts converge instead of racing the same bytes.
9. `storage reconcile` is dry-run by default. Execute mode retries tombstones, marks missing or size/hash-mismatched media explicitly, restores a recovered row only after expected bytes verify, deletes stale in-root stages, and tombstones/deletes unreferenced in-root orphans. It never traverses unavailable external roots and never deletes outside configured roots.
10. Tombstones retain only operational metadata needed to complete deletion. They do not retain captured text, media content, URLs, or deleted document rows.

## Consequences

### Positive

- A committed forget receipt has a durable byte-deletion work record before document provenance is removed.
- Failed media purge/eviction remains visible, unreadable, retryable, and included in capacity accounting.
- Crash recovery no longer depends on reconstructing deleted owners from filesystem names.
- Orphans, missing files, stale stages, blocked locators, and pending tombstones have one dry-run-first operator surface.
- Concurrent processors converge under a cross-process local lock.

### Negative

- Blob lifecycle metadata grows monotonically until a future, backup-gated metadata compaction policy is approved.
- SQLite transactions and filesystem deletion remain separate operations; reconciliation is the explicit convergence mechanism.
- `missing` is treated as terminal because the requested bytes are already absent, but it is reported distinctly from a confirmed unlink.
- External media-root outages can leave tombstones pending until storage identity is healthy again.

### Neutral

- Authoritative snapshot text remains in SQLite and is deleted by the relational forget transaction; clean-text records cover only optional derivatives.
- Disposable media bytes remain excluded from backup by default.
- This decision does not add automatic retention, content tombstones, legal hold, cloud storage, or secure erase guarantees.

## Verification and validation

- Migration tests upgrade a representative v10 database, backfill media and derivative `committed` records, and verify the v11 schema fingerprint.
- Fault-injection tests force unlink failure after tombstone commit, prove the database cascade/receipt survives, then prove execute reconciliation deletes the bytes and updates the receipt.
- Purge tests prove failed bytes remain `purging`, are not served or overwritten, continue to count against admission budgets, and converge to `purged` after retry.
- Concurrency tests start two processors on the same failed tombstone and prove one delete with one terminal lifecycle state.
- Reconciliation tests cover dry-run and execute behavior for missing/corrupt/recovered references, in-root orphans, and stale stages.
- Existing adversarial containment tests continue to prove that outside-root paths are not deleted.

## Rollback

Migration v11 is additive. Rollback means using the pre-migration online backup with the prior binary. There is no destructive down-migration. The v11 binary can preserve failed/blocked records indefinitely without deleting bytes; execute reconciliation is an explicit operator action.
