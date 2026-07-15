---
id: ADR-0013
title: Use generated high-level docs and HTML companions for publish-ready documentation
status: accepted
date: 2026-06-28
owners: [Operator]
verification:
  - python scripts/generate_test_inventory.py --check
  - python scripts/generate_showcase.py --spec scripts/showcase.spec.json --check
  - python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
  - local HTML link-integrity verifier
  - python -m pytest -q
  - cd extension && npm test && npm run build
  - ./scripts/secret-scan.sh
  - git diff --check -- .
---

# ADR-0013: Use Generated High-Level Docs and HTML Companions for Publish-Ready Documentation

## Context

Browser Memory Daemon already had detailed Markdown documentation: architecture, C4 diagrams, behavioral Mermaid diagrams, CLI/API contracts, security model, test plan, status, and ADRs. Before publishing publicly, the docs needed a higher-altitude front door and a browser-polished reading experience without making generated HTML the source of truth.

The repo also needs doc metrics that do not drift. Test counts and rendered docs should be reproducible from source, not hand-maintained.

## Decision

We will keep Markdown as the canonical editable source and add generated documentation artifacts for publish polish:

1. A root `browser-memory-daemon-high-level-doc.html` visual front door generated from `scripts/showcase.spec.json`.
2. A `docs/EXECUTIVE_BRIEF.md` high-level reader entry point.
3. Styled `*.html` companions generated from Markdown by `scripts/render_docs.py`.
4. A generated test inventory in `docs/TESTS.md`, produced by `scripts/generate_test_inventory.py` from daemon pytest and extension node:test sources.
5. Drift checks for each generator before publishing or committing docs updates.

Generated HTML files are committed artifacts, but they are not hand-edited. To change content, edit Markdown or `scripts/showcase.spec.json`, regenerate, and rerun the checks.

## Decision drivers

- Public readers need a polished overview before diving into detailed architecture and operations docs.
- Browser-opened raw Markdown is a jarring drop from a visual front door; rendered companions keep the reading path coherent.
- The repo already owns generated C4 artifacts, so generated docs are consistent with existing documentation discipline.
- Test inventory and doc artifacts should fail fast when stale.
- Markdown remains reviewable and GitHub-native.

## Consequences

- Docs changes now have generated-artifact obligations: run the showcase, inventory, and render-docs checks.
- Generated HTML increases repository size and file count, but keeps public browsing polished and offline-friendly.
- Mermaid diagrams in docs are rendered into themed inline SVG in the generated HTML companions.
- C4/Structurizr Markdown and committed diagram artifacts remain the architecture source of truth.
- Future docs pipeline changes should update this ADR or supersede it.

## Alternatives considered

| Option | Benefit | Cost | Outcome |
|---|---|---|---|
| Markdown only | Small repo; simplest maintenance. | No polished browser front door; raw Markdown drops from HTML links. | Rejected for public polish. |
| Hand-authored HTML | Full design control. | High drift risk; hard to verify. | Rejected. |
| Generated root HTML only | Lower artifact count. | Links still fall into raw Markdown in browser. | Rejected. |
| Generated root + Markdown companions | Polished and drift-checkable while preserving Markdown as source. | More generated files and checks. | Chosen. |

## Revisit triggers

- Generated docs become too large or noisy for public review.
- GitHub Pages or another static-site pipeline replaces committed same-path companions.
- The repo adopts a package-managed docs build with equivalent drift checks.
- The public README becomes the only desired entry point and Operator explicitly drops HTML companions.
