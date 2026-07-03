---
id: ADR-0018
status: accepted
date: 2026-07-03
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - docs/wayfinder/durability-performance-coverage/tickets/015-storage-headroom-service-start-budget.md
  - daemon/src/browser_memory_daemon/daily_driver_health.py
  - scripts/daily-driver-health.sh
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/unit/test_daily_driver_health.py daemon/tests/e2e/test_cli_admin.py
  - ./scripts/daily-driver-health.sh --journal-since '1 hour ago' --no-fail >/tmp/bmd_daily_health_015.json
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
  - /tmp/browser-memory-daemon-verify-venv/bin/python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
---

# ADR-0018: Enforce daily-driver headroom and start-failure budgets

## Context

Ticket 001 captured a resolved daily-driver failure class where the media-worker service hit repeated systemd start failures around `No space left on device` / `resources`. Existing health checks reported aggregate storage and journal state, but did not attach explicit warning/error budgets to low filesystem headroom or service-start churn.

This repo runs a local Windows Chrome ⇄ WSL daemon. The operator needs redaction-safe health output that fails early on operational preconditions before the daemon reaches systemd start-limit or storage exhaustion behavior.

## Decision

Daily-driver health will enforce explicit local budgets for:

- WSL config/data/state/clean-text/media and Windows extension artifact filesystem headroom;
- systemd `NRestarts` churn per daily-driver unit;
- recent journal start-failure patterns per daily-driver unit.

The health JSON will report thresholds and statuses without captured page text, raw captured URLs, token values, or cookies. Defaults are intentionally conservative and locally overrideable with `BMD_HEALTH_*` environment variables.

## Decision drivers

- Fail before storage exhaustion causes start-limit or `resources` failures.
- Keep operator output machine-readable and redaction-safe.
- Avoid adding a remote monitoring or alerting dependency.
- Keep retention/compaction design separate; this decision only defines health/preflight detection.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Report raw disk usage and journals only | Simple; no hard semantics. | Repeats the failure class by making operators infer budgets manually. | Rejected. |
| Enforce fixed local budgets in health JSON | Clear warning/error behavior; works in scripts and installer checks. | Thresholds may need tuning per host capacity. | Chosen, with env overrides. |
| Add external alerting now | Better proactive notification. | Requires delivery channel and approval; outside local-only scope. | Deferred. |

## Consequences

- Positive: `daily-driver-health` and installer check paths can fail fast on low headroom or repeated service-start churn.
- Positive: threshold values are visible in JSON for downstream scripts.
- Neutral: default budgets are preflight/health semantics, not retention policy.
- Negative: very small test or VM filesystems may need `BMD_HEALTH_*` overrides to avoid hard errors.

## Verification / validation

- Verification: focused daily-driver health tests cover redaction, token/process secrecy, low-headroom status, restart budget status, and service-start journal budget status.
- Validation: the resolved 2026-06-27/28 failure class is now represented as a machine-readable service-start budget instead of an operator-only journal clue.

## Revisit triggers

- Supersede if ticket 012 defines retention/compaction semantics that require different hard thresholds.
- Supersede if health output moves from local preflight to external alert delivery.
- Revisit defaults after long-running daily-driver soak data establishes better host-specific thresholds.

## References

- `docs/wayfinder/durability-performance-coverage/tickets/015-storage-headroom-service-start-budget.md`
- `docs/wayfinder/durability-performance-coverage/tickets/001-baseline-failure-budget.md`
