---
id: ADR-0022
status: accepted
date: 2026-07-08
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - docs/api.md
  - docs/USER_GUIDE.md
  - docs/CLI_UX_CONTRACT.md
  - daemon/src/browser_memory_daemon/ops.py
  - daemon/src/browser_memory_daemon/daily_driver_health.py
  - daemon/src/browser_memory_daemon/schema.sql
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/unit/test_daily_driver_health.py daemon/tests/e2e/test_admin_api.py daemon/tests/e2e/test_cli_admin.py
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_media_worker.py
  - /tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_test_inventory.py --check
  - /tmp/browser-memory-daemon-verify-venv/bin/python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
  - ./scripts/daily-driver-health.sh --journal-since '1 hour ago' --no-fail
---

# ADR-0022: Use fast doctor and media-queue health telemetry

## Context

A daily-driver health review showed the core text/FTS path was healthy, but two operational blind spots remained:

- `/doctor` performed recursive clean-text/media filesystem walks on every request. On large or NAS-backed blob roots, this made routine health checks slow even when the daemon and database were healthy.
- `daily-driver-health` reported media queue backlog counts, but not enough evidence to distinguish a dead worker from a live worker draining a backlog. Due-task and lease checks also need to compare mixed SQLite `CURRENT_TIMESTAMP` and ISO-`T` timestamp strings as datetimes, not as plain strings.

The daemon remains a local Windows Chrome ↔ WSL service. Health output must stay redaction-safe: aggregate counts and timings are acceptable; captured page text, snippets, raw URLs, cookies, bearer tokens, and token values are not.

## Decision

We will keep `/doctor` as the fast routine diagnostic endpoint by default:

- default `/doctor` returns DB-derived storage counts from SQLite metadata;
- `/doctor?storage_census=full` and CLI `doctor --storage-census` opt into exact filesystem file walks;
- daily-driver health expands media queue telemetry with due counts by task/artifact status, oldest due age, stale lease age, latest media-worker run, and 1h/24h worker throughput;
- queue due/stale checks use SQLite datetime normalization for mixed timestamp formats;
- schema indexes support health reads over media-task lease state and media-worker audit history.

## Decision drivers

- Routine health checks should be fast enough for operator use and automated smoke checks.
- Exact filesystem census is still useful after migrations, purges, or manual cleanup, but should be explicit.
- Media backlogs are warnings unless stale leases, service failures, or missing worker throughput show real failure.
- Health output must remain aggregate and redaction-safe.
- The solution should preserve local SQLite/FTS and avoid new monitoring dependencies.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep `/doctor` recursive by default | Exact file counts every time. | Slow on large/NAS media roots; routine diagnostics appear degraded when only census is expensive. | Rejected. |
| Remove filesystem counts entirely | Fastest and simplest. | Loses exact post-migration/purge verification. | Rejected. |
| Default to DB-derived counts with opt-in filesystem census | Fast routine checks while preserving exact checks when needed. | DB-derived clean-text byte count is an estimate from stored chunk text, not file stat bytes. | Chosen. |
| Add external metrics/alerting | Better long-term observability. | Requires delivery/channel decisions and is outside local-only scope. | Deferred. |

## Consequences

- Positive: `/doctor` is suitable again for routine health probes.
- Positive: media backlog reports include enough evidence to tell whether the worker is alive and making progress.
- Positive: stale-lease and due-task detection no longer depends on lexical timestamp ordering.
- Neutral: default storage bytes are DB-derived/estimated; exact file stats require `storage_census=full`.
- Neutral: the media queue can still backlog on slow/expired public media, but backlog age/throughput is now visible.

## Verification / validation

- Verification: unit tests cover mixed timestamp due/stale-lease detection and worker throughput aggregates.
- Verification: e2e API and CLI tests cover fast default `/doctor` plus opt-in filesystem census.
- Verification: test inventory and generated docs checks keep requirements/docs traceability intact.
- Validation: daily-driver live smoke should show fast `/doctor`, richer `database.media_queue`, and worker throughput without dumping captured URLs or text.

## Revisit triggers

- Supersede if media worker backlog remains chronically above the operator's tolerance after telemetry is visible.
- Supersede if exact filesystem census becomes cheap enough to restore as default.
- Supersede if health output moves to an external metrics/alerting system.

## References

- ADR-0005: durable lazy media sidecars with a bounded cache.
- ADR-0014: WAL and bounded SQLite contention policy.
- ADR-0018: daily-driver headroom and service-start budgets.
