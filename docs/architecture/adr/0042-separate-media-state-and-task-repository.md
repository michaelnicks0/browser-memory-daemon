# ADR-0042: Separate Media State and Task Repository from the Compatibility Facade

- **Status:** accepted
- **Date:** 2026-07-10
- **Decision owners:** Browser Memory Daemon maintainers
- **Related:** ADR-0005, ADR-0014, ADR-0015, ADR-0039, ADR-0040, REQ-017, REQ-022, REQ-036, HRD-011

## Context

`media.py` had become the owner of unrelated concerns: caller payload parsing, artifact persistence, cache admission, guarded public fetch, HLS assembly, task creation, lease selection, retry/backoff, and read models. The public functions were already used by HTTP, worker, benchmark, ingest, and test callers, so a flag-day rename would create compatibility risk.

Task state also mixed ordinary worker progression with historical normalization and explicit requeue. Terminal task states were preserved by SQL convention, but the permitted state vocabulary and force-reset exception were not represented in one inspectable model. Internal artifact recovery states (`purging`, `missing`) existed outside the caller-accepted capture status set.

## Decision

1. Add `media_models.py` as the authority for:
   - caller-accepted capture statuses;
   - internal artifact recovery statuses;
   - media task statuses;
   - fetch-error outcome classification;
   - explicit ordinary artifact/task transition matrices;
   - the explicit terminal-task force-reset exception.
2. Add `media_tasks.py` as the durable task repository and workflow boundary for:
   - deterministic task identity;
   - idempotent task creation;
   - terminal-state preservation and explicit force reset;
   - due-task selection and atomic leasing;
   - stale-lease recovery;
   - retry/backoff and terminal task outcomes.
3. Keep `media.py` as a compatibility facade while extraction proceeds. Existing public imports remain available and the facade injects artifact fetch/store behavior into the task processor instead of creating a circular dependency.
4. Make `media_worker.py` depend directly on the state model and task repository while retaining the existing artifact fetch/store function.
5. Do not add database `CHECK` constraints in this slice. Historical rows and recurring normalizers must first be converted through an ordered migration or explicit operator requeue; schema enforcement follows only after fixture-backed normalization evidence.

## Alternatives considered

### Rewrite all media call sites at once

Rejected. HTTP, benchmark, ingest, worker, and tests already depend on the facade. A compatibility-first extraction is smaller and reversible.

### Leave status sets and SQL in `media.py`

Rejected. It preserves the mixed ownership that made task transitions and terminal-state exceptions difficult to audit.

### Add status `CHECK` constraints immediately

Rejected for this slice. Current worker startup still performs historical normalization scans, so enforcing constraints before one-time normalization and migration evidence would couple two rollback domains.

### Introduce a generic job framework or ORM

Rejected. The media task table and standard-library SQLite code are sufficient; a framework would violate the standard-library-first boundary without solving a measured problem.

## Consequences

### Positive

- Worker leasing and retry behavior have one repository boundary.
- Caller-visible and internal recovery states are distinct and testable.
- Existing public `media.py` imports remain compatible.
- Concurrent claim and terminal force-reset semantics have direct integration evidence.
- Later artifact-store, fetch/HLS, and explicit-requeue extraction can proceed independently.

### Costs and residual risks

- `media.py` remains large until later extraction slices complete.
- Transition matrices document ordinary progression but are not yet database constraints.
- Historical normalization scans still run in every worker pass; a later migration/requeue slice must remove them.
- Task processing still calls the compatibility facade for artifact fetch/store until those modules are extracted.

## Verification and validation

Focused evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q \
  daemon/tests/unit/test_media_models.py \
  daemon/tests/integration/test_media_tasks.py \
  daemon/tests/integration/test_media_worker.py
```

The tests prove:

- public facade symbols remain compatible;
- internal recovery statuses are not caller-selectable;
- terminal task states require explicit force reset;
- two concurrent workers cannot both own one task lease;
- existing worker success, retry, HLS, normalization, purge/rehydration, and upload behavior remains intact.

Phase-level fast, broad, concurrency, generated-document, and isolated real-Chrome evidence is recorded by the repository verification gates before commit.
