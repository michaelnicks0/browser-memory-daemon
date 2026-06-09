# Daily-Driver Chrome Deployment

> **Scope:** Install or refresh Operator's Windows Chrome daily-driver capture stack while keeping durable memory in WSL.
> **Default policy:** `all` — no daemon redaction or URL policy filtering; DOM extraction still skips hidden/form/editable/script/style/no-script text.

---

## Current deployment model

```text
Windows Chrome unpacked extension
  → http://127.0.0.1:8765/capture + /visit-events
  → WSL systemd --user service
  → ~/.local/share/browser-memory-daemon/browser-memory.sqlite3
```

The daemon is persistent in WSL. Chrome still requires **Load unpacked** / **Reload** through Chrome's UI because branded Chrome rejects direct profile JSON extension transplants.

---

## Installed paths

| Item | Path |
|---|---|
| Source repo | `~/repos/workstation/browser-memory-daemon/` |
| Windows extension copy | `C:\Users\user\AppData\Local\browser-memory-daemon\extension\` |
| WSL token file | `~/.config/browser-memory-daemon/token` |
| WSL service env | `~/.config/browser-memory-daemon/env` |
| systemd user unit | `~/.config/systemd/user/browser-memory-daemon.service` |
| SQLite DB | `~/.local/share/browser-memory-daemon/browser-memory.sqlite3` |
| Clean-text blobs | `~/.local/share/browser-memory-daemon/blobs/clean-text/` |
| Audit log | `~/.local/state/browser-memory-daemon/audit.jsonl` |

---

## Install / refresh

```bash
cd ~/repos/workstation/browser-memory-daemon
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

The installer:

1. validates `BMD_POLICY_MODE`;
2. builds the MV3 extension;
3. copies it to the Windows-local extension directory;
4. creates or reuses the daemon token;
5. writes protected WSL env with `BMD_POLICY_MODE`;
6. writes/enables/restarts the `systemd --user` service;
7. preconfigures the Windows extension copy with token and policy mode;
8. verifies WSL and Windows loopback health.

Rotate token and refresh extension copy:

```bash
BMD_ROTATE_TOKEN=1 BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
```

Then reload Chrome extension:

```text
chrome://extensions → Browser Memory Daemon → Reload
```

---

## Local workstation installed state

```text
Extension ID: pgebbgmpbngnjgebbacafndebdjbbida
Extension path: C:\Users\user\AppData\Local\browser-memory-daemon\extension
Chrome profile backup root: C:\Users\user\AppData\Local\browser-memory-daemon\backups\
```

Direct `Preferences` / `Secure Preferences` JSON transplant was tested and rejected by Chrome on launch. Chrome protects extension entries with legacy MACs and encrypted hashes; invalid entries are removed. Use Chrome's own **Load unpacked** / **Reload** flow.

---

## Verify service

```bash
systemctl --user status browser-memory-daemon.service
journalctl --user -u browser-memory-daemon.service -n 50 --no-pager
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
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

---

## Local UI

```text
http://127.0.0.1:8765/ui
```

Paste the daemon token from `~/.config/browser-memory-daemon/token` into the UI once. The UI stores it in browser `localStorage`; the daemon does not embed the token in HTML.

Current UI controls:

- search exact FTS snippets;
- review recent captures and timeline by date;
- open document and snapshot detail, including visit dwell and lifecycle events;
- add block-domain policy rules for non-`all` modes;
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
   PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
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
- explicit local block rules are ignored;
- hidden/form/editable/script/style/no-script DOM text is still skipped;
- Chrome platform restrictions can still prevent injection on browser-owned pages.

Use `forget` after the fact if a domain should be removed:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  forget --domain example.com
```

---

## Stop / disable

Pause capture from the extension popup, or stop the daemon:

```bash
systemctl --user stop browser-memory-daemon.service
```

Disable autostart:

```bash
systemctl --user disable --now browser-memory-daemon.service
```

Remove the Chrome extension from `chrome://extensions` if needed.

---

## Security note

The Windows extension copy contains the local daemon token so the extension can post captures. The token is not committed to Git and is stored only in the Windows-local extension artifact plus protected WSL config files. Rotating the token requires rerunning the installer and reloading the extension in Chrome.
