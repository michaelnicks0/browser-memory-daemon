# Implement retention maintenance command

## Status
deferred-split

## Question

Can Browser Memory Daemon provide a local dry-run/execute maintenance command for WAL checkpointing, SQLite/FTS optimization, orphan sidecar audit, and optional compacted DB copy without dumping captured content or surprising the operator?

## Type

task

## Inputs / links

- `docs/retention-compaction-backup.md`
- `docs/architecture/adr/0019-use-durable-text-retention-with-wal-aware-local-backup.md`
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/cli.py`
- `daemon/src/browser_memory_daemon/db.py`
- `daemon/src/browser_memory_daemon/schema.sql`

## Blocks / blocked by

- Blocks: future automated retention/compaction operations and long-running maintenance gates.
- Blocked by: ticket 012 design; no longer blocked once ADR-0019 is accepted.

## Required coverage

- Dry-run report for DB file, WAL file, clean-text, media, and filesystem headroom sizes.
- `PRAGMA integrity_check` and FTS consistency check in the maintenance report.
- Optional `PRAGMA optimize` / FTS optimize path gated by `--execute`.
- WAL checkpoint path that does not manually delete `-wal`/`-shm` files.
- Optional compacted DB copy with explicit destination and enough-headroom guard.
- Orphan clean-text/media file audit with no raw captured text/URLs/tokens in output.

## Resolution

Deferred split from ticket 012; not part of the current durability/performance/coverage closeout unless explicitly promoted.

## New tickets / fog updates

Pending implementation.
