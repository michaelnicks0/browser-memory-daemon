---
id: ADR-0001
status: accepted
date: 2026-06-14
decider: Operator
scope: repo
supersedes: []
superseded_by: []
related:
  - docs/ARCHITECTURE.md
  - docs/test-plan.md
  - [removed-publication-dossier]
verification:
  - git diff --check -- .
  - markdown fence check over repo Markdown files
  - ./scripts/secret-scan.sh
---

# ADR-0001: Use Repo-Local Architecture Decision Records

## Context

Browser Memory Daemon has accumulated long-lived architecture decisions across several surfaces: Windows Chrome extension boundaries, WSL daemon ownership, local-only storage, policy modes, media sidecars, deletion semantics, C4 diagrams, and real-browser verification.

The repo already has strong architecture documentation in `docs/ARCHITECTURE.md`, verification traceability in `docs/test-plan.md`, and local research dossiers for hardening work. Those documents describe the current architecture well, but they do not provide a small change-by-change decision ledger for future agents to answer: “Why was this direction chosen, what alternatives were rejected, and what evidence made it acceptable?”

Hermes chat history and persistent memory are not the right storage layer for that rationale. Chat history can be hard to reconstruct during future repo work, and memory is global, small, and not repo-local. Future agents need the decision trail beside the code and docs they are modifying.

## Decision

We will keep repo-local Markdown Architecture Decision Records under `docs/architecture/adr/` for architecture-significant Browser Memory Daemon changes.

Each ADR will be a small Markdown file named `NNNN-short-title.md`, indexed from `docs/architecture/adr/README.md`, and written from `docs/architecture/adr/template.md`. Accepted ADRs are historical records; if a decision changes materially, a later ADR will supersede the older one instead of rewriting it in place.

## Decision drivers

- Future agents need a durable paper trail that survives session compaction, chat loss, and repo handoffs.
- Browser Memory Daemon design choices often involve privacy, security, storage, and Chrome/WSL boundary tradeoffs.
- ADRs should stay close to implementation and verification artifacts so design rationale changes with the code.
- `AGENTS.md` should contain the operating rule and pointer, not the full decision archive.
- The first slice should be Markdown-only and dependency-light; validators or automation can wait until the process is proven useful.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep rationale only in chat/session history | Zero repo changes | Hard to find later; not tied to commits; brittle across compaction or handoff | Rejected |
| Store decisions in Hermes memory | Always visible to Hermes | Global, tiny, not project-local, pollutes every session | Rejected |
| Add decisions only to `docs/ARCHITECTURE.md` | Central architecture doc already exists | Large docs become hard to diff by decision; historical reversals are unclear | Rejected as sole mechanism |
| Repo-local Markdown ADRs under `docs/architecture/adr/` | Source-controlled, searchable, reviewable, close to code/docs, no new dependency | Requires judgment to avoid ADR spam | Chosen |
| Add an ADR CLI/static site now | Automates numbering/search/publishing | Extra dependency and ceremony before the workflow is dogfooded | Deferred |

## Consequences

- Positive: future architecture changes can cite a specific decision record rather than reconstructing rationale from scattered docs or chat.
- Positive: implementation commits can include both the change and its rationale/verification evidence.
- Positive: agents get a concrete preflight step before changing boundaries, policy modes, APIs, schemas, or security/privacy behavior.
- Negative: the repo gains one more documentation surface that must be kept concise and indexed.
- Negative: agents may over-create ADRs unless they apply the trigger threshold in `docs/architecture/adr/README.md`.
- Neutral: existing architecture docs remain canonical for the current system description; ADRs explain why important choices were made or changed.

## Verification / validation

- Verification: `docs/architecture/adr/README.md`, `docs/architecture/adr/template.md`, and this first ADR exist in the repo.
- Verification: `AGENTS.md` points future agents to `docs/architecture/adr/` before architecture-impacting work.
- Verification: `docs/README.md` includes the decision-record reading path.
- Verification: `git diff --check -- .` passes before commit.
- Verification: a repo-wide Markdown fence check passes before commit.
- Verification: `./scripts/secret-scan.sh` passes before commit.
- Validation: the next architecture/design change in this repo should be able to start by reading this ADR index and either cite an existing ADR, create a new one, or state that no ADR is needed.

## Revisit triggers

- Supersede this ADR if ADRs become noisy enough to need stricter thresholds or automation.
- Supersede this ADR if a dedicated ADR tool/static site becomes necessary after the repo accumulates enough records.
- Supersede this ADR if the repo moves to a different architecture knowledge-management structure.

## References

- `~/repos/research/hermes-architecture-decision-records/hermes-architecture-decision-records.md`
- `docs/ARCHITECTURE.md`
- `docs/test-plan.md`
- `[removed-publication-dossier]`
