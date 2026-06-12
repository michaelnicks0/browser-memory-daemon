# Browser Memory Daemon Diagrams — Visual Atlas

> **Audience:** maintainers and future agents.
> **Format:** Mermaid diagrams embedded in Markdown.
> **Scope:** current Windows Chrome + WSL implementation.

---

## 1. System context

```mermaid
flowchart TB
  Operator[Operator] --> Chrome[Windows Chrome]
  Chrome --> Extension[Browser Memory MV3 extension]
  Extension -->|Bearer HTTP over localhost| Daemon[WSL browser-memory daemon]
  Daemon --> SQLite[(SQLite + FTS5)]
  Daemon --> MediaWorker[Media worker]
  MediaWorker --> SQLite
  Daemon --> Blobs[Clean text + media blobs]
  MediaWorker --> Blobs
  Daemon --> UI[Local UI]
  Daemon --> CLI[CLI]
  UI --> Operator
  CLI --> Operator
```

This is a local-first single-operator system. The browser surface is Windows Chrome; durable data and search live in WSL.

---

## 2. Extension runtime boundary

```mermaid
flowchart LR
  Page[Page DOM] --> Extractor[extractor.js]
  Extractor --> Content[content_script.js]
  Content -->|chrome.runtime.sendMessage| ServiceWorker[service_worker.js]
  ServiceWorker -->|fast fetch /capture| DaemonCapture[POST /capture]
  ServiceWorker -->|fetch /visit-events| DaemonVisit[POST /visit-events]
  ServiceWorker -->|credentialed media fetch + raw PUT| DaemonMedia["PUT /media-artifacts/id/blob"]
  ServiceWorker --> IDB[(IndexedDB media queue)]
  Popup[popup.js] --> ServiceWorker
  Options[options.js] --> Storage[(chrome.storage.local)]
  Storage --> Content
  Storage --> ServiceWorker
```

Content scripts extract and message; they do not call the daemon directly. The service worker owns auth, queues, tab state, and daemon transport.

---

## 3. Policy mode ladder

```mermaid
flowchart TD
  Mode{policy_mode}
  Mode --> All["all"]
  Mode --> Recall["recall"]
  Mode --> Balanced["balanced"]
  Mode --> Strict["strict"]

  All --> AllOutcome["Capture all URL surfaces Chrome allows<br/>No daemon redaction<br/>Skip hidden/form/editable/script/style/no-script DOM text<br/>Ignore block rules"]
  Recall --> RecallOutcome["Capture most http(s)<br/>Block internal/non-web/incognito<br/>Redact"]
  Balanced --> BalancedOutcome["Recall + private-host/known-risk blocks<br/>Redact"]
  Strict --> StrictOutcome["Legacy broad keyword blocks<br/>Redact"]
```

The operator can start at `all` and move upward only if recall completeness becomes less important than filtering.

---

## 4. Capture ingest pipeline

```mermaid
sequenceDiagram
  participant Page as Chrome page
  participant CS as Content script
  participant SW as Service worker
  participant API as WSL API
  participant Ingest as Ingest pipeline
  participant DB as SQLite/FTS

  Page->>CS: DOM text + URL + title + media refs
  CS->>SW: BMD_CAPTURE payload
  SW->>API: POST /capture + bearer token
  API->>API: evaluate policy mode
  API->>Ingest: CapturePayload
  Ingest->>Ingest: normalize URL + text hash
  alt policy_mode = all
    Ingest->>DB: store original URL/title/text
  else non-all mode
    Ingest->>Ingest: redact URL/title/text
    Ingest->>DB: store redacted URL/title/text
  end
  DB-->>API: document/snapshot/chunk IDs + media artifact IDs
  API-->>SW: stored result
```

`all` bypasses redaction. Other modes redact before DB/FTS/blob storage. Media binary fetch is intentionally outside this fast path.

---

## 5. Durable media sidecars

```mermaid
flowchart TB
  Capture["/capture result with artifact IDs"] --> BrowserQueue[(Chrome IndexedDB media queue)]
  Capture --> DaemonTasks[(SQLite media_fetch_tasks)]
  Capture --> CDP["CDP recorder<br/>x.com/twitter.com only"]

  BrowserQueue --> BrowserFetch["Browser lazy sidecar<br/>fetch(credentials: include)"]
  BrowserFetch --> BrowserBlob[(IndexedDB fetched blob)]
  BrowserBlob --> RawPut["PUT /media-artifacts/{id}/blob"]
  RawPut --> MediaBlobs[(blobs/media)]
  RawPut --> ArtifactStored["media_artifacts.status = stored"]

  CDP --> CdpRows["video.twimg.com<br/>manifests/segments"]
  CdpRows --> RawPut
  CdpRows --> DaemonTasks

  DaemonTasks --> Lease["daemon media worker lease"]
  Lease --> PublicFetch["public fetch / HLS assembly<br/>no Chrome cookies"]
  PublicFetch --> MediaBlobs
  PublicFetch --> Terminal["stored / referenced / skipped / expired"]

  MediaBlobs --> Rolling["domain/global rolling cache<br/>oldest blob eviction"]
  Rolling --> Purged["purged rows keep refs/metadata"]
```

This is the core durability split: text/FTS capture completes first; media bytes are best-effort sidecars with explicit states and cache controls.

---

## 6. Dedupe and versioning

```mermaid
flowchart TD
  Capture["Capture payload"] --> Normalize["Normalize URL"]
  Normalize --> DocID["document_id = hash(normalized URL)"]
  Capture --> TextHash["text_hash = hash(stored text)"]
  DocID --> SnapshotID["snapshot_id = hash(document_id + text_hash)"]
  SnapshotID --> Exists{"snapshot exists?"}
  Exists -->|yes| VisitOnly["Insert/update visit only"]
  Exists -->|no| NewSnapshot["Create snapshot + chunks + FTS rows"]
```

Repeated unchanged captures add visits without duplicating text. Changed text at the same normalized URL creates another snapshot under the same document.

---

## 7. Lifecycle telemetry

```mermaid
stateDiagram-v2
  [*] --> Active: tab active + URL trackable
  Active --> Inactive: tab deactivated / window blurred
  Active --> Closed: tab closed
  Active --> Navigated: navigation-away / SPA route
  Inactive --> Active: tab active again
  Closed --> [*]
  Navigated --> Active: new URL state
```

Lifecycle events carry URL, timestamps, active seconds, and max-scroll percent. Body text only flows through `/capture`.

---

## 8. Local read model

```mermaid
flowchart LR
  Search["GET /search"] --> FTS[(chunks_fts)]
  Recent["GET /recent"] --> DB[(SQLite)]
  Timeline["GET /timeline"] --> DB
  Detail["GET /documents/{id}"] --> DB
  Snapshot["GET /snapshots/{id}"] --> DB
  UI["Local UI"] --> Search
  UI --> Recent
  UI --> Timeline
  UI --> Detail
  CLI[CLI] --> Search
  CLI --> Recent
  CLI --> Timeline
  CLI --> Detail
```

The read model is exact-search-first. Semantic search and agent/MCP tools are later lanes.

---

## 9. Forget/delete cascade

```mermaid
flowchart TD
  Scope{Forget scope}
  Scope --> Domain[domain]
  Scope --> URL[url]
  Domain --> Match[Find matching documents/visits]
  URL --> Match
  Match --> DeleteEvents[Delete visit_events]
  Match --> DeleteFTS[Delete chunks_fts]
  Match --> DeleteChunks[Delete chunks]
  Match --> DeleteSnapshots[Delete snapshots + blobs]
  Match --> DeleteVisits[Delete visits]
  Match --> DeleteDocs[Delete documents]
  DeleteDocs --> Receipt[deletion_receipts]
```

Forget returns counts so the operator can verify which stores were affected.

---

## Provenance

These diagrams trace to current implementation files:

| Diagram | Source files |
|---|---|
| System/context | `README.md`, `config.py`, `app.py` |
| Extension boundary | `manifest.json`, `extractor.js`, `content_script.js`, `service_worker.js` |
| Policy ladder | `policy.py`, `extractor.js`, `options.js`, `install-daily-driver.sh` |
| Ingest pipeline | `models.py`, `ingest.py`, `schema.sql`, `media.py` |
| Media sidecars | `service_worker.js`, `media_queue.js`, `media.py`, `media_worker.py`, `schema.sql` |
| Lifecycle | `service_worker.js`, `lifecycle.py`, `schema.sql` |
| Read model | `search.py`, `ops.py`, `ui/`, `cli.py` |
| Forget/delete | `forget.py`, `schema.sql` |
