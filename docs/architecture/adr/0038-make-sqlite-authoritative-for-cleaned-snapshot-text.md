---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0038: Make SQLite authoritative for complete cleaned snapshot text

## Context and problem statement

The ingest path committed searchable chunks to SQLite but also synchronously wrote a clean-text filesystem sidecar before the database transaction. When the configured blob root lived on NAS, a mount or storage failure could therefore prevent otherwise valid text and provenance from committing locally. The sidecar also competed with SQLite as the apparent detail-read authority.

The system needs one local authority for complete cleaned text, while retaining evidence-bounded recovery for databases created before this invariant.

## Decision drivers

- text and provenance must commit without waiting for NAS or media storage;
- detail reads must have one explicit authority and provenance label;
- migration must never invent historical text or trust arbitrary database paths;
- legacy sidecars remain readable and recoverable during expansion;
- startup must not create or touch blob roots merely to initialize local SQLite;
- destructive contraction remains a later, separately approved step.

## Considered options

### Keep synchronous sidecar writes and treat chunks as fallback

Rejected. A reconstructible cache would still gate the authoritative capture path.

### Write sidecars after commit in the request path

Rejected. SQLite would commit first, but request completion could still block on an unavailable or slow NAS.

### Store complete cleaned text in SQLite and stop creating new text sidecars

Accepted. SQLite already owns search, provenance, transactions, backup, and local availability. Existing sidecars remain compatibility evidence, not a second authority.

## Decision

Migration version 9 adds two nullable/additive snapshot fields:

- `cleaned_text`: complete cleaned capture text;
- `cleaned_text_source`: `capture`, `chunks-hash-verified`, `sidecar-hash-verified`, or `legacy-fallback`.

New captures:

1. commit complete cleaned text, chunks, FTS, visit/document/snapshot provenance, and audit data in one SQLite transaction;
2. label the text source `capture`;
3. leave clean-text sidecar path and locator fields null;
4. do not create or touch the blob root.

Reads prefer non-null `snapshots.cleaned_text`. A legacy sidecar or chunk reconstruction is consulted only while that field remains null. Summary/detail responses expose authority and availability state without exposing raw locator strings.

The version-9 migration attempts only a deterministic SQLite-local historical promotion: ordered chunks are joined with the canonical separator and stored only when their SHA-256 exactly matches the snapshot's recorded text hash. Mismatches remain `legacy-fallback`.

The explicit operator command is:

```bash
memory snapshot-text reconcile [--limit N] [--execute]
```

It is dry-run by default. It first tests hash-verified chunk reconstruction, then resolves a legacy sidecar through the contained clean-text `BlobStore`, reads only an in-root regular file, and promotes it only when its SHA-256 matches the recorded snapshot hash. Unresolved rows remain unchanged and are reported by ID plus redaction-safe reason. `--execute` writes only previously null authority fields and emits one aggregate audit event.

`RuntimeConfig.ensure_dirs()` creates local config/data/state directories only. Blob roots are created lazily by operations that actually write blobs. The explicit required-mount guard remains fail-closed when enabled.

Doctor reports `snapshots_missing_authoritative_text`, includes it in overall health, and reports SQLite text bytes separately from legacy sidecar bytes.

## Consequences

### Positive

- text/provenance capture has no blob-root filesystem dependency;
- exact cleaned text and its source are transactional and locally backed up with SQLite;
- new captures do not create redundant text files;
- historical promotion is hash-verified and root-contained;
- mount/NAS latency is removed from the text request path.

### Negative

- SQLite files grow by approximately one additional complete-text copy beyond chunks/FTS;
- historical rows whose chunks do not hash-match require an accessible valid sidecar or remain unhealthy;
- existing clean-text sidecars remain until forget, explicit cleanup, or a future contraction migration;
- `BMD_REQUIRE_BLOB_ROOT_MOUNT=1` intentionally remains a daemon startup policy and can still trade availability for fail-closed external-media storage.

### Neutral

- FTS5 continues to index chunk rows;
- media storage, root separation, spool bounds, tombstones, and backup/restore manifests remain separate slices;
- version-8 relative locators remain the compatibility contract for legacy text sidecars and current media blobs.

## Verification

Required evidence:

- fresh and v8-to-v9 migration fingerprints, integrity, foreign keys, and exact hash-verified backfill;
- new capture with a nonexistent blob root and no blob-root creation;
- SQLite-first detail reads and doctor authority metrics;
- dry-run and execute reconciliation from a contained hash-verified legacy sidecar;
- CLI command wiring and default dry-run behavior;
- existing ingest/search/forget/media, HTTP, concurrency, broad e2e, and real-Chrome gates.

Recorded repository evidence on 2026-07-10:

- migration plus text-authority suites: `18 passed`;
- affected config/ingest/media/HTTP/CLI suites: `38 passed`;
- fast gate: `151` Python tests, `30` extension tests, `80.98%` branch coverage, Ruff, strict Mypy over 14 source files, generated-doc/catalog, secret, whitespace, and XDG-sentinel checks all passed;
- broad e2e with isolated real-Chrome skip: exit `0`;
- concurrency stress: `status=ok`, `52/52` operations succeeded, zero operation errors, SQLite integrity `ok`, and zero chunks missing FTS;
- real Windows Chrome e2e with download disabled: exit `0`, including complete SQLite authority count equality for every captured snapshot;
- generated inventory: `181` tests across `30` files and `43` requirements; `104` rendered HTML documents matched source.
- Structurizr DSL validation passed; all `19` views have Mermaid SVG/PNG, DOT, Graphviz SVG/PNG, and Markdown artifacts; adversarial pixel QA passed for ingest, fast-capture, container, and system-context views after removing the stale sidecar-write edge; `281` local HTML links resolved with zero missing targets.

## Related decisions

- [ADR-0036](0036-route-blob-operations-through-contained-blobstore.md)
- [ADR-0037](0037-expand-blob-references-with-relative-locators.md)
