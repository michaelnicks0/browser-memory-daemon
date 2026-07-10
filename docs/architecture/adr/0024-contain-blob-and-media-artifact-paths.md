---
id: ADR-0024
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes: []
superseded_by: []
related:
  - docs/security-model.md
  - docs/media-artifacts.md
  - daemon/src/browser_memory_daemon/storage_paths.py
  - daemon/src/browser_memory_daemon/ingest.py
  - daemon/src/browser_memory_daemon/media.py
  - daemon/src/browser_memory_daemon/ops.py
  - daemon/src/browser_memory_daemon/forget.py
verification:
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_ingest_search_forget.py daemon/tests/integration/test_media_worker.py daemon/tests/integration/test_visit_lifecycle.py daemon/tests/e2e/test_performance_benchmarks.py
---

# ADR-0024: Contain blob and media artifact paths

## Context

Browser Memory Daemon stores durable text blobs and disposable media sidecars under the configured blob root. SQLite rows also carry filesystem paths for snapshot clean text and stored media bytes.

Those paths are local evidence, not authority. They can become stale after migrations, can be edited by local tooling, and can be influenced by compatibility API lanes. Read, serve, purge, and forget paths therefore need to prove a DB-supplied path remains inside the current configured storage root before touching the filesystem.

## Decision

All blob/media filesystem operations shall resolve through a small storage-path boundary:

- clean-text writes construct paths from validated `snap_...` IDs under `config.clean_text_root`;
- media writes construct final filenames from a hashed storage stem under `config.media_root`, not directly from caller-controlled artifact IDs;
- media temp files live under `config.media_root/.tmp` and are atomically renamed into the same contained root;
- snapshot detail, document detail, media detail, media listing, cache purge, eviction, and forget/delete flows resolve DB paths against the configured root before reading, serving, or unlinking;
- out-of-root or invalid DB paths are treated as unavailable evidence and reported with status/counters rather than followed;
- blob-root migration still preserves relative paths when moving from the old default blob root to a new configured root.

## Decision drivers

- A local DB row must not make the daemon read, serve, purge, or delete arbitrary host files.
- Compatibility media APIs must not be able to choose filesystem filenames through artifact IDs or URL suffix tricks.
- The hardening must preserve the current SQLite schema and blob-root configuration; no replatforming or cloud storage.
- Existing operator workflows need diagnostic status for suspicious/stale paths rather than silent broad deletion.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Trust DB paths as-is | Minimal code | Lets stale/tampered rows point outside configured storage roots | Rejected |
| Store only relative paths in DB immediately | Cleaner long-term contract | Requires schema/data migration and wider compatibility surface | Deferred |
| Central contained-path resolver plus hashed media filenames | Small patch; no schema migration; closes read/serve/delete escape paths | Absolute paths remain in DB, but validated at use sites | Chosen |

## Consequences

- Positive: DB path tampering cannot make API reads or destructive cleanup touch files outside configured blob roots.
- Positive: media filenames no longer expose or depend on artifact IDs; uploaded/fetched blobs use deterministic hash-stem filenames under the media root.
- Positive: suspicious out-of-root paths appear in API/read-model status or deletion/purge counters.
- Neutral: SQLite schema is unchanged; stored `file_path` values remain absolute paths.
- Negative: older tests or tools that assumed `${artifact_id}.png` filenames must query `media_artifacts.file_path` instead.

## Verification / validation

- Verification: `daemon/tests/integration/test_ingest_search_forget.py` covers configured blob-root writes, path-contained snapshot/media reads, and forget refusing out-of-root clean/media DB paths.
- Verification: `daemon/tests/integration/test_media_worker.py` covers hashed media filenames, contained temp cleanup, and purge refusing out-of-root media DB paths.
- Verification: focused command passed: `BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_ingest_search_forget.py daemon/tests/integration/test_media_worker.py daemon/tests/integration/test_visit_lifecycle.py daemon/tests/e2e/test_performance_benchmarks.py`.

## Revisit triggers

- Supersede this ADR if a future schema migration stores blob paths as relative root-scoped paths instead of absolute paths.
- Revisit before adding alternate blob backends, remote object stores, symlink-following behavior, or UI affordances that expose raw filesystem paths.
- Revisit if blob-root migration starts deleting source files by default or crossing multiple configured roots.

## References

- `daemon/src/browser_memory_daemon/storage_paths.py`
- `daemon/src/browser_memory_daemon/media.py`
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/forget.py`
- `daemon/tests/integration/test_ingest_search_forget.py`
- `daemon/tests/integration/test_media_worker.py`
