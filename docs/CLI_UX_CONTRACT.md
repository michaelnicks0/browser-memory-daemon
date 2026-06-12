# Browser Memory Daemon CLI UX Contract

> **Audience:** operators, tests, and future CLI/API maintainers.
> **Source of truth:** `daemon/src/browser_memory_daemon/cli.py` plus live `--help`.
> **Status:** ✅ Current command surface documented.

---

## Invocation shape

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  [--host HOST] \
  [--port PORT] \
  [--token TOKEN] \
  [--runtime-root PATH] \
  [--policy-mode all|recall|balanced|strict] \
  COMMAND [COMMAND_ARGS]
```

Global defaults:

| Flag/env | Default | Notes |
|---|---|---|
| `--host` / `BMD_HOST` | `127.0.0.1` | Loopback only unless explicitly changed. |
| `--port` / `BMD_PORT` | `8765` | Daily-driver default. |
| `--token` / `BMD_API_TOKEN` | required | Test mode can synthesize, production cannot. |
| `--runtime-root` / `BMD_RUNTIME_ROOT` | XDG paths | Tests/e2e use temp runtime roots. |
| `--policy-mode` / `BMD_POLICY_MODE` | `all` | Daily-driver default is maximum recall. |

---

## Commands

| Command | Purpose | Output |
|---|---|---|
| `serve` | Start the loopback daemon. | Human startup line; process stays running. |
| `health` | Fetch `/health`. | Raw JSON string. |
| `doctor` | Fetch `/doctor`. | Pretty JSON. |
| `recent --limit N` | Recent captures. | Pretty JSON list. |
| `timeline [--date YYYY-MM-DD] [--after ISO] [--before ISO] [--limit N]` | Capture timeline. | Pretty JSON. |
| `document DOCUMENT_ID` | Document details. | Pretty JSON. |
| `snapshot SNAPSHOT_ID` | Snapshot details and text. | Pretty JSON. |
| `search QUERY [--limit N]` | Exact FTS query. | Pretty JSON search results. |
| `policy-rules [--block-domain DOMAIN]` | List or add block-domain rule. | Pretty JSON. Ignored in `all` mode. |
| `forget [--domain DOMAIN] [--url URL]` | Delete memory by domain or URL. | Pretty JSON deletion receipt. |
| `capture-fixture --url URL --title TITLE --text TEXT` | Synthetic capture through HTTP API. | Pretty JSON ingest result. |
| `media-worker [--once|--loop] [--limit N] [--interval SEC]` | Run daemon public-media worker manually or as service. | Pretty JSON for `--once`; long-running loop for `--loop`. |
| `media-cache purge [--domain DOMAIN] [--document-id ID] [--snapshot-id ID] [--older-than ISO] [--max-bytes-to-purge N] [--dry-run|--execute] [--rehydrate]` | Dry-run/execute media blob cache purge without deleting text/FTS/ref rows. | Pretty JSON purge summary. |
| `media-cache rehydrate [--domain DOMAIN] [--document-id ID] [--snapshot-id ID] [--limit N]` | Queue/refetch purged public media refs. | Pretty JSON worker summary. |

---

## Exit/error contract

| Condition | Expected behavior |
|---|---|
| Missing production token | `load_config` raises and CLI exits non-zero. |
| Unauthorized API call | HTTP `401`; CLI surfaces exception/non-zero. |
| Bad capture payload | HTTP `400` with JSON error. |
| Blocked capture in non-`all` mode | HTTP `200`, `{"stored": false, "blocked": true, "reason": "..."}`. |
| `all` mode capture | Stores unredacted payload when payload is otherwise parseable. |
| Forget by neither URL nor domain | HTTP `400` expected from daemon validation. |

---

## Examples

Start a dev daemon in all mode:

```bash
PYTHONPATH=daemon/src BMD_API_TOKEN=dev-token \
  python3 -m browser_memory_daemon --token dev-token --policy-mode all serve
```

Search daily-driver memory:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  search "example" --limit 10
```

Add a non-all block rule:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  policy-rules --block-domain example.com
```

Forget a domain:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  forget --domain example.com
```

Media cache dry-run:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-cache purge --domain linkedin.com --dry-run
```

---

## Stability notes

- CLI output is currently JSON but not formally versioned.
- `capture-fixture` exists for tests/smoke checks, not browser capture replacement.
- Future CLI changes should update this contract and `daemon/tests/e2e/test_cli_admin.py` together.
