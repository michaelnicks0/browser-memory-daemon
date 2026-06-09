# Daily-Driver Chrome Deployment

> **Scope:** Install the local browser-memory daemon for Operator's Windows Chrome daily-driver profile while keeping captured data in WSL.

## Current deployment model

```text
Windows Chrome unpacked extension
  → http://127.0.0.1:8765/capture + /visit-events
  → WSL systemd --user service
  → ~/.local/share/browser-memory-daemon/browser-memory.sqlite3
```

The daemon is persistent in WSL. Chrome still requires a one-time manual **Load unpacked** step because branded Chrome does not allow unattended local unpacked-extension installation through `--load-extension` or local CRX policy on Windows.

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

## Install / refresh

From the repo:

```bash
./scripts/install-daily-driver.sh
```

The installer:

1. builds the MV3 extension;
2. copies it to the Windows-local extension directory;
3. creates or reuses the daemon token;
4. writes the protected WSL env file;
5. writes/enables/restarts the `systemd --user` service;
6. preconfigures the Windows extension copy with the token;
7. verifies WSL and Windows loopback health.

To rotate the token and refresh the extension copy:

```bash
BMD_ROTATE_TOKEN=1 ./scripts/install-daily-driver.sh
```

## One-time Chrome load

Open:

```text
chrome://extensions
```

Then:

1. enable **Developer mode**;
2. click **Load unpacked**;
3. select:

   ```text
   C:\Users\user\AppData\Local\browser-memory-daemon\extension
   ```

If the extension is already loaded and the files were refreshed, click **Reload** on the extension card.

### Local workstation installed state

The real Windows Chrome `Default` profile has been installed with the unpacked extension from that directory:

```text
Extension ID: pgebbgmpbngnjgebbacafndebdjbbida
Extension path: C:\Users\user\AppData\Local\browser-memory-daemon\extension
Chrome profile backup root: C:\Users\user\AppData\Local\browser-memory-daemon\backups\
```

Direct `Preferences` / `Secure Preferences` JSON transplant was tested and rejected by Chrome on launch. Chrome 149 protects extension entries with both legacy MACs and encrypted hashes; invalid/transplanted entries are removed. Use Chrome's own **Load unpacked** path, manual or UI-automated, so Chrome writes valid profile state.

## Verify service

```bash
systemctl --user status browser-memory-daemon.service
journalctl --user -u browser-memory-daemon.service -n 50 --no-pager
PYTHONPATH=daemon/src python3 -m browser_memory_daemon --token "$(cat ~/.config/browser-memory-daemon/token)" health
```

Windows loopback check from WSL:

```bash
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile \
  -Command "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 5 | ConvertTo-Json -Compress"
```

## Local UI

With the daemon running, open:

```text
http://127.0.0.1:8765/ui
```

Paste the daemon token from `~/.config/browser-memory-daemon/token` into the UI once. The UI stores it in browser `localStorage`; the daemon does not embed the token in HTML.

Current UI controls:

- search exact FTS snippets;
- review recent captures and timeline by date;
- open document and snapshot detail, including visit dwell and lifecycle events;
- add block-domain policy rules;
- forget a domain after explicit browser confirmation;
- run `doctor` diagnostics for DB, FTS, storage, and paths.

## Manual smoke test

After loading/reloading the extension in Chrome:

1. visit a harmless non-sensitive page;
2. wait a few seconds;
3. search from WSL:

   ```bash
   PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
     --token "$(cat ~/.config/browser-memory-daemon/token)" \
     search "distinct phrase from the page"
   ```

Expected result: the page appears with URL/title/snippet metadata.

If the daemon is healthy but a harmless test page does not appear in search and no `capture.*` audit rows are written, check the Chrome extension popup. `Toggle pause` persists `capturePaused` in `chrome.storage.local`, so reloading the unpacked extension does **not** automatically resume capture.

Verified daily-driver smoke on Local workstation:

- allowed page on `lvh.me` captured and searched successfully;
- hidden/form/editable text was absent from search;
- synthetic capture was removed with `forget --domain lvh.me`;
- bank-like `bank.lvh.me` page remained absent from search.

## Privacy checks

Sensitive and private surfaces should not capture by default:

- `chrome://*`
- `file://*`
- localhost and private IPs
- banking/medical/tax/insurance/webmail/messaging/account/billing/admin-like domains/paths
- forms, textareas, contenteditable content, hidden/ARIA-hidden/display-none text
- incognito tabs

Quick negative check:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(cat ~/.config/browser-memory-daemon/token)" \
  search "password account billing bank"
```

Use `forget` immediately if an unwanted synthetic capture appears:

```bash
PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
  --token "$(cat ~/.config/browser-memory-daemon/token)" \
  forget --domain example.com
```

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

## Security note

The Windows extension copy contains the local daemon token so the extension can post captures. The token is not committed to Git and is stored only in the Windows-local extension artifact plus protected WSL config files. Rotating the token requires rerunning the installer and reloading the extension in Chrome.
