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
| `/doctor` | `GET` | DB integrity, FTS consistency, storage counts, runtime paths. | Yes |

---

## Health response

```json
{
  "ok": true,
  "version": "0.1.0",
  "storage_root": "/home/user/.local/share/browser-memory-daemon",
  "capture_enabled": true,
  "policy_mode": "all"
}
```

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

Queue/cache status:

```http
GET /media-artifacts/queue-status?limit=50
Authorization: Bearer ***
```

The response includes artifact/task status counts, stored-byte totals, recent non-stored artifacts, and live cache gates (`max_media_artifact_bytes`, `max_media_bytes_per_snapshot`, `max_media_bytes_per_domain`, `max_media_cache_bytes`, MIME allowlist, priority floor, and cache pressure).

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

Rules narrow capture in every policy mode, including `all`. Use `domain` for host/subdomain blocks and `url-prefix` for scoped local ports or paths, such as `http://127.0.0.1:32400/`.

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

Forget a domain:

```json
{"domain": "example.com"}
```

Forget one URL:

```json
{"url": "https://example.com/article"}
```

The response includes `receipt_id`, `scope`, and deletion counts for documents, visits, lifecycle events, snapshots, chunks, FTS, clean-text blobs, media artifacts/blobs, embeddings, redactions, and feedback events.
