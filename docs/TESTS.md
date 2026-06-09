# Browser Memory Daemon Tests — Verification Gates

> **Audience:** maintainers and future agents.
> **Goal:** verify policy modes, capture, storage, search, deletion, UI/API, and real Windows Chrome behavior.

---

## Primary gates

```bash
python3 -m pytest -q
cd extension && npm test && npm run build
./scripts/run-real-chrome-e2e.sh
./scripts/run-e2e.sh
./scripts/secret-scan.sh
git diff --check -- .
```

`./scripts/run-e2e.sh` runs daemon tests, extension tests/build, real Chrome e2e unless `BMD_SKIP_REAL_CHROME_E2E=1`, secret scan, and whitespace check.

---

## Test inventory

| Test file/script | Covers |
|---|---|
| `daemon/tests/unit/test_policy.py` | Policy-mode decisions and redaction helpers. |
| `daemon/tests/integration/test_ingest_search_forget.py` | Ingest, redaction/non-redaction, FTS, dedupe, media artifact refs/blobs, forget, schema. |
| `daemon/tests/integration/test_visit_lifecycle.py` | Lifecycle events, dwell updates, duplicate/overlap protection. |
| `daemon/tests/e2e/test_http_api.py` | HTTP capture/search/forget/auth behavior. |
| `daemon/tests/e2e/test_admin_api.py` | UI asset serving and admin/read/policy endpoints. |
| `daemon/tests/e2e/test_cli_admin.py` | CLI read/admin commands. |
| `extension/tests/unit/extractor.test.js` | DOM extraction and URL policy modes. |
| `extension/tests/unit/queue.test.js` | Queue/helper behavior. |
| `scripts/real-chrome-e2e.mjs` | Real Windows Chrome for Testing extension/daemon path. |
| `scripts/secret-scan.sh` | Secret-shaped content scan over repo. |

---

## Policy-mode verification matrix

| Mode | Daemon unit/integration | Extension unit | Real Chrome e2e |
|---|---|---|---|
| `all` | Allows formerly blocked URL surfaces; stores unredacted fixture secrets. | Does not block URLs; still skips hidden/form/editable/script/style/no-script DOM text. | Default e2e expects banking and localhost fixtures searchable while hidden/form text stays absent. |
| `recall` | Allows profile/settings and known domains; blocks incognito/internal schemes; redacts. | Allows broad `http(s)`; blocks browser/internal schemes. | Optional via `BMD_REAL_CHROME_POLICY_MODE=recall`. |
| `balanced` | Allows normal profile/settings; blocks known high-risk domains/private hosts/query secrets; redacts. | Same class in extension prefilter. | Optional via `BMD_REAL_CHROME_POLICY_MODE=balanced`. |
| `strict` | Legacy broad keyword/domain/path/query blocks; redacts. | Legacy URL/DOM skip behavior. | Optional via `BMD_REAL_CHROME_POLICY_MODE=strict`. |

Run a real-browser e2e in a non-default mode:

```bash
BMD_REAL_CHROME_POLICY_MODE=strict ./scripts/run-real-chrome-e2e.sh
```

---

## Daily-driver smoke checklist

After `./scripts/install-daily-driver.sh` and Chrome extension reload:

1. Confirm daemon:

   ```bash
   systemctl --user is-active browser-memory-daemon.service
   PYTHONPATH=daemon/src python3 -m browser_memory_daemon \
     --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" doctor
   ```

2. Confirm Windows loopback:

   ```bash
   /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe \
     -NoProfile -Command "Invoke-RestMethod http://127.0.0.1:8765/health | ConvertTo-Json -Compress"
   ```

3. Confirm popup shows:

   ```text
   mode=all paused=false
   ```

4. Browse a synthetic/harmless page and search for a unique visible string.

5. If no capture appears, check popup pause state first.

---

## Doc/diagram validation

Mechanical checks:

```bash
git diff --check -- .
python3 - <<'PY'
from pathlib import Path
bad=[]
for p in Path('docs').glob('*.md'):
    text=p.read_text()
    if text.count(chr(96) * 3) % 2:
        bad.append(str(p))
if bad:
    raise SystemExit(f'unbalanced code fences: {bad}')
print('markdown fence check passed')
PY
```

Mermaid render check when `mmdc` is available:

```bash
npx --yes @mermaid-js/mermaid-cli --version
```

Then extract/render diagrams or use the repo/tooling equivalent. Do not claim rendered-diagram validation unless it actually ran.
