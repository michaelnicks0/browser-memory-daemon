# Browser Memory Daemon User Guide — Chrome Recall on Windows + WSL

> **Audience:** Operator using daily-driver Chrome.
> **Default mode:** `all` — maximum URL-surface capture with no daemon redaction.
> **Runtime data:** `~/.local/share/browser-memory-daemon/` in WSL.

---

## What it does

The system captures text from pages you browse in Windows Chrome, sends it over loopback to a WSL daemon, stores it in SQLite + FTS5, and lets you search, inspect, and forget it locally.

```text
Windows Chrome extension → http://127.0.0.1:8765 → WSL SQLite/FTS authority + media cache → CLI/UI/search
```

The mental model:

| Layer | Owns | Operator takeaway |
|---|---|---|
| Chrome extension | Capture, pause/block/forget UI, transactional capture/lifecycle outbox, browser-side media queue. | Reload this after extension code or token/policy changes. |
| WSL daemon | Auth, policy, ingest, search, UI shell, delete receipts, media cache controls. | This is the durable memory service. |
| WSL runtime paths | SQLite complete-text/FTS authority, media blobs, legacy text sidecars, token/env, audit log. | Runtime data never belongs in Git. New captures create no text sidecar. |

Use Python 3.11+ for CLI/dev commands. If the host `python3` is older, run `python3.11` explicitly or set `BMD_PYTHON=/path/to/python3.11` for helper scripts.

---

## I want to…

| Goal | Start here |
|---|---|
| Refresh daily Chrome integration | [`Install or refresh daily Chrome integration`](#install-or-refresh-daily-chrome-integration) |
| Check whether capture is healthy | [`Daily-driver state checks`](#daily-driver-state-checks) |
| Search remembered pages | [`Search and inspect memory`](#search-and-inspect-memory) |
| Narrow capture for a host/path/port | [`Policy modes`](#policy-modes) and `policy-rules` examples |
| Remove remembered data | [`Forget memory`](#forget-memory) |
| Purge or refill media blobs | [`Media cache controls`](#media-cache-controls) |
| Stop Chrome's debugging banner | [`Troubleshooting`](#troubleshooting) |

---

## Daily-driver state checks

One redaction-safe snapshot command covers WSL services, loopback health from WSL and Windows, recent systemd journal warning/error counts and service-start churn budgets, SQLite integrity/freshness/counts, media-queue aggregates, storage headroom thresholds, protected token/env files, service process-argument secrecy, unit-file expectations, and the Windows extension artifact state:

```bash
./scripts/daily-driver-health.sh
```

The command prints JSON and exits non-zero when a hard health error is present. It does **not** dump captured page text, snippets, cookies, bearer tokens, raw captured URLs, or extension token values. Warnings such as due media retries are reported in `summary.warnings` while still producing a zero exit when the stack is otherwise healthy. The media-queue section reports due task counts by task/artifact status, oldest-due age, stale lease age, latest media-worker run, and 1h/24h worker throughput. Default storage thresholds are warning below 5 GB free or 90% used and hard error below 1 GB free or 98% used; restart/start-failure budgets warn at 3 and hard-fail at 10. If `BMD_REQUIRE_BLOB_ROOT_MOUNT=1`, health also hard-fails when the configured blob root is no longer under a mounted filesystem. Override local health thresholds with `BMD_HEALTH_HEADROOM_*` and `BMD_HEALTH_SERVICE_*` only when a small VM or test filesystem needs different bounds.

Manual spot checks, if you need to isolate a layer:

```bash
systemctl --user is-active browser-memory-daemon.service
systemctl --user is-active browser-memory-media-worker.service
systemctl --user is-enabled browser-memory-daemon.service
systemctl --user is-enabled browser-memory-media-worker.service
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" doctor
```

`doctor` defaults to fast DB-derived storage counts. If you need exact file counts after a storage migration or manual cleanup, opt in to the slower filesystem walk:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  doctor --storage-census
```

Doctor reports `database.snapshots_missing_authoritative_text` and includes it in overall health. To preview promotion of pre-version-9 rows from exact hash-verified chunks or contained legacy sidecars:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  snapshot-text reconcile
```

Review the redaction-safe JSON, then add `--execute` to promote only the reported exact candidates. Unresolved rows remain unchanged.

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

Preview the install without writing files, copying artifacts, or restarting services:

```bash
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh --dry-run
```

Check the current installed stack without rebuilding/copying/restarting:

```bash
./scripts/install-daily-driver.sh --check
```

To place only disposable media on a WSL-mounted NAS dataset while keeping derivatives local, pre-provision `/mnt/nas/browser-memory-daemon/media/.bmd-media-root-id` with the exact single-line identity `bmd-media-prod`, then configure:

```bash
BMD_DERIVATIVE_ROOT="$HOME/.local/share/browser-memory-daemon/derivatives" \
  BMD_MEDIA_ROOT=/mnt/nas/browser-memory-daemon/media \
  BMD_MEDIA_ROOT_IDENTITY=bmd-media-prod \
  BMD_REQUIRE_MEDIA_ROOT_MOUNT=1 \
  BMD_MEDIA_SPOOL_ROOT="$HOME/.local/share/browser-memory-daemon/media-spool" \
  BMD_MAX_MEDIA_SPOOL_BYTES=1073741824 \
  BMD_MAX_MEDIA_INFLIGHT_BYTES=524288000 \
  BMD_MAX_MEDIA_CONCURRENT_REQUESTS=4 \
  BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

Explicit external `BMD_MEDIA_ROOT` values are intentionally strict: media access requires a non-root mounted ancestor and an exact identity marker. The installer does not create the external media root or marker. A failed guard degrades media handling but does not block local SQLite text/provenance capture. The spool is optional, must remain under the local data root, and is enabled only when both its path and a positive byte cap are configured. `BMD_MAX_MEDIA_INFLIGHT_BYTES` must be positive and at least `BMD_MAX_MEDIA_ARTIFACT_BYTES`; `BMD_MAX_MEDIA_CONCURRENT_REQUESTS` must also be positive. These caps apply independently inside the daemon and worker processes, while SQLite cache reservations coordinate persistent cache admission across them. `BMD_BLOB_ROOT` and `BMD_REQUIRE_BLOB_ROOT_MOUNT` remain compatibility inputs for legacy layouts.

Then reload the unpacked extension in Chrome:

```text
chrome://extensions → Browser Memory Daemon → Reload
```

Chrome stores the loaded extension at:

```text
%LOCALAPPDATA%\browser-memory-daemon\extension
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
  python3.11 -m browser_memory_daemon --token dev-token --policy-mode balanced serve
```

Add a domain block or scoped local URL-prefix block:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  policy-rules --block-domain example.com

PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  policy-rules --block-url-prefix http://127.0.0.1:32400/
```

---

## Search and inspect memory

CLI search:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  search "my query" --limit 10
```

Recent captures:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  recent --limit 25
```

Recent and timeline items represent extraction observations, so repeated captures during one navigation appear separately while sharing deduplicated snapshots when text is unchanged. Historical visits without an observation row are retained as explicit ambiguous `legacy-visit` fallbacks. Document and snapshot details show the observation/snapshot relationship and keep page-provided URL claims separate from observed identity.

Local UI:

```text
http://127.0.0.1:8765/ui
```

The daily-driver daemon embeds the current token into the `/ui` HTML bootstrap, so opening `http://127.0.0.1:8765/ui` from the local machine should prepopulate the token and immediately load recent captures, today's timeline, policy rules, and diagnostics. The UI shell rejects non-loopback `Host` headers, the token is not written into the static JS/CSS assets or the repo, and every memory/admin API call still requires the bearer token.

---

## Media cache controls

Text/FTS rows are the durable recall source. Final media blobs are a bounded disposable cache under `BMD_MEDIA_ROOT` (legacy default `${BMD_BLOB_ROOT:-~/.local/share/browser-memory-daemon/blobs}/media/`); artifact refs remain even if blobs are purged. During a guarded-root outage, explicitly configured local spool bytes remain readable as stored artifacts.

Raw uploads, daemon-public HTTP/HLS fetch, artifact publication, and stored-media responses use bounded streams. The authenticated `/media/queue-status` response reports configured/current counters for the serving daemon process; CLI queue status runs in its own short-lived process, so those counters are normally idle. A temporary `media-resource-budget` outcome is retryable; snapshot/domain/global cache-budget skips remain terminal until explicitly requeued after a cap or policy change. SQLite version 13 reservations prevent daemon and worker processes from concurrently committing beyond persistent cache caps.

Inspect spool capacity and final-root readiness without mutation:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-spool status
```

Preview a bounded drain, review the JSON, then add `--execute` only after the expected media mount and marker are verified:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-spool drain --limit 100
```

Preview durable deletion/reconciliation work without mutation:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  storage reconcile --limit 1000
```

Review `tombstones`, `missing`, `corrupt`, `recovered`, `wrong_root`, `unavailable`, `orphans`, and `stale_stages`. Add `--execute` only to retry contained tombstones, mark confirmed missing media, and remove reported in-root orphan/stage files. Outside-root locators and unavailable external roots remain pending rather than being followed. A non-zero pending count means a prior forget/purge/eviction has not completed byte deletion even if its database rows are already gone.

Create a text-first local backup by previewing first, then executing to a new absolute path:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  backup create --destination /absolute/local/path/backup-bundle

PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  backup create --destination /absolute/local/path/backup-bundle --execute
```

Restore is also dry-run first and only publishes into an absent destination:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  backup restore --source /absolute/local/path/backup-bundle \
  --destination /absolute/local/path/restored-runtime
```

The default bundle includes SQLite-authoritative text/provenance plus a hash manifest. It excludes API tokens/config, Chrome state, final media, and spool bytes. Add `--include-derivatives` only when legacy clean-text sidecars are useful. A backup created before a forget can still contain the forgotten data; backup erasure/retention remains a separate operator action.

Dry-run a domain purge:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-cache purge --domain linkedin.com --dry-run
```

Execute purge and queue best-effort public rehydration:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-cache purge --domain linkedin.com --execute --rehydrate
```

After intentionally raising a media budget, preview a scoped retry of rows that were terminally skipped under the old cap:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-cache requeue --reason all-budget --domain linkedin.com --dry-run
```

Repeat with `--execute` only after reviewing the selected count and sample artifact IDs. The ordinary worker never revives budget skips automatically.

Run one media worker pass manually:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-worker --once --limit 100
```

---

## Forget memory

Forget a domain:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  forget --domain example.com
```

Forget one URL:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
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

Resilience behavior: if the daemon is temporarily unavailable, successfully queued captures and lifecycle messages stay as independent IndexedDB outbox rows and are retried by startup/install/alarm drains after their due time. MV3 suspension claims recover after five minutes; capture acceptance is checkpointed before browser media compensation. At the 100-capture/32 MiB capture or 200-lifecycle/2 MiB lifecycle limit, existing rows remain intact and the new message is visibly rejected instead of silently sliced. The separate browser media queue atomically admits capture task batches, caps work at 500 tasks and 512 MiB of fetched blobs, and keeps failed terminal task/blob pairs in a 24-hour quarantine before bounded cleanup. The popup and options page show redaction-safe counts, serialized bytes, oldest age, claims, quotas, overflow, and last-success state without captured text or URLs. Missing-token or paused states skip new capture queue mutation; resume capture after restoring the token or toggling pause off.

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
