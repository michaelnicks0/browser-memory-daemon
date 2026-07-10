---
title: "Database Migrations"
description: "Versioned SQLite migration, compatibility, backup, and rollback contract"
audience: "operator"
status: "current"
version: "1.0.0"
date: "2026-07-10"
---

# Database Migrations

Browser Memory Daemon keeps SQLite local and authoritative. Schema evolution is controlled by an ordered migration ledger rather than recurring `CREATE IF NOT EXISTS` and historical repair work at request time.

## Safety boundary

- `memory migrate --check` is read-only. It does not create the database, directories, ledger rows, or backups.
- `memory migrate --execute` is the explicit operator path for pending migrations.
- Normal startup applies only pending **non-destructive** migrations. A future destructive migration fails startup before that step and requires explicit `migrate --execute`.
- A destructive step requires disk-headroom preflight and a verified SQLite online backup before its first write.
- There are no destructive down-migrations. Rollback means the prior application plus the pre-migration backup.
- Database migration does not move SQLite to NAS and does not touch media/blob roots.

Do not run these commands against the daily-driver database during repository verification. Use an explicit temporary runtime and blob root.

## Commands

Global options precede the command:

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python

"$BMD_PYTHON" -m browser_memory_daemon \
  --runtime-root /tmp/bmd-migration-check/runtime \
  --blob-root /tmp/bmd-migration-check/blobs \
  --token fixture-token \
  migrate --check
```

Execute pending steps only after reviewing the JSON report:

```bash
"$BMD_PYTHON" -m browser_memory_daemon \
  --runtime-root /tmp/bmd-migration-check/runtime \
  --blob-root /tmp/bmd-migration-check/blobs \
  --token fixture-token \
  migrate --execute
```

Exit codes:

| Code | Meaning |
|---:|---|
| `0` | Database is current, or execution completed and the database is current. |
| `1` | Compatibility, checksum, fingerprint, backup, headroom, or execution failure. |
| `2` | Check succeeded, the database is compatible, and migrations remain pending. |

## Current ordered ledger

| Version | Name | Role |
|---:|---|---|
| `1` | `baseline_current_schema` | Immutable validated baseline. An existing unversioned database is stamped only when its normalized SQLite schema fingerprint exactly matches version 1. |
| `2` | `normalize_baseline_reference_data` | Ensures the built-in Chrome source row and performs one-time privacy-rule deduplication formerly embedded in steady-state `schema.sql`. |
| `3` | `seed_daemon_public_media_fetch_tasks` | One-time historical task seeding formerly run by every `init_db` call. |
| `4` | `add_capture_observations_and_url_claims` | Additive capture-observation and untrusted URL-claim tables with a new exact schema fingerprint; no backfill or read cutover. |
| `5` | `backfill_historical_capture_observations_and_url_claims` | One-time evidence-bounded backfill: inferred observations only from stored snapshot/visit links, ambiguous observations when no visit survives, and historical canonical-authority claims without speculative splits. |

Each `schema_migrations` row stores version, unique name, SHA-256 checksum, and applied timestamp. `PRAGMA user_version` must match the highest contiguous ledger version. Unknown-newer versions, gaps, name drift, checksum drift, and schema-fingerprint drift fail closed.

The version-1 SQL is frozen in `daemon/src/browser_memory_daemon/migration_steps/v0001_baseline_schema.sql`; its declared fingerprint and loader live beside it in `v0001_baseline_schema.py`. Future schema changes add ordered steps; they do not rewrite version 1.

## Backup and rollback

Before a destructive step, the migration kernel:

1. measures the SQLite DB plus WAL/SHM footprint;
2. requires bounded free-space headroom;
3. writes an online backup under the configured state root's `migration-backups/` directory;
4. runs `PRAGMA integrity_check` and `PRAGMA foreign_key_check` against the backup;
5. starts the destructive step only after those checks pass.

If a step fails, that step's transaction and ledger row roll back. The failure reports the backup path when one was created. Restore is deliberately not automatic: stop writers, preserve the failed database for diagnosis, restore the backup to an explicit destination, run integrity/FTS/application smoke checks, and use the prior compatible application version.

## Repository verification

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python
"$BMD_PYTHON" -m pytest -q daemon/tests/integration/test_migrations.py
```

The fixture suite covers fresh initialization, exact unversioned detection, repeated and concurrent no-op/application behavior, checksum and unknown-newer rejection, injected rollback, FTS/foreign-key/integrity checks, destructive headroom refusal, online backup, restore-backed search, a version-3-to-4 expand upgrade, observation/claim constraints, and version-5 evidence-bounded historical backfill.
