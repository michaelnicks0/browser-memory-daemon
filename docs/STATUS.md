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
| SQLite/FTS/media storage | ✅ Documents/visits/snapshots/chunks/FTS/media/audit/deletion receipts plus version-4 observation/claim tables, version-5 historical observation backfill, version-6 media-observation links, version-7 claimed lifecycle identity, version-8 relative blob locators, exact schema fingerprint, ordered checksum ledger, and restore-backed migration gate. Ingest dual-writes observations/claims/media provenance; recent/timeline/detail reads are observation-first with explicit legacy fallback. | `schema.sql`, `migrations.py`, `migration_steps/`, `db.py`, `ingest.py`, `ops.py`, tests. |
| Blob filesystem boundary | ✅ `BlobStore` contains DB locators; stages streaming writes with size/hash accounting; atomically commits; and owns blob read/stat/delete operations across ingest, media, forget, read models, HTTP, and blob migration. New writes dual-write root-relative plus absolute compatibility locators; reads prefer relative locators and use the contained legacy path only when the relative field is absent. | `blob_store.py`, migration/storage integration tests, ADR-0036, ADR-0037. |
| Exact search | ✅ FTS5 exact search with snippets/source metadata and media artifact counts. | `search.py`, `/search`, tests. |
| Forget/delete | ✅ URL/domain forget with receipts and text/media blob + FTS cleanup. | `forget.py`, tests. |
| Media artifacts | ✅ Durable image/video refs and binaries: fast text/manifest capture, browser IndexedDB lazy queue, credentialed fetch, raw blob upload, enabled-by-default X/Twitter CDP recorder with disable control, HLS/audio sidecar handling, daemon public worker, rolling cache gates, purge/rehydrate controls; no OCR/media indexing. | `media.py`, `media_worker.py`, `media_queue.js`, `cdp_recorder.js`, `/media-artifacts/*`, real Chrome e2e. |
| Local UI | ✅ Token-bootstrapped search/recent/timeline/detail/doctor/policy/delete panels; recent/today/doctor/policy auto-load on open. | `ui/`, admin API tests. |
| CLI | ✅ serve/health/migrate/doctor/daily-driver-health/search/recent/timeline/detail/policy/forget/capture-fixture/media-worker/media-cache/blob-root migration. | `cli.py`, CLI e2e. |
| Dedupe/versioning | ✅ Observed-URL document identity, text-hash snapshots, browser-authored per-extraction observation idempotency, per-tab/URL navigation identity, and non-authoritative canonical URL claims. | ingest/observation/migration/extension tests. |
| SPA/delayed capture | ✅ Delayed passes and History API hooks. | real Chrome SPA fixture. |
| Dwell/lifecycle | ✅ Metadata-only visit events with exact claimed/resolved visit identity, delayed-capture reconciliation, explicit legacy fallback labels, and validated interval-union dwell. | lifecycle/migration tests + real e2e. |
| Policy modes | ✅ `all`, `recall`, `balanced`, `strict`. | daemon + extension unit tests. |
| Fast quality gate | ✅ Network-free Ruff/mypy/branch-coverage/Python/Node/catalog/secret/diff gate with a default-XDG write sentinel and measured 80% floor. | `scripts/run-fast-gate.sh`, `docs/coverage-baseline.md`, ADR-0029. |
| Daily-driver install | ✅ systemd user daemon + media-worker services, Windows extension copy, non-mutating dry-run/check path, token/env/unit/process-arg health checks. | `scripts/install-daily-driver.sh`, `scripts/daily-driver-health.sh`, daily-driver tests. |

---

## Requirement posture

<!-- BEGIN GENERATED:requirement-posture -->
The canonical catalog contains **43 stable requirements**: **35 active** and **8 planned**. Normative statements, implementation links, V-model evidence, and legacy aliases are owned by [`requirements/catalog.toml`](../requirements/catalog.toml); generated tables in this doc set must not be hand-edited.
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
| Retention policies/export/backup | Medium | Design posture accepted in `docs/retention-compaction-backup.md`; implementation split into deferred maintenance and backup/export tickets. |
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
