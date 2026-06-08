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

## Deletion shape

```json
{"domain": "example.com"}
```

or:

```json
{"url": "https://example.com/article"}
```

The response includes `receipt_id`, `scope`, and per-store deletion counts for documents, visits, snapshots, chunks, FTS, blobs, embeddings, redactions, and feedback events.
