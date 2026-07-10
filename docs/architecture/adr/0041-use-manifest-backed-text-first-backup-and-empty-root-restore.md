---
id: ADR-0041
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes: []
superseded_by: []
related:
  - ADR-0014
  - ADR-0019
  - ADR-0028
  - ADR-0038
  - ADR-0039
  - ADR-0040
implementation_status: implemented
implementation:
  - daemon/src/browser_memory_daemon/backup_ops.py
  - daemon/src/browser_memory_daemon/cli.py
  - daemon/tests/integration/test_backup_restore.py
verification:
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_backup_restore.py
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-fast-gate.sh
---

# ADR-0041: Use Manifest-Backed Text-First Backup and Empty-Root Restore

## Context

SQLite now contains complete cleaned snapshot text, capture provenance, FTS data, media metadata, deletion receipts, and blob lifecycle state. Media bytes remain a disposable cache and the local spool is outage buffering, not recall authority. The repository had an online backup helper only for destructive schema migrations; it did not provide a user-facing backup bundle, manifest, or restore drill.

A naked copy of a live WAL database is unsafe. A restore that overwrites an existing runtime is also too easy to misdirect. Backups must exclude tokens and high-volume disposable media by default while still proving search, detail, and forget from an empty destination.

## Decision

1. `backup create` and `backup restore` are dry-run by default and require explicit absolute local paths.
2. Execute backup rejects symlinked/out-of-root source databases, checks source inode identity around SQLite's online backup API, writes into a private `0700` sibling staging tree with `0600` files, verifies integrity/foreign keys/FTS relationships/complete text/schema compatibility, writes a redaction-safe manifest last, fsyncs, and atomically publishes the bundle with Linux no-replace semantics.
3. The default bundle contains the SQLite snapshot and `manifest.json` only. API tokens/config, Chrome profile/extension copy, media cache, and media spool are explicitly excluded.
4. `--include-derivatives` optionally copies only DB-referenced, root-contained, hash-verified clean-text compatibility sidecars. Orphans are not copied.
5. Every manifest file entry records a bundle-relative path, kind, byte size, and SHA-256. The manifest contains counts and compatibility metadata but no captured text, URLs, token values, or source runtime paths.
6. Restore accepts only a real manifest-backed bundle, rejects traversal, symlinks (including `manifest.json`), undeclared files, duplicate paths, malformed provenance/types, size/hash mismatches, unsupported kinds, unknown manifest formats, and manifest/database semantic disagreement.
7. Dry-run restore performs immutable read-only SQLite integrity, foreign-key, FTS relationship, authoritative-text, schema-version, and fingerprint checks without creating the destination. Execute restore requires an absent explicit destination, stages with private permissions under the destination parent, verifies copied bytes and the restored database, normalizes restored derivative locators, then atomically renames the staged runtime into place. It never overwrites or merges into an existing runtime.
8. Restored media bytes are absent by design. SQLite-authoritative search, snapshot detail, and forget must work without media cache or spool.
9. A backup predating forget can still contain forgotten content. Backup retention or erasure is a separate explicit operator action and is not implied by live-store forget.

## Consequences

### Positive

- Online backup captures committed WAL state without stopping the daemon or copying live sidecars.
- A small default bundle preserves complete text recall and provenance without NAS/media dependency.
- Hash manifests make accidental corruption detectable before restore mutation.
- Empty-root restore avoids clobbering a running or pre-existing installation.
- Optional derivatives remain evidence only; they do not become restore authority.

### Negative

- Bundles are integrity-manifested but not encrypted or cryptographically signed.
- Backup retention/pruning remains manual and approval-gated.
- Restored media rows may report missing bytes until media is rehydrated or reconciled.
- Restore creates a new runtime root but does not install services, tokens, or the Chrome extension.
- `SIGKILL`, power loss, or host failure can leave a hidden private `0700` staging directory; automatic stale-stage deletion is intentionally not attempted because it could race a concurrent operation. Inspect and remove stale stages explicitly.
- The Linux no-replace primitive prevents destination overwrite, but this local operator workflow does not claim protection from a hostile same-user process repeatedly replacing destination-parent namespace components during execution.

### Neutral

- Media cache and spool stay outside backups by default.
- The migration-only backup path remains separate because it has a different rollback scope.

## Verification

- Tests create an online backup while SQLite is in WAL mode and verify a manifest with no media or secrets.
- Restore tests prove integrity, foreign keys, FTS, complete text search/detail, and forget from a new runtime with no media root.
- Tamper tests reject a same-size SHA-256 mismatch before destination creation.
- Path tests reject relative, overlapping, and existing destinations plus traversal and symlinked bundles without publication.
- Corrupt/truncated and unknown-newer database tests fail after manifest verification and clean their staging directories.
- An injected restore interruption proves no partial destination is published and staging is removed.
- A publication-race test proves a destination appearing after preflight is preserved rather than overwritten.
- Optional derivative tests copy only referenced contained sidecars and exclude orphans.
- Adversarial manifest tests cover malformed JSON/root/provenance/types, unknown formats, unsupported kinds, duplicate/undeclared/missing files, and size/hash mismatch.
- Dry-run semantic tests reject manifest fingerprint disagreement, FTS missing rows, foreign-key violations, corrupt SQLite, and unknown-newer schemas before destination creation.
- Permission/source tests prove private output modes and rejection of symlinked or out-of-root source databases.
- Derivative tests require the declared set and hashes to match DB references and normalize legacy absolute references to relative locators on restore.
- Interruption tests cover caught I/O failure and `KeyboardInterrupt`; a post-publication parent-fsync failure reports explicitly that the destination exists and requires inspection.
- Populated exclusion fixtures prove config/state/media/spool files and fixture secret bytes do not enter the default bundle.
- CLI tests prove create/restore are dry-run first, execute both paths, dry-run create does not initialize a database, and restore cannot target the active runtime.

## Rollback

The slice is additive and repository-local. Roll back the backup module, CLI commands, tests, and docs together. Existing runtime databases and storage roots are unchanged. Bundles already created remain ordinary local directories and require explicit operator handling; rollback does not delete them.
