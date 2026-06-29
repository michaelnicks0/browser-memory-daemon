---
id: ADR-0009
status: accepted
date: 2026-06-15
decider: Operator
scope: repo
backfilled: false
supersedes:
  - ADR-0003
superseded_by: []
related:
  - docs/architecture/adr/0003-use-all-policy-mode-as-daily-driver-default.md
  - daemon/src/browser_memory_daemon/app.py
  - daemon/src/browser_memory_daemon/policy_store.py
  - daemon/tests/e2e/test_admin_api.py
  - daemon/tests/unit/test_policy_store.py
verification:
  - python3.11 -m pytest daemon/tests/unit/test_policy_store.py daemon/tests/e2e/test_admin_api.py::test_url_prefix_policy_rule_applies_in_all_mode_without_blocking_all_localhost daemon/tests/e2e/test_cli_admin.py::test_cli_admin_commands -q
---

# ADR-0009: Apply Explicit Block Rules in `all` Mode

## Context

ADR-0003 made `policy_mode=all` the daily-driver default so Browser Memory Daemon would maximize local recall and avoid broad built-in privacy filtering. That worked for recall, but it also meant operator-created local block rules were ignored in the daily-driver mode.

A concrete localhost media case exposed the mismatch: blocking `127.0.0.1:32400` through a domain-oriented UI normalized the rule to `127.0.0.1`, and because rules were ignored in `all`, it neither blocked Plex playback capture nor provided safe port scoping if rules were later enabled.

## Decision

We will keep `policy_mode=all` as the daily-driver default, but explicit local block rules will apply in every policy mode, including `all`.

Domain rules remain host/subdomain rules only. Inputs that include ports, paths, queries, or fragments must use URL-prefix rules so local services such as `http://127.0.0.1:32400/` can be blocked without blocking all `127.0.0.1` pages.

## Decision drivers

- Operator needs maximum local recall by default, with precise opt-out controls for noisy or unwanted local surfaces.
- Explicit operator block intent should override the broad `all` posture.
- Localhost ports often represent unrelated applications; blocking one port must not suppress every loopback page.
- Domain rules should not silently discard port/path information and become broader than requested.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep ignoring local rules in `all` | Preserves ADR-0003 exactly | Operator block controls fail in the daily-driver mode | Rejected |
| Switch daily driver to `recall` | Existing local rules work | Loses intended all-mode recall and redaction posture | Rejected |
| Apply explicit block rules in `all` and require URL-prefix for scoped local ports | Honors operator intent while preserving all-mode recall | Changes ADR-0003 semantics and needs tests/docs | Chosen |

## Consequences

- Positive: explicit blocks now work in the daily-driver mode.
- Positive: URL-prefix rules can block Plex at `127.0.0.1:32400` without blocking BMD UI or other localhost ports.
- Positive: domain rules are safer because port/path inputs are rejected instead of normalized to broad host-only blocks.
- Negative: an existing overbroad domain rule can now affect `all` mode after upgrade; operators should migrate such rules to scoped URL-prefix rules before or during deployment.
- Neutral: all-mode redaction remains off, and built-in sensitive URL filtering remains off.

## Verification / validation

- Verification: `daemon/src/browser_memory_daemon/app.py` evaluates persistent rules whenever the static policy decision allows capture, including in `all` mode.
- Verification: `daemon/src/browser_memory_daemon/policy_store.py` rejects domain rules with ports/paths and returns URL-prefix-specific block reasons.
- Verification: `daemon/tests/unit/test_policy_store.py` covers port/path rejection and URL-prefix port/path scoping.
- Verification: `daemon/tests/e2e/test_admin_api.py::test_url_prefix_policy_rule_applies_in_all_mode_without_blocking_all_localhost` covers all-mode Plex blocking while `127.0.0.1:8765` remains allowed.
- Validation: the operator can block Plex playback capture at `http://127.0.0.1:32400/` while preserving capture for other localhost pages.

## Revisit triggers

- Supersede this ADR if local block rules gain allowlist precedence or richer policy actions.
- Supersede this ADR if BMD moves beyond loopback/single-operator deployment.
- Supersede this ADR if all-mode redaction or built-in URL filtering is reintroduced.

## References

- [ADR-0003](0003-use-all-policy-mode-as-daily-driver-default.md)
- `daemon/src/browser_memory_daemon/app.py`
- `daemon/src/browser_memory_daemon/policy_store.py`
- `docs/security-model.md`
- `docs/api.md`
