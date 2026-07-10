# Implement local backup/export command

## Status
closed — implemented 2026-07-10

## Question

Can Browser Memory Daemon create a local backup/export bundle with a manifest, consistent SQLite snapshot, optional blob inclusion, restore smoke checks, and honest forget/backups caveats?

## Type

task

## Inputs / links

- `docs/retention-compaction-backup.md`
- `docs/architecture/adr/0019-use-durable-text-retention-with-wal-aware-local-backup.md`
- `docs/architecture/adr/0041-use-manifest-backed-text-first-backup-and-empty-root-restore.md`
- `daemon/src/browser_memory_daemon/backup_ops.py`
- `daemon/tests/integration/test_backup_restore.py`
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
- Include SQLite-authoritative complete text by default; make referenced clean-text compatibility derivatives optional.
- Exclude disposable media and spool bytes. ADR-0041 intentionally tightens the older ticket's optional-media wording to the adopted backup boundary.
- Exclude token/env/unit files and Windows extension artifact by default.
- Restore smoke against the exported DB: opens read-only and passes `PRAGMA integrity_check` plus FTS consistency.
- Docs and tests that state forget deletes the live store, not historical backups already created.

## Resolution

Implemented as a promoted hardening slice under ADR-0041:

- `backup create` and `backup restore` are dry-run first and require explicit absolute local paths;
- SQLite online backup captures committed WAL state into a staged, hash-manifested bundle;
- tokens/config, Chrome state, media cache, and media spool are excluded;
- optional derivatives are DB-referenced, root-contained, deduplicated, and hash-verified;
- restore rejects traversal, symlinks, undeclared files, tampering, truncation, unknown-newer schemas, active-root overlap, and existing destinations;
- Linux no-replace publication and injected interruption tests prove no partial or raced destination overwrite;
- restored search, snapshot detail/provenance, and forget work without media bytes.

Focused evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_backup_restore.py
```

## New tickets / fog updates

Backup retention/pruning, encryption/signing, and automatic compaction remain separate approval-gated work. Ticket 017 remains open for retention maintenance.
