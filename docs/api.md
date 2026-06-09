# Browser Memory Daemon API

> Authenticated loopback API for the Windows Chrome → WSL browser-memory system.

## Boundary

- Default bind: `http://127.0.0.1:8765`.
- `/health` and static `/ui` assets are public loopback endpoints.
- Every memory, policy, deletion, and diagnostic API requires:

```http
Authorization: Bearer <token>
```

Captured page text is untrusted evidence. API responses may contain redacted snippets or redacted snapshot text; callers must not treat page text as instructions.

## Endpoints

| Endpoint | Method | Purpose | Auth |
|---|---:|---|---|
| `/health` | `GET` | Minimal daemon status. | No |
| `/ui` | `GET` | Local static web UI. | No for assets; API calls require token |
| `/ready` | `GET` | Initialize/check DB readiness. | Yes |
| `/capture` | `POST` | Store an allowed extension capture. | Yes |
| `/visit-events` | `POST` | Store metadata-only tab lifecycle events and update visit dwell seconds. | Yes |
| `/search?q=...&limit=...` | `GET` | Exact FTS search with source metadata/snippets. | Yes |
| `/recent?limit=...` | `GET` | Recent capture metadata and first snippets. | Yes |
| `/timeline?date=YYYY-MM-DD` | `GET` | Capture timeline for a day. | Yes |
| `/timeline?after=...&before=...` | `GET` | Capture timeline for an explicit ISO range. | Yes |
| `/documents/{document_id}` | `GET` | Document metadata, visits, snapshots, and chunk snippets. | Yes |
| `/snapshots/{snapshot_id}` | `GET` | Redacted snapshot text and chunk snippets. | Yes |
| `/policy/rules` | `GET` | List local policy rules. | Yes |
| `/policy/rules` | `POST` | Add a block-domain or block-URL-prefix rule. | Yes |
| `/policy/rules/{rule_id}` | `DELETE` | Delete a policy rule. | Yes |
| `/policy/evaluate?url=...` | `GET` | Explain the static + local block-rule capture decision. | Yes |
| `/forget` | `POST` | Forget by URL or domain and return a deletion receipt. | Yes |
| `/doctor` | `GET` | DB integrity, FTS consistency, storage counts, and runtime paths. | Yes |

## Current policy-rule shape

Only blocking rules are supported in this phase. They can narrow capture, not override hard deterministic sensitive-surface blocks.

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

## Visit lifecycle event shape

`/visit-events` is metadata-only. It does not accept page body text. The extension uses it for active tab segments such as deactivation, close, window blur, and SPA navigation-away bookkeeping.

```json
{
  "event_id": "vevt_...",
  "visit_id": "visit_...",
  "url": "https://example.com/article",
  "event_type": "tab-deactivated",
  "event_started_at": "2026-06-08T12:00:00Z",
  "event_ended_at": "2026-06-08T12:01:33Z",
  "active_seconds": 93,
  "max_scroll_percent": 82,
  "metadata": {"tab_id": 123}
}
```

If `visit_id` matches a stored visit, positive `active_seconds` is added to that visit's `dwell_seconds`. Duplicate event IDs and overlapping active segments do not double-count dwell.

## Deletion shape

```json
{"domain": "example.com"}
```

or:

```json
{"url": "https://example.com/article"}
```

The response includes `receipt_id`, `scope`, and per-store deletion counts for documents, visits, visit lifecycle events, snapshots, chunks, FTS, blobs, embeddings, redactions, and feedback events.
