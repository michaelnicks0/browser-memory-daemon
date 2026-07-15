# Browser Memory Daemon Behavioral Diagrams

> **Audience:** maintainers and future agents.
> **Purpose:** preserve hand-authored Mermaid diagrams for behavior that should not be forced into C4.
> **Architecture atlas:** [`architecture/c4-diagrams.md`](architecture/c4-diagrams.md).
> **C4 source of truth:** [`architecture/workspace.dsl`](architecture/workspace.dsl).

---

## Diagram ownership

C4 owns the architecture topology: systems, containers, components, deployment, and major scenario views. This file keeps lower-level behavior that C4 intentionally omits or only summarizes.

| Need | Canonical home |
|---|---|
| System context, container topology, component topology, deployment | [`architecture/c4-diagrams.md`](architecture/c4-diagrams.md) |
| Exact endpoint/message names, redaction branches, state machines, algorithms, cache/status semantics, delete cascades | This file and the relevant feature docs |
| Durable media sidecar protocol details | [`media-artifacts.md`](media-artifacts.md) plus the media diagrams below |
| Policy/security posture | [`security-model.md`](security-model.md) plus the policy ladder below |
| HTTP payload shapes and route index | [`api.md`](api.md) plus the endpoint maps below |

Topological diagrams previously in this atlas were folded into C4. The diagrams below remain because they carry behavior/state/API semantics not cleanly represented by C4.

---

## 1. Extension protocol boundary

```mermaid
flowchart LR
  Page["Chrome page light DOM"] --> Extractor["extractor.js<br/>computed/ancestor rendered visibility"]
  Extractor --> Content["content_script.js<br/>full deterministic SHA-256 digest"]
  Content -->|"BMD_CAPTURE + inline blob messages"| ServiceWorker["service_worker.js"]
  ServiceWorker --> Config["config_store.js<br/>typed settings + durable restart context"]
  ServiceWorker --> Visit["visit_tracker.js<br/>navigation identity + lifecycle"]
  ServiceWorker --> Injection["injection.js<br/>active-tab reconstruction"]
  ServiceWorker --> CDPSession["cdp_session.js<br/>attachment + provenance + Network event recovery"]
  ServiceWorker --> CaptureBridge["capture_bridge.js<br/>capture/lifecycle delivery + outbox drain"]
  ServiceWorker --> MediaBridge["media_bridge.js<br/>credentialed fetch + blob delivery"]
  ServiceWorker --> Telemetry["telemetry.js<br/>redaction-safe aggregate status"]
  Injection -->|"ordered idempotent executeScript"| Page
  Visit --> Config
  CDPSession --> Config
  CDPSession -->|"chrome.debugger"| Page
  CDPSession --> MediaBridge
  CaptureBridge --> Outbox[("IndexedDB capture/lifecycle outbox")]
  Outbox -->|"atomic claim/checkpoint/ack/retry"| CaptureBridge
  CaptureBridge -->|"POST /capture<br/>Bearer JSON"| DaemonCapture["WSL daemon /capture"]
  CaptureBridge -->|"POST /visit-events<br/>metadata only"| DaemonVisit["WSL daemon /visit-events"]
  CaptureBridge --> MediaBridge
  MediaBridge -->|"PUT /media-artifacts/{id}/blob<br/>raw bytes"| DaemonMedia["WSL media blob upload"]
  MediaBridge --> MediaIDB[("Separate IndexedDB media task/blob queue<br/>atomic batch/blob transitions<br/>500 tasks / 512 MiB / terminal TTL")]
  CaptureBridge --> Telemetry
  MediaBridge --> Telemetry
  CDPSession --> Telemetry
  Popup["popup.js"] -->|"runtime messages"| ServiceWorker
  Options["options.js"] --> Storage[("chrome.storage.local")]
  Storage --> Content
  Storage --> Config
```

C4 shows the extension, service worker, browser storage, and daemon containers/components. This diagram keeps protocol names, endpoint names, and popup/options/storage wiring in one place.

---

## 2. Policy mode ladder

```mermaid
flowchart TD
  Mode{"policy_mode"}
  Mode --> All["all<br/>Capture Chrome-allowed URL surfaces unless explicitly blocked<br/>No daemon redaction<br/>Skip hidden/form/editable/script/style/no-script DOM text"]
  Mode --> Recall["recall<br/>Block internal/non-web/incognito<br/>Redact URL/title/body before storage"]
  Mode --> Balanced["balanced<br/>Recall + private-host / known-risk blocks<br/>Redact URL/title/body before storage"]
  Mode --> Strict["strict<br/>Legacy broad keyword blocks<br/>Redact URL/title/body before storage"]
```

Operator posture: start at `all` for maximum recall; move upward only when filtering becomes more important than recall completeness.

---

## 3. Capture ingest and redaction branch

```mermaid
flowchart TD
  Page["Chrome page light DOM"] --> Extract["Content script extracts rendered<br/>URL + title + text + media refs<br/>and computes full digest"]
  Extract -->|"BMD_CAPTURE"| SW["Service worker"]
  SW --> Outbox[("Transactional IndexedDB outbox")]
  Outbox -->|"claim due row"| SW
  SW -->|"POST /capture + bearer token"| API["WSL API"]
  API --> Policy["Policy engine<br/>mode + local rules"]
  Policy --> Decision{"policy_mode"}
  Decision -->|"all"| All["Store original URL/title/text<br/>no daemon redaction"]
  Decision -->|"recall / balanced / strict"| Redact["Redact URL/title/body<br/>before persistence"]
  All --> Store["Ingest pipeline<br/>normalize URL + text hash<br/>write visits/observations/documents/snapshots/chunks/FTS"]
  Redact --> Store
  Store --> SQLiteText["Commit complete cleaned text<br/>inside local SQLite transaction"]
  Store --> MediaRefs["Store media refs + observation links<br/>enqueue daemon-public tasks"]
  Store --> Response["Return observation/document/snapshot/chunk IDs<br/>+ media artifact IDs"]
  Response --> Checkpoint["Checkpoint capture result<br/>in claimed outbox row"]
  Checkpoint --> Queue["Queue browser media work<br/>in separate IndexedDB"]
  Queue --> Ack["Acknowledge outbox row"]
```

Text/FTS recall completes before media bytes. Media sidecars are best-effort and asynchronous.

---

## 4. Durable media sidecars and cache outcomes

```mermaid
flowchart TB
  CaptureResult["/capture response<br/>document/snapshot/artifact IDs"] --> BrowserQueue[("Chrome IndexedDB media queue")]
  CaptureResult --> DaemonTasks[("SQLite media_fetch_tasks")]
  CaptureResult --> CDP["CDP recorder<br/>x.com/twitter.com tabs<br/>video.twimg.com Network events"]

  BrowserQueue --> BrowserFetch["Browser lazy sidecar<br/>fetch(credentials: include)"]
  BrowserFetch --> BrowserBlob[("IndexedDB fetched blob")]
  BrowserBlob --> RawPut["PUT /media-artifacts/{id}/blob"]
  RawPut --> RootReady{"guarded media root<br/>ready?"}
  RootReady -->|"yes"| MediaBlobs[("BMD_MEDIA_ROOT<br/>final disposable bytes")]
  RootReady -->|"no"| SpoolReady{"explicit local spool<br/>reservation available?"}
  SpoolReady -->|"yes"| MediaSpool[("bounded local media spool")]
  SpoolReady -->|"no"| MediaUnavailable["media write rejected visibly<br/>text/provenance remain committed"]
  MediaBlobs --> Stored["media_artifacts.status = stored<br/>tier = media-root<br/>hash + byte_size recorded"]
  MediaSpool --> Spooled["media_artifacts.status = stored<br/>tier = spool<br/>hash + byte_size recorded"]
  Spooled --> BrowserDone
  Stored --> BrowserDone["delete completed IndexedDB task"]

  CDP --> CdpRows["cdp_recorder=true rows<br/>manifests/segments or response bodies"]
  CdpRows --> RawPut
  CdpRows --> DaemonTasks
  CdpRows --> Covered["same-page blob refs may become<br/>covered-by-cdp-recorder"]

  DaemonTasks --> Lease["daemon media worker lease"]
  Lease --> PublicFetch["public fetch / HLS assembly<br/>no Chrome cookies"]
  PublicFetch --> RootReady
  PublicFetch --> Classified["referenced / metadata-only / retrying<br/>stored / skipped / expired / failed"]

  MediaBlobs --> Rolling["domain/global rolling cache<br/>oldest blob eviction"]
  MediaSpool --> Drain["worker auto-drain when root is ready<br/>manual dry-run-first override<br/>stream + verify size/SHA-256"]
  Drain --> MediaBlobs
  Drain --> TierSwitch["compare-and-switch SQLite tier<br/>then remove spool source"]
  Rolling --> Purged["status = purged<br/>refs/hash/provenance remain"]
```

The final media cache is bounded and disposable. The optional local spool has a separate hard byte cap covering committed/orphaned files plus distinct in-flight reservations. Each worker pass checks guarded-root readiness and automatically drains at most one bounded batch before claiming new fetch work; the manual command remains a dry-run-first override. SQLite version 13 also reserves snapshot/domain/global cache capacity transactionally across processes, while process-local request and byte leases bound concurrent streaming HTTP/HLS/upload/download work. Text, FTS rows, media refs, hashes, status reasons, and provenance remain authoritative when bytes are absent, spooled, purged, or delayed by resource pressure.

---

## 5. Dedupe and versioning

```mermaid
flowchart TD
  Capture["Capture payload"] --> Normalize["Normalize URL"]
  Normalize --> DocID["document_id = hash(normalized URL)"]
  Capture --> TextHash["text_hash = hash(stored text)"]
  DocID --> SnapshotID["snapshot_id = hash(document_id + text_hash)"]
  TextHash --> SnapshotID
  SnapshotID --> Exists{"snapshot exists?"}
  Exists -->|"yes"| ObservationOnly["Insert observation linked to existing snapshot"]
  Exists -->|"no"| NewSnapshot["Create snapshot + chunks + FTS rows<br/>then insert observation"]
```

Repeated unchanged extractions add observations without duplicating text or replacing the visit. Changed text at the same normalized observed URL creates another snapshot under the same document, and each observation retains its contemporaneous snapshot.

---

## 6. Lifecycle telemetry

```mermaid
flowchart LR
  Start(("start")) --> Active["Active"]
  Active --> Deactivate["tab deactivated<br/>window blurred"] --> Inactive["Inactive"]
  Inactive --> Reactivate["tab activated<br/>window focused"] --> Active
  Active --> Close["tab closed"] --> Closed["Closed"] --> End(("end"))
  Active --> Navigate["navigation-away<br/>SPA route"] --> Navigated["Navigated"]
  Navigated --> NewURL["new URL state"] --> Active
  Deactivate --> Identity{"exact claimed<br/>visit exists?"}
  Close --> Identity
  Navigate --> Identity
  Identity -->|yes| Link["link by visit ID"]
  Identity -->|not yet| Pending["store claimed ID<br/>attachment=unmatched"]
  Pending --> Capture["matching capture arrives"] --> Link
  Link --> Union["validate + union all<br/>positive active intervals"]
  Union --> Dwell["replace derived dwell"]
```

Lifecycle events carry claimed visit identity, URL, timezone-qualified timestamps, active seconds, and max-scroll percent. Identity-bearing events never fall back to the latest same-URL visit; delayed capture reconciles by claimed ID plus normalized observed URL. Dwell is the union of valid positive-active intervals, not an additive counter. `/visit-events` is metadata-only; body text only flows through `/capture`.

---

## 7. Local read endpoint map

```mermaid
flowchart LR
  Search["GET /search"] --> FTS[("chunks_fts")]
  Recent["GET /recent<br/>observation-first + explicit legacy fallback"] --> DB[("SQLite")]
  Timeline["GET /timeline<br/>observation-first"] --> DB
  Detail["GET /documents/{id}<br/>observations + URL claims"] --> DB
  Snapshot["GET /snapshots/{id}<br/>exact observations"] --> DB
  Media["GET /media-artifacts/{id}"] --> MediaBlobs[("blobs/media")]
  UI["Local UI"] --> Search
  UI --> Recent
  UI --> Timeline
  UI --> Detail
  UI --> Snapshot
  UI --> Media
  CLI["CLI"] --> Search
  CLI --> Recent
  CLI --> Timeline
  CLI --> Detail
```

The read model is exact-search-first. Semantic search and agent/MCP tools are later lanes, not current runtime architecture.

---

## 8. Forget/delete cascade

```mermaid
flowchart TD
  Scope{"Forget scope"}
  Scope --> Domain["domain"]
  Scope --> URL["url"]
  Domain --> Match["Find matching documents/visits"]
  URL --> Match
  Match --> Tx["One SQLite transaction"]
  Tx --> Tombstones["Persist blob_storage_records<br/>state=tombstoned"]
  Tx --> DeleteRows["Delete FTS/chunks/snapshots/media/<br/>events/visits/documents"]
  Tx --> Receipt["Persist minimized deletion receipt"]
  Tombstones --> Commit{"Transaction commits?"}
  DeleteRows --> Commit
  Receipt --> Commit
  Commit -->|no| Rollback["No cascade or tombstone is durable"]
  Commit -->|yes| Processor["Serialized contained tombstone processor"]
  Processor --> Outcome{"BlobStore delete outcome"}
  Outcome -->|deleted| Deleted["state=deleted"]
  Outcome -->|already absent| Missing["state=missing"]
  Outcome -->|I/O failure| Failed["state=failed<br/>retryable"]
  Outcome -->|outside/unavailable| Blocked["state=blocked<br/>fail closed"]
  Failed --> Reconcile["storage reconcile --execute"]
  Blocked --> Reconcile
  Reconcile --> Processor
  Deleted --> Complete{"No pending records?"}
  Missing --> Complete
  Complete -->|yes| Success["forgotten=true"]
  Complete -->|no| Pending["forgotten=false<br/>database_forgotten=true"]
```

Forget returns database counts plus durable deletion state. It cannot report complete success while required bytes remain failed or blocked.

---

## Provenance

| Diagram | Primary source files/docs |
|---|---|
| Extension protocol boundary | `manifest.json`, `extension/src/extractor.js`, `content_script.js`, `service_worker.js`, `popup.js`, `options.js`, `media_queue.js` |
| Policy mode ladder | `docs/security-model.md`, `daemon/src/browser_memory_daemon/policy.py`, `policy_store.py`, `extension/src/extractor.js` |
| Capture ingest and redaction branch | `docs/api.md`, `daemon/src/browser_memory_daemon/http_server.py`, `application.py`, `ingest.py`, `policy.py`, `schema.sql`, `extension/src/service_worker.js` |
| Durable media sidecars and cache outcomes | `docs/media-artifacts.md`, `daemon/src/browser_memory_daemon/media.py`, `media_worker.py`, `schema.sql`, `extension/src/media_queue.js`, `cdp_recorder.js`, `service_worker.js` |
| Dedupe and versioning | `daemon/src/browser_memory_daemon/ingest.py`, `schema.sql`, ingest tests |
| Lifecycle telemetry | `docs/api.md`, `daemon/src/browser_memory_daemon/lifecycle.py`, `schema.sql`, `extension/src/service_worker.js` |
| Local read endpoint map | `docs/api.md`, `daemon/src/browser_memory_daemon/search.py`, `ops.py`, `ui/`, `cli.py` |
| Forget/delete cascade | `docs/api.md`, `daemon/src/browser_memory_daemon/forget.py`, `schema.sql`, forget tests |
