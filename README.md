# Browser Memory Daemon

> **Status:** Phase 0/1 foundation in progress
> **Scope:** Windows Chrome capture with WSL-resident storage, search, policy, deletion, and future agent integration.

This repo implements the plan from:

```text
~/repos/research/browser-memory-daemon-architecture/chrome-windows-wsl-implementation-plan.md
```

The current implementation is the first verified vertical slice:

```text
Chrome extension payload
  → authenticated WSL HTTP daemon
  → deterministic privacy/redaction
  → SQLite + FTS5 + clean-text blobs under WSL runtime paths
  → search / forget / health APIs
```

## Runtime data boundary

Live data belongs under WSL runtime paths, not this repo:

```text
~/.config/browser-memory-daemon/
~/.local/share/browser-memory-daemon/
~/.local/state/browser-memory-daemon/
```

Do not commit browser captures, DBs, logs, extension private keys, raw HTML, tokens, cookies, or Chrome profile material.

## Commands

```bash
# Run daemon tests
python3 -m pytest -q

# Run extension unit tests and build
cd extension
npm test
npm run build

# Run all current checks
./scripts/run-e2e.sh

# Start daemon in dev/test mode
BMD_API_TOKEN=dev-token ./scripts/dev-daemon.sh

# Search through the CLI
PYTHONPATH=daemon/src BMD_API_TOKEN=dev-token python3 -m browser_memory_daemon --token dev-token search "example"
```

## Implemented now

- Daemon config/path handling.
- SQLite schema with visits/documents/snapshots/chunks/FTS/audit/deletion receipts.
- Capture policy for blocked schemes, localhost/private IPs, and sensitive domains.
- Redaction before storage and FTS indexing.
- Ingest, exact FTS search, and forget-by-domain/URL.
- HTTP API: `/health`, `/ready`, `/capture`, `/search`, `/forget`.
- CLI: `serve`, `health`, `search`, `forget`, `capture-fixture`.
- MV3 extension skeleton with content extractor, queue helpers, service worker, options, popup, and build/test scripts.

## Not implemented yet

- Real Windows Chrome e2e extension loading.
- UI.
- Semantic/vector search.
- MCP/Hermes tools.
- Native messaging fallback.
- Backups/restore.
- Multi-source importers.

Those are later phases in the V-model plan.
