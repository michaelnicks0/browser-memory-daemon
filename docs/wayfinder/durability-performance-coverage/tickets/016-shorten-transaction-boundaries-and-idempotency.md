# Shorten transaction boundaries and capture idempotency

## Status
open

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

Pending.

## New tickets / fog updates

Pending. If transaction sequencing changes deletion, media retention, or backup expectations, inspect ADR-0004/ADR-0005/ADR-0014 and update or supersede docs as needed.
