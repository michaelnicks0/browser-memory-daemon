---
id: ADR-0027
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes:
  - ADR-0020
superseded_by: []
related:
  - requirements/catalog.toml
  - scripts/generate_test_inventory.py
  - docs/ARCHITECTURE.md
  - docs/test-plan.md
  - docs/TESTS.md
  - docs/architecture/workspace.dsl
---

# ADR-0027: Use a canonical semantic requirement catalog

## Context

ADR-0020 established a useful static check, but requirement semantics remained duplicated in `docs/ARCHITECTURE.md` and `docs/test-plan.md`. The two documents assigned conflicting meanings to `REQ-009` through `REQ-017`, while the gate compared only row presence and path-like Markdown references. It could therefore pass while the same stable ID meant different things.

The hardening program also introduced plan-local `HRD-*` requirements. Those identifiers need explicit mappings to stable repository requirements without silently changing existing architecture meanings. Volatile test counts and requirement tables should be generated rather than copied between documents.

## Decision

1. `requirements/catalog.toml` is the sole source of normative requirement semantics.
2. Each canonical requirement records:
   - stable `REQ-NNN` ID and explicit revision;
   - normative statement, rationale, owner component, and status;
   - implementation paths;
   - unit, integration, system, operational, and validation evidence;
   - plan-local aliases where applicable.
3. Pre-catalog conflicting IDs are retained in source-qualified `legacy_aliases` records with explicit alias, split, or superseded dispositions.
4. `scripts/generate_test_inventory.py` reads the catalog with Python 3.11 `tomllib` and fails on:
   - duplicate stable IDs or aliases;
   - malformed records;
   - absent implementation paths;
   - unresolved evidence paths or test node IDs;
   - active requirements without validation evidence;
   - requirement removal without catalog disposition;
   - normative statement changes that do not increment the requirement revision relative to `HEAD`.
5. The same generator owns volatile requirement tables and static test counts in `docs/ARCHITECTURE.md`, `docs/test-plan.md`, `docs/TESTS.md`, `docs/STATUS.md`, and `docs/EXECUTIVE_BRIEF.md`.
6. `docs/architecture/workspace.dsl` models current implemented components with the `Current` tag. Planned target components remain catalog requirements until modeled explicitly with the `Target` tag.

## Consequences

### Positive

- Every stable ID has one normative meaning.
- Plan-local hardening requirements map explicitly into repository history.
- Broken implementation/evidence paths and stale test node IDs fail deterministically.
- Requirement and test-count drift becomes generated-artifact drift instead of editorial disagreement.
- Current C4 topology is no longer confused with planned target boundaries.

### Trade-offs

- Requirement changes now require catalog edits, revision discipline, and regeneration of multiple Markdown/HTML artifacts.
- The revision guard depends on Git `HEAD` when a prior catalog exists; outside a Git checkout, structural validation still runs but historical comparison is unavailable.
- Planned requirements may legitimately lack implementation and validation evidence until their phase closes, but they must remain visibly `planned`.

## Verification

- `python3.11 -m pytest -q daemon/tests/e2e/test_generate_test_inventory.py`
- `python3.11 scripts/generate_test_inventory.py --check`
- `python3.11 scripts/render_docs.py --repo . --slug browser-memory-daemon --check`
- Structurizr validation and full C4 artifact regeneration from `docs/architecture/workspace.dsl`
- `git diff --check -- .`
