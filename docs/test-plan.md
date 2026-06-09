# Test Plan

## Current requirement coverage

| Requirement | Test evidence |
|---|---|
| REQ-001 capture | `daemon/tests/e2e/test_http_api.py` synthetic capture; `scripts/run-real-chrome-e2e.sh` verifies allowed page and delayed SPA route capture from Windows Chrome for Testing |
| REQ-002 WSL storage | tests use runtime root outside repo; runtime paths ignored |
| REQ-003 service worker bridge | `scripts/run-real-chrome-e2e.sh` loads the extension in Windows Chrome for Testing and verifies service-worker-owned injection/capture |
| REQ-004 auth + loopback | HTTP unauthorized test; bind defaults in config |
| REQ-005 privacy blocks | `daemon/tests/unit/test_policy.py` |
| REQ-006 redaction | policy and ingest tests verify secrets absent |
| REQ-007 FTS search | integration/e2e search tests |
| REQ-008 schema | DB initialized by integration/e2e tests |
| REQ-009 dedupe/versioning | `daemon/tests/integration/test_ingest_search_forget.py` verifies query-normalized repeat visits create one snapshot and changed content creates a new snapshot under one document |
| REQ-010/011 forget | integration/e2e forget tests |
| REQ-012 cited results | `/search`, `/documents/{id}`, and `/snapshots/{id}` expose source metadata, snapshot IDs, and snippets/text |
| REQ-014 extension controls | Extension popup can pause capture, open dashboard, block current domain, and forget current domain; daemon policy-rule e2e verifies block behavior |
| REQ-015 CLI | `daemon/tests/e2e/test_cli_admin.py` covers `recent`, `document`, `snapshot`, `doctor`, and `policy-rules` |
| REQ-016 local UI | `daemon/tests/e2e/test_admin_api.py` verifies `/ui` asset serving plus UI-backed API surfaces |
| REQ-025 audit logging | Admin API paths write metadata-only audit events for search/recent/timeline/detail/doctor/policy/delete |
| REQ-028 doctor | `/doctor` and CLI `doctor` e2e verify DB integrity, FTS consistency, storage counts, and runtime paths |
| REQ-030 artifact boundary | `.gitignore` and `scripts/secret-scan.sh` |
| REQ-031 Windows browser e2e | `scripts/run-real-chrome-e2e.sh` synthetic allowed/blocked/localhost scenarios |

## Current commands

```bash
python3 -m pytest -q
cd extension && npm test && npm run build
./scripts/run-real-chrome-e2e.sh
./scripts/run-e2e.sh
```

`run-real-chrome-e2e.sh` uses Windows Chrome for Testing because branded Chrome 137+ no longer honors command-line `--load-extension` automation.
