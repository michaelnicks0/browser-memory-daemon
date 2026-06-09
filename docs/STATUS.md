# Browser Memory Daemon Status — Implemented, Pending, Risks

> **Audience:** Operator and future maintainers.
> **Current branch:** `master`.
> **Policy default:** `all`.

---

## Implemented

| Area | Status | Evidence |
|---|---|---|
| Windows Chrome extension | ✅ MV3 extension with service-worker-owned injection/transport. | `extension/src/`, extension unit tests, real Chrome e2e. |
| WSL daemon | ✅ Loopback HTTP daemon with bearer auth. | `app.py`, HTTP e2e tests. |
| SQLite/FTS/media storage | ✅ Documents/visits/snapshots/chunks/FTS/media/audit/deletion receipts. | `schema.sql`, integration/e2e tests. |
| Exact search | ✅ FTS5 exact search with snippets/source metadata and media artifact counts. | `search.py`, `/search`, tests. |
| Forget/delete | ✅ URL/domain forget with receipts and text/media blob + FTS cleanup. | `forget.py`, tests. |
| Media artifacts | ✅ Durable image/video refs and binaries: fast text/manifest capture, browser IndexedDB lazy queue, credentialed fetch, raw blob upload, daemon public worker, purge/rehydrate controls; no OCR/media indexing. | `media.py`, `media_worker.py`, `media_queue.js`, `/media-artifacts/*`, real Chrome e2e. |
| Local UI | ✅ Search/recent/timeline/detail/doctor/policy/delete panels. | `ui/`, admin API tests. |
| CLI | ✅ serve/health/search/recent/timeline/detail/policy/forget/capture-fixture. | `cli.py`, CLI e2e. |
| Dedupe/versioning | ✅ URL normalization + text-hash snapshots. | ingest tests. |
| SPA/delayed capture | ✅ Delayed passes and History API hooks. | real Chrome SPA fixture. |
| Dwell/lifecycle | ✅ Metadata-only visit events with idempotent dwell updates. | lifecycle tests + real e2e. |
| Policy modes | ✅ `all`, `recall`, `balanced`, `strict`. | daemon + extension unit tests. |
| Daily-driver install | ✅ systemd user daemon + media-worker services, Windows extension copy, health checks. | `scripts/install-daily-driver.sh`. |

---

## Current default posture

```text
BMD_POLICY_MODE=all
```

This means:

- no static URL/domain/path/query filtering;
- no daemon redaction before storage/FTS;
- extension DOM extraction still skips hidden/form/editable/script/style/no-script text;
- local block rules are ignored;
- platform limits still apply when Chrome refuses extension injection.

---

## Pending roadmap lanes

| Lane | Priority | Notes |
|---|---:|---|
| Native messaging transport | Later | HTTP loopback is working; native messaging can reduce network-like surface later. |
| Semantic/vector search | Later, explicit approval required | Exact FTS remains current source of truth. |
| Retention policies/export/backup | Medium | Needed before long-term high-volume use. |
| MCP/Hermes integration | Later | Should treat captured text as untrusted evidence. |
| Rich policy rules | Medium | Future allow/redact/metadata-only modes; current explicit rules are block-only and skipped in `all`. |
| Reconciliation for orphan lifecycle events | Low/medium | Some media/dynamic pages can send lifecycle before capture attaches. |
| Packaged extension distribution | Later | Daily driver currently uses manual Load unpacked due Chrome Secure Preferences. |

---

## Known limits and risks

| Risk/limit | Current handling |
|---|---|
| `all` stores secrets if visible/exposed in page DOM. | Intentional operator choice. Use `recall`/`balanced`/`strict` later if desired. |
| Chrome internal pages may not inject. | Platform limit; e2e covers web pages. |
| Branded Chrome automation ignores unpacked extension flags. | E2E uses Chrome for Testing. Daily driver uses manual Load unpacked/reload. |
| Extension token is copied into Windows-local unpacked extension artifact. | Token is generated in WSL, never committed, and can rotate. |
| SQLite can grow over time. | Media blobs have size/cache gates plus purge/rehydrate controls; no retention/compaction job yet for the full DB/text store. |
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
