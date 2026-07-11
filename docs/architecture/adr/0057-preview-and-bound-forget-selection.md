---
id: ADR-0057
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes:
  - ADR-0025
superseded_by: []
related:
  - docs/architecture/adr/0006-use-forget-cascade-with-deletion-receipts.md
  - docs/architecture/adr/0040-use-durable-deletion-intents-and-reconciliation.md
  - docs/security-model.md
  - docs/api.md
  - docs/CLI_UX_CONTRACT.md
  - daemon/src/browser_memory_daemon/forget.py
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_ingest_search_forget.py daemon/tests/unit/test_application.py daemon/tests/e2e/test_http_api.py daemon/tests/e2e/test_cli_admin.py daemon/tests/e2e/test_ui_dashboard_smoke.py
  - cd extension && npm test && npm run build
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-fast-gate.sh
  - BMD_SKIP_REAL_CHROME_E2E=1 BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
  - BMD_REAL_CHROME_ALLOW_DOWNLOAD=0 BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-real-chrome-e2e.sh
---

# ADR-0057: Preview and bound forget selection

## Context

ADR-0025 made forget selectors literal and policy-aware but intentionally left preview and unexpectedly broad selection guards open. Forget now cascades across authoritative documents, visits, observations, snapshots, FTS rows, URL claims, media provenance, and durable blob tombstones. A syntactically valid domain can therefore select substantially more state than an operator expects, and the old CLI executed immediately without showing that scope.

The hardening requirement is not merely to validate selector syntax. The operator must be able to inspect the exact current selection without mutation, and execution must fail closed when the current selection exceeds an explicit record bound.

## Decision

Forget selection shall be planned before mutation:

- Domain input is normalized and validated as a hostname or IP literal. SQL wildcard syntax, malformed labels and IDNs, schemes, paths, ports, userinfo, and whitespace are rejected.
- Domain matching is literal apex-plus-subdomain matching without SQL `LIKE` wildcard semantics.
- URL matching follows active storage policy and selects exact observed document/visit URLs plus exact URL claims as documented aliases. A claim never changes identity; it only participates when the operator explicitly supplies that exact claimed URL.
- Preview returns redaction-safe scope, row counts across every selected authority/provenance surface, reconstructible blob candidates, and a guard result. It creates no deletion receipt, audit event, tombstone, or filesystem change.
- Execution uses a default `max_records` bound of 10,000 selected database/FTS records and rejects a broader selection before any mutation. An operator may deliberately raise the positive bound for that request to the reviewed scope; no hard ceiling can make a valid large domain impossible to forget.
- The CLI is dry-run by default and requires `--execute` for mutation. `--max-records` carries the reviewed bound into execution.
- The authenticated HTTP endpoint retains execute-by-default behavior for older compatible callers, but accepts `dry_run` and `max_records`. The current UI and extension popup preview first, show document/record counts in confirmation, then execute with the previewed record bound.
- Successful execution retains the existing durable deletion receipt and blob-tombstone workflow and includes the applied guard in its response.

## Decision drivers

- Destructive selection must be reviewable before mutation.
- A valid domain selector can still be unexpectedly broad.
- Preview must not manufacture audit evidence that implies deletion occurred.
- Existing authenticated UI and extension endpoint behavior must remain compatible.
- URL claims remain untrusted for identity and must not trigger implicit merging.
- Selection and receipt metadata must remain redaction-safe.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep immediate execution after syntax validation | Fully compatible | No scope review or broad-selection protection | Rejected |
| Require a frozen plan token for every API execution | Strong review/apply binding | Breaks existing UI/extension contract and adds a larger protocol migration | Deferred |
| Add preview plus a per-request record ceiling | Compatible, bounded, independently testable | Preview and later CLI execution can observe different current state; execution therefore recomputes and enforces the bound | Chosen |
| Bound only document count | Simple | One document can own many observations/chunks/events | Rejected |

## Consequences

- Positive: CLI forget is non-mutating unless `--execute` is explicit.
- Positive: API and CLI callers can inspect exact current counts without receipts, audits, tombstones, or file deletion.
- Positive: executions above the reviewed/default bound fail before the transaction begins.
- Positive: literal suffix matching no longer depends on SQL wildcard behavior.
- Positive: receipts count capture observations, URL claims, and media provenance rows removed by cascades.
- Neutral: domain scope remains apex plus subdomains for compatibility.
- Neutral: the API remains execute-by-default for older clients even though current first-party operator surfaces preview before bounded execution.
- Negative: large intentional deletions require a preview and an explicitly raised `max_records` value.

## Verification / validation

- Integration tests cover malformed domains, exact apex/subdomain selection, exclusion of suffix lookalikes, non-mutating preview, broad-guard refusal, exact URL-claim aliases, and preview/execution count agreement.
- HTTP tests prove preview leaves searchable text intact, guarded execution returns a stable typed error, and bounded execution completes.
- CLI tests prove default dry-run and explicit bounded `--execute` behavior against a temporary daemon runtime.
- UI and popup contract tests prove first-party controls preview before confirmation and carry the previewed bound into execution.
- Existing all/recall/balanced/strict policy and durable blob-deletion tests remain part of the broad gate.

## Revisit triggers

- Version the HTTP contract if the UI/extension can adopt mandatory preview-bound execution.
- Introduce immutable plan hashes if concurrent drift between review and execution becomes an operational problem.
- Supersede if deletion scopes expand to dates, arbitrary queries, policy groups, or backup bundles.

## References

- `daemon/src/browser_memory_daemon/forget.py`
- `daemon/src/browser_memory_daemon/application.py`
- `daemon/src/browser_memory_daemon/cli.py`
- `daemon/tests/integration/test_ingest_search_forget.py`
- `daemon/tests/e2e/test_http_api.py`
- `daemon/tests/e2e/test_cli_admin.py`
