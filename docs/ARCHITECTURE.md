# Browser Memory Daemon Architecture — Windows Chrome to WSL Recall

> **Audience:** maintainers and future agents.
> **Mission:** provide local-first, searchable personal browser recall from Windows Chrome with durable storage in WSL.
> **Current default:** `policy_mode=all` for maximum recall.

---

## Mission and ConOps

The system shall enable Operator to reconstruct recently viewed web content by capturing Chrome page text locally, storing it in WSL, and exposing exact search, timeline, detail, lifecycle, and deletion tools without cloud dependency.

| Field | Current design |
|---|---|
| Operator | Operator only. |
| Browser surface | Windows Chrome daily-driver profile plus Chrome for Testing in e2e. |
| Capture path | MV3 extension → service worker → authenticated localhost HTTP. |
| Storage owner | WSL daemon. Chrome profile is not the durable memory store. |
| Search model | Exact SQLite FTS5 first. No embeddings yet. |
| Default policy posture | `all`: no daemon redaction or URL policy filtering, maximum recall, DOM extraction skip retained. |
| Deletion model | Forget by domain/URL with deletion receipts. |
| Validation target | Real Windows Chrome can capture, search, and forget synthetic pages through WSL. |

## High-level architecture at a glance

![High-level architecture diagram showing Windows Chrome capture, authenticated loopback transport, WSL-owned memory, and local operator/verification surfaces.](architecture/high-level-architecture.svg)

The fast path is text-first: page text, lifecycle metadata, and media references are captured before any media bytes are fetched. Media sidecars run later in Chrome or the daemon, and all durable memory remains under WSL-owned storage.

---

## Requirements trace

| ID | Requirement | Implementation | Verification |
|---|---|---|---|
| REQ-001 | Capture Chrome page text into WSL. | `extension/src/*`, `/capture`, `ingest.py` | `scripts/run-real-chrome-e2e.sh` |
| REQ-002 | Keep durable data out of repo and Chrome profile. | `RuntimeConfig`, XDG paths, `.gitignore` | `doctor`, secret scan, runtime-root tests |
| REQ-003 | Service worker owns daemon communication. | `service_worker.js` | extension unit tests + real e2e |
| REQ-004 | Authenticated loopback API. | `app.py`, bearer token | HTTP e2e unauthorized test |
| REQ-005 | Adjustable capture policy modes. | `policy.py`, `extractor.js`, options/popup | daemon + extension unit tests |
| REQ-006 | `all` mode disables URL filtering and daemon redaction while still skipping hidden/form/editable/script/style/no-script DOM text. | `policy_mode=all`, no-redaction ingest path | unit/integration + real e2e all-mode expectations |
| REQ-007 | Non-all modes preserve redaction and stricter policy options. | `redact_text`, `redact_url`, strict/balanced/recall | policy and ingest tests |
| REQ-008 | Exact search with citations. | `chunks_fts`, `search.py`, detail APIs | integration/e2e search tests |
| REQ-009 | Dedupe repeated unchanged captures. | normalized URLs + text hash snapshots | ingest tests |
| REQ-010 | Capture SPA/delayed pages. | content-script delayed passes + history hooks | real Chrome SPA fixture |
| REQ-011 | Track dwell/lifecycle metadata. | `/visit-events`, `lifecycle.py` | lifecycle tests + real e2e |
| REQ-012 | Local UI and CLI operations. | `ui/`, `cli.py`, admin APIs; `/ui` token bootstrap | admin/CLI e2e tests |
| REQ-013 | Delete stored memory with receipts. | `forget.py`, `deletion_receipts` | forget integration/e2e tests |
| REQ-014 | Real daily-driver install path. | `install-daily-driver.sh` | WSL + Windows health checks |
| REQ-015 | Media bytes shall never block text/FTS capture. | `/capture` media refs, extension IndexedDB queue, media worker | integration + real Chrome e2e |
| REQ-016 | Credentialed media fetch shall stay inside Chrome; WSL shall not receive browser cookies. | browser lazy sidecar `fetch(... credentials: 'include')` + raw `PUT` | cookie-required real Chrome fixture |
| REQ-017 | Media cache shall be bounded and disposable/rebuildable. | size gates, `/media-artifacts/purge-cache`, `media-cache` CLI | HTTP/integration tests |

---

## Logical decomposition

| Component | Responsibility | Notes |
|---|---|---|
| Chrome manifest | Permission envelope and extension entrypoints. | Uses `<all_urls>` so `all` mode is meaningful. |
| Extractor | Traverse DOM and build capture payload. | Policy-aware; all modes skip hidden/form/editable/script/style/no-script DOM text. |
| Content script | Schedule initial/delayed/SPA captures and scroll tracking. | Reads `policyMode` from extension storage. |
| Service worker | Auth, queues, injection, lifecycle state, fast `/capture`, browser lazy media queue/drain, daemon POST/PUTs, CDP recorder orchestration. | Text capture does not wait on media bytes. |
| Extension media queue | Durable IndexedDB queue for credentialed media fetch/upload. | Stores fetched blobs until raw upload succeeds. |
| CDP recorder | Enabled-by-default, operator-disableable domain-gated Chrome DevTools Protocol recorder for X/Twitter media network responses. | Captures `video.twimg.com` HLS manifests/segments before they collapse into opaque `blob:` player refs, but Chrome shows a native debugging banner while attached. |
| Daemon API | Auth, CORS, routing, UI serving, token bootstrap, raw media blob upload, cache controls. | `/health` public loopback; `/ui` HTML gets same-origin token bootstrap; memory APIs tokened. |
| Policy engine | Mode-specific allow/block/redact decisions. | `all`, `recall`, `balanced`, `strict`. |
| Ingest pipeline | Normalize, store visits/documents/snapshots/chunks/FTS plus related media artifact refs/blobs. | `all` bypasses redaction. |
| Lifecycle pipeline | Store metadata-only visit events and update dwell. | Uses policy mode for URL redaction/filtering. |
| Daemon media worker | Durable public-media backfill with leases/backoff/retry and HLS/audio sidecar assembly. | Does not receive or export Chrome cookies. |
| Media cache manager | Applies size gates, manual purge/rehydrate, and oldest-first domain/global rolling eviction. | Blob bytes are disposable; text, refs, hashes, and provenance remain durable. |
| Ops/read model | Search, recent, timeline, detail, doctor. | Captured text remains untrusted evidence. |
| Deletion pipeline | Domain/URL forget and receipt creation. | Removes DB rows, FTS rows, text/media blobs, lifecycle rows. |

---

## Architecture diagrams

The canonical C4 model lives in [`architecture/workspace.dsl`](architecture/workspace.dsl). Use the generated single-file atlas at [`architecture/c4-diagrams.md`](architecture/c4-diagrams.md) for architecture topology.

| Question | C4 view |
|---|---|
| What is the system boundary? | `SystemContext` |
| How does fast capture move from Chrome to WSL storage? | `CaptureContainers`, `ExtensionCaptureComponents`, `DaemonIngestComponents`, `FastCaptureFlow` |
| How do browser-side media sidecars work at architecture level? | `BrowserMediaContainers`, `ExtensionMediaComponents`, `CredentialedMediaSidecarFlow` |
| How does daemon-public media backfill work? | `DaemonMediaWorkerContainers`, `DaemonMediaComponents`, `DaemonPublicMediaWorkerFlow` |
| How do read/search/forget/doctor operations reach storage? | `OpsContainers`, `DaemonReadComponents`, `DaemonForgetComponents`, `DaemonDoctorComponents` |
| What runs where on the daily-driver workstation? | `DailyDriverDeployment` |

Hand-authored Mermaid diagrams for behavior that C4 intentionally omits — policy ladders, redaction branches, state machines, dedupe formulas, endpoint maps, media status/cache semantics, and delete cascades — live in [`DIAGRAMS.md`](DIAGRAMS.md).

---

## Durable media sidecar architecture

The media lane is built around one invariant:

```text
fast text sidecar owns recall correctness
lazy media sidecars own byte completeness
media blobs are a bounded disposable cache
text/FTS/media refs remain authoritative
```

`/capture` stores page text, FTS chunks, visits/snapshots, and media reference rows first. Binary media work is explicitly asynchronous so slow videos, signed URLs, or worker suspension cannot break text recall.

### Media lanes

| Lane | Purpose | Current files |
|---|---|---|
| Fast capture | Store text, FTS, visits/snapshots, and media refs immediately. | `extension/src/content_script.js`, `extension/src/service_worker.js`, `daemon/src/browser_memory_daemon/ingest.py`, `media.py` |
| Browser lazy sidecar | Fetch credentialed media inside Chrome and upload raw blobs. | `extension/src/media_queue.js`, `service_worker.js` |
| Inline/blob upload | Let the content script read transient `blob:` / `data:` bytes while page context is alive. | `extension/src/content_script.js`, `service_worker.js` |
| CDP recorder | Enabled-by-default capture of X/Twitter `video.twimg.com` HLS manifests/segments before only opaque `blob:` player URLs remain, with an options-page disable control. | `extension/src/cdp_recorder.js`, `service_worker.js` |
| Daemon lazy sidecar | Public unauthenticated backfill with leases, backoff, HLS assembly, and status classification. | `daemon/src/browser_memory_daemon/media_worker.py`, `media.py` |
| Cache management | Purge/rehydrate controls plus oldest-first rolling eviction for domain/global caps. | `media.py`, `cli.py`, `/media-artifacts/*` |

### Visual references

| Need | Diagram/doc |
|---|---|
| Architecture-level media topology | [`architecture/c4-diagrams.md`](architecture/c4-diagrams.md): `BrowserMediaContainers`, `ExtensionMediaComponents`, `DaemonMediaWorkerContainers`, `DaemonMediaComponents` |
| Browser credentialed sidecar scenario | [`architecture/c4-diagrams.md`](architecture/c4-diagrams.md): `CredentialedMediaSidecarFlow` |
| Daemon-public worker scenario | [`architecture/c4-diagrams.md`](architecture/c4-diagrams.md): `DaemonPublicMediaWorkerFlow` |
| Parallel browser/daemon sidecar sequence, status reasons, HLS/CDP details | [`media-artifacts.md`](media-artifacts.md#capture-flow) |
| Cache/status behavior and provenance-preserving purge | [`DIAGRAMS.md`](DIAGRAMS.md#4-durable-media-sidecars-and-cache-outcomes) |

### Requirements resolved by the current media design

| Requirement | Current implementation status |
|---|---|
| Text/FTS must not wait on media bytes. | `/capture` stores refs and returns artifact IDs before lazy binary work. |
| Every discovered media candidate should produce a durable row. | Implemented subject to the per-capture ref cap; video refs are prioritized over lower-priority images. |
| Browser media work must survive service-worker suspension. | IndexedDB tasks/blobs plus stale-task requeue. |
| Credentialed media fetch must stay inside Chrome. | Browser lazy sidecar uses Chrome's credential envelope; WSL daemon never receives Chrome cookies. |
| Raw binary upload should avoid base64 inflation. | Primary path is `PUT /media-artifacts/{artifact_id}/blob`; JSON/base64 is compatibility-only. |
| Daemon public backfill should use durable leases/backoff. | `media_fetch_tasks` stores leases, attempts, retry time, worker kind, and terminal status. |
| X/Twitter video should be recoverable when the DOM only exposes `blob:` player URLs. | Enabled-by-default domain-gated CDP recorder captures `video.twimg.com` manifests/segments and tags related rows with `cdp_recorder=true`; the options page can disable it to avoid Chrome's debugging banner. |
| HLS audio/video should be stored when technically feasible. | Worker resolves master/media playlists, assembles segments under caps, and stores audio-only renditions as `audio/*` sidecars while preserving video provenance. |
| Blob video refs should not remain ambiguous. | Same-document or same-snapshot CDP-covered refs become `covered-by-cdp-recorder`; residual unreadable refs become `opaque-browser-blob`. |
| Media blobs must be bounded and disposable. | Per-artifact/snapshot/domain/global gates plus manual purge/rehydrate and oldest-first rolling eviction. |
| Purged blobs should be rehydratable when remote URLs still work. | Cache purge can reset eligible daemon-public tasks to `pending` for best-effort refetch. |

### Media state and cache semantics

| State/reason | Meaning |
|---|---|
| `referenced` | Durable ref exists; bytes are absent by design, not a failure. |
| `metadata-only` | CDP/browser/compat path recorded a row without local bytes yet. |
| `stored` | Local blob exists under `blobs/media/`. |
| `retrying` | Transient fetch condition with future retry. |
| `skipped` | Classified terminal non-storage condition, such as over-size, unsupported MIME, or policy gate. |
| `expired` | Remote signed/dated media disappeared before fetch. |
| `purged` | Blob bytes were intentionally removed while ref/hash/provenance stayed durable. |
| `failed` | Reserved for unexpected/unclassified bugs; normal remote/cache outcomes should not land here. |

Current default media gates come from `RuntimeConfig`:

| Gate | Default |
|---|---:|
| Max artifact bytes | 250 MB |
| Per-snapshot media bytes | 1 GB |
| Per-domain media bytes | 10 GB |
| Global media cache bytes | 100 GB |
| Media refs per capture | 50 |
| Daemon public fetches per capture | 12 |
| Manual `/fetch-pending` API call limit | 100 |
| Worker service interval / batch | 30 seconds / 25 items |

Domain/global gates are rolling caches. When a new blob would exceed either cap, the daemon evicts the oldest stored blobs in that scope first and preserves rows as:

```text
capture_status = purged
status_reason  = cache-evicted:domain-oldest
# or
status_reason  = cache-evicted:global-oldest
```

### Explicit media non-goals

- OCR or media-derived text indexing.
- DRM/EME capture.
- General DASH/MSE capture when Chrome exposes no readable blob, direct URL, or public HLS manifest.
- Always-on screenshots for every page.

---

## Policy mode semantics

| Mode | URL filtering | DOM filtering | URL/body redaction | Persistent block rules |
|---|---|---|---|---|
| `all` | Built-in filters off. Allows any absolute URL accepted by runtime unless explicitly blocked. | Skips hidden/form/editable/script/style/no-script. | Off. | Applied. |
| `recall` | Blocks incognito/browser-internal/file/non-web schemes. | Skips hidden/form/editable/script/style/no-script. | On. | Applied. |
| `balanced` | `recall` plus private hosts, known high-risk domains, high-risk query keys. | Same as `recall`. | On. | Applied. |
| `strict` | Legacy broad keyword filters for domains/paths/query keys. | Same as `recall`. | On. | Applied. |

`all` still has platform limits: Chrome may refuse extension injection on browser-owned pages or pages outside extension permission/runtime access.

---

## Storage model

| Table/path | Role |
|---|---|
| `documents` | Stable normalized document identity. |
| `visits` | Each captured visit, original/stored URL, dwell, browser profile. |
| `visit_events` | Metadata-only lifecycle segments. |
| `snapshots` | Distinct text versions per document. |
| `chunks` / `chunks_fts` | Searchable text chunks and exact FTS index. |
| `media_artifacts` | Related image/video refs, current blob status, provenance, purge state. |
| `media_fetch_tasks` | Durable daemon-public media backfill leases/retries/status. |
| `privacy_rules` | Explicit local block rules applied in every policy mode. |
| `audit_events` | Metadata-only operational audit. |
| `deletion_receipts` | Forget receipts and counts. |
| `~/.local/share/browser-memory-daemon/blobs/clean-text/` | Stored text snapshots. |
| `~/.local/share/browser-memory-daemon/blobs/media/` | Stored media blobs; purgeable cache. |

---

## Trust and safety boundaries

- Retrieved page text is untrusted evidence. It must not drive agent actions without operator intent.
- The daemon binds to loopback and uses bearer auth for memory/admin endpoints.
- The daily-driver token lives in WSL config, is copied into the local extension artifact during install, and is embedded into daemon-served `/ui` HTML for same-origin dashboard bootstrap; static UI assets stay token-free.
- `all` mode intentionally removes daemon redaction and URL policy filtering; this is a local personal-recall tradeoff, not a multi-user default.
- No cloud LLM/vector/embedding pipeline is implemented.

---

## Open architecture lanes

| Lane | Status |
|---|---|
| Native messaging hardening | Planned. HTTP loopback remains current transport. |
| Semantic search | Planned only after explicit approval. |
| Retention/export/backup | Planned. |
| MCP/Hermes tool integration | Planned. |
| Rich allow/redact/quarantine policies | Planned; current explicit rules are block-only and applied in every mode. |
