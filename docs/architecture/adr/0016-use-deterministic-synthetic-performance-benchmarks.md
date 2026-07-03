---
id: ADR-0016
status: accepted
date: 2026-07-03
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - docs/wayfinder/durability-performance-coverage/tickets/009-performance-benchmark-harness.md
  - scripts/run-performance-benchmarks.sh
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_performance_benchmarks.py
  - ./scripts/run-performance-benchmarks.sh --small --json >/tmp/bmd_benchmark.json
---

# ADR-0016: Use deterministic synthetic performance benchmarks

## Context

The durability/performance Wayfinder identified that baseline live-system checks were useful but not enough to guide read-model and storage optimization. Ticket 010 needs repeatable benchmark evidence before changing indexes, pagination, read-audit writes, or storage behavior. The benchmark input must not use live captured page text, must run locally, and must produce both machine-readable data for agents and compact human-readable output for operators.

## Decision

We will maintain a repo-local deterministic synthetic benchmark harness as the performance evidence source for ingest, read surfaces, media-worker task selection/maintenance, read-endpoint audit writes, and SQLite/blob sidecar growth.

The harness is advisory by default: it reports explicit local budgets and whether they were exceeded, but budget misses do not fail the command until a later ADR/ticket converts a measured threshold into a hard gate.

## Decision drivers

- The benchmark must be repeatable without uploading data or using live browser captures.
- Agents need JSON output to compare before/after changes for ticket 010 and future tuning work.
- Operators need a short summary when running the benchmark manually.
- Initial budgets need evidence before becoming hard gates.
- Benchmark runtime must stay small enough to run during local development and Wayfinder ticket closure.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Live daily-driver benchmark | Realistic data and workload. | Uses Michael's real captured data, risks long runtime and unstable results, and can mutate live state. | Rejected. |
| Synthetic deterministic local benchmark | Repeatable, safe, no captured text fixtures, works in temp WSL runtime roots. | Less representative than live data; budgets need calibration. | Chosen. |
| Hard performance gate immediately | Prevents regressions early. | Premature without enough historical benchmark evidence; likely noisy across WSL/Windows hosts. | Rejected for now. |

## Consequences

- Positive: ticket 010 can use JSON benchmark output as the baseline for query/index optimization.
- Positive: benchmark data stays under temporary or explicit runtime roots, not in the repo.
- Positive: read surfaces include both direct function cost and endpoint-style audit-write cost estimates.
- Neutral / operational: advisory budgets may report exceeded thresholds without failing; agents must read the JSON instead of assuming command success means performance is good.
- Negative: synthetic text/media fixtures do not capture all real-world page-shape variance.

## Verification / validation

- Verification: focused test `daemon/tests/e2e/test_performance_benchmarks.py` checks JSON shape, synthetic-source labeling, media-worker task counts, storage sidecar reporting, and human summary output.
- Verification: `scripts/run-performance-benchmarks.sh --small --json` emits a parseable JSON summary with ingest/read/media/storage/budget sections.
- Validation: the harness produces the evidence ticket 010 needs without touching daily-driver Chrome, remote services, or live captured browsing text.

## Revisit triggers

- Supersede this ADR if benchmark budgets become hard CI/local gates.
- Supersede this ADR if benchmarks start using anonymized/fixture-captured corpora instead of purely synthetic generated text.
- Revisit if the default small profile becomes too slow for routine Wayfinder ticket verification.

## References

- `docs/wayfinder/durability-performance-coverage/tickets/009-performance-benchmark-harness.md`
- `scripts/run-performance-benchmarks.sh`
- `daemon/src/browser_memory_daemon/performance_benchmarks.py`
