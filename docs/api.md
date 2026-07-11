# Browser Memory Daemon API

> **Audience:** API callers, UI/CLI maintainers, extension maintainers.
> **Boundary:** authenticated loopback API for Windows Chrome → WSL recall.
> **Default policy:** `all`.

---

## Auth and boundary

- Default bind: `http://127.0.0.1:8765`.
- `/health` is public loopback. `/ui` HTML is public loopback, rejects non-loopback `Host` headers, and includes an inline JSON bootstrap with the current daemon token for same-origin dashboard use; static JS/CSS assets do not include the token.
- Every memory, policy, deletion, and diagnostic API requires:

```http
Authorization: Bearer ***
```

Captured page text is untrusted evidence. API clients must not treat retrieved page text as executable instructions.

Every response carries a server-generated `X-Request-ID`. Error responses repeat it as `request_id` while retaining the compatible top-level `error` string and stable machine-readable `error_code`:

```json
{"error": "unauthorized", "error_code": "unauthorized", "request_id": "req_<opaque>"}
```

Missing or invalid bearer tokens return `401`; malformed JSON and invalid payloads return `400`; identity/integrity conflicts return `409`; unknown routes return `404`; database/resource availability failures return `503`; unexpected internal failures return a sanitized `500`; unsupported HTTP methods return `501`. Limit parameters are bounded server-side (`recent` max 100, `timeline` max 250, media queue max 200); invalid integer limits return `400` on endpoints that parse limits directly. Current stable codes are `invalid_request`, `unauthorized`, `forbidden`, `not_found`, `conflict`, `resource_unavailable`, `database_busy`, `database_unavailable`, `internal_error`, and `unsupported_method`.

JSON requests accept at most one unsigned-decimal `Content-Length` and reject duplicate, signed, malformed, oversized, or truncated lengths before invoking an application use case. JSON body limits are 2 MiB for ordinary capture/lifecycle/policy/admin requests and 16 MiB for the compatibility base64 media artifact route. Raw media uploads require one explicit unsigned-decimal length and stream separately under artifact and process budgets.

JSON, UI/static, binary, error, and OPTIONS responses share a no-store security envelope with content-type, frame, referrer, permissions, and content-security protections. Ordinary request telemetry is one compact journald JSON event containing only request ID, method, descriptor route name, status, integer latency, and safe error code; paths, queries, URLs, headers, tokens, bodies, and exception prose are excluded.

---

## Endpoint index

The method/path entries below are matched through immutable route descriptors in `routes.py`; UI assets remain a separate finite static-file boundary. Descriptor precedence keeps exact routes such as queue status ahead of parameterized artifact routes without changing endpoint behavior.

`http_server.py` owns bearer authentication, request parsing, response serialization, security headers, telemetry, static UI serving, and bounded stream transport. It invokes explicit request-independent methods in `application.py`, which owns database transaction/audit boundaries, capture policy decisions, reads, forget, policy administration, media coordination, and resource leases. `app.py` only initializes and composes those boundaries; this separation does not change any endpoint contract.

| Endpoint | Method | Purpose | Auth |
|---|---:|---|---|
| `/health` | `GET` | Minimal daemon status and current policy mode. | No |
| `/ui` | `GET` | Local web UI HTML with same-origin token bootstrap. Static `/ui/*.js`/`*.css` assets remain token-free. | No for UI shell; API calls require token |
| `/ready` | `GET` | Initialize/check DB readiness. | Yes |
| `/capture` | `POST` | Store an allowed extension capture plus media references. | Yes |
| `/media-artifacts` | `POST` | Compatibility JSON store/upgrade for related media row and optional base64 blob. | Yes |
| `/media-artifacts/{artifact_id}/blob` | `PUT` | Raw binary blob upload from browser lazy media sidecar. | Yes |
| `/media-artifacts/fetch-pending` | `POST` | Daemon-side fetch of pending public media artifact refs. | Yes |
| `/media-artifacts/queue-status?limit=...` | `GET` | Media artifact/task queue health and cache-gate status. | Yes |
| `/media-artifacts/purge-cache` | `POST` | Dry-run or execute media blob cache purge, optionally rehydrate. | Yes |
| `/visit-events` | `POST` | Store tab lifecycle events and update visit dwell seconds. | Yes |
| `/search?q=...&limit=...` | `GET` | Exact FTS search with source metadata/snippets. | Yes |
| `/recent?limit=...` | `GET` | Recent capture metadata and first snippets. | Yes |
| `/timeline?date=YYYY-MM-DD` | `GET` | Capture timeline for a day. | Yes |
| `/timeline?after=...&before=...` | `GET` | Capture timeline for an explicit ISO range. | Yes |
| `/documents/{document_id}` | `GET` | Document metadata, visits, lifecycle events, snapshots, chunks. | Yes |
| `/snapshots/{snapshot_id}` | `GET` | Snapshot text, chunk snippets, and related media artifacts. | Yes |
| `/media-artifacts/{artifact_id}` | `GET` | Retrieve stored media blob if present. | Yes |
| `/policy/rules` | `GET` | List local policy rules. | Yes |
| `/policy/rules` | `POST` | Add block-domain or block-URL-prefix rule. | Yes |
| `/policy/rules/{rule_id}` | `DELETE` | Delete a policy rule. | Yes |
| `/policy/evaluate?url=...` | `GET` | Explain static + local capture decision. | Yes |
| `/forget` | `POST` | Forget by URL or domain and return a deletion receipt. | Yes |
| `/doctor[?storage_census=full]` | `GET` | DB integrity, FTS consistency, runtime paths, blob lifecycle/pending deletion health, media queue, and fast DB-derived storage counts; optional filesystem census walks blob roots. | Yes |

---

## Health response

```json
{
  "ok": true,
  "version": "0.1.0",
  "storage_root": "/home/<user>/.local/share/browser-memory-daemon",
  "blob_root": "/mnt/nas/browser-memory-daemon/blobs",
  "derivative_root": "/home/<user>/.local/share/browser-memory-daemon/derivatives",
  "media_root": "/mnt/nas/browser-memory-daemon/media",
  "media_spool_enabled": true,
  "media_root_status": "ready",
  "capture_enabled": true,
  "policy_mode": "all"
}
```

---

## Doctor response

`/doctor` is the fast authenticated diagnostic endpoint. By default it reports storage counts from SQLite metadata so routine checks do not recursively walk large clean-text/media roots:

```http
GET /doctor
Authorization: Bearer ***
```

```json
{
  "ok": true,
  "database": {"integrity_check": "ok", "chunks_missing_fts": 0, "snapshots_missing_authoritative_text": 0},
  "storage": {
    "census_mode": "db-derived",
    "clean_text_files": 0,
    "clean_text_bytes": 0,
    "sqlite_text_bytes": 12345,
    "media_files": 10,
    "media_bytes": 987654,
    "spool_files": 2,
    "spool_bytes": 12345
  },
  "media_storage": {
    "enabled": true,
    "limit_bytes": 1073741824,
    "stored_artifacts": 2,
    "filesystem_bytes": 12345,
    "reserved_bytes": 0,
    "accounted_bytes": 12345,
    "available_bytes": 1073729479,
    "media_root": {"ok": true, "status": "ready"}
  },
  "media_queue": {"artifacts": {"stored": 10}, "tasks": {"succeeded": 10}}
}
```

When exact filesystem file counts are needed, opt in explicitly:

```http
GET /doctor?storage_census=full
Authorization: Bearer ***
```

Full storage census returns `storage.census_mode="filesystem"` and walks `clean_text_root`, `media_root`, and the configured local spool; it can be slow on large NAS-backed media roots. `media_storage` separately reports final-root readiness and capacity accounting used for admission.

---

## Capture payload

```json
{
  "url": "https://example.com/article",
  "title": "Example Article",
  "canonical_url": "https://example.com/article",
  "text": "Visible or extracted page text...",
  "captured_at": "2026-06-09T12:00:00Z",
  "visit_id": "visit_...",
  "navigation_id": "navigation_...",
  "observation_id": "observation_...",
  "capture_reason": "initial",
  "extraction_method": "dom-visible-text",
  "extraction_version": "extractor-v2",
  "visit_started_at": "2026-06-09T11:59:01Z",
  "dwell_seconds": 32,
  "max_scroll_percent": 80,
  "is_incognito": false,
  "source": "chrome-extension",
  "browser_profile": "Default",
  "media_artifacts": [
    {
      "media_type": "image",
      "role": "content",
      "source_url": "https://example.com/hero.png",
      "alt_text": "Hero image",
      "mime_type": "image/png",
      "width": 640,
      "height": 360
    }
  ]
}
```

Response:

```json
{
  "stored": true,
  "document_id": "doc_...",
  "snapshot_id": "snap_...",
  "visit_id": "visit_...",
  "observation_id": "obs_...",
  "observation_created": true,
  "url_claim_ids": [],
  "snapshot_created": true,
  "chunk_count": 3,
  "media_ref_count": 1,
  "media_artifacts": [
    {
      "artifact_id": "media_...",
      "document_id": "doc_...",
      "snapshot_id": "snap_...",
      "media_type": "image",
      "role": "content",
      "source_url": "https://example.com/hero.png"
    }
  ],
  "redaction_count": 0,
  "policy_mode": "all"
}
```

In `all` mode, daemon redaction is disabled. In non-`all` modes, URL/title/body redaction runs before DB/FTS/blob storage.

The normalized observed `url` is authoritative for new document identity. `canonical_url` is stored only as a URL claim when it differs; it never causes an automatic cross-origin document merge. Repeated captures may share one `visit_id`/`navigation_id` while producing distinct observations. Reusing an `observation_id` with identical stored provenance is idempotent; changing its navigation, document, snapshot, URL, capture time/method/reason, extraction version, title, or provenance quality is rejected. Exact retries return the same URL-claim and media-reference response shape without creating another observation. Reusing a `visit_id` for a different normalized observed URL/document is rejected so one visit cannot span navigations.

The MV3 service worker emits opaque stable IDs: one observation ID per extraction and one navigation ID per persisted tab/URL state. It stores those IDs in the queued payload before daemon transport, preserves them across retry/restart, rotates navigation identity on URL change, and lazily decorates legacy queued captures before their next POST.

---

## Observation-first activity reads

`GET /recent` and `GET /timeline` return one item per capture observation. Each item keeps the existing visit/document/snapshot fields and adds `observation_id`, `navigation_id`, `record_source`, capture method/reason/version, disposition, provenance quality, and `max_scroll_percent`. The snippet and media count are taken only from that observation's snapshot and stored media relationships.

Historical visits without any observation row remain visible as `record_source: "legacy-visit"`, `disposition: "legacy-fallback"`, and `provenance_quality: "ambiguous"`. The fallback prefers a visit-linked snapshot and never labels a document-latest fallback as exact.

`GET /timeline` also includes an additive `summary` for the bounded returned items: distinct visits, observation count, capture count, dwell summed once per visit, maximum lifecycle scroll, and media relationship count.

Document detail includes ordered `observations` and `url_claims`; snapshot detail includes only observations referencing that exact snapshot. Existing `visits`, `snapshots`, and endpoint paths remain available for compatibility.

---

## Blob locator read contract

SQLite migration version 8 adds root-relative blob locators while retaining legacy absolute compatibility paths. Media writes populate both forms. Legacy snapshot/media sidecar reads, media serving, forget, purge, and eviction prefer the relative locator and use the legacy absolute path only when the relative field is null or empty. Every selected value still resolves through the configured-root `BlobStore`; a populated invalid relative locator fails closed rather than falling back.

SQLite migration version 9 makes `snapshots.cleaned_text` the complete-text authority and records `text_authority`/`text_source` as `capture`, `chunks-hash-verified`, `sidecar-hash-verified`, or `legacy-fallback`. New captures create no clean-text sidecar and return `clean_text_sidecar_status="not-created"`. Detail reads use non-null SQLite text before any legacy sidecar or chunk fallback.

Snapshot summaries expose `clean_text_locator_kind`; media metadata exposes `file_locator_kind`. Locator values are `relative`, `legacy-absolute`, `none`, or `unresolved` where configuration is unavailable. `clean_text_path_status` and `file_path_status` report sidecar containment/availability such as `ok`, `missing`, `outside-root`, `empty`, or `config-required`. `has_clean_text` is true when authoritative SQLite text exists even if the sidecar status is `empty`. List/detail projections do not expose the underlying locator strings or duplicate complete text in summary rows.

---

## Media artifact APIs

Media references in `/capture` are relationship metadata only. Binary storage is asynchronous: the browser lazy sidecar fetches with Chrome cookies and uploads raw blobs, while the daemon media worker backfills public refs without Chrome cookies.

Media artifact rows returned from artifact, document-detail, and snapshot-detail reads include `observations`. Each entry contains `observation_id`, `observed_at`, `link_provenance_quality`, `observation_provenance_quality`, visit/navigation identity, observed URL, and capture method/reason/version. The list contains only stored observation/artifact relationships; unresolved historical ambiguity is represented by an empty list rather than a synthesized latest-snapshot link.

Raw browser upload:

```http
PUT /media-artifacts/<artifact_id>/blob
Authorization: Bearer ***
Content-Type: image/png
X-BMD-Document-ID: doc_...
X-BMD-Snapshot-ID: snap_...
```

Compatibility JSON upload:

```json
{
  "document_id": "doc_...",
  "snapshot_id": "snap_...",
  "visit_id": "visit_...",
  "page_url": "https://example.com/article",
  "media_type": "image",
  "role": "content",
  "source_url": "https://example.com/hero.png",
  "mime_type": "image/png",
  "width": 640,
  "height": 360,
  "content_base64": "..."
}
```

If `content_base64` is omitted, the artifact is metadata-only.

Raw `PUT` requires a non-negative `Content-Length`, rejects bodies above the configured artifact cap before consumption, and streams accepted bytes directly into contained `BlobStore` staging with reads capped at 64 KiB. Truncated or disconnected uploads abort staging, release cache and process reservations, and leave the prior artifact row authoritative. Media route capacity exhaustion returns HTTP `503` with the compatible top-level `error` field. Compatibility JSON remains bounded but can still require a base64 decode copy; raw upload is the preferred binary path.

Public daemon backfill:

```http
POST /media-artifacts/fetch-pending
Authorization: Bearer ***
Content-Type: application/json
```

```json
{"domain": "x.com", "limit": 100}
```

Response summary:

```json
{
  "attempted": 1,
  "claimed": 1,
  "seeded_tasks": 0,
  "stored": 1,
  "failed": 0,
  "skipped": 0,
  "remaining": 0,
  "results": [
    {
      "artifact_id": "media_...",
      "capture_status": "stored",
      "status_reason": "",
      "stored": true
    }
  ]
}
```

Manual and background fetches use the same `media_fetch_tasks` lease path as the media worker. Each caller claims one task immediately before processing it, so later tasks do not age in a preclaimed batch while earlier work waits for process capacity or network deadlines. An actively leased task is not fetched by a competing caller; stale leases are eligible for recovery.

Queue/cache status:

```http
GET /media-artifacts/queue-status?limit=50
Authorization: Bearer ***
```

The response includes artifact/task status counts, stored-byte totals, recent non-stored artifacts, live cache gates (`max_media_artifact_bytes`, `max_media_bytes_per_snapshot`, `max_media_bytes_per_domain`, `max_media_cache_bytes`, MIME allowlist, priority floor, and cache pressure), and aggregate process-resource counters (`max_inflight_bytes`, `inflight_bytes`, `max_concurrent_requests`, `active_requests`). The counters expose no captured content, URL, or storage path. The daily-driver health snapshot additionally derives due-task, oldest-due, stale-lease, latest-worker-run, and 1h/24h worker-throughput telemetry from the same task/audit tables using SQLite datetime comparisons, so mixed `CURRENT_TIMESTAMP` and ISO-`T` timestamps are compared as times rather than strings.

Purge local media blob cache without deleting text/FTS/ref rows:

```http
POST /media-artifacts/purge-cache
Authorization: Bearer ***
Content-Type: application/json
```

```json
{"domain": "linkedin.com", "dry_run": true, "rehydrate": false}
```

Execute mode first records a blob tombstone and sets selected artifacts to `purging`. It returns `pending_deletions > 0` instead of claiming purge success when bytes are blocked or an unlink fails. Pending artifacts retain locators for retry but are not served or overwritten; they continue to count against media admission budgets until `storage reconcile --execute` reaches `deleted` or `missing`.

Stored binaries are available via:

```http
GET /media-artifacts/<artifact_id>
Authorization: Bearer ***
```

The daemon validates the tier-owned locator against the configured media/spool root before serving bytes and streams accepted responses from `BlobStore.open` in 64 KiB chunks while holding a process byte/request lease. It checks the emitted length against the advertised length. A client disconnect closes the response without attempting a second HTTP response, emits only the safe `client_disconnected` telemetry code, and releases the lease. Missing, stale, invalid, out-of-root, `purging`, or `purged` artifacts return metadata/not-stored responses rather than reading arbitrary local files.

Media metadata is not inserted into FTS; search results only expose `media_artifact_count`.

---

## Policy rules

Current explicit rules are block-only:

```json
{
  "rule_type": "domain",
  "pattern": "example.com",
  "action": "block"
}
```

```json
{
  "rule_type": "url-prefix",
  "pattern": "https://example.com/private/",
  "action": "block"
}
```

Rules narrow capture in every policy mode, including `all`. Use `domain` for host/subdomain blocks and `url-prefix` for scoped local ports or paths, such as `http://127.0.0.1:32400/`. Rule creation is semantic-idempotent: duplicate `(rule_type, normalized pattern, action)` requests return the existing rule instead of creating parallel rows.

---

## Policy evaluate response

```json
{
  "allowed": false,
  "reason": "policy-rule:block-url-prefix:http://127.0.0.1:32400/",
  "privacy_class": "blocked",
  "policy_mode": "all",
  "static_reason": "allowed:all"
}
```

---

## Visit lifecycle event payload

`/visit-events` is metadata-only. It does not accept page body text.

```json
{
  "event_id": "vevt_...",
  "visit_id": "visit_...",
  "url": "https://example.com/article",
  "event_type": "tab-deactivated",
  "event_started_at": "2026-06-09T12:00:00Z",
  "event_ended_at": "2026-06-09T12:01:33Z",
  "active_seconds": 93,
  "max_scroll_percent": 82,
  "metadata": {"tab_id": 123}
}
```

If `visit_id` is present, it resolves only when exact identity and normalized observed URL agree. An event that arrives before its capture is retained with `visit_id: null`, its `claimed_visit_id`, and `attachment_method: "unmatched"`; capture ingestion later reconciles it only when claimed ID and normalized observed URL both match. Payloads that omit `visit_id` retain an explicitly labeled `legacy-url-fallback` during the compatibility window.

Positive-active intervals require timezone-qualified start/end timestamps, a positive bounded duration, and reported `active_seconds` within one second of that duration. `visits.dwell_seconds` is replaced with the union of all valid positive-active intervals for the resolved visit, so overlap, containment, adjacency, out-of-order delivery, and duplicate event IDs do not double-count. The response separates resolved `visit_id` from `claimed_visit_id` and reports `attachment_method`, `dwell_updated`, and the current derived `dwell_seconds`.

---

## Deletion payloads

Forget accepts exactly one destructive selector. A domain selector is a literal hostname; it continues to delete that host and its subdomains:

```json
{"domain": "example.com"}
```

Forget one absolute URL. URL matching is policy-aware: `all` mode matches the literal stored URL, while `recall`/`balanced`/`strict` match the redacted URL representation used at ingest time:

```json
{"url": "https://example.com/article"}
```

Requests with neither selector or with both selectors return `400`. Domain selectors reject URL/path/query/wildcard/port/userinfo syntax; use `url` for a scoped URL deletion.

The relational cascade, minimized receipt, and blob tombstones commit in one SQLite transaction. The response includes `database_forgotten`, `deletion`, and `counts.blob_deletions_pending`. `forgotten` is `true` only when every required byte is confirmed `deleted` or already `missing`; failed, blocked, unavailable-root, or outside-root deletion remains durable retry work and keeps `forgotten: false`. The receipt ID is also the deletion operation ID used by reconciliation.

The response includes `receipt_id`, redaction-safe `scope`, and deletion counts for documents, visits, lifecycle events, snapshots, chunks, FTS, clean-text blobs, media artifacts/blobs, embeddings, redactions, and feedback events. Blob counters include out-of-root/failed unlink counts when stale or tampered DB paths are refused instead of followed. URL deletion receipts redact sensitive selector values even when `all` mode used the literal URL to find rows.
