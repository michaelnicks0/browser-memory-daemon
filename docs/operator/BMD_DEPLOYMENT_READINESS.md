# Packet A — BMD Deployment Readiness

**Status:** source ready; live deployment held at `APPROVAL-BMD-STAGED-DEPLOYMENT`

**Source branch:** `integration/x-observation-export`

**Contract:** `bmd.x-observations` v1

## Preflight runtime truth

The 2026-07-11 read-only preflight established that repository source and live deployment are different states:

| Signal | Observed live state |
|---|---|
| Daemon and worker | active, long-running processes started before current source hardening |
| Daily-driver check | exited successfully but warned that installed extension/service source was older than repository source |
| Live SQLite | `pragma user_version=0`; no `schema_migrations` table |
| Live logical integrity | `pragma integrity_check=ok` |
| Live row-count fingerprint | metadata only; no row bodies inspected |
| Isolated HermesXCDP profile | profile exists; no BMD extension setting was present in `Default/Preferences` |

Do not describe the live runtime as schema 14 or contract-v1 capable until this packet completes.

## Source pins

| Item | Pin |
|---|---|
| Contract/ADR | ADR-0060 / `67f2822b7ab6a31d180d9aaa0a7fa80e06e88ea9` |
| Observation ingest sequence | `c389f94` |
| Query-only export | `8136149` |
| Current schema head | 14 |
| Requirement | REQ-044 |

## Readiness checks — no deployment

Run from the BMD repository using the Python 3.11 verification environment:

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  ./scripts/run-fast-gate.sh
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  ./scripts/run-e2e.sh
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  ./scripts/run-concurrency-stress.sh
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  ./scripts/run-performance-gate.sh
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh --dry-run
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh --check
```

The source gate must remain green. `--check` may continue to report deployment drift before the approved install; that warning is the reason this packet exists.

## Backup and baseline — approval required before execution

1. Stop if Michael has not explicitly approved `APPROVAL-BMD-STAGED-DEPLOYMENT`.
2. Record body-safe service state and installed-source hashes. Do not print tokens, environment contents, URLs, page titles, or database rows.
3. Create and verify a manifest-backed SQLite backup bundle with the repository CLI before migration.
4. Record:
   - SQLite file/WAL-aware backup checksum;
   - `pragma integrity_check` result;
   - `pragma user_version`;
   - migration-ledger presence/count;
   - metadata-only table counts;
   - installed extension file hashes;
   - daemon/worker unit hashes and active state.
5. Preserve the prior unpacked extension directory, token/env files, unit files, and absence markers used by installer rollback.

## Staged deployment

Only after the backup verifies:

```bash
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

The installer must stage and swap source atomically, migrate through schema 14, restart daemon then worker, and pass its readiness checks. If any step fails, treat rollback as incomplete until all prior artifacts are restored **and prior daemon/worker service state is verified**, not merely until files copy back.

## Extension load/reload checklist

1. Confirm the intended ordinary BMD Chrome profile—not the dedicated HermesXCDP backfill profile—is selected.
2. Confirm the unpacked extension path is the staged installed path.
3. Reload the extension once.
4. Verify the installed `service_worker.js`, `cdp_session.js`, manifest, and module hashes match source.
5. Verify extension health/queue telemetry is body-safe and no queue regression appears.
6. Do not load the BMD writer extension into the backfill-owned HermesXCDP profile.

## Post-deploy verification

1. Verify daemon and worker are active with expected executable/unit provenance.
2. Verify SQLite:
   - `pragma user_version=14`;
   - migration ledger contains exactly versions 1–14 with expected names/checksums;
   - schema fingerprint matches migration 14;
   - `pragma integrity_check=ok`;
   - every capture observation has one ingest-sequence row.
3. Verify query-only export against the existing database:

   ```bash
   memory export x-observations --limit 1
   ```

4. Confirm the export does not change logical table counts, audit-event count, schema, migration ledger, or database checksum snapshot.
5. Verify authenticated loopback `GET /exports/x-observations?limit=1` returns the same contract major and remains unauthorized without the bearer token.
6. Rerun `install-daily-driver.sh --check`; no source-drift warning may remain.
7. Run the consumer cross-repository gate from `birdclaw-x-backfill`.

## Rollback triggers

Rollback immediately if any of these occur:

- service readiness failure;
- migration ledger/fingerprint mismatch;
- integrity failure;
- missing observation ingest sequence;
- extension source hash mismatch;
- export writes an audit row or changes logical/database state;
- export contract major mismatch;
- daemon/worker cannot return to the expected service state.

Rollback restores the verified pre-deploy SQLite backup and prior extension/token/env/unit artifacts. Verify prior daemon and worker state after restoration. If prior service restart fails, leave the system stopped, preserve diagnostics, and report an incomplete rollback—do not continue forward.

## Approval boundary

Approval for this packet authorizes staged BMD deployment/readiness verification only. It does not authorize live X backfill capture or Birdclaw apply. After Packet A passes, the next bounded action is one read-only 25-row `bmd-pull` pilot under Packet B.
