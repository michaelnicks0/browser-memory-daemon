# Implement local backup/export command

## Status
deferred-split

## Question

Can Browser Memory Daemon create a local backup/export bundle with a manifest, consistent SQLite snapshot, optional blob inclusion, restore smoke checks, and honest forget/backups caveats?

## Type

task

## Inputs / links

- `docs/retention-compaction-backup.md`
- `docs/architecture/adr/0019-use-durable-text-retention-with-wal-aware-local-backup.md`
- `daemon/src/browser_memory_daemon/schema.sql`
- `daemon/src/browser_memory_daemon/forget.py`
- `docs/api.md#deletion-payloads`
- `docs/architecture/adr/0014-use-wal-and-bounded-sqlite-contention-policy.md`

## Blocks / blocked by

- Blocks: operator-managed backups, restore testing, and any later backup-retention/prune automation.
- Blocked by: ticket 012 design; no longer blocked once ADR-0019 is accepted.

## Required coverage

- Local-only backup/export destination; no remote upload or publishing.
- Consistent SQLite backup via online backup / `VACUUM INTO` or explicit quiesced copy mode.
- Manifest with counts, file sizes, hashes, created-at, policy mode, and include/exclude flags; no tokens/secrets/raw captured content.
- Include `blobs/clean-text/` by default; make `blobs/media/` optional and explicit.
- Exclude token/env/unit files and Windows extension artifact by default.
- Restore smoke against the exported DB: opens read-only and passes `PRAGMA integrity_check` plus FTS consistency.
- Docs and tests that state forget deletes the live store, not historical backups already created.

## Resolution

Deferred split from ticket 012; not part of the current durability/performance/coverage closeout unless explicitly promoted.

## New tickets / fog updates

Pending implementation.
