# Browser Memory Daemon Status — Implemented, Pending, Risks

> **Audience:** Operator and future maintainers.
> **Current source:** repository HEAD; release branch may vary.
> **Policy default:** `all`.

---

## Implemented

| Area | Status | Evidence |
|---|---|---|
| Windows Chrome extension | ✅ MV3 extension with service-worker-owned injection/transport and opaque observation/navigation IDs persisted in queued capture payloads across retry/restart. | `extension/src/`, extension unit tests, real Chrome e2e. |
| WSL daemon | ✅ Loopback HTTP daemon with bearer auth. | `app.py`, HTTP e2e tests. |
| SQLite/FTS/media storage | ✅ Documents/visits/snapshots/chunks/FTS/media/audit/deletion receipts plus version-4 through version-8 provenance/locator expansion, version-9 complete cleaned-text authority, version-10 media storage tiers/spool reservations, version-11 blob lifecycle records, version-12 historical media-state correction, and version-13 transactional cache reservations. New text/provenance commits locally without media-root access; recent/timeline/detail reads are observation-first with explicit legacy fallback. | `schema.sql`, `migration_steps/`, `migrations.py`, `text_authority.py`, `media_storage.py`, `blob_lifecycle.py`, migration/text/read tests, ADR-0028, ADR-0030 through ADR-0040, ADR-0046, ADR-0047. |
| Blob filesystem boundary | ✅ `BlobStore` contains DB locators; stages streaming media writes with size/hash accounting; atomically commits; and owns media plus legacy-sidecar read/stat/delete operations. Derivative and media roots are separate; external media is identity-guarded; the local spool is bounded; durable tombstones and dry-run-first reconciliation cover failed deletion, missing references, orphans, and stale stages. | `blob_store.py`, `blob_lifecycle.py`, `storage_reconcile.py`, storage integration tests, ADR-0036 through ADR-0040. |
| Exact search | ✅ FTS5 exact search with snippets/source metadata and media artifact counts. | `search.py`, `/search`, tests. |
| Forget/delete | ✅ URL/domain forget commits receipt plus blob tombstones with the relational cascade, suppresses pending bytes from serving, reports incomplete deletion honestly, and retries failures through reconciliation. | `forget.py`, `blob_lifecycle.py`, `test_storage_reconcile.py`, ADR-0040. |
| Backup/restore | ✅ Dry-run-first manifest-backed SQLite online backup, optional referenced derivatives, strict hash/path verification, and atomic restore into an absent runtime root; media/spool/secrets excluded by default. | `backup_ops.py`, `test_backup_restore.py`, ADR-0041. |
| Media artifacts | ✅ Durable image/video refs and streamed binaries: fast text/manifest capture, browser IndexedDB lazy queue, credentialed raw upload, enabled-by-default X/Twitter CDP recorder, guarded public transport, acyclic direct/HLS coordination, total request budgeting from the first open, bounded path/MIME/magic playlist detection, per-read deadlines, bounded streamed HLS/audio assembly, process request/byte budgets, transactional cross-process cache reservations, just-in-time task claiming, explicit state/task stores, bounded current-state reconciliation, scoped dry-run-first budget requeue, and failed-write compensation; no OCR/media indexing. | `media_models.py`, `media_tasks.py`, `media_store.py`, `media_transport.py`, `media_fetch.py`, `media_hls.py`, `media_resources.py`, `media_ops.py`, worker/extension tests, ADR-0042 through ADR-0047. |
| Local UI | ✅ Token-bootstrapped search/recent/timeline/detail/doctor/policy/delete panels; recent/today/doctor/policy auto-load on open. | `ui/`, admin API tests. |
| CLI | ✅ serve/health/migrate/doctor/daily-driver-health/search/recent/timeline/detail/policy/forget/capture-fixture/media-worker/media-cache/media-spool/blob-root migration/snapshot-text reconciliation/storage reconciliation/backup create/restore. | `cli.py`, CLI and backup integration tests. |
| Dedupe/versioning | ✅ Observed-URL document identity, text-hash snapshots, browser-authored per-extraction observation idempotency, per-tab/URL navigation identity, and non-authoritative canonical URL claims. | ingest/observation/migration/extension tests. |
| SPA/delayed capture | ✅ Delayed passes and History API hooks. | real Chrome SPA fixture. |
| Dwell/lifecycle | ✅ Metadata-only visit events with exact claimed/resolved visit identity, delayed-capture reconciliation, explicit legacy fallback labels, and validated interval-union dwell. | lifecycle/migration tests + real e2e. |
| Policy modes | ✅ `all`, `recall`, `balanced`, `strict`. | daemon + extension unit tests. |
| Fast quality gate | ✅ Network-free Ruff/mypy/branch-coverage/Python/Node/catalog/secret/diff gate with a default-XDG write sentinel and measured 80% floor. | `scripts/run-fast-gate.sh`, `docs/coverage-baseline.md`, ADR-0029. |
| Daily-driver install | ✅ systemd user daemon + media-worker services, Windows extension copy, non-mutating dry-run/check path, token/env/unit/process-arg health checks. | `scripts/install-daily-driver.sh`, `scripts/daily-driver-health.sh`, daily-driver tests. |

---

## Requirement posture

<!-- BEGIN GENERATED:requirement-posture -->
The canonical catalog contains **43 stable requirements**: **38 active** and **5 planned**. Normative statements, implementation links, V-model evidence, and legacy aliases are owned by [`requirements/catalog.toml`](../requirements/catalog.toml); generated tables in this doc set must not be hand-edited.
<!-- END GENERATED:requirement-posture -->

---

## Current default posture

```text
BMD_POLICY_MODE=all
```

This means:

- no static URL/domain/path/query filtering;
- no daemon redaction before storage/FTS;
- extension DOM extraction still skips hidden/form/editable/script/style/no-script text;
- explicit local block rules still apply;
- platform limits still apply when Chrome refuses extension injection.

---

## Pending roadmap lanes

| Lane | Priority | Notes |
|---|---:|---|
| Native messaging transport | Later | HTTP loopback is working; native messaging can reduce network-like surface later. |
| Semantic/vector search | Later, explicit approval required | Exact FTS remains current source of truth. |
| Retention/compaction/backup pruning | Medium | Text-first backup/restore is implemented; automatic retention, compaction, encryption/signing, and backup pruning remain approval-gated. |
| MCP/Hermes integration | Later | Should treat captured text as untrusted evidence. |
| Rich policy rules | Medium | Future allow/redact/metadata-only modes; current explicit rules are block-only and apply in every mode, including `all`. |
| Packaged extension distribution | Later | Daily driver currently uses manual Load unpacked due Chrome Secure Preferences. |

---

## Known limits and risks

| Risk/limit | Current handling |
|---|---|
| `all` stores secrets if visible/exposed in page DOM. | Intentional operator choice. Use `recall`/`balanced`/`strict` later if desired. |
| Chrome internal pages may not inject. | Platform limit; e2e covers web pages. |
| Branded Chrome automation ignores unpacked extension flags. | E2E uses Chrome for Testing. Daily driver uses manual Load unpacked/reload. |
| Extension token is copied into Windows-local unpacked extension artifact. | Token is generated in WSL, never committed, and can rotate. |
| SQLite can grow over time. | Media blobs have size/cache gates plus purge/rehydrate controls; ADR-0019 keeps text durable by default and splits maintenance/backup/export implementation into follow-up tickets. |
| Captured text may contain prompt injection. | UI/CLI treat it as evidence; future agents must not follow page instructions. |

---

## Source inventory

| Path | Role |
|---|---|
| `daemon/src/browser_memory_daemon/` | Python daemon package. |
| `daemon/tests/` | Unit/integration/e2e tests. |
| `extension/src/` | MV3 extension source. |
| `extension/tests/` | Extension unit tests. |
| `ui/` | Local static dashboard. |
| `scripts/` | E2E, install, build, dev, secret-scan helpers. |
| `docs/` | Operator and architecture docs. |
