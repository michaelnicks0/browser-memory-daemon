# Browser Memory Daemon Docs — Reading Path

> **Audience:** Operator and future agents maintaining the Windows Chrome → WSL browser-memory stack.
> **Status:** ✅ Publish-ready doc set with executive brief, user guide, generated HTML companions, architecture, diagrams, CLI/API, tests, deployment, and status pages.
> **Data boundary:** Live browser memory stays under WSL runtime paths, never in this repo.

---

## Start here

| If you need to... | Read |
|---|---|
| Get the polished visual overview | [`../browser-memory-daemon-high-level-doc.html`](../browser-memory-daemon-high-level-doc.html) |
| Understand value, maturity, and risk posture quickly | [`EXECUTIVE_BRIEF.md`](EXECUTIVE_BRIEF.md) |
| Use the system day to day | [`USER_GUIDE.md`](USER_GUIDE.md) |
| Understand the architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md), [`architecture/c4-diagrams.md`](architecture/c4-diagrams.md) |
| Inspect canonical requirements and V-model evidence | [`../requirements/catalog.toml`](../requirements/catalog.toml), [`test-plan.md`](test-plan.md), [`TESTS.md`](TESTS.md) |
| Understand architecture/design decision history | [`architecture/adr/README.md`](architecture/adr/README.md) |
| See behavioral Mermaid flows/diagrams | [`DIAGRAMS.md`](DIAGRAMS.md) |
| Call or extend the HTTP API | [`api.md`](api.md) |
| Understand CLI commands and flags | [`CLI_UX_CONTRACT.md`](CLI_UX_CONTRACT.md) |
| Install/refresh daily Chrome | [`daily-driver-deployment.md`](daily-driver-deployment.md) |
| Understand policy/security tradeoffs | [`security-model.md`](security-model.md) |
| Check what is implemented vs pending | [`STATUS.md`](STATUS.md) |
| Model storage growth | [`storage-growth-model.md`](storage-growth-model.md) |
| Understand retention, compaction, export, and backup posture | [`retention-compaction-backup.md`](retention-compaction-backup.md) |
| Review the current blob-root migration helper and its safety limits | [`blob-root-migration.md`](blob-root-migration.md) |
| Inspect or operate SQLite schema migrations | [`database-migrations.md`](database-migrations.md), [`architecture/adr/0028-use-versioned-restore-backed-sqlite-migrations.md`](architecture/adr/0028-use-versioned-restore-backed-sqlite-migrations.md) |
| Understand durable lazy media sidecars | [`ARCHITECTURE.md`](ARCHITECTURE.md#durable-media-sidecar-architecture), [`media-artifacts.md`](media-artifacts.md) |
| Run verification gates | [`TESTS.md`](TESTS.md), [`test-plan.md`](test-plan.md) |
| Review the measured branch-coverage baseline and ratchet | [`coverage-baseline.md`](coverage-baseline.md) |
| Review Phase 0 gate evidence | [`verification/phase-0-gate-2026-07-10.md`](verification/phase-0-gate-2026-07-10.md) |
| Review Phase 2 gate evidence | [`verification/phase-2-gate-2026-07-10.md`](verification/phase-2-gate-2026-07-10.md) |

---

## Ownership map

| Area | Canonical files |
|---|---|
| Publish-ready front door | `browser-memory-daemon-high-level-doc.html`, `scripts/showcase.spec.json`, `scripts/generate_showcase.py` |
| Markdown-to-HTML companions | `scripts/render_docs.py`, `scripts/mermaid-theme.json`, generated `*.html` siblings |
| Generated test inventory | `scripts/generate_test_inventory.py`, `docs/TESTS.md` generated regions |
| Hermetic fast quality gate | `scripts/run-fast-gate.sh`, `pyproject.toml`, `docs/coverage-baseline.md` |
| Daemon runtime/config | `daemon/src/browser_memory_daemon/config.py`, `scripts/install-daily-driver.sh` |
| HTTP API, application use cases, and UI serving | `daemon/src/browser_memory_daemon/http_server.py`, `daemon/src/browser_memory_daemon/application.py`, `daemon/src/browser_memory_daemon/app.py`, `ui/` |
| Ingest/storage/search/forget | `ingest.py`, `schema.sql`, `search.py`, `forget.py` |
| SQLite migration lifecycle | `migrations.py`, `migration_steps/`, `database-migrations.md` |
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

`all` is intentionally the least restrictive mode: it disables built-in URL/incognito/private-host filtering and redaction, while still applying explicit local block rules. Other modes remain available:

| Mode | Intended use |
|---|---|
| `all` | Maximum personal recall; no daemon redaction or built-in URL policy filtering; explicit local block rules still apply; DOM extraction still skips hidden/form/editable/script/style/no-script text. |
| `recall` | Broad capture with browser/internal scheme and incognito blocks plus redaction. |
| `balanced` | Broad capture with known high-risk domain/query/private-host blocks plus redaction. |
| `strict` | Legacy broad privacy filtering plus redaction. |

---

## Verification quickstart

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-fast-gate.sh
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-e2e.sh
python scripts/generate_test_inventory.py --check
python scripts/generate_showcase.py --spec scripts/showcase.spec.json --check
python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
python -m pytest -q
cd extension && npm test && npm run build
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-real-chrome-e2e.sh
./scripts/secret-scan.sh
git diff --check -- .
```

For daily-driver refresh after extension code changes:

```bash
BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
# Then in Chrome: chrome://extensions → Browser Memory Daemon → Reload
```
