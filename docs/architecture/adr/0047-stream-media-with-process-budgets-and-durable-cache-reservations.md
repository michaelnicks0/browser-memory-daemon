# ADR-0047: Stream media with process budgets and durable cache reservations

- Status: accepted
- Date: 2026-07-10
- Amended: 2026-07-10 after late adversarial transport review
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0014, ADR-0039, ADR-0043, ADR-0044, ADR-0045, ADR-0046, REQ-032, REQ-035, REQ-036, REQ-040

## Context

Media paths still accumulated complete artifacts in memory at several daemon boundaries. HTTP uploads and downloads, guarded public fetch, HLS assembly, and artifact publication could each create another complete copy. Per-artifact size limits did not bound aggregate memory or simultaneous network requests. Cache admission also read committed byte totals before publication without reserving capacity, so concurrent daemon and worker processes could each admit candidates against the same apparent headroom.

Task callers could claim a batch before processing its first item. A task lease could therefore age while earlier tasks waited for process capacity or network deadlines. These failures must remain independent from the already-committed searchable text transaction.

## Decision

1. Media byte paths stream through bounded binary streams:
   - known-length raw HTTP uploads stream directly into contained `BlobStore` staging through a reader capped at 64 KiB per read; legacy internal callers without a known length retain a bounded `SpooledTemporaryFile` compatibility path;
   - stored media responses stream from `BlobStore.open` in bounded 64 KiB chunks, verify the emitted length against the advertised length, and stop without a second response when the client disconnects;
   - guarded HTTP responses write incrementally to a supplied stream;
   - HLS variants, init maps, and segments append to the same bounded output stream while retaining one aggregate HLS request/byte/depth/deadline budget;
   - artifact publication stages from a binary stream and verifies the expected size before SQLite publication.
2. The compatibility JSON `content_base64` input remains accepted and bounded by request/artifact limits. New daemon worker and raw-upload paths do not create an internal base64 copy.
3. `BMD_MAX_MEDIA_INFLIGHT_BYTES` and `BMD_MAX_MEDIA_CONCURRENT_REQUESTS` define a process-wide condition-backed resource budget. The byte cap must be at least one configured maximum artifact; both values must be positive.
4. Public fetch reserves one maximum-artifact byte lease for the transfer and one request slot for each guarded HTTP hop. Raw upload and stored-media response routes hold leases for their known transfer size. Every lease releases on success, ordinary failure, timeout, or cancellation-like `BaseException`.
5. Process budgets deliberately coordinate threads within one daemon or worker process. They are not represented as a cross-process semaphore. Cross-process cache-cap correctness instead uses SQLite migration version 13 and `media_cache_reservations`:
   - reservation acquisition starts an immediate transaction and counts committed plus active reserved bytes for snapshot, domain, and global caps;
   - a successful publication replaces the reservation with the committed artifact row in the same SQLite transaction;
   - failed staging/publication explicitly releases the reservation;
   - each reservation records its owner PID and Linux process-start token; the next admission refreshes an expired reservation while that exact process remains live and removes it only after the owner is gone.
6. Manual fetch and the long-running worker claim one task immediately before processing it rather than holding a preclaimed batch behind earlier work.
7. Process-capacity exhaustion is classified as `media-resource-budget` and remains retryable. It never rolls back or weakens the prior local SQLite text/provenance commit.
8. Queue status exposes only aggregate configured/current request and byte counters; it exposes no captured content, URL, or storage path.
9. `media_transport.py` coordinates direct-versus-HLS classification without creating a fetch/HLS module cycle. Potential HLS video transport creates its aggregate request budget before the initial open, caps path/MIME playlists before body consumption, applies bounded magic-prefix sniffing to disguised playlists, and enforces the shared deadline before and after every response-body read.

No live database migration, service restart, media-root write, or daily-driver install is performed by this repository change.

## Consequences

### Positive

- Peak daemon memory and simultaneous request count are bounded by explicit process-level caps instead of multiplying the per-artifact cap across threads and buffering layers.
- HLS streaming retains the existing aggregate SSRF, redirect, byte, request, depth, and deadline controls.
- Concurrent cache admission across daemon and worker processes cannot commit combined stored plus reserved bytes beyond configured snapshot/domain/global caps.
- Failed or cancelled publication releases both process and durable capacity while preserving a prior committed replacement blob.
- Task leases start close to real work and do not age behind an already-claimed local batch.
- Searchable text remains available when media capacity is exhausted.

### Tradeoffs and deferred work

- SQLite cache reservations coordinate capacity, not active network concurrency; separate processes can each use their configured process budget. Operators must size service-level caps with that boundary in mind.
- A hard process crash after filesystem publication but before SQLite commit can leave a contained orphan. Existing storage reconciliation detects that orphan; the durable capacity reservation expires.
- Compatibility callers may still submit bounded base64 JSON and Chrome/CDP APIs may originate base64 data. Removing those browser/API compatibility boundaries belongs to later extension/HTTP contract work.
- Stable typed HTTP errors and request IDs remain Phase 6 work; overload currently preserves the compatible top-level `error` shape with HTTP 503.

## Verification

- `daemon/tests/unit/test_media_resources.py`
- `daemon/tests/unit/test_media_hls.py::test_hls_assembly_streams_segments_without_joining_whole_artifact`
- `daemon/tests/unit/test_media_worker_claiming.py`
- `daemon/tests/integration/test_media_storage.py::test_cache_reservations_serialize_concurrent_global_admission`
- `daemon/tests/integration/test_media_storage.py::test_cache_reservation_blocks_publication_until_released_and_expired_rows_are_reclaimed`
- `daemon/tests/integration/test_media_storage.py::test_cancellation_like_stage_failure_releases_spool_and_cache_reservations`
- `daemon/tests/integration/test_media_worker.py::test_media_resource_pressure_does_not_roll_back_searchable_text`
- `daemon/tests/integration/test_media_worker.py::test_guarded_hls_initial_redirect_claims_total_request_budget`
- `daemon/tests/integration/test_media_worker.py::test_guarded_fetch_enforces_deadline_during_slow_response_body`
- `daemon/tests/integration/test_media_worker.py::test_guarded_hls_enforces_initial_playlist_byte_budget`
- `daemon/tests/integration/test_migrations.py::test_version_thirteen_adds_cache_reservations_from_exact_prior_schema`
- `daemon/tests/e2e/test_http_api.py::test_http_upload_get_and_purge_use_bounded_spool_during_media_root_outage`
- `daemon/tests/e2e/test_http_api.py::test_http_raw_media_upload_returns_503_when_global_byte_budget_cannot_admit_body`
- `daemon/tests/e2e/test_http_api.py::test_http_raw_media_upload_disconnect_cleans_staging_reservations_and_process_budget`
- `daemon/tests/e2e/test_http_api.py::test_http_media_download_disconnect_stops_stream_and_releases_process_budget`
- `daemon/tests/integration/test_ingest_search_forget.py::test_raw_blob_upload_streams_without_whole_artifact_spool_and_rejects_truncated_body`
- `daemon/tests/unit/test_http_server.py`
- `daemon/tests/e2e/test_concurrency_stress.py::test_concurrency_stress_harness_exercises_shared_sqlite_db`
