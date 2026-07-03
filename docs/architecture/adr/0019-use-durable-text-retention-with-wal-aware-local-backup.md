---
id: ADR-0019
status: accepted
date: 2026-07-03
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - docs/retention-compaction-backup.md
  - docs/wayfinder/durability-performance-coverage/tickets/012-retention-compaction-backup-design.md
  - docs/architecture/adr/0014-use-wal-and-bounded-sqlite-contention-policy.md
  - docs/architecture/adr/0018-enforce-daily-driver-headroom-and-start-budgets.md
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
  - /tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_test_inventory.py --check
  - /tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_showcase.py --spec scripts/showcase.spec.json --check
  - ./scripts/secret-scan.sh
---

# ADR-0019: Use durable text retention with WAL-aware local backup and disposable media cache

## Context

Browser Memory Daemon stores daily-driver browser recall in WSL-owned SQLite/FTS5 plus clean-text and media blob sidecars. Ticket 001 showed the live DB/text store was modest relative to host headroom, while media blobs were materially larger and a prior no-space/service-start failure class had already occurred. ADR-0014 made WAL sidecars expected runtime companions, and ADR-0018 added explicit storage headroom and service-start health budgets.

The remaining design question is how to preserve high-value local recall while adding retention, compaction, export, and backup posture that future agents can implement without breaking forget semantics or copying inconsistent SQLite state.

## Decision

We will use this storage posture:

1. **Durable text by default:** keep documents, visits, lifecycle events, snapshots, chunks, FTS rows, audit rows, and deletion receipts indefinitely unless the operator explicitly enables a narrower retention policy later.
2. **Disposable media cache:** keep media refs/provenance durable but treat media blob bytes as bounded cache managed by existing/future purge and rehydration controls.
3. **WAL-aware backups:** backup/export must use SQLite online backup / `VACUUM INTO` or a quiesced copy that respects `memory.sqlite3`, `memory.sqlite3-wal`, and `memory.sqlite3-shm` as one live unit.
4. **Dry-run-first maintenance:** retention, compaction, checkpoint, orphan audit, and backup/export tools must produce redaction-safe dry-run output before destructive or large-copy execution.
5. **Forget/live-store boundary:** forget deletes current live DB/blob state and records receipts; backups made before forget may still contain forgotten data until backup retention/pruning removes them.

## Decision drivers

- Preserve the daily-driver maximum-recall posture and avoid surprising silent text expiration.
- Avoid reintroducing the storage/start-failure class captured in ticket 001.
- Keep every storage operation local, boring, and inspectable.
- Make SQLite WAL handling explicit before backup/export implementation.
- Prevent future docs/API from overstating forget semantics across historical backups.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Auto-delete old text by default | Controls growth aggressively. | Violates maximum-recall default and could erase useful history silently. | Rejected for default posture. |
| Keep all DB/text forever, bound only media bytes | Preserves recall; matches current DB/media evidence. | DB can still grow and needs later maintenance/export. | Chosen. |
| Treat media blobs as durable backup-required data | Maximizes binary completeness. | Media dominates storage and is intentionally cache-like today. | Rejected by default; optional backup inclusion is allowed. |
| Raw-copy live SQLite files without WAL rules | Easy to script. | Can create inconsistent backups or miss WAL contents. | Rejected. |
| Online backup / `VACUUM INTO` or quiesced WAL-aware copy | Consistent and local. | Requires implementation care and restore smokes. | Chosen. |

## Consequences

- Positive: high-value text/FTS recall remains stable by default.
- Positive: media growth stays governed by cache gates rather than backup expectations.
- Positive: future backup/export work has an explicit include/exclude boundary and restore contract.
- Positive: forget semantics are honest about live store versus historical backups.
- Negative: default text retention still requires monitoring and future maintenance tooling as volume grows.
- Neutral: this ADR does not implement maintenance/export commands; it splits them into follow-up tickets.

## Verification / validation

- Verification: `docs/retention-compaction-backup.md` records requirements, backup boundaries, WAL handling, forget interaction, and split follow-up tickets.
- Verification: generated docs and repository hygiene checks must pass in the ticket 012 commit.
- Validation: the design uses ticket 001/009/015 evidence to prioritize media cache bounding and WAL-aware backup before adding any automatic text expiration.

## Revisit triggers

- Supersede if DB/text growth becomes the dominant storage pressure and the operator approves age/domain/profile retention.
- Supersede if backup/export must satisfy stronger legal deletion semantics across historical backups.
- Supersede if SQLite/FTS5/WAL is replaced.
- Revisit after implementing backup/export and observing restore-smoke evidence.

## References

- `docs/retention-compaction-backup.md`
- `docs/wayfinder/durability-performance-coverage/tickets/012-retention-compaction-backup-design.md`
- `docs/wayfinder/durability-performance-coverage/tickets/001-baseline-failure-budget.md`
- `docs/architecture/adr/0014-use-wal-and-bounded-sqlite-contention-policy.md`
- `docs/architecture/adr/0018-enforce-daily-driver-headroom-and-start-budgets.md`
