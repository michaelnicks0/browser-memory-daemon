---
title: "Coverage Baseline"
description: "Measured Python branch-coverage baseline and critical-risk verification posture"
audience: "maintainer"
status: "current"
version: "1.0.0"
date: "2026-07-10"
---

# Coverage Baseline

## Authority and command

The authoritative local measurement is the hermetic network-free gate:

```bash
BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python \
  ./scripts/run-fast-gate.sh
```

The gate redirects `HOME`, `TMPDIR`, and every XDG root into an explicit `/tmp` tree; keeps Ruff, mypy, and coverage caches outside the repository; rejects any file written beneath the redirected default-XDG sentinel; and deletes its temporary tree on exit.

## Phase 1.3 measurement

Measured with Coverage.py `7.15.0` and branch coverage enabled:

| Metric | Measured result |
|---|---:|
| Python tests | 125 passing |
| Node tests | 29 passing |
| Python statements covered | 3,543 / 4,232 (83.72%) |
| Python branches covered | 929 / 1,338 (69.43%) |
| Coverage.py combined line/branch result | **80.29%** |
| Enforced overall floor | **80%** |

The first measurement before the new direct storage-boundary tests was 79.95%. The final measured 80.29% result establishes the integer `fail_under = 80` ratchet. The floor may increase only after a new green measurement and must not be lowered merely to admit untested code.

## Critical-risk posture

Coverage percentages are supporting evidence, not substitutes for scenario assertions.

| Boundary | Combined | Branch | Executable evidence / interpretation |
|---|---:|---:|---|
| Versioned migrations | 79.53% | 66.67% | Fresh/unversioned/repeat/concurrent/checksum/newer/failure/headroom/backup/restore/FTS/FK/integrity scenarios in `test_migrations.py`. |
| Storage-path containment | 96.19% | **100.00%** | Direct grammar, traversal, symlink, outside-root, missing-file, and explicit-root tests in `test_storage_paths.py`, plus integration callers. |
| Forget/deletion selection | 85.63% | 76.09% | Literal selector, policy-mode, scope, containment, and receipt cases in ingest/search/forget integration tests. Crash-recoverable tombstones remain Phase 3 work. |
| Media core | 76.73% | 67.77% | Guarded fetch/HLS/path/cache/task tests cover the current module. Transactional admission/global resource budgets remain Phase 4 work. |
| Media worker state transitions | 89.33% | 89.29% | Retry, lease, terminal, and convergence scenarios are executable. |

## Extension queue boundary

Node tests are not included in the Python coverage percentage. They run in the same fast gate.

The suite now explicitly characterizes capture-queue overflow: with 100 stored captures and an offline daemon, the existing queue preserves the 100 old entries but drops the newly submitted capture without visible backpressure. That passing test is **defect evidence**, not acceptance. `REQ-037` / `HRD-012` remains planned until Phase 5 delivers the transactional IndexedDB outbox, byte quotas, visible overflow, and restart-safe claims.

Media queue due-state tests cover pending, deferred retry, stale processing, malformed processing timestamps, terminal states, fetched-blob retention, and delete cleanup.

## Static-analysis scope

Ruff and strict mypy are intentionally limited to:

- `migrations.py`;
- `migration_steps/`;
- `storage_paths.py`.

This is a targeted quality ceiling for newly hardened boundary code, not a claim that the entire legacy daemon is strictly typed or Ruff-clean. New migration/storage/state-machine modules should enter this scope when added.

## Ratchet rule

1. Run the fast gate from a clean checkout.
2. Preserve the JSON/report output outside the repository when changing the floor.
3. Add branch-specific tests for new critical behavior.
4. Raise the floor only after a repeated green measurement.
5. Never reduce the floor without a documented exceptional rationale and superseding ADR.
