# Shorten transaction boundaries and capture idempotency

## Status
closed

## Question
Can capture, media-blob, forget/purge, and policy-rule write paths be made shorter and idempotent enough that filesystem work or duplicate requests do not hold SQLite writer locks longer than necessary or surface avoidable uniqueness/contention failures?

## Type
task

## Inputs / links

- Subagent audit `deleg_26f18a8a`, 2026-07-02
- `daemon/src/browser_memory_daemon/ingest.py`
- `daemon/src/browser_memory_daemon/media.py`
- `daemon/src/browser_memory_daemon/forget.py`
- `daemon/src/browser_memory_daemon/policy_store.py`
- `daemon/src/browser_memory_daemon/schema.sql`
- `daemon/tests/e2e/test_concurrency_stress.py`
- `docs/architecture/adr/0014-use-wal-and-bounded-sqlite-contention-policy.md`

## Blocks / blocked by

- Blocks: sustained high-volume capture durability and cleaner future retention/backup work.
- Blocked by: none. Ticket 004's stress harness and WAL policy are available; ticket 009's benchmark harness would improve sizing evidence but is not required for a first idempotency slice.

## Scope notes from late ticket-004 audit

- File I/O occurs inside or adjacent to write transactions in capture/text blob staging, media blob budget/eviction paths, purge/forget loops, and related DB updates.
- Capture duplicate/idempotency handling still has check-then-insert edges around snapshots/chunks/FTS rows.
- Policy-rule creation can create concurrent duplicates because `privacy_rules` has no uniqueness guard over rule semantics.
- Ticket 004 already fixed same-artifact media temp-path collisions; this ticket should avoid reopening that slice unless tests expose a related class.

## Candidate verification

- Add focused duplicate-capture/concurrent-capture tests that exercise the same URL/text/snapshot under parallel requests.
- Add policy-rule duplicate tests and schema/UPSERT behavior if uniqueness is introduced.
- Extend `./scripts/run-concurrency-stress.sh` or add a focused harness mode if the fix changes capture/forget/media side-effect sequencing.
- Run `BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh` after implementation.

## Resolution

Closed in this slice. The durable write paths now converge duplicate work and avoid broad file I/O while active SQLite writer transactions are open:

- Capture writes stage clean-text files through unique temporary paths before the DB transaction, insert deterministic snapshot/chunk rows with `INSERT OR IGNORE`, and only add FTS rows when their owning chunk was newly inserted.
- Concurrent duplicate captures for the same normalized URL/text now produce one document, one snapshot, one chunk, one FTS row, and one visit per request.
- Media cache eviction/purge and forget now collect filesystem candidates separately from DB row updates so unlink work is not performed inside broad writer transactions.
- Policy rules now enforce semantic uniqueness on `(rule_type, normalized pattern, action)` with a migration-safe duplicate cleanup before creating `idx_privacy_rules_semantics`; concurrent duplicate creates return the same existing rule.
- ADR-0015 records the schema/write-path decision and its orphan-cleanup revisit trigger.

Evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_ingest_search_forget.py daemon/tests/integration/test_media_worker.py daemon/tests/unit/test_policy_store.py daemon/tests/unit/test_db.py daemon/tests/e2e/test_http_api.py
# 48 passed

./scripts/run-concurrency-stress.sh --captures 80 --reader-rounds 80 --media-worker-runs 24 --max-workers 64 --timeout 90 --no-fail
# ok=true; captures 80/80; mixed 264/264; integrity_check=ok; media_task_statuses={"succeeded": 80}

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
# pytest passed; extension node:test 23/23; extension build; real Chrome for Testing e2e ok; secret scan passed
```

## New tickets / fog updates

No new ticket from this slice. ADR-0015 explicitly leaves orphan cleanup/retention semantics as a revisit trigger for ticket 012 rather than expanding ticket 016 into retention implementation.
