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
| [ADR-0006](0006-use-forget-cascade-with-deletion-receipts.md) | superseded | Use forget/delete cascades with deletion receipts. Superseded by [ADR-0040](0040-use-durable-deletion-intents-and-reconciliation.md). |
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
| [ADR-0020](0020-enforce-static-requirement-traceability-gate.md) | superseded | Enforce static requirement traceability in the generated test inventory gate. Superseded by [ADR-0027](0027-use-canonical-semantic-requirement-catalog.md). |
| [ADR-0021](0021-use-configurable-nas-blob-root-with-local-sqlite.md) | superseded | Use a configurable NAS-capable blob root while keeping SQLite/WAL local. Superseded by [ADR-0039](0039-split-media-root-and-add-bounded-durable-spool.md). |
| [ADR-0022](0022-use-fast-doctor-and-media-queue-health-telemetry.md) | accepted | Use fast doctor and media-queue health telemetry. |
| [ADR-0023](0023-guard-daemon-public-media-egress.md) | superseded | Guard daemon-public media egress. Superseded by [ADR-0045](0045-isolate-guarded-media-fetch-and-hls.md). |
| [ADR-0024](0024-contain-blob-and-media-artifact-paths.md) | superseded | Contain blob and media artifact paths. Superseded by [ADR-0037](0037-expand-blob-references-with-relative-locators.md). |
| [ADR-0025](0025-literal-policy-aware-forget-selectors.md) | superseded | Use literal and policy-aware forget selectors. Superseded by [ADR-0057](0057-preview-and-bound-forget-selection.md). |
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
| [ADR-0039](0039-split-media-root-and-add-bounded-durable-spool.md) | superseded | Split derivative and media roots, guard external identity, and bound local outage buffering. Superseded by [ADR-0061](0061-automatically-drain-bounded-media-spool-after-root-recovery.md). |
| [ADR-0040](0040-use-durable-deletion-intents-and-reconciliation.md) | accepted | Persist blob deletion intent before cascades and reconcile failures through contained retryable operations. |
| [ADR-0041](0041-use-manifest-backed-text-first-backup-and-empty-root-restore.md) | accepted | Create manifest-backed text-first online backups and restore only into an absent explicit runtime root. |
| [ADR-0042](0042-separate-media-state-and-task-repository.md) | accepted | Separate media status/transition authority and durable task leasing/retry workflow from the compatibility facade. |
| [ADR-0043](0043-isolate-media-cache-admission-and-eviction.md) | accepted | Isolate media cache accounting, admission, oldest-first eviction, and tombstone-backed deletion outcomes. |
| [ADR-0044](0044-publish-media-through-artifact-store.md) | accepted | Publish, resolve, and purge media through the artifact store with unique candidates and failed-write compensation. |
| [ADR-0045](0045-isolate-guarded-media-fetch-and-hls.md) | accepted | Isolate guarded media fetch and bounded HLS transport. |
| [ADR-0046](0046-move-historical-media-correction-out-of-worker-loop.md) | accepted | Move historical media correction out of the worker loop. |
| [ADR-0047](0047-stream-media-with-process-budgets-and-durable-cache-reservations.md) | accepted | Stream media with process budgets and durable cache reservations. |
| [ADR-0048](0048-use-transactional-indexeddb-capture-lifecycle-outbox.md) | accepted | Use a transactional IndexedDB outbox for capture and lifecycle delivery. |
| [ADR-0049](0049-bound-browser-media-queue-lifecycle.md) | accepted | Bound the browser media task and blob lifecycle. |
| [ADR-0050](0050-use-full-capture-digest-and-rendered-visibility.md) | accepted | Use full capture digests and a conservative rendered-visibility contract. |
| [ADR-0051](0051-extract-mv3-restart-state-controllers.md) | accepted | Extract MV3 restart-state controllers from the service worker. |
| [ADR-0052](0052-complete-mv3-service-worker-orchestration-split.md) | accepted | Complete the MV3 service-worker orchestration split. |
| [ADR-0053](0053-introduce-compatible-http-route-descriptors.md) | accepted | Introduce explicit HTTP route descriptors behind compatible endpoint contracts. |
| [ADR-0054](0054-use-typed-compatible-http-errors.md) | accepted | Use typed compatible HTTP errors and sanitize internal failures. |
| [ADR-0055](0055-add-redaction-safe-http-request-envelope.md) | accepted | Add opaque request IDs, common security headers, and redaction-safe request telemetry. |
| [ADR-0056](0056-separate-http-transport-from-application-use-cases.md) | accepted | Separate the standard-library HTTP adapter from explicit request-independent application use cases. |
| [ADR-0057](0057-preview-and-bound-forget-selection.md) | accepted | Preview exact forget scope and bound destructive execution. |
| [ADR-0058](0058-stage-daily-driver-install-and-rollback-failed-readiness.md) | accepted | Stage daily-driver artifacts and restore the prior generation after failed forward readiness. |
| [ADR-0059](0059-pin-and-verify-chrome-for-testing-release.md) | accepted | Pin and checksum-verify Chrome for Testing as isolated release authority. |
| [ADR-0060](0060-export-versioned-body-safe-x-observations.md) | accepted | Export versioned body-safe X observations through a mutation-free producer contract. |
| [ADR-0061](0061-automatically-drain-bounded-media-spool-after-root-recovery.md) | accepted | Automatically drain the bounded local media spool after the guarded final root recovers. |
| [ADR-0062](0062-reject-ambiguous-or-truncated-http-request-bodies.md) | accepted | Reject ambiguous, oversized, missing-required, or truncated HTTP request bodies before application use cases. |

## Backfilled decision history

ADR-0002 through ADR-0008 are historical backfills recorded on 2026-06-14 from repo docs, code, tests, and git history. They did not introduce new runtime behavior; they document already-accepted architecture decisions so future changes can cite, comply with, or supersede them.

ADR-0062 was backfilled on 2026-07-14 to record the strict HTTP request-body framing contract implemented and tested by commit `5161aa8a`; it likewise introduces no new runtime behavior.

The repository history was later rewritten while preserving those changes. The accepted ADR bodies retain their originally recorded short hashes; use this immutable errata map when resolving them against current history:

| Recorded hash | Current hash | Current commit subject |
|---|---|---|
| `2ba4373` | `27468b6` | `feat: bootstrap browser memory daemon` |
| `2c2b76b` | `1ca4e00` | `test: add real Windows Chrome extension e2e` |
| `fb025df` | `4921b61` | `ops: add daily-driver Chrome deployment helper` |
| `29410de` | `aa560ec` | `feat: add local memory UI and ops APIs` |
| `26f0202` | `2b010ee` | `feat: add adjustable capture policy modes` |
| `39fced1` | `21d19b6` | `feat: add capture dedupe and URL normalization tests` |
| `a1ff667` | `0824266` | `docs: model browser memory storage growth` |
| `b6446d6` | `6b7349b` | `feat: store related media artifacts` |
| `d8eea55` | `320d87c` | `feat: fetch pending media artifacts in daemon` |
| `fa6dc26` | `e4b9368` | `docs: plan durable media sidecars` |
| `04e6482` | `c0510e5` | `feat: add durable media sidecars` |
| `ab38213` | `cef7cc5` | `Harden media sidecar retrieval` |
| `77d8f3d` | `ce97633` | `Add HLS media backfill and normalize video skips` |
| `061e490` | `0ccf2bc` | `Add CDP recorder for X video media` |
| `97b0e81` | `a31b3c7` | `Store HLS audio sidecars and classify blob video refs` |
| `969a20d` | `f875779` | `Raise media cache caps and add rolling eviction` |
| `e85da5b` | `0b05dc3` | `Fold media sidecar design into architecture` |
| `a384d41` | `43d4af1` | `docs: note Chrome CDP profile caveat` |
| `dfeb585` | `0811045` | `docs: record daily-driver Chrome install results` |
| `2ee7dd1` | `4e88ee4` | `docs: add C4 architecture model` |
| `ae36fbf` | `8b7697a` | `docs: add markdown C4 diagram wrappers` |
| `3e4df5c` | `b054b49` | `docs: clean C4 diagram renders` |
| `cbef41c` | `7ae5427` | `docs: add combined C4 diagram atlas` |
| `a25289f` | `9ce7feb` | `docs: reconcile C4 and behavioral diagrams` |
| `23cd82d` | `3b44e33` | `docs: move C4 architecture under docs` |

Backfill verification run on 2026-06-14:

- ADR lint and repo Markdown fence check passed.
- `git diff --check -- .` passed.
- `./scripts/secret-scan.sh` passed.
- `BMD_SKIP_REAL_CHROME_E2E=1 ./scripts/run-e2e.sh` passed using a temporary Python 3.11 shim because the host `python3` is Python 3.8 while this repo declares `requires-python = ">=3.11"`.

## Metadata compatibility

New ADRs must use the YAML frontmatter in [`template.md`](template.md), including an `ADR-NNNN` ID and explicit supersession arrays. The historical ledger also contains two readable legacy encodings that tooling must preserve rather than mass-rewrite:

- ADR-0028 through ADR-0039 use legacy YAML without an `id` field.
- ADR-0042 through ADR-0056 use a short inline metadata list below the title.

Status/index checks may read those encodings, but accepted decision bodies remain immutable except for status, supersession, references, verification metadata, and explicit errata in this index.

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
