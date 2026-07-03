---
id: ADR-0015
status: accepted
date: 2026-07-03
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - docs/wayfinder/durability-performance-coverage/tickets/016-shorten-transaction-boundaries-and-idempotency.md
  - daemon/src/browser_memory_daemon/ingest.py
  - daemon/src/browser_memory_daemon/media.py
  - daemon/src/browser_memory_daemon/forget.py
  - daemon/src/browser_memory_daemon/policy_store.py
  - daemon/src/browser_memory_daemon/schema.sql
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_ingest_search_forget.py daemon/tests/integration/test_media_worker.py daemon/tests/unit/test_policy_store.py daemon/tests/unit/test_db.py daemon/tests/e2e/test_http_api.py
  - ./scripts/run-concurrency-stress.sh --captures 80 --reader-rounds 80 --media-worker-runs 24 --max-workers 64 --timeout 90 --no-fail
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
---

# ADR-0015: Use Idempotent Local Write Paths

## Context

Browser Memory Daemon has several local write paths that can repeat or overlap under normal daily-driver behavior: Chrome may send duplicate captures, media bytes can arrive through browser upload and daemon worker paths, operators can repeat policy-rule requests, and forget/cache operations touch both SQLite rows and WSL-local files.

ADR-0014 accepted SQLite WAL plus a bounded busy-timeout policy, but WAL does not remove SQLite's single-writer model. Avoidable duplicate inserts, check-then-insert races, or file I/O performed while a write transaction is open can still extend writer-lock duration or surface transient failures.

## Decision

We will keep SQLite/FTS5 and local filesystem storage, but make hot local write paths idempotent and keep filesystem byte work outside short SQLite write transactions where safe:

- captures stage clean-text files through unique temporary paths before the DB transaction and use `INSERT OR IGNORE` for deterministic snapshot/chunk IDs;
- FTS rows are inserted only when their owning chunk row is newly inserted, preventing duplicate FTS entries for repeated snapshot IDs;
- media blob writes continue to stage bytes before row updates, and cache purge/eviction/forget paths avoid unlinking files while holding broad write transactions;
- explicit local policy rules are unique by normalized `(rule_type, pattern, action)` and duplicate creates return the existing semantic rule.

## Decision drivers

- Duplicate captures should be safe and cheap: one document, many visits, one snapshot/chunk/FTS set for identical content.
- Browser uploads, daemon media workers, purge, and forget should not keep SQLite writer locks open during avoidable filesystem work.
- Explicit block rules are operator policy, so duplicate semantic rules should converge rather than create ambiguous rows.
- The fix should remain local, boring, and migration-safe for existing runtime databases.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Leave check-then-insert behavior | No migration | Duplicate/concurrent requests can create avoidable errors or duplicate policy rows | Rejected |
| Add deterministic idempotent writes and semantic uniqueness | Local, testable, preserves SQLite | Adds a migration/dedup step for old duplicate policy rules | Chosen |
| Introduce a server queue/write service | Stronger serialization model | Larger architecture change, unnecessary for current evidence | Rejected |

## Consequences

- Positive: repeated captures of the same URL/text snapshot converge without duplicate chunks or FTS rows.
- Positive: policy-rule creation is race-safe under concurrent duplicate requests.
- Positive: filesystem byte writes/unlinks are less likely to extend active SQLite writer locks.
- Neutral: clean-text files may be atomically refreshed for an existing deterministic snapshot ID; the bytes are identical for that ID because the ID includes the text hash.
- Neutral: existing duplicate policy rows are deduplicated during schema initialization before the unique index is created.
- Negative: if a post-commit filesystem unlink fails, a media/clean-text file can remain as an orphan under the local data root; retention/backup work should continue to account for orphan cleanup explicitly.

## Verification / validation

- Verification: `daemon/tests/integration/test_ingest_search_forget.py::test_concurrent_duplicate_capture_is_idempotent_for_snapshot_chunks_and_fts` covers concurrent duplicate capture convergence.
- Verification: `daemon/tests/unit/test_policy_store.py::test_policy_rule_creation_is_semantically_idempotent_under_concurrency` covers duplicate policy rule creation under concurrency.
- Verification: `daemon/tests/unit/test_policy_store.py::test_init_db_dedupes_existing_policy_rules_before_unique_index` covers migration-safe semantic uniqueness.
- Verification: `./scripts/run-concurrency-stress.sh --captures 80 --reader-rounds 80 --media-worker-runs 24 --max-workers 64 --timeout 90 --no-fail` passed with 80 captures, 264 mixed operations, SQLite `integrity_check=ok`, and 80 succeeded media tasks.
- Verification: `BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh` passed pytest, extension unit/build, real Chrome for Testing e2e, and secret scan gates.
- Validation: the daily-driver write model remains local SQLite/FTS5 plus XDG/WSL files while reducing avoidable writer-lock duration and duplicate-request failure modes.

## Revisit triggers

- Supersede this ADR if future retention/backup work changes deletion/orphan cleanup semantics.
- Supersede this ADR before introducing a dedicated queue service or replacing SQLite as the local write coordinator.

## References

- `docs/wayfinder/durability-performance-coverage/tickets/016-shorten-transaction-boundaries-and-idempotency.md`
- `docs/architecture/adr/0014-use-wal-and-bounded-sqlite-contention-policy.md`
