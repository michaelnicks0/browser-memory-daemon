---
id: ADR-0025
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes: []
superseded_by: []
related:
  - docs/architecture/adr/0006-use-forget-cascade-with-deletion-receipts.md
  - docs/security-model.md
  - docs/api.md
  - docs/CLI_UX_CONTRACT.md
  - daemon/src/browser_memory_daemon/forget.py
verification:
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_ingest_search_forget.py daemon/tests/e2e/test_http_api.py daemon/tests/e2e/test_cli_admin.py
---

# ADR-0025: Use literal and policy-aware forget selectors

## Context

ADR-0006 established the forget cascade and deletion receipts. The selector boundary still needs hardening because deletion is destructive:

- a request with both `domain` and `url` previously selected the domain branch implicitly;
- domain input was lowercased directly rather than parsed as a literal hostname;
- URL forget always applied redaction before matching, which made `all` mode unable to forget exact unredacted stored URLs containing sensitive query/path material;
- deletion receipts must not preserve the URL secrets the operator just deleted.

The daemon now supports multiple policy modes. `all` stores literal URL/title/text; `recall`, `balanced`, and `strict` store redacted URL metadata. Forget selectors must therefore match the storage representation for the active policy while keeping receipts redaction-safe.

## Decision

Forget requests shall accept exactly one selector:

- `domain`: a literal hostname only; no URL, path, query, userinfo, wildcard, SQL wildcard, or port syntax. The domain scope continues to include subdomains for compatibility with ADR-0006's domain-suffix behavior.
- `url`: an absolute URL. In `all` mode, matching uses the literal URL because storage is unredacted. In non-`all` modes, matching uses the same redacted URL representation used at ingest time.

Deletion receipts shall record a redaction-safe selector scope:

- URL scopes are redacted before receipt storage even when `all` mode used the literal URL for matching.
- Scope metadata records the selector policy (`literal`, `redacted`, or `domain-suffix`) without storing deleted page body text or secrets.

## Decision drivers

- Destructive APIs must fail closed on ambiguous selector input.
- `all` mode forget must be able to delete exactly the literal memory it stored.
- Non-`all` mode forget must remain able to delete records whose URLs were redacted before storage.
- Receipts should prove action/counts without retaining the secret selector value.
- The change should preserve the current database schema and the existing domain-suffix deletion behavior.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep unconditional URL redaction | Preserves old receipt shape | Cannot forget some `all` mode literal URLs; ambiguous both-selector requests remain | Rejected |
| Always match both literal and redacted URL forms | More likely to find records after policy changes | Broadens deletion for token-collapsed redacted URLs and makes receipts harder to reason about | Rejected |
| Match by active storage policy and redact receipt scope | Exact for `all`, compatible for non-`all`, redaction-safe evidence | If policy mode changed since capture, the operator may need to use a domain selector or the stored URL form | Chosen |
| Make domain exact-only now | Narrowest destructive behavior | Breaks established ADR-0006/UI expectation that domain forget includes subdomains | Deferred |

## Consequences

- Positive: `/forget` and CLI forget reject missing or both selectors before mutation.
- Positive: domain selectors cannot accidentally accept full URLs, wildcards, paths, queries, ports, or userinfo.
- Positive: all-mode URL forget works for literal stored URLs while receipts avoid storing URL secrets.
- Positive: strict/balanced/recall URL forget continues to work with original input by applying ingest-equivalent redaction.
- Neutral: domain forget still includes subdomains; this remains documented as `domain-suffix` scope.
- Negative: if an operator changes policy mode after capture, URL forget follows the current mode's storage representation rather than trying every historical representation.

## Verification / validation

- `daemon/tests/integration/test_ingest_search_forget.py` covers all-mode literal URL forget with redaction-safe receipt scope, strict-mode redacted URL forget, and selector validation.
- `daemon/tests/e2e/test_http_api.py` covers API rejection for both selectors.
- `daemon/tests/e2e/test_cli_admin.py` covers CLI rejection for missing and both selectors.

## Revisit triggers

- Supersede if domain forget becomes exact-only by default or grows an explicit `include_subdomains` flag.
- Revisit if deletion scopes expand to document IDs, snapshot IDs, policy rules, date ranges, or arbitrary query selectors.
- Revisit if receipts need cryptographic proofs, tombstones, backup erasure semantics, or raw-selector escrow.

## References

- `daemon/src/browser_memory_daemon/forget.py`
- `daemon/tests/integration/test_ingest_search_forget.py`
- `daemon/tests/e2e/test_http_api.py`
- `daemon/tests/e2e/test_cli_admin.py`
