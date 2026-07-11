---
id: ADR-0020
status: superseded
date: 2026-07-03
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by:
  - ADR-0027
related:
  - docs/TESTS.md
  - docs/test-plan.md
  - scripts/generate_test_inventory.py
  - docs/wayfinder/durability-performance-coverage/tickets/014-coverage-gates-traceability.md
verification:
  - /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_generate_test_inventory.py
  - /tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_test_inventory.py --check
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
  - /tmp/browser-memory-daemon-verify-venv/bin/python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
---

# ADR-0020: Enforce Static Requirement Traceability Gate

## Status

superseded by [ADR-0027](0027-use-canonical-semantic-requirement-catalog.md)

## Context

The repo already generated a source-level test inventory from pytest and Node `node:test` sources, but the gate only checked that `docs/TESTS.md` matched discovered test functions. Ticket 014 asked whether to enforce measured coverage and requirement-to-test traceability beyond that static inventory after the coverage expansion tickets landed.

Current measurement before choosing enforcement:

- `python -m pytest -q` passed in roughly 13.56 seconds on the local verification venv.
- `cd extension && npm test && npm run build` passed in roughly 0.45 seconds for the Node unit/build gate.
- Python line coverage tooling is not present in `requirements-dev.txt`; adding it would introduce a new dependency and a threshold choice without historical trend data.
- The generated inventory now observes 111 static tests across 23 files after the ticket 013 UI smoke coverage.

## Decision

Use `scripts/generate_test_inventory.py --check` as the hard low-cost coverage/traceability gate for now:

1. Continue enforcing the generated static source inventory in `docs/TESTS.md`.
2. Add a generated traceability report that cross-checks every `REQ-*` row in `docs/ARCHITECTURE.md` against `docs/test-plan.md`.
3. Fail the gate when `docs/test-plan.md` omits an architecture requirement row.
4. Fail the gate when file/test references in `docs/test-plan.md` point to paths that no longer exist.
5. Keep line/branch coverage thresholds advisory/deferred until the project has explicit coverage tooling and baseline trend data.

## Consequences

- Future architecture requirements must be reflected in `docs/test-plan.md` or the inventory gate fails.
- Test-plan references cannot silently drift to deleted/renamed test files.
- The gate remains cheap and deterministic; it does not execute browser captures or read runtime data.
- This is not a full statement-coverage metric. It is a traceability guard plus static test inventory until a later ADR promotes line/branch coverage thresholds.

## Verification / validation

- The focused generator tests prove pass/fail behavior for successful traceability, missing requirements, and unresolved test references.
- `docs/TESTS.md` now includes the generated traceability report.
- The gate output is redaction-safe because it scans repo Markdown and test source names only; it does not inspect runtime capture content.

## References

- `docs/TESTS.md`
- `docs/test-plan.md`
- `scripts/generate_test_inventory.py`
- `docs/wayfinder/durability-performance-coverage/tickets/014-coverage-gates-traceability.md`
