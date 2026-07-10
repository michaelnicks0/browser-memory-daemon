# Design retention, compaction, and backup posture

## Status
closed

## Question
What retention, compaction, export, and backup posture should Browser Memory Daemon adopt for long-term high-volume use while preserving local-first recall and deletion semantics?

## Type
research

## Inputs / links

- `docs/STATUS.md#pending-roadmap-lanes`
- `docs/ARCHITECTURE.md#storage-model`
- `docs/api.md#media-artifact-apis`
- `daemon/src/browser_memory_daemon/schema.sql`
- `daemon/src/browser_memory_daemon/forget.py`
- Baseline DB/media growth evidence from ticket 001
- ADR-0014 SQLite WAL sidecar policy (`*.sqlite3-wal`, `*.sqlite3-shm` are expected live runtime companions)

## Blocks / blocked by

- Blocks: retention implementation tickets and any backup/export feature.
- Blocked by: none. Ticket 001 provides current DB/media/headroom evidence; likely ADR-worthy.

## Resolution

Closed as a design/ADR slice, not a large retention implementation.

Accepted posture:

- text/FTS recall stays durable by default; no silent age-based full-text expiration in this queue;
- media rows/provenance stay durable while media bytes remain bounded disposable cache;
- backup/export must be local, manifest-backed, and WAL-aware (`memory.sqlite3` plus live sidecars as one unit unless using SQLite online backup / `VACUUM INTO`);
- maintenance/compaction must be dry-run-first and redaction-safe;
- forget deletes the live store and records receipts, but backups made before a forget can still contain forgotten data until backup retention/pruning removes them.

Durable outputs:

- `docs/retention-compaction-backup.md`
- ADR-0019: `docs/architecture/adr/0019-use-durable-text-retention-with-wal-aware-local-backup.md`

Evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
# 78 rendered docs match source

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_test_inventory.py --check
# 106 tests / 21 files

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_showcase.py --spec scripts/showcase.spec.json --check
# browser-memory-daemon-high-level-doc.html matches spec

./scripts/secret-scan.sh
# secret scan passed
```

## New tickets / fog updates

Split deferred implementation tickets:

- [017 — Implement retention maintenance command](017-retention-maintenance-command.md)
- [018 — Implement local backup/export command](018-local-backup-export-command.md) — closed 2026-07-10 under ADR-0041.

Ticket 017 remains a deferred follow-up. Ticket 018 was later promoted and closed under ADR-0041; this historical design ticket remains closed.
