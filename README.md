# Browser Memory Daemon

> **Status:** ✅ Windows Chrome → WSL local-first recall system with adjustable policy modes, local UI, CLI, exact search, deletion, and real Chrome e2e.
> **Default policy:** `all` — maximum personal recall, no URL policy filtering or daemon redaction.
> **Scope:** Windows Chrome capture with WSL-resident storage/search/ops.

This implementation follows the plan from:

```text
~/repos/research/browser-memory-daemon-architecture/chrome-windows-wsl-implementation-plan.md
```

---

## Current data path

```text
Windows Chrome extension
  → service-worker-owned authenticated localhost HTTP
  → WSL daemon policy mode
  → SQLite + FTS5 + text blobs under WSL runtime paths
  → CLI / local UI / search / timeline / detail / forget / doctor
```

---

## Docs

Start with:

- [`docs/README.md`](docs/README.md) — documentation reading path.
- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — operator guide.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system architecture and requirements trace.
- [`docs/DIAGRAMS.md`](docs/DIAGRAMS.md) — Mermaid visual atlas.
- [`docs/CLI_UX_CONTRACT.md`](docs/CLI_UX_CONTRACT.md) — CLI contract.
- [`docs/api.md`](docs/api.md) — HTTP API.
- [`docs/security-model.md`](docs/security-model.md) — policy/security model.
- [`docs/STATUS.md`](docs/STATUS.md) — implemented vs pending.
- [`docs/TESTS.md`](docs/TESTS.md) — verification gates.

---

## Runtime data boundary

Live data belongs under WSL runtime paths, not this repo:

```text
~/.config/browser-memory-daemon/
~/.local/share/browser-memory-daemon/
~/.local/state/browser-memory-daemon/
```

Do not commit browser captures, DBs, logs, extension private keys, raw HTML, tokens, cookies, or Chrome profile material.

---

## Policy modes

| Mode | Behavior |
|---|---|
| `all` | Default. Captures every URL surface Chrome/extension runtime allows; no daemon redaction; skips hidden/form/editable/script/style/no-script DOM text; ignores local block rules. |
| `recall` | Broad capture with minimal internal/incognito/non-web blocking and redaction. |
| `balanced` | Practical blocks for private hosts, known high-risk domains/query keys, and redaction. |
| `strict` | Legacy broad privacy filtering and redaction. |

---

## Commands

```bash
# Run daemon tests
python3 -m pytest -q

# Run extension unit tests and build
cd extension
npm test
npm run build

# Run all checks, including real Windows Chrome-family e2e
./scripts/run-e2e.sh

# Run only the real browser extension e2e
./scripts/run-real-chrome-e2e.sh

# Install/refresh daily-driver WSL service + Windows extension copy in all mode
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh

# Start daemon in dev/test mode
PYTHONPATH=daemon/src BMD_API_TOKEN=dev-token \
  python3 -m browser_memory_daemon --token dev-token --policy-mode all serve

# Search through the CLI
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  search "example"
```

Local UI:

```text
http://127.0.0.1:8765/ui
```

---

## Implemented now

- Daemon config/path handling with `BMD_POLICY_MODE` / `--policy-mode`.
- SQLite schema with visits/documents/snapshots/chunks/FTS/audit/deletion receipts/lifecycle events.
- Adjustable capture modes: `all`, `recall`, `balanced`, `strict`.
- All-mode no-redaction ingest path and no extension URL privacy filters; DOM extraction still skips hidden/form/editable/script/style/no-script text.
- Non-all redaction before storage and FTS indexing.
- Ingest, exact FTS search, recent/timeline/detail, and forget-by-domain/URL.
- URL normalization and snapshot dedupe/versioning.
- Delayed SPA capture and History API hooks.
- Tab lifecycle events, dwell seconds, and max-scroll metadata.
- Local web UI and MV3 extension popup/options controls.
- Real Windows Chrome for Testing e2e harness.
- Daily-driver install helper for WSL systemd service and Windows unpacked extension artifact.

---

## Not implemented yet

- Semantic/vector search.
- MCP/Hermes tools.
- Native messaging fallback/hardening.
- Encrypted backups/restore.
- Multi-source importers.
- Rich allow/redact/quarantine policy editing and retention jobs.
