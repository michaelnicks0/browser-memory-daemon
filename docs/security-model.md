# Security Model

The daemon is local-first and WSL-resident. It assumes captured page text may be private and may contain hostile prompt-injection text.

## Current controls

- API token required for `/capture`, `/search`, `/ready`, `/recent`, `/timeline`, `/documents/{id}`, `/snapshots/{id}`, `/policy/*`, `/doctor`, and `/forget`.
- `/health` exposes only minimal status.
- Daemon binds to `127.0.0.1` by default.
- Deterministic policy blocks sensitive schemes/domains and private/loopback hosts.
- Redaction runs before storage and FTS indexing.
- Audit logs are metadata-only in SQLite.
- Extension uses broad HTTP/HTTPS host permission so the service worker can inject capture scripts, but both service worker and injected extractor apply URL privacy gates before queue/storage.
- Injected content scripts extract text; service worker owns daemon communication.
- Daily-driver install stores the daemon API token in protected WSL config files and injects it into the Windows-local extension artifact; the token is never committed, and rotation is supported via `BMD_ROTATE_TOKEN=1 ./scripts/install-daily-driver.sh`.
- Local web UI is served from the loopback daemon at `/ui`; static UI assets are public, but every memory/admin API call still requires the bearer token. The UI stores a pasted token in browser `localStorage` only.
- Policy controls currently support explicit block-domain and URL-prefix rules; they can only narrow capture, not override deterministic sensitive-surface blocks.
- Deletion UX requires an explicit browser confirmation before UI/popup forget-domain calls, and the daemon returns a deletion receipt with DB/FTS/blob counts.

## Current limitations

- Native messaging hardening is not implemented yet.
- Extension queue persistence is skeletal.
- No semantic embeddings yet.
- No encrypted backups yet.
- Policy rules are block-only in this phase; allow/redact/quarantine editing is not implemented yet.
