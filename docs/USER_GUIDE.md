# Browser Memory Daemon User Guide — Chrome Recall on Windows + WSL

> **Audience:** Operator using daily-driver Chrome.
> **Default mode:** `all` — maximum URL-surface capture with no daemon redaction.
> **Runtime data:** `~/.local/share/browser-memory-daemon/` in WSL.

---

## What it does

The system captures text from pages you browse in Windows Chrome, sends it over loopback to a WSL daemon, stores it in SQLite + FTS5, and lets you search/inspect/forget it locally.

```text
Windows Chrome extension → http://127.0.0.1:8765 → WSL SQLite/FTS/blobs → CLI/UI/search
```

---

## Daily-driver state checks

```bash
systemctl --user is-active browser-memory-daemon.service
systemctl --user is-active browser-memory-media-worker.service
systemctl --user is-enabled browser-memory-daemon.service
systemctl --user is-enabled browser-memory-media-worker.service
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" doctor
```

Windows loopback check from WSL:

```bash
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe \
  -NoProfile -Command "Invoke-RestMethod http://127.0.0.1:8765/health | ConvertTo-Json -Compress"
```

Expected health includes:

```json
{"ok": true, "capture_enabled": true, "policy_mode": "all"}
```

---

## Install or refresh daily Chrome integration

```bash
cd ~/repos/workstation/browser-memory-daemon
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

Then reload the unpacked extension in Chrome:

```text
chrome://extensions → Browser Memory Daemon → Reload
```

Chrome stores the loaded extension at:

```text
C:\Users\user\AppData\Local\browser-memory-daemon\extension
```

Do **not** install by editing Chrome profile JSON. Chrome Secure Preferences rejects direct extension-entry transplants.

---

## Policy modes

| Mode | Capture behavior | Redaction | Local block rules |
|---|---|---:|---:|
| `all` | Captures all URL surfaces the extension/Chrome platform allows unless explicitly blocked; skips hidden/form/editable/script/style/no-script DOM text. | ❌ Off | ✅ Applied |
| `recall` | Captures most `http(s)` pages; blocks incognito/browser-internal/non-web schemes. | ✅ On | ✅ Applied |
| `balanced` | `recall` plus private-host, known bank/payment/mail/auth domains, and high-risk query-key blocks. | ✅ On | ✅ Applied |
| `strict` | Legacy broad keyword filtering for sensitive domains/paths/query keys. | ✅ On | ✅ Applied |

Switch daemon default and refresh extension artifact:

```bash
BMD_POLICY_MODE=recall ./scripts/install-daily-driver.sh
```

Or for one CLI/dev daemon run:

```bash
PYTHONPATH=daemon/src BMD_API_TOKEN=dev-token \
  python3 -m browser_memory_daemon --token dev-token --policy-mode balanced serve
```

Add a domain block or scoped local URL-prefix block:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  policy-rules --block-domain example.com

PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  policy-rules --block-url-prefix http://127.0.0.1:32400/
```

---

## Search and inspect memory

CLI search:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  search "my query" --limit 10
```

Recent captures:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  recent --limit 25
```

Local UI:

```text
http://127.0.0.1:8765/ui
```

The daily-driver daemon embeds the current token into the `/ui` HTML bootstrap, so opening `http://127.0.0.1:8765/ui` from the local machine should prepopulate the token and immediately load recent captures, today's timeline, policy rules, and diagnostics. The token is not written into the static JS/CSS assets or the repo, and every memory/admin API call still requires the bearer token.

---

## Media cache controls

Text/FTS rows are the durable recall source. Media blobs are a bounded cache under `~/.local/share/browser-memory-daemon/blobs/media/`; artifact refs remain even if blobs are purged.

Dry-run a domain purge:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-cache purge --domain linkedin.com --dry-run
```

Execute purge and queue best-effort public rehydration:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-cache purge --domain linkedin.com --execute --rehydrate
```

Run one media worker pass manually:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-worker --once --limit 100
```

---

## Forget memory

Forget a domain:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  forget --domain example.com
```

Forget one URL:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  forget --url "https://example.com/article"
```

The response includes a deletion receipt and per-store deletion counts.

---

## Chrome extension controls

Popup controls:

| Control | Behavior |
|---|---|
| Toggle pause | Pauses/resumes capture. Reloading the extension does not necessarily clear pause state. |
| Health | Checks daemon health and reports extension mode/pause state. |
| Open dashboard | Opens `/ui`. |
| Block current domain/prefix | Adds a daemon block rule. Localhost pages with explicit ports use URL-prefix rules so one local app does not block every loopback page. |
| Forget current domain | Deletes stored memory for the current domain after confirmation. |

Options page controls:

| Field | Meaning |
|---|---|
| Daemon URL | Usually `http://127.0.0.1:8765`. |
| API token | Token copied from WSL config during install. |
| Policy mode | `all`, `recall`, `balanced`, or `strict`. |
| Pause capture | Same pause state as popup. |
| Enable CDP media recorder | On by default. Domain-gated `chrome.debugger` recorder for X/Twitter video manifests/segments; disabling it stops Chrome's native “Browser Memory Daemon started debugging this browser” banner after detach/reload. |
| CDP recorder domains | Comma-separated page domains that may attach CDP recorder; default `x.com,twitter.com`. |

---

## Troubleshooting

| Symptom | Check |
|---|---|
| No captures after reload | Extension popup may still be paused. Toggle pause until `paused=false`. |
| Daemon healthy in WSL but Chrome cannot capture | Verify Windows loopback health and that Chrome extension token is present. |
| Chrome shows “Browser Memory Daemon started debugging this browser” | Expected while **Enable CDP media recorder** is on and attached to an X/Twitter tab. To stop it, disable that option, then click the banner **Cancel** button or reload the extension. Normal text capture continues, but X/Twitter CDP video recovery is reduced. |
| Real-browser e2e fails to load extension | Use Chrome for Testing, not branded Chrome command-line unpacked-extension automation. |
| Search returns URLs but not expected text | Check policy mode. `strict`/`balanced` may block/redact; `all` should preserve text. |
| Daily Chrome extension disappears after profile edits | Do not edit profile JSON; use Chrome Load unpacked UI. |

---

## Important limits

- Chrome may refuse extension injection on browser-owned internal pages even in `all` mode.
- `all` disables daemon redaction and policy blocks by design.
- Cloud LLM/vector uploads are not implemented and should not be added without explicit approval.
