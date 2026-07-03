# Test Plan

> **Audience:** maintainers and future agents.
> **Scope:** requirement-to-test traceability for the current implementation.
> **Default policy under test:** `all`, with explicit strict/balanced/recall coverage where needed.

---

## Current requirement coverage

| Requirement | Test evidence |
|---|---|
| REQ-001 capture | `daemon/tests/e2e/test_http_api.py` synthetic capture; `scripts/run-real-chrome-e2e.sh` verifies Windows Chrome capture. |
| REQ-002 WSL storage | tests use runtime roots outside repo; runtime paths ignored; doctor exposes runtime paths. |
| REQ-003 service worker bridge | `extension/tests/unit/service_worker.test.js` covers service-worker queue/pause/token/rule resilience; real Chrome e2e verifies service-worker-owned injection/capture. |
| REQ-004 auth + loopback | HTTP unauthorized tests; bind defaults in config; Windows PowerShell health checks. |
| REQ-005 adjustable policy modes | `daemon/tests/unit/test_policy.py`; `extension/tests/unit/extractor.test.js`. |
| REQ-006 all-mode no built-in URL filtering/redaction | daemon integration stores unredacted fixture secrets; extension unit tests verify built-in URL filters are off while hidden/form/editable/script/style/no-script DOM text is skipped; real Chrome e2e default expects banking/local fixtures searchable. |
| REQ-006A explicit block rules | `daemon/tests/unit/test_policy_store.py`; `daemon/tests/e2e/test_admin_api.py::test_url_prefix_policy_rule_applies_in_all_mode_without_blocking_all_localhost`. |
| REQ-007 non-all redaction | policy and ingest tests verify secrets absent in strict mode. |
| REQ-008 FTS search | integration/e2e search tests. |
| REQ-009 schema | DB initialized and table inventory checked by integration/e2e tests. |
| REQ-010 dedupe/versioning | ingest tests verify repeat visits do not duplicate snapshots and changed content creates new snapshots. |
| REQ-011 SPA/delayed capture | real Chrome e2e delayed `history.pushState` fixture. |
| REQ-012 dwell/reading signals | lifecycle integration tests and real Chrome e2e tab-switch dwell/max-scroll checks. |
| REQ-013 forget/delete | integration/e2e forget tests. |
| REQ-014 cited results | `/search`, `/documents/{id}`, `/snapshots/{id}` expose source metadata, snapshot IDs, snippets/text. |
| REQ-015 extension controls | popup/options support pause, health, dashboard, block/forget domain, policy mode. |
| REQ-015A daily-driver install consistency | `daemon/tests/e2e/test_daily_driver_install.py` and `daemon/tests/unit/test_daily_driver_health.py` cover non-mutating installer dry-run, protected token/env files, service process-argument secrecy, unit expectations, and extension token matching. |
| REQ-016 local UI | admin API tests verify `/ui` asset serving and UI-backed API surfaces; `daemon/tests/e2e/test_ui_dashboard_smoke.py` verifies token bootstrap parsing, core panels, empty/error states, and initial dashboard API calls through a low-dependency DOM harness. |
| REQ-017 CLI | `daemon/tests/e2e/test_cli_admin.py` covers read/admin commands. |
| REQ-018 audit logging | API paths write metadata-only audit events. |
| REQ-019 doctor | `/doctor` and CLI doctor verify DB integrity, FTS consistency, paths, counts, and policy mode. |
| REQ-020 artifact boundary | `.gitignore` and `scripts/secret-scan.sh`. |
| REQ-021 Windows browser e2e | `scripts/run-real-chrome-e2e.sh` synthetic allowed/SPA/banking/local scenarios plus public media, cookie-required media, and synthetic `blob:` video artifacts. |
| REQ-022 durable media sidecars | `test_media_worker.py`, `media_queue.test.js`, `service_worker.test.js` media upload retry coverage, HTTP raw blob/purge tests, real Chrome media e2e. |

---

## Current commands

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
cd extension && npm test && npm run build
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-real-chrome-e2e.sh
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-e2e.sh
python scripts/generate_test_inventory.py --check
python scripts/generate_showcase.py --spec scripts/showcase.spec.json --check
python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
```

Advisory performance benchmark:

```bash
./scripts/run-performance-benchmarks.sh --small --json >/tmp/bmd_benchmark.json
```

The benchmark uses deterministic synthetic captures and local data/media sidecars only. It reports ingest, read surface, endpoint-style audit-write, media-worker selection/run, storage growth, and advisory budget sections; use its JSON output as the baseline for read-model tuning.

`run-real-chrome-e2e.sh` uses Windows Chrome for Testing because branded Chrome 137+ no longer reliably honors command-line `--load-extension` automation. It honors `BMD_PYTHON` for the WSL daemon and DB probes. By default it runs the `all strict` matrix; set `BMD_REAL_CHROME_POLICY_MODE=<mode>` for a single debugging run or `BMD_REAL_CHROME_MATRIX_MODES="all strict balanced recall"` for an extended local matrix.

---

## Mode-specific e2e

Default matrix (`all` + `strict`):

```bash
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-real-chrome-e2e.sh
```

Single strict-mode debugging run:

```bash
BMD_PYTHON="${BMD_PYTHON:-python}" BMD_REAL_CHROME_POLICY_MODE=strict ./scripts/run-real-chrome-e2e.sh
```

Balanced/recall smoke:

```bash
BMD_PYTHON="${BMD_PYTHON:-python}" BMD_REAL_CHROME_POLICY_MODE=balanced ./scripts/run-real-chrome-e2e.sh
BMD_PYTHON="${BMD_PYTHON:-python}" BMD_REAL_CHROME_POLICY_MODE=recall ./scripts/run-real-chrome-e2e.sh
```

---

## Documentation verification

See [`TESTS.md`](TESTS.md) for Markdown fence checks, Mermaid-render guidance, and daily-driver smoke checklist.
