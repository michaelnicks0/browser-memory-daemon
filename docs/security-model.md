# Security Model

The daemon is local-first and WSL-resident. It assumes captured page text may be private and may contain hostile prompt-injection text.

## Current controls

- API token required for `/capture`, `/search`, `/ready`, and `/forget`.
- `/health` exposes only minimal status.
- Daemon binds to `127.0.0.1` by default.
- Deterministic policy blocks sensitive schemes/domains and private/loopback hosts.
- Redaction runs before storage and FTS indexing.
- Audit logs are metadata-only in SQLite.
- Extension uses broad HTTP/HTTPS host permission so the service worker can inject capture scripts, but both service worker and injected extractor apply URL privacy gates before queue/storage.
- Injected content scripts extract text; service worker owns daemon communication.

## Current limitations

- Native messaging hardening is not implemented yet.
- Extension queue persistence is skeletal.
- No semantic embeddings yet.
- No encrypted backups yet.
- No UI confirmation flow for deletion yet.
