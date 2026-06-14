---
id: ADR-0003
status: accepted
date: 2026-06-14
decision_date: 2026-06-09
decider: Operator
scope: repo
backfilled: true
supersedes: []
superseded_by: []
related:
  - docs/ARCHITECTURE.md
  - docs/security-model.md
  - docs/TESTS.md
  - docs/test-plan.md
  - daemon/src/browser_memory_daemon/policy.py
  - daemon/src/browser_memory_daemon/ingest.py
  - daemon/tests/integration/test_ingest_search_forget.py
verification:
  - ADR lint + repo Markdown fence check
  - git diff --check -- .
  - ./scripts/secret-scan.sh
  - BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh with temporary Python 3.11 shim
---

# ADR-0003: Use `all` Policy Mode as the Daily-Driver Default

## Context

This ADR backfills a decision that existed before the ADR workflow was added.

Browser Memory Daemon originally needed privacy guardrails, but the daily-driver product goal shifted toward maximum personal recall. Overblocking account, local, banking-like, private-host, and other high-value pages made recall less useful for Operator's single-operator local setup.

The project still needs adjustable privacy behavior, but the default must optimize for recall rather than conservative filtering.

## Decision

We will use `policy_mode=all` as the daily-driver default.

In `all` mode, URL filtering is off, daemon redaction is off, and persistent local block rules are ignored. The DOM extractor still skips hidden, form, editable, script, style, and no-script text. The `recall`, `balanced`, and `strict` modes remain available for narrower capture postures.

## Decision drivers

- Operator wants maximum personal recall from his daily-driver browser.
- The system is local-first, loopback-only, bearer-tokened, and single-operator.
- Overblocking sensitive-looking pages loses exactly the memories most likely to matter later.
- The architecture should preserve stricter modes for tests, experiments, and future posture changes.
- DOM extraction should still avoid hidden/form/editable/script/style/no-script surfaces in every mode.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep strict as default | Conservative privacy posture | Blocks too many high-value personal recall pages | Rejected as default |
| Use balanced as default | Less overblocking than strict | Still blocks private hosts and known high-risk domains | Rejected as default |
| Use recall as default | Broad web recall with some redaction | Still blocks incognito/internal/file/non-web surfaces and redacts | Rejected as default |
| Use all as default with stricter modes retained | Maximum recall while preserving alternate postures | Stores visible secrets/private pages if browsed | Chosen |

## Decision history

- `26f0202` (2026-06-09) added adjustable capture policy modes.
- Current evidence: `daemon/src/browser_memory_daemon/policy.py` defines `DEFAULT_POLICY_MODE = POLICY_MODE_ALL` and documents the four modes.
- Current evidence: `daemon/src/browser_memory_daemon/ingest.py` bypasses URL/title/body redaction when `config.policy_mode == POLICY_MODE_ALL`.
- Current evidence: `docs/security-model.md` explicitly records `all` as the default and documents the risk acceptance.
- Current evidence: `docs/TESTS.md` and `docs/test-plan.md` include all-mode test expectations and non-all regressions.

## Consequences

- Positive: daily-driver recall captures pages that strict/balanced filters would have hidden.
- Positive: policy behavior is explicit and testable instead of implicit in scattered filters.
- Positive: future agents can preserve non-all modes without making them the product default.
- Negative: visible secrets, private account pages, email/chat/health/payment pages, and local/private hosts can be stored and indexed.
- Negative: local block rules do not protect `all` mode by design.
- Neutral: Chrome platform limits still apply where extension injection is denied.

## Verification / validation

- Verification: `policy.py` defines `all`, `recall`, `balanced`, and `strict`, with `DEFAULT_POLICY_MODE = POLICY_MODE_ALL`.
- Verification: `ingest.py` stores original URL/title/text with `redaction_count=0` in all mode.
- Verification: `daemon/tests/integration/test_ingest_search_forget.py` includes all-mode storage/no-redaction behavior.
- Verification: `scripts/real-chrome-e2e.mjs` expects sensitive-domain and localhost/private fixtures to be searchable in all mode while hidden/form/editable text remains absent.
- Backfill hygiene verification passed on 2026-06-14: ADR lint, repo Markdown fence check, `git diff --check -- .`, `./scripts/secret-scan.sh`, and `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` using a temporary Python 3.11 shim.
- Validation: the daily-driver product favors maximum local recall while retaining narrower policy modes for future runs.

## Revisit triggers

- Supersede this ADR if the system becomes multi-user or network-exposed.
- Supersede this ADR if Operator chooses privacy-first capture over maximum recall.
- Supersede this ADR before adding cloud processing, cloud search, or shared data export.
- Supersede this ADR if retention/quarantine policy becomes the primary control instead of post-hoc forget.

## References

- `docs/security-model.md`
- `docs/ARCHITECTURE.md#policy-mode-semantics`
- `docs/TESTS.md#policy-mode-verification-matrix`
- `docs/test-plan.md`
- `daemon/src/browser_memory_daemon/policy.py`
- `daemon/src/browser_memory_daemon/ingest.py`
- `scripts/real-chrome-e2e.mjs`
