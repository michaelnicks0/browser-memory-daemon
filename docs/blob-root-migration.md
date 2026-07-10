# Blob-Root Migration

> **Status:** Current helper documented; live migration remains approval-gated.
> **Authority:** `daemon/src/browser_memory_daemon/blob_migration.py` and `blob-root migrate` in `cli.py`.
> **Scope:** Move DB-referenced clean-text and media blob files while keeping SQLite/WAL local.

---

## Current contract

`blob-root migrate` plans relocation only for DB-referenced paths beneath the selected source root and under the recognized `clean-text/`, `raw-html/`, or `media/` subtrees. The configured `BMD_BLOB_ROOT` is the target. The command is a dry run unless `--execute` is supplied.

```bash
PYTHONPATH=daemon/src BMD_BLOB_ROOT=/explicit/target/blobs \
  python3.11 -m browser_memory_daemon blob-root migrate
```

The summary reports planned, copied, already-present, missing-source, updated, source-removal, and error counts. Dry-run does not copy files, rewrite SQLite paths, or remove source bytes.

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

- Existing target files are treated as present; this helper does not yet compare hashes or content.
- SQLite path updates occur after copy attempts, but the filesystem copies and DB transaction are not one crash-consistent transaction.
- `--remove-source` unlinks after DB updates and is not tombstone/reconciliation-backed.
- The helper stores absolute paths; root-relative BlobStore locators arrive in the planned storage phase.
- It is not the versioned database migration kernel planned for Phase 1.2.

These limitations are why the default remains dry-run and why `--remove-source` is a separate explicit flag.

## Hermetic verification

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python
"$BMD_PYTHON" -m pytest -q \
  daemon/tests/integration/test_ingest_search_forget.py \
  -k blob_root_migration
```

The test uses temporary runtime/blob roots and does not touch the daily-driver database, user blob root, or NAS.
