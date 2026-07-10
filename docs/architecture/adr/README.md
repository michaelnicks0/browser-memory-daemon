# Architecture Decision Records

> Purpose: preserve the reasoning behind architecture, design, interface, dependency, policy, and Hermes workflow decisions that future agents must understand before changing this repo.

ADRs live in this repo because Browser Memory Daemon is architecture-heavy and agent-maintained. Chat history, memory, and commit messages are not sufficient paper trails for long-lived design choices.

## Index

| ADR | Status | Decision |
|---|---|---|
| [ADR-0001](0001-use-repo-local-architecture-decision-records.md) | accepted | Use repo-local Markdown ADRs for architecture-significant changes. |
| [ADR-0002](0002-keep-browser-memory-local-across-windows-chrome-and-wsl.md) | accepted | Keep browser memory local across Windows Chrome and the WSL daemon. |
| [ADR-0003](0003-use-all-policy-mode-as-daily-driver-default.md) | superseded | Use `all` policy mode as the daily-driver default. Superseded by ADR-0009. |
| [ADR-0004](0004-use-text-first-sqlite-fts5-and-blob-storage.md) | superseded | Use text-first SQLite/FTS5 and WSL-local blob storage. Superseded by ADR-0021 for blob placement. |
| [ADR-0005](0005-use-durable-lazy-media-sidecars-with-bounded-cache.md) | accepted | Use durable lazy media sidecars with a bounded disposable cache. |
| [ADR-0006](0006-use-forget-cascade-with-deletion-receipts.md) | superseded by ADR-0040 | Use forget/delete cascades with deletion receipts. |
| [ADR-0007](0007-use-real-chrome-e2e-as-verification-authority.md) | accepted | Use real Chrome / Chrome for Testing e2e as the verification authority. |
| [ADR-0008](0008-use-c4-structurizr-as-canonical-architecture-model.md) | accepted | Use C4/Structurizr under `docs/architecture/` as the canonical architecture model. |
| [ADR-0009](0009-apply-explicit-block-rules-in-all-mode.md) | accepted | Apply explicit local block rules in `all` mode while preserving the daily-driver default. |
| [ADR-0010](0010-disable-cdp-recorder-by-default.md) | superseded | Disable the CDP recorder by default so daily Chrome avoids the native debugging banner while preserving opt-in X/Twitter video recovery. Superseded by ADR-0011. |
| [ADR-0011](0011-enable-cdp-recorder-by-default-with-disable-control.md) | accepted | Enable the CDP recorder by default for X/Twitter video completeness while preserving an operator disable control for banner-free browsing. |
| [ADR-0012](0012-bootstrap-local-ui-token-from-daemon.md) | accepted | Bootstrap the local dashboard token from the daemon-served `/ui` HTML so the UI opens populated while memory/admin APIs remain bearer-authenticated. |
| [ADR-0013](0013-generated-publish-docs.md) | accepted | Use generated high-level docs and HTML companions for publish-ready documentation while keeping Markdown canonical. |
| [ADR-0014](0014-use-wal-and-bounded-sqlite-contention-policy.md) | accepted | Use WAL, busy-timeout, startup-only DB initialization, and bounded loopback backlog as the SQLite contention policy. |
| [ADR-0015](0015-use-idempotent-local-write-paths.md) | accepted | Use idempotent local write paths for duplicate captures, media/cache filesystem work, and semantic policy-rule uniqueness. |
| [ADR-0016](0016-use-deterministic-synthetic-performance-benchmarks.md) | accepted | Use deterministic synthetic benchmarks as advisory performance evidence before read-model/index tuning. |
| [ADR-0017](0017-add-read-model-composite-indexes.md) | accepted | Add composite SQLite indexes for measured read-model ordering paths. |
| [ADR-0018](0018-enforce-daily-driver-headroom-and-start-budgets.md) | accepted | Enforce daily-driver headroom and service-start failure budgets in local health checks. |
| [ADR-0019](0019-use-durable-text-retention-with-wal-aware-local-backup.md) | accepted | Use durable text retention with WAL-aware local backup and disposable media cache. |
| [ADR-0020](0020-enforce-static-requirement-traceability-gate.md) | superseded by ADR-0027 | Enforce static requirement traceability in the generated test inventory gate. |
| [ADR-0021](0021-use-configurable-nas-blob-root-with-local-sqlite.md) | superseded by ADR-0039 | Use a configurable NAS-capable blob root while keeping SQLite/WAL local. |
| [ADR-0022](0022-use-fast-doctor-and-media-queue-health-telemetry.md) | accepted | Use fast doctor and media-queue health telemetry. |
| [ADR-0023](0023-guard-daemon-public-media-egress.md) | accepted | Guard daemon-public media egress. |
| [ADR-0024](0024-contain-blob-and-media-artifact-paths.md) | accepted | Contain blob and media artifact paths. |
| [ADR-0025](0025-literal-policy-aware-forget-selectors.md) | accepted | Use literal and policy-aware forget selectors. |
| [ADR-0026](0026-harden-loopback-ui-and-required-blob-mounts.md) | accepted | Harden loopback UI and required blob mounts. |
| [ADR-0027](0027-use-canonical-semantic-requirement-catalog.md) | accepted | Use one machine-readable semantic requirement catalog with explicit legacy aliases and generated V-model traceability. |
| [ADR-0028](0028-use-versioned-restore-backed-sqlite-migrations.md) | accepted | Use versioned restore-backed SQLite migrations with exact schema fingerprints, ordered checksums, and backup-gated destructive steps. |
| [ADR-0029](0029-use-hermetic-fast-quality-gate.md) | accepted | Add a network-free fast gate with targeted static analysis, branch coverage, an XDG write sentinel, and a measured coverage ratchet. |
| [ADR-0030](0030-separate-capture-observations-and-url-claims.md) | accepted | Add expand-only capture-observation and untrusted URL-claim authority before dual-write and read cutover. |
| [ADR-0031](0031-dual-write-observed-url-capture-provenance.md) | accepted | Dual-write observed-URL capture provenance, preserve visit rows on recapture, and backfill only evidence-supported historical relationships. |
| [ADR-0032](0032-link-media-artifacts-to-capture-observations.md) | accepted | Add explicit observation/artifact provenance links with conservative evidence-bounded historical backfill. |
| [ADR-0033](0033-use-observation-first-historical-activity-reads.md) | accepted | Read recent/timeline/detail activity from contemporaneous observations with an explicit ambiguous legacy fallback. |
| [ADR-0034](0034-bind-lifecycle-by-visit-identity-and-union-dwell.md) | accepted | Preserve claimed visit identity, reconcile delayed events, and derive dwell from interval unions. |
| [ADR-0035](0035-emit-stable-browser-observation-and-navigation-identities.md) | accepted | Persist opaque observation IDs per extraction and navigation IDs per tab/URL state across queue retries. |
| [ADR-0036](0036-route-blob-operations-through-contained-blobstore.md) | accepted | Route staged streaming writes, contained reads, stats, and deletes through one BlobStore while legacy locators remain compatible. |
| [ADR-0037](0037-expand-blob-references-with-relative-locators.md) | accepted | Dual-write root-relative blob locators, prefer them on reads, and retain a contained legacy absolute fallback during expansion. |
| [ADR-0038](0038-make-sqlite-authoritative-for-cleaned-snapshot-text.md) | accepted | Commit complete cleaned text to SQLite, stop creating new text sidecars, and hash-verify legacy promotion. |
| [ADR-0039](0039-split-media-root-and-add-bounded-durable-spool.md) | accepted | Split derivative and media roots, guard external identity, and bound local outage buffering. |
| [ADR-0040](0040-use-durable-deletion-intents-and-reconciliation.md) | accepted | Persist blob deletion intent before cascades and reconcile failures through contained retryable operations. |
| [ADR-0041](0041-use-manifest-backed-text-first-backup-and-empty-root-restore.md) | accepted | Create manifest-backed text-first online backups and restore only into an absent explicit runtime root. |
| [ADR-0042](0042-separate-media-state-and-task-repository.md) | accepted | Separate media status/transition authority and durable task leasing/retry workflow from the compatibility facade. |
| [ADR-0043](0043-isolate-media-cache-admission-and-eviction.md) | accepted | Isolate media cache accounting, admission, oldest-first eviction, and tombstone-backed deletion outcomes. |

## Backfilled decision history

ADR-0002 through ADR-0008 are historical backfills recorded on 2026-06-14 from repo docs, code, tests, and git history. They did not introduce new runtime behavior; they document already-accepted architecture decisions so future changes can cite, comply with, or supersede them.

Backfill verification run on 2026-06-14:

- ADR lint and repo Markdown fence check passed.
- `git diff --check -- .` passed.
- `./scripts/secret-scan.sh` passed.
- `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` passed using a temporary Python 3.11 shim because the host `python3` is Python 3.8 while this repo declares `requires-python = ">=3.11"`.

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
