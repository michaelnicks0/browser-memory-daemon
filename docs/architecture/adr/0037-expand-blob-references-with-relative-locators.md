---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0037: Expand blob references with root-relative locators

> **Supersession note:** [ADR-0038](0038-make-sqlite-authoritative-for-cleaned-snapshot-text.md) stops creating new clean-text sidecars. This ADR remains current for media blobs and compatibility handling of legacy text sidecars.

## Context and problem statement

ADR-0036 established a contained, streaming `BlobStore`, but SQLite still stored only absolute filesystem paths. Absolute paths couple database rows to one workstation or mount point and complicate blob-root relocation, restore, and verification.

Changing every row in place would create a flag-day migration. The versioned SQLite migration kernel also must not inspect or mutate the filesystem while applying schema changes: it does not have reliable runtime root identity, mount state, or proof that a historical path belongs to the currently configured root.

The next storage slice therefore needs a reversible expand phase that improves locator portability without making historical rows unreadable or weakening path containment.

## Decision drivers

- Preserve compatibility with databases whose blob columns contain absolute paths.
- Make new blob references portable across root relocation and restore.
- Keep all database-provided values untrusted and resolved through `BlobStore`.
- Avoid filesystem reads or inferred path backfills inside schema migration transactions.
- Keep the change additive and reversible before eventual absolute-path contraction.
- Fail closed when a populated preferred locator is invalid; do not silently downgrade to a second database-controlled path.

## Decision

Add nullable relative-locator columns in migration version 8:

- `snapshots.cleaned_text_locator`, relative to `RuntimeConfig.clean_text_root`;
- `media_artifacts.blob_locator`, relative to `RuntimeConfig.media_root`.

New clean-text and media writes dual-write:

1. the new relative locator; and
2. the existing absolute compatibility path.

Read, serve, stat, delete, purge, eviction, and forget flows use this precedence:

1. use the relative locator when it is non-null and non-empty;
2. otherwise use the legacy absolute path;
3. resolve the selected value through the configured-root `BlobStore`.

A non-empty invalid or out-of-root relative locator fails closed. The system does **not** fall back to the absolute column after rejecting the preferred locator because doing so would turn locator corruption into an implicit policy downgrade.

Migration version 8 adds nullable columns only. It does not guess historical relative locators. Historical rows retain `NULL` and continue through the contained legacy fallback. The operator blob-root migration populates both absolute and relative fields when it successfully relocates a known blob.

Media purge and eviction clear both media locator columns when bytes cease to be authoritative. Availability responses expose locator kind (`relative`, `legacy-absolute`, or `unresolved`) and containment status without exposing the selected locator in list/detail projections.

## Considered alternatives

### Rewrite existing absolute paths during migration version 8

Rejected. Schema migration lacks trusted runtime root/mount context, and basename-based inference would silently misclassify customized or historical layouts.

### Replace the absolute columns immediately

Rejected. A contraction would remove the rollback/read compatibility needed while relative-locator behavior is still being validated.

### Fall back to the absolute path whenever the relative locator fails containment

Rejected. A tampered preferred locator must remain visible and fail closed; silently trying another database-controlled path hides corruption and makes precedence non-deterministic.

### Store locators relative to the top-level blob root

Rejected for this expand slice. Clean text and media already have separate configured containment roots. Root-specific locators keep the current security boundary explicit and prepare for later media-root separation.

## Consequences

### Positive

- New references survive root relocation without embedding host-specific prefixes.
- Existing databases remain readable without a filesystem-coupled schema migration.
- Read precedence is deterministic and testable.
- Locator corruption cannot force unchecked or cross-root access.
- Blob-root migration can converge historical rows while copying bytes under operator control.

### Negative

- Two locator columns describe each blob during the expand window.
- Historical rows remain absolute until an evidence-backed operator migration or later reconciliation fills the relative locator.
- A corrupt non-empty relative locator makes an otherwise valid legacy path unavailable until repaired; this is intentional fail-closed behavior.
- Absolute-column contraction and durable reconciliation/tombstones remain separate later phases.

## Verification and validation

Required executable evidence:

- migration version 8 upgrades version 7 exactly once and preserves historical rows with nullable locators;
- new ingest and media writes populate both relative and absolute columns;
- read paths prefer valid relative locators even when legacy paths are tampered;
- invalid preferred locators are rejected rather than falling back;
- historical `NULL` locators use contained legacy absolute paths;
- purge and eviction clear both media columns;
- blob-root migration copies bytes and updates both locator forms;
- migration fingerprints, foreign keys, focused storage tests, broad repository gates, generated documentation, secret scan, and diff checks pass.

Recorded implementation evidence on 2026-07-10:

- `pytest` migration suite: 15 passed;
- focused BlobStore/migration/ingest/media/observation/HTTP/admin group: 96 passed;
- `scripts/run-fast-gate.sh`: passed with 147 pytest tests, 30 Node tests, strict mypy/Ruff, and 81.17% aggregate branch coverage;
- `scripts/run-e2e.sh` with isolated real-Chrome delegation disabled: passed;
- `scripts/run-real-chrome-e2e.sh` with cached Chrome for Testing: passed, including relative clean-text/media locator assertions;
- `scripts/run-concurrency-stress.sh`: passed with 12/12 captures, 40/40 mixed operations, SQLite integrity `ok`, and no missing FTS rows;
- generated test inventory, rendered documentation, showcase, secret scan, and diff checks: passed.

## Rollback

The code can revert to legacy absolute-path reads while the additive nullable columns remain harmless. Do not drop the new columns until a later contraction decision proves that all supported binaries and historical rows no longer require the absolute compatibility fields.

## Related decisions

- [ADR-0021](0021-use-configurable-nas-blob-root-with-local-sqlite.md)
- [ADR-0028](0028-use-versioned-restore-backed-sqlite-migrations.md)
- [ADR-0036](0036-route-blob-operations-through-contained-blobstore.md)
