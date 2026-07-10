# Retention, Compaction, Export, and Backup Posture

> **Audience:** operator and future agents.
> **Status:** accepted design posture; implementation is split into follow-up tickets.
> **Scope:** Browser Memory Daemon WSL-owned runtime data, SQLite/FTS5/WAL sidecars, local derivatives, guarded media root, bounded local media spool, backup/export boundaries, and forget/deletion semantics.

---

## Bottom line

Browser Memory Daemon should preserve text/FTS recall by default and treat media bytes as a bounded disposable cache. Backups must be local, explicit, manifest-backed, and WAL-aware. Forget deletes the current live store; any backup made before the forget can still contain forgotten data until backup retention/pruning removes it.

This design does **not** add automatic age-based deletion yet. That would be a separate operator-approved retention policy because the daily-driver default is maximum local recall.

ADR-0028 implements a narrower migration-only SQLite online backup gate before destructive schema steps. That backup excludes blob roots and is not the full manifest-backed backup/export command described here.

---

## Mission / ConOps

Browser Memory Daemon exists to provide local-first browser recall from Windows Chrome with durable WSL storage and a configurable WSL-visible blob root. Long-term operation needs enough storage hygiene to avoid SQLite/media growth surprises without undermining recall or deletion receipts.

Operational sequence:

1. Chrome and the daemon keep writing visits, snapshots, FTS chunks, audit rows, lifecycle events, media refs, and bounded media blobs.
2. Health checks expose headroom, DB/WAL/blob/media sizes, and worker churn without dumping captured content.
3. A future maintenance command performs dry-run-first checkpoint/optimize/audit/optional-compaction work under local runtime paths.
4. A future backup/export command creates a local bundle or snapshot with a manifest and explicit inclusion/exclusion choices.
5. Forget remains a live-store deletion operation; backup lifecycle must be documented and eventually automatable separately.

---

## Evidence baseline

| Evidence | Current fact |
|---|---|
| Ticket 001 live baseline | DB ~350.74 MiB, clean text ~22.46 MiB, media blobs ~11.54 GiB, WAL 0 bytes at probe time, WSL `/` had ~477 GiB free. The blob root is now separately configurable for NAS placement. |
| Ticket 009 synthetic benchmark | Machine-readable benchmark reports DB/WAL/media sidecar size output and advisory budgets. |
| Ticket 015 health budget | Daily-driver health now reports storage `headroom.status`, systemd restart budgets, and service-start failure budgets. |
| ADR-0014 | SQLite WAL sidecars (`*.sqlite3-wal`, `*.sqlite3-shm`) are expected live companions, not junk files. |
| Current forget path | Deletes DB rows, FTS rows, clean-text files, media rows/files for the live store, then records a deletion receipt. |

---

## Requirements

| Requirement | Statement | Verification / evidence |
|---|---|---|
| RCB-001 | Full text/FTS recall remains durable by default unless the operator explicitly enables a narrower retention policy. | ADR-0019; no automatic text expiration in this design. |
| RCB-002 | Media blobs remain a bounded, disposable cache while media refs/provenance remain durable. | ADR-0005 and current media cache gates. |
| RCB-003 | SQLite backup/compaction handling must respect WAL sidecars and avoid copying an inconsistent live database. | ADR-0014; future backup command ticket. |
| RCB-004 | Maintenance/export tools must be local-only and redaction-safe by default. | Future tickets require dry-run/manifest tests and secret scan. |
| RCB-005 | Forget semantics must distinguish live-store deletion from historical backup copies. | This doc and ADR-0019; future backup retention ticket. |
| RCB-006 | Any destructive retention, purge, compaction, or backup-prune action must have dry-run output before execute. | Follow-up implementation tickets. |

---

## Recommended posture

### 1. Default retention

- Keep `documents`, `visits`, `visit_events`, `snapshots`, `chunks`, `chunks_fts`, `audit_events`, and `deletion_receipts` indefinitely by default.
- Do not add an automatic age-based full-text retention job in this design slice.
- Later policy can add explicit operator-selected scopes such as domain, age, profile, or media-only retention, but default local recall stays complete.

Rationale: `policy_mode=all` is an intentional maximum-recall posture. Silent text expiration would surprise the operator more than growth, especially while DB size is still modest relative to host headroom.

### 2. Media bytes

- Preserve media rows, hashes, statuses, and provenance as durable evidence alongside snapshots.
- Continue treating final media blobs under `BMD_MEDIA_ROOT` as a cache bounded by artifact/snapshot/domain/global gates. A configured local spool is durable outage buffering under its own strict byte cap, not backup authority.
- Prefer purge/rehydrate over permanent media metadata deletion.
- Keep OCR/media-derived indexing out of this design; it belongs to a later media-enrichment lane.

### 3. SQLite WAL and checkpoint handling

- `memory.sqlite3`, `memory.sqlite3-wal`, and `memory.sqlite3-shm` are one live SQLite unit while services are running.
- Do **not** delete `-wal` or `-shm` files manually.
- For a consistent local backup, prefer one of:
  - SQLite online backup API / `VACUUM INTO` to a backup DB path; or
  - stop/quiesce daemon + worker services, copy `memory.sqlite3` plus live sidecars if present, then restart.
- Maintenance may run `PRAGMA wal_checkpoint(PASSIVE)` online. `TRUNCATE` checkpoint or `VACUUM` should be maintenance-window work with enough free space and no competing writers.

### 4. Compaction / maintenance

Future maintenance command should be dry-run-first and local-only:

1. report DB file, WAL file, clean-text, media, and filesystem headroom sizes;
2. run/read `PRAGMA integrity_check` and FTS consistency checks;
3. optionally run `PRAGMA optimize` and FTS optimize;
4. checkpoint WAL safely;
5. audit orphaned clean-text/media files and missing blob paths;
6. optionally produce a compacted DB copy with `VACUUM INTO` when headroom is sufficient;
7. never dump captured text, raw URLs, tokens, or cookies in logs.

### 5. Backup/export boundaries

A complete local backup/export should include:

| Artifact | Include by default? | Notes |
|---|---:|---|
| SQLite DB snapshot | ✅ | Use online backup / quiesced copy, not a naked live DB copy. |
| SQLite WAL/SHM sidecars | Conditional | Include only for raw quiesced/live filesystem snapshots; not needed for `VACUUM INTO` / online backup output. |
| `${BMD_DERIVATIVE_ROOT}/clean-text/` | Optional | Reconstructible legacy sidecars; complete cleaned text is authoritative in SQLite. |
| `BMD_MEDIA_ROOT` | ❌ | Large disposable cache; exclude by default. Refs, hashes, status, and provenance remain in SQLite. |
| `BMD_MEDIA_SPOOL_ROOT` | ❌ | Transient durable outage buffer; drain or reconcile separately rather than treating it as backup authority. |
| Manifest JSON | ✅ | Counts, byte sizes, created-at, repo/version, policy mode, hashes for files copied. No secrets. |
| Token/env/unit files | ❌ by default | Sensitive and reinstallable. Back up only through an explicit secrets-aware operator path. |
| Windows extension copy | ❌ | Rebuild/copy from repo plus token/env; do not treat as durable memory. |
| Chrome profile | ❌ | Out of scope; tests must not mutate/copy the daily-driver profile. |

Export is not a publishing workflow. It stays on local filesystem paths unless the operator explicitly approves a destination.

### 6. Forget and backups

Current forget guarantees live-store deletion from:

- DB rows and FTS rows;
- clean-text files referenced by deleted snapshots;
- media artifact rows and local media files;
- deletion receipt recording.

Backups are different. A backup created before a forget may still contain the forgotten data. Therefore:

- forget responses and docs should not imply retroactive backup erasure;
- backup bundles need timestamps/manifests so the operator can identify pre-forget copies;
- a future backup retention/prune path should allow deleting old local backup bundles after sensitive forgets;
- if legal/operational semantics ever require backup erasure, that is a separate hard requirement and likely a new ADR.

---

## V-model traceability

| Requirement | Logical component | Future implementation unit | Verification gate |
|---|---|---|---|
| RCB-001 | Retention policy | Retention config + dry-run sweep report | Unit/e2e proving default keeps text; explicit sweep requires `--execute`. |
| RCB-002 | Media cache | Existing media purge/rehydrate controls | Existing media tests plus future orphan audit. |
| RCB-003 | WAL-aware backup | Backup/export command | Test online backup while WAL exists; restore opens with `integrity_check=ok`. |
| RCB-004 | Redaction-safe maintenance | Maintenance report serializer | Golden tests asserting no raw captured text/URLs/tokens. |
| RCB-005 | Forget/backup boundary | Docs + manifest metadata | Forget test plus backup manifest timestamp/prune tests. |
| RCB-006 | Dry-run before destructive work | CLI/API command guards | CLI tests for no mutation in dry-run and mutation only with `--execute`. |

---

## Split follow-up tickets

This design intentionally stops before implementation. Follow-ups:

- `017-retention-maintenance-command.md` — dry-run/execute maintenance command for checkpoint/optimize/orphan audit/optional compacted copy.
- `018-local-backup-export-command.md` — local backup/export bundle with manifest, restore smoke, and backup/forget caveats.

These are split follow-ups, not blockers for closing the current durability/performance/coverage queue.

---

## Revisit triggers

Revisit this posture if:

- DB/text growth becomes the dominant headroom pressure rather than media cache growth;
- a retention policy becomes operator-approved for age/domain/profile scopes;
- backups need to satisfy stronger deletion/legal erasure semantics;
- Browser Memory moves away from SQLite/FTS5/WAL;
- media OCR/captioning adds new derived-data stores.
