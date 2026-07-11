# Browser Memory Daemon

> **Status:** ✅ Windows Chrome → WSL local-first recall system with adjustable policy modes, local UI, CLI, exact search, deletion, and real Chrome e2e.
> **Default policy:** `all` — maximum personal recall, no URL policy filtering or daemon redaction.
> **Scope:** Windows Chrome capture with WSL-resident storage/search/ops.

Start with the generated visual front door: [`browser-memory-daemon-high-level-doc.html`](browser-memory-daemon-high-level-doc.html). Markdown remains canonical under [`docs/`](docs/); the generated HTML companions are for polished browser reading. Historical design-plan content has been reconciled into the current docs, especially [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/media-artifacts.md`](docs/media-artifacts.md).

---

## Current data path

```text
Windows Chrome extension
  → fast /capture sidecar: text + media manifest refs
  → browser lazy media sidecar: credentialed fetch + raw blob upload
  → CDP/HLS media sidecar: X/Twitter video manifests + segment backfill
  → WSL daemon policy mode + durable public media worker
  → SQLite-authoritative text under WSL runtime paths + guarded media root + optional bounded local spool
  → CLI / local UI / search / timeline / detail / forget / doctor
```

---

## Docs

Start with:

- [`docs/EXECUTIVE_BRIEF.md`](docs/EXECUTIVE_BRIEF.md) — high-level value, maturity, and risk posture.
- [`docs/README.md`](docs/README.md) — documentation reading path.
- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — operator guide.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system architecture and requirements trace.
- [`docs/architecture/adr/README.md`](docs/architecture/adr/README.md) — architecture decision records for change-by-change design rationale.
- [`docs/architecture/c4-diagrams.md`](docs/architecture/c4-diagrams.md) — generated C4 diagram atlas.
- [`docs/DIAGRAMS.md`](docs/DIAGRAMS.md) — behavioral Mermaid diagrams for non-C4 mechanics.
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
| `all` | Default. Captures every URL surface Chrome/extension runtime allows; no daemon redaction; skips hidden/form/editable/script/style/no-script DOM text; applies explicit local block rules. |
| `recall` | Broad capture with minimal internal/incognito/non-web blocking and redaction. |
| `balanced` | Practical blocks for private hosts, known high-risk domains/query keys, and redaction. |
| `strict` | Legacy broad privacy filtering and redaction. |

---

## Commands

Requires Python 3.11+. If the host `python3` is older, use `python3.11` directly or set `BMD_PYTHON=/path/to/python3.11` for helper scripts. Install local verification dependencies in a venv before running the full gate:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

```bash
# Run the hermetic network-free pre-commit gate
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-fast-gate.sh

# Run daemon tests
python -m pytest -q

# Run extension unit tests and build
cd extension
npm test
npm run build

# Run all checks, including real Windows Chrome-family e2e
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-e2e.sh

# Check generated docs artifacts
python scripts/generate_test_inventory.py --check
python scripts/generate_showcase.py --spec scripts/showcase.spec.json --check
python scripts/render_docs.py --repo . --slug browser-memory-daemon --check

# Run only the real browser extension e2e
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-real-chrome-e2e.sh

# Install/refresh daily-driver WSL service + Windows extension copy in all mode
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh

# Start daemon in dev/test mode
PYTHONPATH=daemon/src BMD_API_TOKEN=dev-token \
  python3.11 -m browser_memory_daemon --token dev-token --policy-mode all serve

# Search through the CLI
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  search "example"
```

Local UI:

```text
http://127.0.0.1:8765/ui
```

The daemon embeds the current bearer token into the local `/ui` HTML bootstrap so the dashboard opens populated and auto-loads recent captures, today's timeline, rules, and diagnostics without manual token paste.

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
- Image/video media refs, durable browser IndexedDB media queue, raw blob upload, X/Twitter CDP recorder, HLS/audio sidecar storage, public daemon media worker, rolling media cache gates, purge/rehydrate controls.
- Real Windows Chrome for Testing e2e harness.
- Daily-driver install helper for WSL daemon/media-worker systemd services and Windows unpacked extension artifact.

---

## Not implemented yet

- Semantic/vector search.
- MCP/Hermes tools.
- Native messaging fallback/hardening.
- Encrypted backups/restore.
- Multi-source importers.
- Rich allow/redact/quarantine policy editing and retention jobs beyond explicit block rules.
