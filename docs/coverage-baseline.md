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
| Media core | 81.25% | 72.77% | Current post-audit Phase 4 measurement across `media.py` and all `media_*` modules: 1,607/1,910 statements and 473/650 branches. Guarded streaming fetch/HLS, initial-open request budgeting, response-body deadlines, bounded playlist sniffing, process budgets, transactional cache reservations, failure cleanup, bounded reconciliation, and explicit requeue paths have executable evidence. |
| Media worker state transitions | 89.33% | 89.29% | Retry, lease, terminal, and convergence scenarios are executable. |

## Extension queue boundary

Node tests are not included in the Python coverage percentage. They run in the same fast gate.

The media-core row was remeasured after late Phase 4 transport-audit remediation on 2026-07-10. The Phase 1.3 repository baseline and 80% ratchet above remain the historical floor-setting measurement.

The extension suite now verifies that the versioned IndexedDB capture/lifecycle outbox preserves existing rows at the 100-item capture limit and visibly rejects the new message, rather than silently slicing a whole-array `chrome.storage.local` queue. It also covers concurrent admission, token-checked claims, retry due times, stale-claim recovery, legacy-array import, serialized-byte accounting, daemon-outage restart, and capture-result checkpointing before media compensation. `REQ-037` / `HRD-012` remains planned until enforced byte quotas, operator-facing telemetry, and specialized media queue quota/cleanup behavior close.

Media queue due-state tests cover pending, deferred retry, stale processing, malformed processing timestamps, terminal states, fetched-blob retention, and delete cleanup.

## Static-analysis scope

Ruff and strict mypy use an explicit 30-file inventory covering migrations, storage-path and blob boundaries, media state/tasks/store/transport/HLS/resources/worker/orchestration, text authority, lifecycle, and related operator workflows. This is a targeted quality ceiling for hardened boundary code, not a claim that the entire legacy daemon is strictly typed or Ruff-clean. New migration/storage/state-machine/transport modules enter this scope when added.

## Ratchet rule

1. Run the fast gate from a clean checkout.
2. Preserve the JSON/report output outside the repository when changing the floor.
3. Add branch-specific tests for new critical behavior.
4. Raise the floor only after a repeated green measurement.
5. Never reduce the floor without a documented exceptional rationale and superseding ADR.
