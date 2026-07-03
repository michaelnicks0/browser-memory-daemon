---
id: ADR-0021
status: accepted
date: 2026-07-03
decider: Operator
scope: repo
backfilled: false
supersedes:
  - ADR-0004
superseded_by: []
related:
  - daemon/src/browser_memory_daemon/config.py
  - scripts/install-daily-driver.sh
  - docs/ARCHITECTURE.md
  - docs/daily-driver-deployment.md
  - docs/retention-compaction-backup.md
verification:
  - focused pytest for configurable blob root and migration
  - generated docs/check gates
  - live NAS dataset/mount smoke
---

# ADR-0021: Use configurable NAS blob root with local SQLite

## Context

ADR-0004 chose text-first SQLite/FTS5 with WSL-local blob files. That remains the right recall model, but browser-memory blob bytes now deserve a storage boundary separate from SQLite/WAL runtime files: media blobs are materially larger than text/FTS, clean-text blobs are easy filesystem payloads, and the NAS has encrypted ZFS capacity plus snapshot posture for local operator-owned storage.

The operator wants BMD blobs moved to the NAS while preserving the current retention posture: text/FTS remains durable by default, media bytes remain a bounded disposable cache, and forget continues to delete the live DB/blob state while historical backups/snapshots remain a separate lifecycle concern.

## Decision

We will keep SQLite, WAL/SHM, config, token/env, audit state, and systemd units under WSL XDG runtime paths, and make the blob root configurable with `BMD_BLOB_ROOT` / `--blob-root`.

`RuntimeConfig.clean_text_root`, `raw_html_root`, and `media_root` will resolve under `blob_root`. The default remains the old layout under `${data_root}/blobs`, so existing dev/test runtimes keep working. Daily-driver deployments may set `BMD_BLOB_ROOT` to a WSL-mounted NAS dataset; NFS is preferred when available, and SSHFS is acceptable for this blob-only path when WSL cannot kernel-mount the NAS export.

This ADR supersedes ADR-0004 only for the blob placement portion. It carries forward ADR-0004's text-first SQLite/FTS5 decision.

## Decision drivers

- SQLite/WAL behaves best on the local WSL filesystem; NAS latency and lock semantics are unnecessary risk for the DB.
- Blob files are append/read/delete filesystem payloads and are better suited to NAS placement.
- Media bytes already have bounded cache semantics; the cache caps should not change just because the backing filesystem moves.
- Clean-text blobs should stay in the same live forget/delete path as before.
- Runtime data must remain outside the Git repo and outside Chrome profile storage.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Move all BMD runtime data, including SQLite/WAL, to NAS | Single storage root | Adds DB latency/locking risk; WAL over network FS is a bad default | Rejected |
| Keep all blobs under WSL local disk | Simple, existing behavior | Consumes workstation storage; does not use NAS capacity | Rejected for daily driver |
| Add configurable blob root, keep SQLite local | Uses NAS for large payloads while preserving DB locality and test defaults | Requires mount/provisioning and DB path migration for existing blobs | Chosen |
| Split text blobs and media blobs into separate roots | More granular durability/cache placement | Extra config complexity before a proven need | Deferred |

## Consequences

- Positive: daily-driver blob growth moves off the WSL root filesystem without changing SQLite/FTS correctness.
- Positive: media cache gates, purge/rehydrate, and live forget semantics remain unchanged.
- Positive: tests can keep using temporary local roots while production points only blob files to the NAS.
- Negative: deployment now depends on the NAS mount being available before services start.
- Negative: existing absolute blob paths in the live DB need one-time migration if old files are physically moved.
- Neutral: NAS/ZFS snapshots are backup copies; they do not change live-store forget semantics.

## Verification / validation

- Verification: focused config/ingest/media tests prove `blob_root` can move independently from `data_root` while SQLite stays local.
- Verification: generated docs and static traceability gates must pass after the docs update.
- Verification: live deployment must prove the NAS dataset is mounted, writable by the daemon user, and visible in `/health`/daily-driver health as `blob_root`.
- Validation: a capture after migration writes clean-text/media blobs under the NAS mount, while search/detail still reads SQLite locally and forget deletes live blob files.

## Revisit triggers

- Supersede if SQLite itself needs NAS-backed storage or a different DB engine.
- Supersede if clean-text blobs and media cache need separate roots or separate ZFS datasets.
- Supersede if stronger backup erasure semantics require coordinated ZFS snapshot pruning on forget.

## References

- ADR-0004: `0004-use-text-first-sqlite-fts5-and-blob-storage.md`
- ADR-0005: `0005-use-durable-lazy-media-sidecars-with-bounded-cache.md`
- ADR-0019: `0019-use-durable-text-retention-with-wal-aware-local-backup.md`
- `docs/daily-driver-deployment.md`
- `daemon/src/browser_memory_daemon/config.py`
