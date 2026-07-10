---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0028: Use versioned restore-backed SQLite migrations

## Context and problem statement

The daemon treated `schema.sql` as a recurring startup script. `migrations.py` was only an alias for `init_db`, schema version was implicit, historical privacy-rule deduplication ran inside `schema.sql`, and unresolved media-task seeding could scan and write on every initialization. There was no durable version/checksum ledger, no exact unversioned-schema compatibility test, and no backup gate for future destructive changes.

Phase 2 capture-model work requires explicit expand/backfill/cutover steps. Continuing with recurring `CREATE IF NOT EXISTS` and repair DML would make partial upgrades, checksum drift, and rollback ambiguous.

## Decision drivers

- Keep SQLite/WAL/FTS5 local and authoritative.
- Preserve fresh-install and existing-database compatibility without speculative schema acceptance.
- Make migration application ordered, idempotent, auditable, and fault-injectable.
- Refuse unknown-newer or locally modified migration histories.
- Require recoverability before destructive schema/data changes.
- Keep normal request handling free of historical full-table repair work.

## Considered options

### Continue idempotent `schema.sql` at startup

Rejected. It has no ordered history, cannot distinguish an unknown schema, and turns historical repairs into recurring runtime work.

### Adopt an ORM or third-party migration framework

Rejected. It adds a new framework boundary without solving the repository's local-first backup and exact-fingerprint requirements better than a small standard-library kernel.

### Use an ordered standard-library migration ledger

Accepted. The schema is small, migration ownership is local, and explicit SQLite transactions/backups fit the operating model.

## Decision outcome

The daemon uses `schema_migrations(version, name, checksum, applied_at)` plus matching `PRAGMA user_version`.

- Version 1 freezes the validated current schema and its normalized SQLite schema fingerprint.
- An existing unversioned database is stamped as version 1 only when that fingerprint matches exactly.
- Versions are contiguous and names/checksums are immutable.
- Unknown-newer versions, gaps, checksum/name drift, and fingerprint drift fail closed.
- Version 2 owns baseline source seeding plus the one-time privacy-rule deduplication formerly in `schema.sql`.
- Version 3 owns historical daemon-public media-task seeding formerly in `init_db`.
- Each step owns one `BEGIN IMMEDIATE` transaction and advances its ledger row and `user_version` together.
- Startup may apply non-destructive pending steps. Destructive steps require explicit `memory migrate --execute`.
- Before a destructive step, the kernel requires free-space headroom, creates an SQLite online backup, and verifies integrity and foreign keys.
- Down-migrations are not provided. Rollback uses the prior application and the verified pre-migration backup.

The version-1 baseline is immutable. Future DDL migrations declare the expected post-step schema fingerprint; data-only steps inherit the most recent declared fingerprint.

## Consequences

### Positive

- Every supported database has an explicit, inspectable version.
- Existing current databases have a narrow compatibility path instead of heuristic stamping.
- Migration history drift is detectable before application work begins.
- Historical repair scans run once rather than on every request/worker initialization.
- Destructive changes have a mandatory backup and headroom boundary.
- Fixture tests can inject failure at a numbered step and verify rollback/restore.

### Negative

- New schema changes must add immutable migration steps and checksums.
- A locally modified or unknown schema must be investigated rather than auto-repaired.
- Backup files contain authoritative private text and require the same local protection as the database.
- Startup can refuse service when a destructive or incompatible migration is pending; this is intentional fail-closed behavior.

## Validation

- `daemon/tests/integration/test_migrations.py`
- `daemon/tests/e2e/test_cli_admin.py`
- `daemon/tests/e2e/test_http_api.py`
- `daemon/tests/integration/test_media_worker.py`
- `BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh`

No live daily-driver database migration, service restart, NAS mutation, or install is part of this decision's repository implementation.
