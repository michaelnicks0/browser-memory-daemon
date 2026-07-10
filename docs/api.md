# Browser Memory Daemon API

> **Audience:** API callers, UI/CLI maintainers, extension maintainers.
> **Boundary:** authenticated loopback API for Windows Chrome → WSL recall.
> **Default policy:** `all`.

---

## Auth and boundary

- Default bind: `http://127.0.0.1:8765`.
- `/health` is public loopback. `/ui` HTML is public loopback and includes an inline JSON bootstrap with the current daemon token for same-origin dashboard use; static JS/CSS assets do not include the token.
- Every memory, policy, deletion, and diagnostic API requires:

```http
Authorization: Bearer ***
```

Captured page text is untrusted evidence. API clients must not treat retrieved page text as executable instructions.

Error responses are JSON with a stable top-level `error` string:

```json
{"error": "unauthorized"}
```

Missing or invalid bearer tokens return `401`; malformed JSON and invalid payloads return `400`; unknown routes return `404`; unsupported HTTP methods return `501`. Limit parameters are bounded server-side (`recent` max 100, `timeline` max 250, media queue max 200); invalid integer limits return `400` on endpoints that parse limits directly.

---

## Endpoint index

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
| `/doctor[?storage_census=full]` | `GET` | DB integrity, FTS consistency, runtime paths, media queue, and fast DB-derived storage counts; optional filesystem census walks blob roots. | Yes |

---

## Health response

```json
{
  "ok": true,
  "version": "0.1.0",
  "storage_root": "/home/<user>/.local/share/browser-memory-daemon",
  "blob_root": "/mnt/nas/browser-memory-daemon/blobs",
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
  "database": {"integrity_check": "ok", "chunks_missing_fts": 0},
  "storage": {
    "census_mode": "db-derived",
    "clean_text_files": 2,
    "clean_text_bytes": 12345,
    "media_files": 10,
    "media_bytes": 987654
  },
  "media_queue": {"artifacts": {"stored": 10}, "tasks": {"succeeded": 10}}
}
```

When exact filesystem file counts are needed, opt in explicitly:

```http
GET /doctor?storage_census=full
Authorization: Bearer ***
```

Full storage census returns `storage.census_mode="filesystem"` and walks `clean_text_root` plus `media_root`; it can be slow on large NAS-backed blob roots.

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

---

## Media artifact APIs

Media references in `/capture` are relationship metadata only. Binary storage is asynchronous: the browser lazy sidecar fetches with Chrome cookies and uploads raw blobs, while the daemon media worker backfills public refs without Chrome cookies.

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

Manual and background fetches use the same `media_fetch_tasks` lease path as the media worker. An actively leased task is not fetched by a competing caller; stale leases are eligible for recovery.

Queue/cache status:

```http
GET /media-artifacts/queue-status?limit=50
Authorization: Bearer ***
```

The response includes artifact/task status counts, stored-byte totals, recent non-stored artifacts, and live cache gates (`max_media_artifact_bytes`, `max_media_bytes_per_snapshot`, `max_media_bytes_per_domain`, `max_media_cache_bytes`, MIME allowlist, priority floor, and cache pressure). The daily-driver health snapshot additionally derives due-task, oldest-due, stale-lease, latest-worker-run, and 1h/24h worker-throughput telemetry from the same task/audit tables using SQLite datetime comparisons, so mixed `CURRENT_TIMESTAMP` and ISO-`T` timestamps are compared as times rather than strings.

Purge local media blob cache without deleting text/FTS/ref rows:

```http
POST /media-artifacts/purge-cache
Authorization: Bearer ***
Content-Type: application/json
```

```json
{"domain": "linkedin.com", "dry_run": true, "rehydrate": false}
```

Stored binaries are available via:

```http
GET /media-artifacts/<artifact_id>
Authorization: Bearer ***
```

The daemon validates the stored DB `file_path` against the configured media root before serving bytes. Missing, stale, invalid, or out-of-root paths return metadata/not-stored responses rather than reading arbitrary local files.

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

If `visit_id` matches a stored visit, positive `active_seconds` is added to `visits.dwell_seconds`. Duplicate event IDs and overlapping active segments do not double-count dwell.

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

The response includes `receipt_id`, redaction-safe `scope`, and deletion counts for documents, visits, lifecycle events, snapshots, chunks, FTS, clean-text blobs, media artifacts/blobs, embeddings, redactions, and feedback events. Blob counters include out-of-root/failed unlink counts when stale or tampered DB paths are refused instead of followed. URL deletion receipts redact sensitive selector values even when `all` mode used the literal URL to find rows.
