# ADR-0046: Move historical media correction out of the worker loop

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0028, ADR-0042, ADR-0045, REQ-007, REQ-036

## Context

Every media-worker pass scanned broad artifact/task sets to reclassify historical failures, revive rows affected by older HLS capabilities or cache caps, label blob/CDP relationships, and close stale tasks. Most scans described software-upgrade history rather than steady-state work. They made an idle worker proportional to all historical media rows and could repeatedly revive unchanged terminal budget skips.

The migration kernel now provides ordered, checksummed, transactional data migrations. Operator mutation surfaces already use dry-run-first conventions.

## Decision

1. Migration version 12 performs the one-time historical media-state correction:
   - classify legacy terminal fetch failures;
   - reclassify unsupported legacy blob/video rows;
   - revive HLS video, audio-rendition, and CDP-manifest rows made eligible by later capabilities;
   - label historical blob references covered by stored CDP bytes or still opaque;
   - close stale tasks whose artifacts already have committed bytes.
2. Per-snapshot and domain/global cache-budget skips are not revived by migration or normal worker execution. They require `media-cache requeue`, an explicit scoped operator command that is dry-run by default and requires `--execute` to mutate rows/tasks.
3. Requeue scope must include a literal domain, document ID, or snapshot ID. Reason families are explicit (`snapshot-budget`, `storage-budget`, or `all-budget`) and execution is bounded by a limit.
   Executed requeues write a minimized durable audit event containing the reason, scope kinds, selected/updated counts, and limit but not scope values.
4. New blob-video references are labeled `opaque-browser-blob` at ingest rather than by a later full-table sweep.
5. Genuine current-state repair remains in `media_ops.py` as bounded reconciliation:
   - correlate recent unresolved/opaque blob-video refs with stored CDP bytes;
   - close a bounded batch of stale active tasks whose artifact bytes are already committed.
6. `media_worker.run_once` performs only those bounded repairs, leases due tasks, and processes the claimed batch. It no longer runs historical or budget requeue scans.

No live database migration or operator requeue is executed by this repository change.

## Consequences

### Positive

- Idle worker cost is bounded rather than proportional to historical artifact volume.
- Terminal budget skips converge to no work until the operator deliberately changes policy and requests a scoped retry.
- Historical correction is auditable and exactly-once through the migration ledger.
- New opaque blob rows are truthful immediately.

### Tradeoffs and deferred work

- Existing databases require migration 12 before startup is ready.
- Operators must choose a scope and execute requeue after raising relevant caps.
- Bounded CDP/task reconciliation may require several worker passes for a large real-time backlog.
- Database `CHECK` constraints and streamed/global resource budgets remain later Phase 4 work.

## Verification

- `daemon/tests/integration/test_migrations.py::test_version_twelve_normalizes_historical_media_state_once`
- `daemon/tests/integration/test_media_ops.py`
- `daemon/tests/integration/test_media_worker.py::test_media_worker_does_not_auto_requeue_terminal_budget_skips`
- `daemon/tests/integration/test_media_worker.py::test_media_worker_marks_blob_video_refs_covered_by_cdp_bytes`
- `daemon/tests/e2e/test_cli_admin.py::test_cli_media_requeue_defaults_to_scoped_dry_run`
