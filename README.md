# Browser Memory Daemon

> **Status:** Phase 0/1 foundation complete; real Windows Chrome-family e2e added
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

## Chrome automation note

Official branded Chrome 137+ ignores `--load-extension` for command-line unpacked-extension automation. The real-browser e2e therefore uses **Chrome for Testing** on Windows, cached under Windows LocalAppData by default, while production/daily-driver Chrome installation remains a later packaging/manual-install task.

## Commands

```bash
# Run daemon tests
python3 -m pytest -q

# Run extension unit tests and build
cd extension
npm test
npm run build

# Run all current checks, including the real Windows Chrome-family e2e
./scripts/run-e2e.sh

# Run only the real browser extension e2e
./scripts/run-real-chrome-e2e.sh

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
- MV3 extension with service-worker-owned programmatic content-script injection, queue helpers, options, popup, and build/test scripts.
- Automated real Windows Chrome-family e2e harness using Chrome for Testing, isolated Windows profile, synthetic allowed/blocked pages, and WSL SQLite/FTS verification.

## Not implemented yet

- Real daily-driver Windows Chrome install/packaging flow.
- UI.
- Semantic/vector search.
- MCP/Hermes tools.
- Native messaging fallback.
- Backups/restore.
- Multi-source importers.

Those are later phases in the V-model plan.
