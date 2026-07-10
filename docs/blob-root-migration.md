# Blob-Root Migration

> **Status:** Current helper documented; live migration remains approval-gated.
> **Authority:** `daemon/src/browser_memory_daemon/blob_migration.py` and `blob-root migrate` in `cli.py`.
> **Scope:** Move DB-referenced legacy clean-text sidecars and media blob files while keeping SQLite/WAL complete-text authority local.

---

## Current contract

`blob-root migrate` plans relocation only for DB-referenced paths beneath the selected source root and under the recognized `clean-text/` or `media/` subtrees. Version-9 and later captures create no clean-text sidecar, so clean-text plans apply only to legacy rows. Clean text targets `BMD_DERIVATIVE_ROOT/clean-text`; final-tier media targets `BMD_MEDIA_ROOT`. Spool-tier rows are excluded because `media-spool drain` owns that transition. The command is a dry run unless `--execute` is supplied.

```bash
PYTHONPATH=daemon/src \
BMD_DERIVATIVE_ROOT=/explicit/local/derivatives \
BMD_MEDIA_ROOT=/explicit/target/media \
  python3.11 -m browser_memory_daemon blob-root migrate
```

The summary reports planned, copied, already-present, missing-source, updated, source-removal, and error counts. Dry-run does not copy files, rewrite SQLite paths, or remove source bytes. Executed copies stream through the contained `BlobStore`, verify expected byte count and SHA-256 before publication, and atomically commit the target. A pre-existing target is adopted only when the same evidence verifies it.

## Execute boundary

Repository verification must use temporary fixture roots only. A live DB migration, external mount mutation, or deletion of source bytes requires separate explicit operator approval.

When approved for a real deployment, the minimum sequence is:

1. stop capture and media-worker writes;
2. create and verify a SQLite online backup;
3. verify target mount availability, free space, and expected storage identity;
4. run the command without `--execute` and review every count/path boundary;
5. run with `--execute` but without `--remove-source`;
6. verify DB integrity, FTS reads, snapshot detail, media reads, and service health against the target;
7. retain the prior copy until an explicit later cleanup approval.

## Current limitations

- SQLite path updates occur after copy attempts, but the filesystem copies and DB transaction are not one crash-consistent transaction.
- `--remove-source` unlinks after DB updates and is not tombstone/reconciliation-backed.
- Successful DB rewrites populate both the target absolute compatibility path and the locator relative to the target clean-text or media root. Historical rows not selected by this operator migration retain their existing nullable relative-locator state.
- It is an operator blob-layout migration, not a versioned SQLite schema migration.

These limitations are why the default remains dry-run and why `--remove-source` is a separate explicit flag.

## Hermetic verification

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python
"$BMD_PYTHON" -m pytest -q \
  daemon/tests/integration/test_ingest_search_forget.py \
  -k blob_root_migration
```

The test uses temporary runtime/blob roots and does not touch the daily-driver database, user blob root, or NAS.
