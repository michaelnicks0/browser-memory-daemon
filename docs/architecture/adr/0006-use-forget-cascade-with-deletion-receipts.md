---
id: ADR-0006
status: accepted
date: 2026-06-14
decision_date: 2026-06-08
decider: Operator
scope: repo
backfilled: true
supersedes: []
superseded_by: []
related:
  - docs/ARCHITECTURE.md
  - docs/security-model.md
  - docs/api.md
  - docs/DIAGRAMS.md
  - daemon/src/browser_memory_daemon/forget.py
  - daemon/src/browser_memory_daemon/schema.sql
  - daemon/tests/integration/test_ingest_search_forget.py
verification:
  - ADR lint + repo Markdown fence check
  - git diff --check -- .
  - ./scripts/secret-scan.sh
  - BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh with temporary Python 3.11 shim
---

# ADR-0006: Use Forget Cascade with Deletion Receipts

## Context

This ADR backfills a decision that existed before the ADR workflow was added.

A local personal-recall system that stores broad/all-mode browser memory needs a reliable operator-controlled deletion path. Deleting only search rows, only visible documents, or only blob files would leave inconsistent recall state. The system needs one deletion operation that removes matching memory from the DB, FTS index, text blobs, media blobs, lifecycle metadata, and related rows, then returns auditable counts.

## Decision

We will implement forget/delete as a physical cascade by domain or URL, with deletion receipts.

Forget operations identify documents by domain suffix or URL, remove related media blobs and rows, FTS rows, chunks, embeddings, feedback events, redaction rows, snapshots, clean-text blobs, visit events, visits, and documents, then insert a `deletion_receipts` row containing the scope and counts. UI/popup forget-domain calls require explicit browser confirmation; API/CLI calls return the receipt data.

## Decision drivers

- `all` mode intentionally captures broad/private pages, so post-hoc deletion must be dependable.
- Search, timeline, detail, lifecycle, media, and blob state must not diverge after deletion.
- The operator needs counts and a receipt ID to understand what was removed.
- Deletion should not depend only on database foreign keys because blob files and FTS rows need explicit handling.
- The current product does not need legal-hold/tombstone retention of deleted content.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Delete only documents and rely on cascading FKs | Simple DB operation | Does not handle FTS rows, files, media blobs, and receipt counts explicitly | Rejected |
| Tombstone deleted content but keep rows/files | Easier audit/history | Retains memory the operator intended to remove | Rejected |
| Physical delete with scope/count receipt | Removes recall artifacts and returns evidence of action | Receipt proves counts, not deleted content; implementation must stay synchronized with schema | Chosen |

## Decision history

- `2ba4373` (2026-06-08) bootstrapped the daemon with delete/forget as part of the core recall loop.
- `29410de` (2026-06-08) added local memory UI and ops APIs.
- Current evidence: `daemon/src/browser_memory_daemon/forget.py` performs explicit deletion across media, chunks, FTS, snapshots, blobs, visits, events, and documents, then inserts a deletion receipt.
- Current evidence: `daemon/src/browser_memory_daemon/schema.sql` defines `deletion_receipts`.
- Current evidence: `docs/DIAGRAMS.md` documents the forget/delete cascade.

## Consequences

- Positive: a domain/URL forget operation removes search-visible memory and associated blobs consistently.
- Positive: deletion receipts provide a durable record of scope and counts without keeping deleted content.
- Positive: the same behavior is available from API, CLI, UI, and extension controls.
- Negative: receipts are not a cryptographic proof that every external copy is gone; they are local action records.
- Negative: schema changes must update forget logic and tests or deletion can drift.
- Neutral: deletion is operator-commanded; no automatic retention/compaction policy is implied.

## Verification / validation

- Verification: `forget.py` deletes document-linked media blobs, media rows, chunks, FTS rows, redactions, clean-text blobs, snapshots, lifecycle events, visits, feedback, documents, and writes a receipt.
- Verification: `schema.sql` includes `deletion_receipts(scope_json, counts_json)`.
- Verification: `daemon/tests/integration/test_ingest_search_forget.py` covers forget by domain and URL, search absence after forget, media artifact deletion, and receipts.
- Verification: `docs/security-model.md` documents explicit confirmation before UI/popup forget-domain calls.
- Backfill hygiene verification passed on 2026-06-14: ADR lint, repo Markdown fence check, `git diff --check -- .`, `./scripts/secret-scan.sh`, and `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` using a temporary Python 3.11 shim.
- Validation: Operator can remove broad/all-mode captured memory after the fact without manually cleaning SQLite, FTS, and blob stores.

## Revisit triggers

- Supersede this ADR if retention/export/backup introduces legal-hold or tombstone requirements.
- Supersede this ADR if deletion scopes expand beyond domain/URL.
- Supersede this ADR if schema changes add new durable memory surfaces that need cascade coverage.
- Supersede this ADR if encrypted backups or external exports become part of normal operation.

## References

- `docs/ARCHITECTURE.md#storage-model`
- `docs/security-model.md`
- `docs/api.md`
- `docs/DIAGRAMS.md#8-forgetdelete-cascade`
- `daemon/src/browser_memory_daemon/forget.py`
- `daemon/src/browser_memory_daemon/schema.sql`
- `daemon/tests/integration/test_ingest_search_forget.py`
