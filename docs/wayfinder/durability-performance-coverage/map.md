# Wayfinder Map: Browser Memory Daemon Durability, Performance, and Coverage

## Notes

- **Foggy goal:** make Browser Memory Daemon more durable under daily-driver failures, faster/measurably performant, and substantially better covered by tests and operational consistency checks.
- **Assumptions:** repo-local Markdown is the tracker; no GitHub/Linear/Kanban remote state. Windows Chrome remains the browser surface; WSL remains durable storage owner. `policy_mode=all` remains the daily-driver default unless a later ADR supersedes it.
- **Non-goals for this map:** no cloud vector DB/LLM upload, no default Chrome profile automation, no publishing/pushing, no native-messaging rewrite unless a later ticket proves it is the next bottleneck.
- **Standing constraints:** runtime data stays under XDG paths, not the repo; captured page text is untrusted evidence; tests must not use Michael's daily Chrome profile; architecture-impacting decisions require `docs/architecture/adr/` inspection and likely an ADR.
- **Inspected context:** `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/TESTS.md`, `docs/test-plan.md`, `docs/api.md`, `docs/USER_GUIDE.md`, `docs/architecture/adr/README.md`, `scripts/install-daily-driver.sh`, `scripts/run-real-chrome-e2e.sh`, `pyproject.toml`, `extension/package.json`.
- **Current baseline from inspected docs:** 82 static tests across 15 files: 59 daemon pytest tests and 23 extension `node:test` tests. Source/test line snapshot: daemon source 4,360 LOC vs daemon tests 1,939 LOC; extension source 2,138 LOC vs extension tests 371 LOC.
- **Relevant accepted ADRs:** local-first Windows Chrome ⇄ WSL boundary, text-first SQLite/FTS5 + blobs, durable lazy media sidecars, real Chrome e2e as verification authority, C4 model as canonical architecture, generated docs as derived artifacts.

## Decisions so far

- None in this Wayfinder map yet. Existing ADR decisions listed above are context, not new decisions from this program.

## Frontier

- [001 — Establish reliability/performance/coverage baseline](tickets/001-baseline-failure-budget.md) — measure the current state and define explicit failure/performance/test budgets before broad edits.
- [002 — Add daily-driver health snapshot command](tickets/002-daily-driver-health-snapshot.md) — create one redaction-safe operator command/report for services, loopback, journals, DB freshness, queues, and extension artifact state.
- [003 — Build deterministic concurrency stress harness](tickets/003-concurrency-stress-harness.md) — produce a repeatable load test for captures, lifecycle events, search, media uploads, and media-worker passes.
- [005 — Expand HTTP API contract coverage](tickets/005-http-api-contract-coverage.md) — cover auth, malformed input, method/route errors, limits, and response consistency across endpoints.
- [006 — Expand media-worker lifecycle invariant coverage](tickets/006-media-worker-invariants.md) — prove task leases, retries, stale recovery, terminal classification, and idempotent blob writes.
- [007 — Expand extension service-worker resilience coverage](tickets/007-extension-service-worker-resilience.md) — test daemon-down/offline, queue persistence, retry/backoff, pause/rule controls, and token/config behavior.
- [008 — Expand real Chrome e2e matrix](tickets/008-real-chrome-e2e-matrix.md) — turn the real-browser authority into a broader policy/control/surface matrix without touching daily Chrome.
- [009 — Add performance benchmark harness and budgets](tickets/009-performance-benchmark-harness.md) — measure ingest/search/timeline/detail/media-worker behavior on synthetic scalable datasets.
- [011 — Harden installer/token/Windows artifact consistency](tickets/011-installer-token-artifact-consistency.md) — make daily-driver install/refresh more testable and self-validating.
- [013 — Add local UI smoke coverage](tickets/013-ui-dashboard-smoke-coverage.md) — add dashboard bootstrap/API rendering checks beyond static asset serving.

## Blocked

- [004 — Harden SQLite write-path policy](tickets/004-sqlite-write-path-hardening.md) — blocked by ticket 003's stress harness so fixes have a tight red/green loop.
- [010 — Optimize read-model query/index performance](tickets/010-read-model-query-performance.md) — blocked by ticket 009's benchmark harness and budgets.
- [012 — Design retention, compaction, and backup posture](tickets/012-retention-compaction-backup-design.md) — blocked by ticket 001 baseline; likely ADR-worthy.
- [014 — Add coverage gates and requirements traceability enforcement](tickets/014-coverage-gates-traceability.md) — blocked by ticket 001 baseline and a first wave of coverage expansion tickets.

## Fog

- Whether long-running soak tests should be local-only scripts, scheduled Hermes jobs, or manual release gates.
- Exact retention policy thresholds for full DB/text storage versus media cache; this likely needs operator preference plus storage-growth evidence.
- Whether native messaging should remain a later hardening lane or become a near-term reliability requirement after loopback/SQLite hardening.
- Whether performance budgets should gate every PR/session or stay advisory because Windows Chrome e2e is comparatively heavy.
- Whether dashboard behavior should be tested with a browser automation dependency or a lower-dependency DOM/static harness.
- Whether operational alerts should integrate with an external notification channel; remote delivery requires explicit approval.

## Handoff

Recommended next ticket: **001 — Establish reliability/performance/coverage baseline**.

Copy into a fresh session:

```text
Use the wayfinder skill on docs/wayfinder/durability-performance-coverage/map.md, ticket docs/wayfinder/durability-performance-coverage/tickets/001-baseline-failure-budget.md.
```
