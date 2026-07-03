---
id: ADR-0004
status: superseded
date: 2026-06-14
decision_date: 2026-06-08
decider: Operator
scope: repo
backfilled: true
supersedes: []
superseded_by:
  - ADR-0021
related:
  - docs/ARCHITECTURE.md
  - docs/storage-growth-model.md
  - daemon/src/browser_memory_daemon/schema.sql
  - daemon/src/browser_memory_daemon/ingest.py
  - daemon/src/browser_memory_daemon/search.py
  - daemon/src/browser_memory_daemon/config.py
verification:
  - ADR lint + repo Markdown fence check
  - git diff --check -- .
  - ./scripts/secret-scan.sh
  - BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh with temporary Python 3.11 shim
---

# ADR-0004: Use Text-First SQLite/FTS5 and Blob Storage

## Context

This ADR backfills a decision that existed before the ADR workflow was added. ADR-0021 supersedes the blob placement portion by making blob storage configurable for NAS-backed daily-driver deployments while preserving the text-first SQLite/FTS5 model.

Browser Memory Daemon needs exact local recall with inspectable storage, modest operational complexity, and a durable data model that supports search, detail pages, timeline, lifecycle metadata, deletion, media refs, and future extensions.

The implementation intentionally starts with captured text, chunks, FTS5, and local blob files. It does not start with semantic embeddings, screenshots, full HTML, cloud vector stores, or a browser-history-only model.

## Decision

We will make text recall authoritative and store it using SQLite plus FTS5 and WSL-local blob files.

The daemon stores documents, visits, snapshots, chunks, FTS rows, lifecycle events, media refs/tasks, audit events, and deletion receipts in SQLite. Clean text snapshots live under the WSL XDG data root as blob files. Exact FTS search is the first retrieval model. Media blobs are related cache artifacts, not the source of recall correctness.

Embeddings, full HTML snapshots, screenshots, and richer retention/compaction are future lanes, not current defaults.

## Decision drivers

- Exact text search is enough to prove useful personal recall before adding semantic complexity.
- SQLite + FTS5 is local, boring, inspectable, backup-friendly, and easy to test.
- Clean text blobs preserve detail views and evidence separate from chunk rows.
- Runtime data must stay outside the Git repo and outside Chrome profile storage.
- The storage model must support real deletion cascades and receipts.
- Growth must be understandable before adding high-volume capture surfaces.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Chrome History / browser profile only | Already exists | No page text, weak search/detail/delete semantics, Chrome profile becomes memory store | Rejected |
| Cloud vector DB / cloud embeddings first | Semantic search from day one | Violates local-first posture, adds provider risk and privacy exposure | Rejected |
| Full HTML/screenshots by default | Rich reconstruction | Large storage growth and privacy surface before need is proven | Rejected |
| SQLite + FTS5 + clean-text blobs | Local, exact, testable, simple operational model | Duplicates text across blob/chunk/FTS storage | Chosen |

## Decision history

- `2ba4373` (2026-06-08) bootstrapped the daemon with local capture/storage/search foundations.
- `39fced1` (2026-06-08) added capture dedupe and URL normalization tests.
- `a1ff667` (2026-06-09) documented the storage growth model.
- Current evidence: `daemon/src/browser_memory_daemon/schema.sql` defines documents, visits, snapshots, chunks, `chunks_fts`, media, audit, and deletion receipt tables.
- Current evidence: `daemon/src/browser_memory_daemon/ingest.py` writes clean text blobs, chunk rows, and FTS rows from captured text.
- Current evidence: `docs/storage-growth-model.md` estimates text/FTS growth and recommends storage observability before capture reduction.

## Consequences

- Positive: exact search, citations, detail views, timeline, doctor, and deletion all share one local data model.
- Positive: runtime state is visible and testable with ordinary SQLite/file tools.
- Positive: storage growth is manageable for normal-heavy browsing under the measured text-first model.
- Negative: text is stored multiple ways: clean blob, chunks, FTS shadow/content/index, and metadata tables.
- Negative: no semantic recall until a later embedding/vector decision is made.
- Neutral: media blobs can be large, but they are governed by separate bounded-cache semantics.

## Verification / validation

- Verification: `schema.sql` defines the SQLite tables and `chunks_fts` virtual table.
- Verification: `ingest.py` writes clean text blobs, chunks, FTS rows, document/visit/snapshot metadata, and dedupes snapshots by text hash.
- Verification: `docs/storage-growth-model.md` records measured DB/blob sizes, FTS duplication, and planning ranges.
- Verification: `daemon/tests/integration/test_ingest_search_forget.py` and `daemon/tests/e2e/test_http_api.py` cover ingest/search/delete behavior.
- Backfill hygiene verification passed on 2026-06-14: ADR lint, repo Markdown fence check, `git diff --check -- .`, `./scripts/secret-scan.sh`, and `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` using a temporary Python 3.11 shim.
- Validation: the system can answer exact recall queries locally without cloud services or semantic infrastructure.

## Revisit triggers

- Supersede this ADR if semantic/vector search becomes authoritative rather than additive.
- Supersede this ADR before storing full HTML or screenshots by default.
- Supersede this ADR if SQLite/FTS5 becomes the performance or scale bottleneck.
- Supersede this ADR if retention/export/backup changes require a materially different storage layout.

## Supersession

ADR-0021 keeps this ADR's text-first SQLite/FTS5 decision but replaces the fixed WSL-local blob placement with a configurable `BMD_BLOB_ROOT` that can point at a WSL-mounted NAS dataset.

## References

- `docs/architecture/adr/0021-use-configurable-nas-blob-root-with-local-sqlite.md`
- `docs/ARCHITECTURE.md#storage-model`
- `docs/storage-growth-model.md`
- `daemon/src/browser_memory_daemon/schema.sql`
- `daemon/src/browser_memory_daemon/ingest.py`
- `daemon/src/browser_memory_daemon/search.py`
- `daemon/src/browser_memory_daemon/config.py`
