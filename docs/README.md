# Browser Memory Daemon Docs — Reading Path

> **Audience:** Operator and future agents maintaining the Windows Chrome → WSL browser-memory stack.
> **Status:** ✅ Operator-grade doc index added with architecture, diagrams, CLI/API, tests, deployment, and status pages.
> **Data boundary:** Live browser memory stays under WSL runtime paths, never in this repo.

---

## Start here

| If you need to... | Read |
|---|---|
| Use the system day to day | [`USER_GUIDE.md`](USER_GUIDE.md) |
| Understand the architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| See visual flows/diagrams | [`DIAGRAMS.md`](DIAGRAMS.md) |
| Call or extend the HTTP API | [`api.md`](api.md) |
| Understand CLI commands and flags | [`CLI_UX_CONTRACT.md`](CLI_UX_CONTRACT.md) |
| Install/refresh daily Chrome | [`daily-driver-deployment.md`](daily-driver-deployment.md) |
| Understand policy/security tradeoffs | [`security-model.md`](security-model.md) |
| Check what is implemented vs pending | [`STATUS.md`](STATUS.md) |
| Model storage growth | [`storage-growth-model.md`](storage-growth-model.md) |
| Understand durable lazy media sidecars | [`ARCHITECTURE.md`](ARCHITECTURE.md#durable-media-sidecar-architecture), [`media-artifacts.md`](media-artifacts.md), [`../[removed-publication-dossier]`](../[removed-publication-dossier]) |
| Run verification gates | [`TESTS.md`](TESTS.md), [`test-plan.md`](test-plan.md) |

---

## Ownership map

| Area | Canonical files |
|---|---|
| Daemon runtime/config | `daemon/src/browser_memory_daemon/config.py`, `scripts/install-daily-driver.sh` |
| HTTP API and UI serving | `daemon/src/browser_memory_daemon/app.py`, `ui/` |
| Ingest/storage/search/forget | `ingest.py`, `schema.sql`, `search.py`, `forget.py` |
| Capture policy modes | `policy.py`, `policy_store.py`, `extension/src/extractor.js`, `service_worker.js` |
| Media sidecars | `daemon/src/browser_memory_daemon/media.py`, `media_worker.py`, `extension/src/media_queue.js`, `service_worker.js` |
| Chrome extension extraction/bridge | `extension/src/extractor.js`, `content_script.js`, `service_worker.js` |
| Real browser verification | `scripts/real-chrome-e2e.mjs`, `scripts/run-real-chrome-e2e.sh` |
| Daily-driver install | `scripts/install-daily-driver.sh`, Chrome Load-unpacked UI |

---

## Current policy posture

The daily-driver default is now:

```text
policy_mode = all
```

`all` is intentionally the least restrictive mode: it disables URL/incognito/private-host filtering, disables redaction, and ignores local block rules. Other modes remain available:

| Mode | Intended use |
|---|---|
| `all` | Maximum personal recall; no daemon redaction or URL policy filtering; DOM extraction still skips hidden/form/editable/script/style/no-script text. |
| `recall` | Broad capture with browser/internal scheme and incognito blocks plus redaction. |
| `balanced` | Broad capture with known high-risk domain/query/private-host blocks plus redaction. |
| `strict` | Legacy broad privacy filtering plus redaction. |

---

## Verification quickstart

```bash
python3 -m pytest -q
cd extension && npm test && npm run build
./scripts/run-real-chrome-e2e.sh
./scripts/run-e2e.sh
./scripts/secret-scan.sh
git diff --check -- .
```

For daily-driver refresh after extension code changes:

```bash
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
# Then in Chrome: chrome://extensions → Browser Memory Daemon → Reload
```
