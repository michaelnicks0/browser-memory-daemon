---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0029: Use a hermetic fast quality gate and measured coverage ratchet

## Context and problem statement

The broad repository gate proves the integrated system, but it did not provide a short network-free command for pre-commit feedback, enforce static quality on newly hardened modules, measure branch coverage, or prove that default XDG roots stayed untouched during the ordinary test suite.

A blanket aspirational coverage percentage would create churn without proving the highest-risk branches. The current extension queue also has a known overflow-loss defect that belongs to the Phase 5 IndexedDB outbox migration; the quality gate must expose that fact without pretending it is fixed.

## Decision drivers

- Keep verification writes inside explicit temporary roots.
- Add fast feedback without weakening the broad and real-Chrome authorities.
- Ratchet from measured evidence rather than a vanity target.
- Apply strict static checks surgically to new migration/storage modules.
- Keep known queue-overflow behavior visible until the durability redesign replaces it.

## Considered options

1. **Rely only on the broad e2e script** — rejected because it lacks coverage and targeted static checks.
2. **Enable Ruff and strict typing repository-wide immediately** — rejected as a drive-by reformat/type-conversion campaign.
3. **Set an arbitrary high coverage target** — rejected because percentage alone is not critical-branch evidence.
4. **Use a measured hermetic fast gate with targeted checks** — accepted.

## Decision outcome

Add `scripts/run-fast-gate.sh` as a network-free repository gate. It:

1. allocates an explicit `/tmp` root;
2. redirects `HOME`, `TMPDIR`, and all XDG roots into that root;
3. keeps Ruff, mypy, and coverage caches outside the repository;
4. runs targeted Ruff and strict mypy against migrations, migration steps, and storage-path code;
5. runs the full Python suite with branch coverage;
6. runs the extension Node tests;
7. checks generated requirement/test inventory, secrets, and diff whitespace;
8. fails if any file appears under the redirected default-XDG sentinel.

Coverage 7.15.0 measured the pre-ratchet Python suite at **79.95% combined line/branch coverage**. Added storage-boundary tests raised the final Phase 1.3 baseline to **80.29%**. Configure `fail_under = 80`, the integer floor proven by that final measurement. Future increases must follow a new measured green baseline; the floor must not be reduced to accommodate untested code.

The extension suite includes an explicit overflow characterization showing that the existing 100-item capture queue preserves old entries but drops the new entry without visible backpressure. This is executable defect evidence, not acceptance of the behavior. `REQ-037`/`HRD-012` remains planned until Phase 5 replaces the queue with a transactional quota-aware outbox.

## Consequences

### Positive

- One command provides deterministic pre-commit feedback without network or real-browser dependencies.
- Default XDG writes fail visibly.
- New migration and storage boundary code has strict static checks.
- Coverage has a measured ratchet instead of an invented target.
- Queue overflow and state transitions have explicit executable characterization.

### Negative

- Development environments must install Ruff, mypy, and coverage.
- The full Python suite runs under coverage in the fast gate, so it is slower than lint-only checks.
- Targeted typing does not imply repository-wide static typing.

## Validation

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-fast-gate.sh
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
```

The gate must print `FAST_GATE_PASS`; generated docs, the broad gate, and isolated real-Chrome validation remain separate release authorities.

## Supersession and rollback

This ADR does not supersede the broad or real-Chrome verification ADRs. Rollback removes the fast-gate script and tool configuration, but it must not silently lower an established coverage floor; replacement evidence and an ADR are required.
