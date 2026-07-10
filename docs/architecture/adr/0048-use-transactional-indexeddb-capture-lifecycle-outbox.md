# ADR-0048: Use a transactional IndexedDB outbox for capture and lifecycle delivery

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0015, ADR-0029, ADR-0035, REQ-003, REQ-037

## Context

The MV3 service worker persisted capture and lifecycle work as whole arrays in `chrome.storage.local`. Concurrent read-modify-write operations could overwrite one another, count caps were enforced by slicing, and worker suspension could interrupt delivery without an atomic claim/ack transition. The overflow characterization proved that 100 accepted captures were preserved only by silently dropping the next capture.

Capture delivery also spans two durable systems: the daemon capture request and the browser media-task queue. If suspension occurs after the daemon accepts a capture but before its media tasks are queued, an uncheckpointed retry can repost the capture and still fail to compensate the browser-side media work.

## Decision

1. Add `outbox.js` as a versioned IndexedDB boundary for ordinary capture and lifecycle messages. Keep media tasks and blobs in the specialized `media_queue.js` database; do not force binary media and ordinary messages into one generic queue.
2. Store each outbox message as an independent row with an auto-incrementing sequence ID, kind, payload, state, claim token/time, attempt count, due time, last error, enqueue/update timestamps, and UTF-8 serialized payload bytes.
3. Enqueue, claim, checkpoint, acknowledge, retry, and stale-claim recovery run in IndexedDB read/write transactions. Claims are token-checked; a different worker instance cannot acknowledge or retry work it does not own. Successful acknowledgement records last-success metadata in the same transaction that deletes the row.
4. Drain at most 25 messages of each kind per invocation. Startup, install, and the one-minute `bmd-outbox-drain` alarm resume due work after MV3 suspension. Failed work receives bounded exponential backoff.
5. Persist a daemon capture result in the claimed outbox row before creating browser media tasks. A retry after media-queue failure reuses the checkpoint and does not repost the accepted capture. The daemon's stable observation identity remains the final idempotency boundary if suspension occurs between the HTTP response and the IndexedDB checkpoint.
6. Import the legacy `captureQueue` and `visitEventQueue` arrays and an import marker in one IndexedDB transaction. Delete the legacy Chrome-storage keys only after that transaction commits. Stable observation/event IDs, with a SHA-256 payload fallback for older rows, deduplicate repeated startup after interruption while still importing new legacy-array rows authored during a one-version rollback.
7. Keep the legacy Chrome-storage path as a one-version failure fallback when IndexedDB is unavailable. The fallback no longer slices arrays: over-capacity writes fail visibly and preserve already queued entries.
8. Enforce the existing 100-capture and 200-lifecycle item limits plus 32 MiB capture and 2 MiB lifecycle serialized-payload limits. Reject new over-capacity work visibly and expose redaction-safe count, byte, age, claim, overflow, quota, and last-success telemetry through the popup and options page.
9. Outbox telemetry contains aggregate kind/count/bytes/attempt/error state only. It does not copy captured text or URLs into ordinary telemetry records.

No live extension install, Chrome-profile mutation, daemon restart, or daily-driver migration is performed by this repository change.

## Consequences

### Positive

- Accepted capture and lifecycle rows no longer share a racy whole-array write.
- Existing rows survive capacity exhaustion; a new over-capacity message is explicitly rejected instead of silently truncated.
- Claims recover after service-worker suspension and cannot be acknowledged by a stale token.
- Capture-result checkpointing closes the daemon-accepted/media-enqueue compensation gap.
- Legacy queues migrate without a delete-before-import loss window.

### Tradeoffs and deferred work

- IndexedDB transactions provide browser-profile-local durability, not cross-profile replication.
- A crash after daemon acceptance but before capture-result checkpointing can retry the HTTP request. Stable observation IDs make that retry idempotent at the daemon.
- `REQ-037` remains planned until specialized media queue byte/count quota and terminal cleanup/quarantine behavior close; lifecycle compaction remains deferred rather than silently changing event semantics.
- Rolling back to the prior extension build does not delete IndexedDB rows, but that build cannot drain them; restoring this or a later build resumes delivery and idempotently imports any new legacy-array rows authored during the rollback.
- The temporary Chrome-storage fallback remains for one compatibility version and must be removed only after real-browser migration evidence is established.

## Verification

- `extension/tests/unit/outbox.test.js::concurrent enqueue preserves existing captures and visibly rejects only new work at capacity`
- `extension/tests/unit/outbox.test.js::claim, retry, due time, and acknowledgement are token-checked atomic transitions`
- `extension/tests/unit/outbox.test.js::stale claims recover after service-worker suspension without becoming concurrently claimable`
- `extension/tests/unit/outbox.test.js::legacy queue import is marked atomically and is idempotent before chrome storage cleanup`
- `extension/tests/unit/outbox.test.js::serialized byte accounting uses UTF-8 payload bytes and survives claim metadata changes`
- `extension/tests/unit/outbox.test.js::serialized byte quota rejects only the new row and reports required bytes`
- `extension/tests/unit/service_worker.test.js::service worker preserves queued captures while daemon is down and drains them after reload`
- `extension/tests/unit/service_worker.test.js::service worker queue overflow preserves old captures and visibly rejects the new capture`
- `extension/tests/unit/service_worker.test.js::service worker enforces byte quota and exposes redaction-safe outbox telemetry`
- `extension/tests/unit/service_worker.test.js::service worker transactionally imports and drains the legacy lifecycle queue before deleting it`
- `extension/tests/unit/service_worker.test.js::capture result checkpoint survives suspension without reposting before media enqueue compensation`
- Isolated Chrome for Testing remains the system authority for the actual IndexedDB implementation and service-worker lifecycle.
