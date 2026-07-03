# Wayfinder Map: Browser Memory Daemon Durability, Performance, and Coverage

## Notes

- **Foggy goal:** make Browser Memory Daemon more durable under daily-driver failures, faster/measurably performant, and substantially better covered by tests and operational consistency checks.
- **Assumptions:** repo-local Markdown is the tracker; no GitHub/Linear/Kanban remote state. Windows Chrome remains the browser surface; WSL remains durable storage owner. `policy_mode=all` remains the daily-driver default unless a later ADR supersedes it.
- **Non-goals for this map:** no cloud vector DB/LLM upload, no default Chrome profile automation, no publishing/pushing, no native-messaging rewrite unless a later ticket proves it is the next bottleneck.
- **Standing constraints:** runtime data stays under XDG paths, not the repo; captured page text is untrusted evidence; tests must not use Michael's daily Chrome profile; architecture-impacting decisions require `docs/architecture/adr/` inspection and likely an ADR.
- **Inspected context:** `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/TESTS.md`, `docs/test-plan.md`, `docs/api.md`, `docs/USER_GUIDE.md`, `docs/architecture/adr/README.md`, `scripts/install-daily-driver.sh`, `scripts/run-real-chrome-e2e.sh`, `pyproject.toml`, `extension/package.json`.
- **Current baseline from inspected docs:** 88 static tests across 17 files: 65 daemon pytest tests and 23 extension `node:test` tests. Source/test line snapshot from ticket 001: daemon source 4,360 LOC vs daemon tests 1,939 LOC; extension source 2,138 LOC vs extension tests 371 LOC.
- **Relevant accepted ADRs:** local-first Windows Chrome ⇄ WSL boundary, text-first SQLite/FTS5 + blobs, durable lazy media sidecars, real Chrome e2e as verification authority, C4 model as canonical architecture, generated docs as derived artifacts.

## Decisions so far

- [001 — Establish reliability/performance/coverage baseline](tickets/001-baseline-failure-budget.md) — baseline captured 2026-07-03 UTC: full gate passed, live daily-driver services and DB integrity were OK, media-worker journal history exposed a resolved no-space start-failure class, and read-model endpoints need deterministic benchmark budgets.
- [002 — Add daily-driver health snapshot command](tickets/002-daily-driver-health-snapshot.md) — added `daily-driver-health` plus `scripts/daily-driver-health.sh`, a redaction-safe aggregate over services, loopback, journals, DB freshness, media queue, storage headroom, and extension artifacts.
- [003 — Build deterministic concurrency stress harness](tickets/003-concurrency-stress-harness.md) — added a temp-runtime stress harness for concurrent captures, lifecycle events, reads, media blob uploads, and media-worker passes against one SQLite DB.
- [004 — Harden SQLite write-path policy](tickets/004-sqlite-write-path-hardening.md) — enforced WAL/synchronous/busy-timeout pragmas, skipped repeated request-time DB initialization after startup, increased loopback listen backlog, isolated concurrent media temp writes, and recorded ADR-0014.
- [006 — Expand media-worker lifecycle invariant coverage](tickets/006-media-worker-invariants.md) — routed manual/background media fetch through the durable task lease path and covered active/stale leases, retry backoff, idempotent stored rows, and `media_fetch_on_capture=True`.
- [016 — Shorten transaction boundaries and capture idempotency](tickets/016-shorten-transaction-boundaries-and-idempotency.md) — staged clean-text writes before short capture transactions, made duplicate captures/chunks/FTS idempotent, enforced semantic policy-rule uniqueness, and recorded ADR-0015.
- [005 — Expand HTTP API contract coverage](tickets/005-http-api-contract-coverage.md) — covered JSON auth/error/malformed/unknown-method behavior, limit bounds, and duplicate policy-rule HTTP semantics.
- [007 — Expand extension service-worker resilience coverage](tickets/007-extension-service-worker-resilience.md) — added a mocked-Chrome service-worker harness proving daemon-down queue persistence, pause/token/rule controls, and media-upload retry blob retention.
- [008 — Expand real Chrome e2e matrix](tickets/008-real-chrome-e2e-matrix.md) — default Chrome for Testing e2e now runs `all` + `strict` and covers pause, explicit URL-prefix block, media, lifecycle, queue drainage, and mode-specific sensitive/local expectations.
- [009 — Add performance benchmark harness and budgets](tickets/009-performance-benchmark-harness.md) — added deterministic synthetic JSON/human benchmarks for ingest, read surfaces with audit-write overhead, media-worker selection/run, sidecar growth, and advisory budgets; recorded ADR-0016.
- [010 — Optimize read-model query/index performance](tickets/010-read-model-query-performance.md) — added measured composite SQLite indexes for recent/timeline/detail/media queue read ordering, preserved API/audit contracts, and recorded ADR-0017.
- [011 — Harden installer/token/Windows artifact consistency](tickets/011-installer-token-artifact-consistency.md) — added non-mutating install dry-run/check modes plus token/env/unit/process-arg/extension artifact health checks without printing token values.

## Frontier

- [015 — Add storage-headroom and service-start failure budget checks](tickets/015-storage-headroom-service-start-budget.md) — turn the no-space systemd failure class into preflight/health checks and a journal budget.
- [012 — Design retention, compaction, and backup posture](tickets/012-retention-compaction-backup-design.md) — now unblocked by the baseline; use current DB/media/headroom evidence plus explicit operator thresholds.
- [013 — Add local UI smoke coverage](tickets/013-ui-dashboard-smoke-coverage.md) — add dashboard bootstrap/API rendering checks beyond static asset serving.
- [014 — Add coverage gates and requirements traceability enforcement](tickets/014-coverage-gates-traceability.md) — now unblocked by ticket 006 coverage expansion, but still best near the end after more coverage tickets land.

## Blocked

None.

## Fog

- Whether long-running soak tests should be local-only scripts, scheduled Hermes jobs, or manual release gates.
- Exact retention policy thresholds for full DB/text storage versus media cache; this likely needs operator preference plus storage-growth evidence.
- Whether native messaging should remain a later hardening lane or become a near-term reliability requirement after loopback/SQLite hardening.
- Whether performance budgets should gate every PR/session or stay advisory because Windows Chrome e2e is comparatively heavy.
- Whether dashboard behavior should be tested with a browser automation dependency or a lower-dependency DOM/static harness.
- Whether operational alerts should integrate with an external notification channel; remote delivery requires explicit approval.

## Handoff

Open frontier tickets: 4. Blocked tickets: 0.

Recommended next ticket: **015 — Add storage-headroom and service-start failure budget checks**. Installer consistency is now self-validating; the next operational gap is making health/preflight output distinguish low filesystem headroom and service-start churn before daily-driver failures.

Copy into a fresh session:

```text
Use the wayfinder skill on docs/wayfinder/durability-performance-coverage/map.md, ticket docs/wayfinder/durability-performance-coverage/tickets/015-storage-headroom-service-start-budget.md.
```
