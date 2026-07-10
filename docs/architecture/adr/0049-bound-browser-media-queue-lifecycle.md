# ADR-0049: Bound the browser media task and blob lifecycle

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0005, ADR-0015, ADR-0048, REQ-037

## Context

The extension already used a dedicated IndexedDB database for media tasks and fetched blobs, but task batches were inserted through separate transactions, fetched blobs and task states changed separately, task count and aggregate blob bytes were unbounded, and terminal upload failures could retain blobs indefinitely. MV3 suspension could therefore leave compensatable intermediate states, but quota exhaustion and terminal cleanup were not explicit or observable.

Media bytes are intentionally separate from the capture/lifecycle outbox. Combining them would couple ordinary text-delivery durability to much larger disposable browser blobs and would weaken the strongest text-first invariant.

## Decision

1. Upgrade the dedicated `browser-memory-media-v1` IndexedDB schema ledger to version 2 while retaining the existing task and blob stores and stable artifact IDs. Add a `byte_size` blob index; the first accounting transaction cursor-backfills pre-version-2 rows one at a time.
2. Admit all media tasks produced by one accepted capture in one read/write transaction. Enforce a 500-task limit against newly introduced artifact IDs. If the batch cannot fit, write none of it and leave the checkpointed capture outbox row retryable.
3. Admit a fetched blob and move its existing task to `pending-upload` in one transaction spanning both stores. Require the task to exist before blob admission.
4. Enforce a 250,000,000-byte per-blob limit and a 512 MiB aggregate fetched-blob limit. Sum indexed size keys without materializing all blob bodies, and subtract the prior blob before checking a replacement's projected total. A rejected blob leaves both the existing blob and task state unchanged.
5. Delete a media task and its fetched blob in one transaction after daemon acceptance or a daemon-terminal disposition.
6. Keep terminal local failures in a 24-hour quarantine so operators can inspect aggregate status. Each media drain removes at most 50 expired terminal task/blob pairs in one transaction. Fresh terminal rows are never selected.
7. Recover interrupted `fetching` and `uploading` rows through the existing two-minute stale-processing rule. Media drain remains bounded and runs on the existing alarm/startup/event paths.
8. Expose only redaction-safe media task counts, status counts, blob count/bytes, quotas, and terminal TTL through the existing popup/options telemetry contract. Do not expose source or page URLs.

No live extension install, Chrome-profile mutation, daemon restart, or daily-driver migration is part of this repository change.

## Consequences

### Positive

- A capture's media-task compensation cannot be partially admitted at the task-count boundary.
- Blob bytes and task state cannot disagree across the fetch-to-upload transition.
- Concurrent admissions serialize through IndexedDB and cannot oversubscribe configured count or byte limits.
- Terminal upload failures no longer retain browser blobs indefinitely.
- Capture text remains accepted independently by the daemon; media quota pressure remains asynchronous and retryable.

### Tradeoffs

- Task quota checks scan at most 500 metadata rows. Blob accounting scans only indexed numeric size keys after the one-time legacy-row cursor backfill, avoiding whole-blob telemetry reads.
- Failed rows and blobs intentionally consume quota for up to 24 hours to preserve a quarantine window.
- Browser media bytes remain disposable and profile-local; daemon SQLite remains the provenance authority.
- Whole-response browser fetch buffering remains a separate resource-usage concern. The per-item cap bounds it but does not turn Chrome's Fetch response into a streaming API.

## Verification

- `extension/tests/unit/media_queue.test.js::media task batch admission is atomic and preserves existing work at count quota`
- `extension/tests/unit/media_queue.test.js::media blob admission atomically applies replacement-aware byte quota and task transition`
- `extension/tests/unit/media_queue.test.js::terminal media quarantine cleanup retains fresh rows and atomically removes expired task and blob`
- `extension/tests/unit/service_worker.test.js::capture result checkpoint survives suspension without reposting before media enqueue compensation`
- `extension/tests/unit/service_worker.test.js::service worker cleans expired terminal media while capture is paused or tokenless`
- `extension/tests/unit/service_worker.test.js::service worker media upload retries keep fetched blob until successful upload`
- Isolated Chrome for Testing verifies the actual version-2 IndexedDB path, media fetch/upload, empty terminal queues after success, and redaction-safe quota telemetry.
