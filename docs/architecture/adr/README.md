# Architecture Decision Records

> Purpose: preserve the reasoning behind architecture, design, interface, dependency, policy, and Hermes workflow decisions that future agents must understand before changing this repo.

ADRs live in this repo because Browser Memory Daemon is architecture-heavy and agent-maintained. Chat history, memory, and commit messages are not sufficient paper trails for long-lived design choices.

## Index

| ADR | Status | Decision |
|---|---|---|
| [ADR-0001](0001-use-repo-local-architecture-decision-records.md) | accepted | Use repo-local Markdown ADRs for architecture-significant changes. |

## When to create or supersede an ADR

Create or supersede an ADR when a change affects:

- component boundaries or ownership;
- Chrome extension ↔ WSL daemon interfaces;
- API, CLI, schema, event, or storage contracts;
- capture policy, redaction, security, privacy, or deletion semantics;
- major dependency/platform/provider choices;
- media sidecar, worker, cache, lifecycle, or recall architecture;
- verification strategy or real-browser e2e boundary;
- recurring Hermes/agent workflow for maintaining this repo.

Do not create an ADR for trivial bug fixes, mechanical refactors, test-only cleanup, or completed-task logs.

## Status values

| Status | Meaning |
|---|---|
| `proposed` | Drafted but not yet accepted by Operator / project direction. |
| `accepted` | Active decision; future changes should comply. |
| `rejected` | Considered and intentionally not chosen. |
| `deprecated` | Still historical, but no longer recommended. |
| `superseded` | Replaced by a later ADR; keep the old record intact and link both ways. |

## Agent workflow

1. Inspect `AGENTS.md`, `docs/README.md`, and this ADR index before architecture-impacting work.
2. Search existing ADRs for related decisions.
3. If changing an accepted decision, create a new ADR and mark the older one `superseded`; do not materially rewrite accepted history.
4. Keep ADRs short and cite real repo evidence, commands, tests, issues, commits, or research docs.
5. Record verification/validation evidence after checks run.
6. Commit the ADR with the implementation/design slice it governs.

## Template

Use [`template.md`](template.md) for new ADRs.
