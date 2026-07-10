# Daily-Driver Chrome Deployment

> **Scope:** Install or refresh a Windows Chrome daily-driver capture stack while keeping durable memory in WSL.
> **Default policy:** `all` — no daemon redaction or URL policy filtering; DOM extraction still skips hidden/form/editable/script/style/no-script text.

---

## Current deployment model

```text
Windows Chrome unpacked extension
  → http://127.0.0.1:8765/capture + /visit-events + media blob PUT
  → WSL systemd --user services
     - browser-memory-daemon.service
     - browser-memory-media-worker.service
  → ~/.local/share/browser-memory-daemon/browser-memory.sqlite3
  → ${BMD_BLOB_ROOT:-~/.local/share/browser-memory-daemon/blobs}/{clean-text,media}/
```

The daemon is persistent in WSL. Chrome still requires **Load unpacked** / **Reload** through Chrome's UI because branded Chrome rejects direct profile JSON extension transplants.

---

## Installed paths

| Item | Path |
|---|---|
| Source repo | `~/repos/workstation/browser-memory-daemon/` |
| Windows extension copy | `%LOCALAPPDATA%\browser-memory-daemon\extension\` |
| WSL token file | `~/.config/browser-memory-daemon/token` |
| WSL service env | `~/.config/browser-memory-daemon/env` |
| systemd daemon unit | `~/.config/systemd/user/browser-memory-daemon.service` |
| systemd media worker unit | `~/.config/systemd/user/browser-memory-media-worker.service` |
| SQLite DB | `~/.local/share/browser-memory-daemon/browser-memory.sqlite3` |
| Blob root | `${BMD_BLOB_ROOT:-~/.local/share/browser-memory-daemon/blobs}` |
| Clean-text blobs | `${BMD_BLOB_ROOT}/clean-text/` |
| Media blobs | `${BMD_BLOB_ROOT}/media/` |
| Audit log | `~/.local/state/browser-memory-daemon/audit.jsonl` |

---

## Install / refresh

```bash
cd ~/repos/workstation/browser-memory-daemon
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

The installer:

1. validates `BMD_POLICY_MODE`, `BMD_REQUIRE_BLOB_ROOT_MOUNT`, and the Python 3.11+ runtime;
2. builds the MV3 extension;
3. copies it to the Windows-local extension directory;
4. creates or reuses the daemon token;
5. writes protected WSL env with `BMD_API_TOKEN`, `BMD_POLICY_MODE`, `BMD_BLOB_ROOT`, `BMD_REQUIRE_BLOB_ROOT_MOUNT`, and `PYTHONPATH`;
6. writes/enables/restarts `systemd --user` daemon and media-worker services whose `ExecStart` values do not carry token material;
7. preconfigures the Windows extension copy with token and policy mode;
8. verifies WSL and Windows loopback health.

Non-mutating install preview:

```bash
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh --dry-run
```

Read-only installed-state check, with no rebuild/copy/unit writes/restarts:

```bash
./scripts/install-daily-driver.sh --check
```

To place blobs on a WSL-mounted NAS dataset while keeping SQLite/WAL local:

```bash
BMD_BLOB_ROOT=/mnt/nas/browser-memory-daemon/blobs \
  BMD_REQUIRE_BLOB_ROOT_MOUNT=1 \
  BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

`BMD_BLOB_ROOT` affects only clean-text/media blob files. The SQLite DB, WAL/SHM sidecars, token/env files, audit state, and systemd units remain under WSL XDG paths.

The mount only needs to be a normal WSL-visible filesystem path. Prefer NFS for simple kernel-mounted NAS storage when it works in the local WSL/network boundary; SSHFS is an acceptable fallback for blob payloads because SQLite/WAL stays local. `BMD_REQUIRE_BLOB_ROOT_MOUNT=1` makes the installer and daemon fail before writing blobs if the configured root no longer has a non-root mounted ancestor; leave it unset or `0` only when the blob root is intentionally local WSL storage.

For an existing install, migrate DB-referenced blob paths after copying/writing to the new root:

```bash
systemctl --user stop browser-memory-media-worker.service browser-memory-daemon.service
BMD_BLOB_ROOT=/mnt/nas/browser-memory-daemon/blobs \
  PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  blob-root migrate --execute
BMD_BLOB_ROOT=/mnt/nas/browser-memory-daemon/blobs \
  BMD_REQUIRE_BLOB_ROOT_MOUNT=1 \
  BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

The migration command is dry-run by default. `--execute` copies files and rewrites DB paths; add `--remove-source` only after verifying the NAS-backed copy and live daemon behavior.

Rotate token and refresh extension copy:

```bash
BMD_ROTATE_TOKEN=1 BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

Then reload Chrome extension:

```text
chrome://extensions → Browser Memory Daemon → Reload
```

---

## Example installed state

```text
Extension ID: assigned by Chrome for the local unpacked extension
Extension path: %LOCALAPPDATA%\browser-memory-daemon\extension
```

Direct `Preferences` / `Secure Preferences` JSON transplant was tested and rejected by Chrome on launch. Chrome protects extension entries with legacy MACs and encrypted hashes; invalid entries are removed. Use Chrome's own **Load unpacked** / **Reload** flow.

---

## Verify service

```bash
./scripts/daily-driver-health.sh
systemctl --user status browser-memory-daemon.service
systemctl --user status browser-memory-media-worker.service
journalctl --user -u browser-memory-daemon.service -n 50 --no-pager
journalctl --user -u browser-memory-media-worker.service -n 50 --no-pager
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  health
```

Windows loopback check from WSL:

```bash
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile \
  -Command "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 5 | ConvertTo-Json -Compress"
```

Expected health includes:

```json
{"ok": true, "capture_enabled": true, "policy_mode": "all"}
```

The aggregate health JSON also checks storage headroom thresholds, required blob-root mount state, systemd restart budgets, recent service-start failure churn, that `~/.config/browser-memory-daemon/token` and `env` are owner-only, that the environment file token matches the token file, that the unit files use the protected `EnvironmentFile`, that service process arguments do not expose token material, and that the Windows extension artifact token defaults match the token file. Token values are not printed. Defaults warn below 5 GB free or 90% used and hard-fail below 1 GB free or 98% used; restart/start-failure budgets warn at 3 and hard-fail at 10. Override with `BMD_HEALTH_HEADROOM_*` / `BMD_HEALTH_SERVICE_*` only for intentionally small local runtimes.

---

## Local UI

```text
http://127.0.0.1:8765/ui
```

Open the local UI directly through the daemon. The daemon embeds the current token into the served `/ui` HTML bootstrap, so the dashboard prepopulates the token and auto-loads recent captures, today's timeline, policy rules, and diagnostics. The UI shell rejects non-loopback `Host` headers, static JS/CSS assets do not contain the token, and every memory/admin API still requires the bearer token.

The **Save override** button remains available for unusual development/test cases; normal daily-driver use should not require pasting a token.

Current UI controls:

- search exact FTS snippets;
- review recent captures and timeline by date;
- open document and snapshot detail, including visit dwell and lifecycle events;
- add block-domain and URL-prefix policy rules;
- forget a domain after explicit browser confirmation;
- run `doctor` diagnostics for DB, FTS, storage, paths, and policy mode.

---

## Manual smoke test

After loading/reloading the extension in Chrome:

1. confirm popup shows `mode=all paused=false`;
2. visit a harmless page;
3. wait a few seconds;
4. search from WSL:

   ```bash
   PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
     --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
     search "distinct phrase from the page"
   ```

Expected result: the page appears with URL/title/snippet metadata.

If the daemon is healthy but a test page does not appear in search and no `capture.*` audit rows are written, check the Chrome extension popup. `Toggle pause` persists `capturePaused` in `chrome.storage.local`, so reloading the unpacked extension does **not** automatically resume capture.

---

## All-mode expectations

In `all` mode:

- banking/account/chat/mail/local/private-host URLs are not blocked by policy;
- URL/title/body text is not redacted by the daemon;
- explicit local block rules still apply;
- hidden/form/editable/script/style/no-script DOM text is still skipped;
- Chrome platform restrictions can still prevent injection on browser-owned pages.

Use `forget` after the fact if a domain should be removed:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  forget --domain example.com
```

---

## Stop / disable

Pause capture from the extension popup, or stop the daemon:

```bash
systemctl --user stop browser-memory-daemon.service browser-memory-media-worker.service
```

Disable autostart:

```bash
systemctl --user disable --now browser-memory-daemon.service browser-memory-media-worker.service
```

Remove the Chrome extension from `chrome://extensions` if needed.

---

## Security note

The Windows extension copy contains the local daemon token so the extension can post captures. The token is not committed to Git and is stored only in the Windows-local extension artifact plus protected WSL config files. Rotating the token requires rerunning the installer and reloading the extension in Chrome.
