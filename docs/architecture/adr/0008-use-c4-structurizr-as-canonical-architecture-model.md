---
id: ADR-0008
status: accepted
date: 2026-06-14
decision_date: 2026-06-14
decider: Operator
scope: repo
backfilled: true
supersedes: []
superseded_by: []
related:
  - docs/architecture/workspace.dsl
  - docs/architecture/README.md
  - docs/architecture/c4-diagrams.md
  - docs/DIAGRAMS.md
  - docs/ARCHITECTURE.md
verification:
  - ADR lint + repo Markdown fence check
  - git diff --check -- .
  - ./scripts/secret-scan.sh
  - BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh with temporary Python 3.11 shim
---

# ADR-0008: Use C4/Structurizr as the Canonical Architecture Model

## Context

This ADR backfills a decision that existed before the ADR workflow was added.

Browser Memory Daemon has enough moving parts that hand-maintained prose and ad hoc diagrams are not enough: Windows Chrome extension internals, WSL daemon components, SQLite/blob stores, media sidecars, policy modes, read/forget/doctor APIs, real-browser e2e, and daily-driver deployment all need stable architecture topology.

At the same time, the repo already has useful behavioral Mermaid diagrams for mechanics such as policy ladders, state machines, endpoint maps, and delete cascades. A single diagram format should not be forced to carry both topology and low-level behavior.

## Decision

We will use C4 with Structurizr DSL as the canonical architecture topology model under `docs/architecture/workspace.dsl`.

The generated human entrypoints are `docs/architecture/c4-diagrams.md`, per-view Markdown wrappers under `docs/architecture/diagrams/markdown/`, and generated Mermaid/DOT/Graphviz artifacts under `docs/architecture/diagrams/`. `docs/DIAGRAMS.md` remains the behavioral-diagram atlas for non-C4 mechanics. `docs/ARCHITECTURE.md` remains the narrative architecture and requirements trace.

## Decision drivers

- Architecture topology needs stable source-of-truth model-as-code, not screenshot-only diagrams.
- Different audiences need C1/C2/C3/dynamic/deployment slices instead of one hairball diagram.
- Generated Markdown wrappers make diagram review easier for agents and humans.
- Behavioral mechanics still belong in focused Markdown/Mermaid docs where C4 would be the wrong abstraction.
- Architecture artifacts should live under `docs/architecture/` with the rest of the documentation tree.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Prose-only architecture | Easy to edit | Hard to see boundaries, relationships, and deployment topology | Rejected |
| Hand-authored Mermaid only | Markdown-native and simple | Easy to drift, hard to enforce C4 levels, poor for broad topology | Rejected as sole source |
| Structurizr DSL outside docs | Model-as-code | Splits architecture artifacts from docs index | Rejected |
| C4/Structurizr under `docs/architecture/` plus behavioral diagrams elsewhere | Traceable topology and preserved mechanical detail | Requires regeneration discipline | Chosen |

## Decision history

- `2ee7dd1` (2026-06-14) added the C4 architecture model.
- `ae36fbf` (2026-06-14) added Markdown C4 diagram wrappers.
- `3e4df5c` (2026-06-14) cleaned C4 diagram renders.
- `cbef41c` (2026-06-14) added the combined C4 diagram atlas.
- `a25289f` (2026-06-14) reconciled C4 and behavioral diagrams.
- `23cd82d` (2026-06-14) moved C4 architecture under `docs/`.
- Current evidence: `docs/architecture/README.md` defines `workspace.dsl` as canonical and separates C4 from behavioral Mermaid diagrams.

## Consequences

- Positive: future agents can inspect one canonical C4 source before changing architecture topology.
- Positive: generated Markdown and rendered artifacts give a readable atlas without losing source control diffability.
- Positive: behavioral diagrams remain focused instead of being distorted into C4 topology views.
- Negative: generated files can drift unless the model is regenerated after DSL changes.
- Negative: C4 introduces additional tooling and validation steps.
- Neutral: `docs/ARCHITECTURE.md` remains current-state narrative; ADRs explain decision history.

## Verification / validation

- Verification: `docs/architecture/workspace.dsl` exists as the canonical model and `docs/architecture/README.md` documents render/validate commands.
- Verification: `docs/architecture/c4-diagrams.md` exists as the generated all-views atlas.
- Verification: `docs/DIAGRAMS.md` is framed as behavioral diagrams for mechanics C4 intentionally omits.
- Verification: prior committed evidence validated Structurizr DSL and generated 18 view wrappers/renders; future topology changes should rerun those checks.
- Backfill hygiene verification passed on 2026-06-14: ADR lint, repo Markdown fence check, `git diff --check -- .`, `./scripts/secret-scan.sh`, and `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` using a temporary Python 3.11 shim.
- Validation: architecture readers can start from a source-controlled C4 model while still finding behavioral mechanics in dedicated docs.

## Revisit triggers

- Supersede this ADR if the canonical architecture source moves away from Structurizr DSL.
- Supersede this ADR if generated diagrams are no longer checked into the repo.
- Supersede this ADR if behavioral diagrams and C4 topology are merged into a different documentation scheme.
- Supersede this ADR if the docs tree is reorganized away from `docs/architecture/`.

## References

- `docs/architecture/workspace.dsl`
- `docs/architecture/README.md`
- `docs/architecture/c4-diagrams.md`
- `docs/DIAGRAMS.md`
- `docs/ARCHITECTURE.md`
