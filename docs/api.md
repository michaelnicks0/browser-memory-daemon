# Browser Memory Daemon API

> **Audience:** API callers, UI/CLI maintainers, extension maintainers.
> **Boundary:** authenticated loopback API for Windows Chrome → WSL recall.
> **Default policy:** `all`.

---

## Auth and boundary

- Default bind: `http://127.0.0.1:8765`.
- `/health` and static `/ui` assets are public loopback endpoints.
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
| `/ui` | `GET` | Local static web UI. | No for assets; API calls require token |
| `/ready` | `GET` | Initialize/check DB readiness. | Yes |
| `/capture` | `POST` | Store an allowed extension capture plus media references. | Yes |
| `/media-artifacts` | `POST` | Store/upgrade a related image/video artifact row and optional blob. | Yes |
| `/media-artifacts/fetch-pending` | `POST` | Daemon-side fetch of pending public media artifact refs. | Yes |
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
  "redaction_count": 0,
  "policy_mode": "all"
}
```

In `all` mode, daemon redaction is disabled. In non-`all` modes, URL/title/body redaction runs before DB/FTS/blob storage.

---

## Media artifact payload

Media references in `/capture` are relationship metadata only. Binary storage uses `/media-artifacts` after `/capture` returns `document_id` and `snapshot_id`.

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

If `content_base64` is omitted, the artifact is metadata-only. Pending public artifacts can be fetched by the daemon:

```http
POST /media-artifacts/fetch-pending
Authorization: Bearer ***
Content-Type: application/json
```

```json
{"domain": "x.com", "limit": 100}
```

That endpoint asks the daemon to fetch pending public `referenced` / `metadata-only` artifact URLs itself. It is useful when Chrome MV3 service-worker upload is suspended before large social/media pages finish binary upload.

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

Rules narrow capture only in `recall`, `balanced`, and `strict`. They are intentionally ignored in `all` mode.

---

## Policy evaluate response

```json
{
  "allowed": true,
  "reason": "allowed:all",
  "privacy_class": "all",
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
