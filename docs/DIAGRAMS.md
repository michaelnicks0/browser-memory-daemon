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
  Page["Chrome page DOM"] --> Extractor["extractor.js"]
  Extractor --> Content["content_script.js"]
  Content -->|"BMD_CAPTURE + inline blob messages"| ServiceWorker["service_worker.js"]
  ServiceWorker -->|"POST /capture<br/>Bearer JSON"| DaemonCapture["WSL daemon /capture"]
  ServiceWorker -->|"POST /visit-events<br/>metadata only"| DaemonVisit["WSL daemon /visit-events"]
  ServiceWorker -->|"PUT /media-artifacts/{id}/blob<br/>raw bytes"| DaemonMedia["WSL media blob upload"]
  ServiceWorker --> IDB[("IndexedDB media task/blob queue")]
  Popup["popup.js"] -->|"runtime messages"| ServiceWorker
  Options["options.js"] --> Storage[("chrome.storage.local")]
  Storage --> Content
  Storage --> ServiceWorker
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
  Page["Chrome page DOM"] --> Extract["Content script extracts<br/>URL + title + text + media refs"]
  Extract -->|"BMD_CAPTURE"| SW["Service worker"]
  SW -->|"POST /capture + bearer token"| API["WSL API"]
  API --> Policy["Policy engine<br/>mode + local rules"]
  Policy --> Decision{"policy_mode"}
  Decision -->|"all"| All["Store original URL/title/text<br/>no daemon redaction"]
  Decision -->|"recall / balanced / strict"| Redact["Redact URL/title/body<br/>before persistence"]
  All --> Store["Ingest pipeline<br/>normalize URL + text hash<br/>write visits/documents/snapshots/chunks/FTS"]
  Redact --> Store
  Store --> TextBlobs["Write clean-text snapshot blob"]
  Store --> MediaRefs["Store media refs<br/>enqueue daemon-public tasks"]
  Store --> Response["Return document/snapshot/chunk IDs<br/>+ media artifact IDs"]
  Response --> Queue["Queue browser media work<br/>in IndexedDB"]
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
  RawPut --> MediaBlobs[("blobs/media")]
  RawPut --> Stored["media_artifacts.status = stored<br/>hash + byte_size recorded"]
  Stored --> BrowserDone["delete completed IndexedDB task"]

  CDP --> CdpRows["cdp_recorder=true rows<br/>manifests/segments or response bodies"]
  CdpRows --> RawPut
  CdpRows --> DaemonTasks
  CdpRows --> Covered["same-page blob refs may become<br/>covered-by-cdp-recorder"]

  DaemonTasks --> Lease["daemon media worker lease"]
  Lease --> PublicFetch["public fetch / HLS assembly<br/>no Chrome cookies"]
  PublicFetch --> MediaBlobs
  PublicFetch --> Classified["referenced / metadata-only / retrying<br/>stored / skipped / expired / failed"]

  MediaBlobs --> Rolling["domain/global rolling cache<br/>oldest blob eviction"]
  Rolling --> Purged["status = purged<br/>refs/hash/provenance remain"]
```

The media cache is bounded and disposable. Text, FTS rows, media refs, hashes, status reasons, and provenance remain authoritative when bytes are absent or purged.

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
  Exists -->|"yes"| VisitOnly["Insert/update visit only"]
  Exists -->|"no"| NewSnapshot["Create snapshot + chunks + FTS rows"]
```

Repeated unchanged captures add visits without duplicating text. Changed text at the same normalized URL creates another snapshot under the same document.

---

## 6. Lifecycle telemetry

```mermaid
flowchart LR
  Start(("start")) --> Active["Active"]
  Active --> Deactivate["tab deactivated<br/>window blurred"] --> Inactive["Inactive"]
  Inactive --> Reactivate["tab active again"] --> Active
  Active --> Close["tab closed"] --> Closed["Closed"] --> End(("end"))
  Active --> Navigate["navigation-away<br/>SPA route"] --> Navigated["Navigated"]
  Navigated --> NewURL["new URL state"] --> Active
```

Lifecycle events carry URL, timestamps, active seconds, and max-scroll percent. `/visit-events` is metadata-only; body text only flows through `/capture`.

---

## 7. Local read endpoint map

```mermaid
flowchart LR
  Search["GET /search"] --> FTS[("chunks_fts")]
  Recent["GET /recent"] --> DB[("SQLite")]
  Timeline["GET /timeline"] --> DB
  Detail["GET /documents/{id}"] --> DB
  Snapshot["GET /snapshots/{id}"] --> DB
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
  Match --> DeleteEvents["Delete visit_events"]
  Match --> DeleteFTS["Delete chunks_fts"]
  Match --> DeleteChunks["Delete chunks"]
  Match --> DeleteSnapshots["Delete snapshots + text blobs"]
  Match --> DeleteMedia["Delete media_artifacts + media blobs"]
  Match --> DeleteVisits["Delete visits"]
  Match --> DeleteDocs["Delete documents"]
  DeleteDocs --> Receipt["deletion_receipts + counts"]
  DeleteMedia --> Receipt
```

Forget returns counts so the operator can verify which stores were affected.

---

## Provenance

| Diagram | Primary source files/docs |
|---|---|
| Extension protocol boundary | `manifest.json`, `extension/src/extractor.js`, `content_script.js`, `service_worker.js`, `popup.js`, `options.js`, `media_queue.js` |
| Policy mode ladder | `docs/security-model.md`, `daemon/src/browser_memory_daemon/policy.py`, `policy_store.py`, `extension/src/extractor.js` |
| Capture ingest and redaction branch | `docs/api.md`, `daemon/src/browser_memory_daemon/app.py`, `ingest.py`, `policy.py`, `schema.sql`, `extension/src/service_worker.js` |
| Durable media sidecars and cache outcomes | `docs/media-artifacts.md`, `daemon/src/browser_memory_daemon/media.py`, `media_worker.py`, `schema.sql`, `extension/src/media_queue.js`, `cdp_recorder.js`, `service_worker.js` |
| Dedupe and versioning | `daemon/src/browser_memory_daemon/ingest.py`, `schema.sql`, ingest tests |
| Lifecycle telemetry | `docs/api.md`, `daemon/src/browser_memory_daemon/lifecycle.py`, `schema.sql`, `extension/src/service_worker.js` |
| Local read endpoint map | `docs/api.md`, `daemon/src/browser_memory_daemon/search.py`, `ops.py`, `ui/`, `cli.py` |
| Forget/delete cascade | `docs/api.md`, `daemon/src/browser_memory_daemon/forget.py`, `schema.sql`, forget tests |
