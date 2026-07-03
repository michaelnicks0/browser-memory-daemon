# Add coverage gates and requirements traceability enforcement

## Status
closed

## Question
After a first wave of new tests lands, should the repo enforce measured coverage and requirement-to-test traceability beyond the generated static inventory?

## Type
task

## Inputs / links

- `docs/TESTS.md`
- `docs/test-plan.md`
- `scripts/generate_test_inventory.py`
- `pyproject.toml`
- `extension/package.json`
- Ticket 001 baseline
- Coverage-expanded tickets 005, 006, 007, 008, and 013

## Blocks / blocked by

- Blocks: future regression policy and release gates.
- Blocked by: none. Coverage-expanded tickets 005, 006, 007, 008, and 013 are closed.

## Resolution

Closed with a measured static inventory/traceability gate rather than premature line-coverage thresholds.

Measurement before choosing enforcement:

- `/usr/bin/time -f 'pytest_elapsed=%e' /tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q` passed in about 13.56s.
- `/usr/bin/time -f 'extension_elapsed=%e' bash -lc 'cd extension && npm test && npm run build'` passed in about 0.45s.
- `coverage` was not installed in the verification venv / `requirements-dev.txt`, so hard line/branch thresholds would require a new dependency plus baseline trend data. Deferred by ADR-0020.
- Static inventory after this ticket: 111 source-level tests across 23 files, with 84 daemon pytest tests and 27 extension `node:test` tests.

Implemented gate:

- `scripts/generate_test_inventory.py --check` still verifies generated `docs/TESTS.md` inventory freshness.
- The same gate now verifies every architecture `REQ-*` row in `docs/ARCHITECTURE.md` appears in `docs/test-plan.md`.
- The gate now fails when `docs/test-plan.md` references missing test/source paths, catching stale traceability links after file renames/deletions.
- `docs/TESTS.md` renders the generated traceability report; ADR-0020 records the verification-strategy decision.

Evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_generate_test_inventory.py
# 2 passed

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_test_inventory.py --check
# docs/TESTS.md ok: 111 tests / 23 files (84 pytest, 27 node:test)

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_test_inventory.py --json
# trace_ok=True; architecture requirements=17; tests=111; files=23

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
# passed: daemon pytest, extension node:test/build, real Chrome for Testing all+strict matrix, secret scan, whitespace check

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_showcase.py --spec scripts/showcase.spec.json --check
# browser-memory-daemon-high-level-doc.html ok

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
# 79 rendered docs match source

cd extension && npm test && npm run build
# 27 node:test tests passed; extension build passed

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-real-chrome-e2e.sh
# passed: real Chrome for Testing all+strict matrix

./scripts/secret-scan.sh && git diff --check -- .
# passed
```

## New tickets / fog updates

No new ticket. Line/branch coverage thresholds remain intentionally deferred until coverage tooling is added and trend data exists; the current hard gate is static inventory + requirements traceability.
