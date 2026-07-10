# Browser Memory Daemon Architecture C4 Diagrams

> Single-file generated C4 diagram atlas. Canonical model: [`workspace.dsl`](workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Reading notes

- This file intentionally includes every generated C4 view in one Markdown document.
- Diagrams prefer clean rendered artifacts first, usually Graphviz SVG with white-backed relationship labels.
- Mermaid source is retained under each diagram for text review and diffability.
- Generated per-view wrappers remain available at [`diagrams/markdown/`](diagrams/markdown); generated artifact index: [`diagrams/README.md`](diagrams/README.md).

## Diagram index

| View | Section | Preferred render | Per-view page |
|---|---|---|---|
| `BrowserMediaContainers` | [`BrowserMediaContainers`](#browser-media-containers) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-BrowserMediaContainers.svg) | [`BrowserMediaContainers.md`](diagrams/markdown/BrowserMediaContainers.md) |
| `CaptureContainers` | [`CaptureContainers`](#capture-containers) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-CaptureContainers.svg) | [`CaptureContainers.md`](diagrams/markdown/CaptureContainers.md) |
| `CredentialedMediaSidecarFlow` | [`CredentialedMediaSidecarFlow`](#credentialed-media-sidecar-flow) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-CredentialedMediaSidecarFlow.svg) | [`CredentialedMediaSidecarFlow.md`](diagrams/markdown/CredentialedMediaSidecarFlow.md) |
| `DaemonDoctorComponents` | [`DaemonDoctorComponents`](#daemon-doctor-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonDoctorComponents.svg) | [`DaemonDoctorComponents.md`](diagrams/markdown/DaemonDoctorComponents.md) |
| `DaemonForgetComponents` | [`DaemonForgetComponents`](#daemon-forget-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonForgetComponents.svg) | [`DaemonForgetComponents.md`](diagrams/markdown/DaemonForgetComponents.md) |
| `DaemonIngestComponents` | [`DaemonIngestComponents`](#daemon-ingest-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonIngestComponents.svg) | [`DaemonIngestComponents.md`](diagrams/markdown/DaemonIngestComponents.md) |
| `DaemonLifecycleComponents` | [`DaemonLifecycleComponents`](#daemon-lifecycle-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonLifecycleComponents.svg) | [`DaemonLifecycleComponents.md`](diagrams/markdown/DaemonLifecycleComponents.md) |
| `DaemonMediaComponents` | [`DaemonMediaComponents`](#daemon-media-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonMediaComponents.svg) | [`DaemonMediaComponents.md`](diagrams/markdown/DaemonMediaComponents.md) |
| `DaemonMediaWorkerContainers` | [`DaemonMediaWorkerContainers`](#daemon-media-worker-containers) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonMediaWorkerContainers.svg) | [`DaemonMediaWorkerContainers.md`](diagrams/markdown/DaemonMediaWorkerContainers.md) |
| `DaemonMigrationComponents` | [`DaemonMigrationComponents`](#daemon-migration-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonMigrationComponents.svg) | [`DaemonMigrationComponents.md`](diagrams/markdown/DaemonMigrationComponents.md) |
| `DaemonPolicyComponents` | [`DaemonPolicyComponents`](#daemon-policy-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonPolicyComponents.svg) | [`DaemonPolicyComponents.md`](diagrams/markdown/DaemonPolicyComponents.md) |
| `DaemonPublicMediaWorkerFlow` | [`DaemonPublicMediaWorkerFlow`](#daemon-public-media-worker-flow) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonPublicMediaWorkerFlow.svg) | [`DaemonPublicMediaWorkerFlow.md`](diagrams/markdown/DaemonPublicMediaWorkerFlow.md) |
| `DaemonReadComponents` | [`DaemonReadComponents`](#daemon-read-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DaemonReadComponents.svg) | [`DaemonReadComponents.md`](diagrams/markdown/DaemonReadComponents.md) |
| `DailyDriverDeployment` | [`DailyDriverDeployment`](#daily-driver-deployment) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-DailyDriverDeployment.svg) | [`DailyDriverDeployment.md`](diagrams/markdown/DailyDriverDeployment.md) |
| `ExtensionCaptureComponents` | [`ExtensionCaptureComponents`](#extension-capture-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-ExtensionCaptureComponents.svg) | [`ExtensionCaptureComponents.md`](diagrams/markdown/ExtensionCaptureComponents.md) |
| `ExtensionMediaComponents` | [`ExtensionMediaComponents`](#extension-media-components) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-ExtensionMediaComponents.svg) | [`ExtensionMediaComponents.md`](diagrams/markdown/ExtensionMediaComponents.md) |
| `FastCaptureFlow` | [`FastCaptureFlow`](#fast-capture-flow) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-FastCaptureFlow.svg) | [`FastCaptureFlow.md`](diagrams/markdown/FastCaptureFlow.md) |
| `OpsContainers` | [`OpsContainers`](#ops-containers) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-OpsContainers.svg) | [`OpsContainers.md`](diagrams/markdown/OpsContainers.md) |
| `SystemContext` | [`SystemContext`](#system-context) | [`Graphviz SVG`](diagrams/dot-rendered/structurizr-SystemContext.svg) | [`SystemContext.md`](diagrams/markdown/SystemContext.md) |

---

## Browser Media Containers

> C4 view `BrowserMediaContainers`.

### Diagram

![Browser Media Containers](diagrams/dot-rendered/structurizr-BrowserMediaContainers.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph TB
  linkStyle default fill:#ffffff

  subgraph diagram ["Container View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      13[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side storage for<br />capture and visit queues in<br />chrome.storage.local plus<br />durable media tasks and<br />fetched blobs in IndexedDB.</div>")]
      style 13 fill:#2f95c8,stroke:#20688c,color:#ffffff
      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
      5["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
      style 5 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    5-. "<div>Extracts DOM refs and fetches<br />queued credentialed media<br />from</div><div style='font-size: 70%'>[DOM; fetch(credentials: include)]</div>" .->3
    5-. "<div>Queues captures, lifecycle<br />events, media tasks, and<br />blobs in</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13
    5-. "<div>Posts /capture,<br />/visit-events, media<br />metadata, and raw blob<br />uploads to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->14
    14-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    14-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->30

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-BrowserMediaContainers.mmd`](diagrams/structurizr-BrowserMediaContainers.mmd) |
| Mermaid SVG | [`structurizr-BrowserMediaContainers.svg`](diagrams/structurizr-BrowserMediaContainers.svg) |
| Mermaid PNG | [`structurizr-BrowserMediaContainers.png`](diagrams/structurizr-BrowserMediaContainers.png) |
| DOT source | [`structurizr-BrowserMediaContainers.dot`](diagrams/dot/structurizr-BrowserMediaContainers.dot) |
| Graphviz SVG | [`structurizr-BrowserMediaContainers.svg`](diagrams/dot-rendered/structurizr-BrowserMediaContainers.svg) |
| Graphviz PNG | [`structurizr-BrowserMediaContainers.png`](diagrams/dot-rendered/structurizr-BrowserMediaContainers.png) |


---

## Capture Containers

> C4 view `CaptureContainers`.

### Diagram

![Capture Containers](diagrams/dot-rendered/structurizr-CaptureContainers.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph TB
  linkStyle default fill:#ffffff

  subgraph diagram ["Container View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    2["<div style='font-weight: bold'>Windows Chrome</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>The Windows Chrome runtime<br />that loads web pages, hosts<br />the MV3 extension, runs the<br />local UI in a tab, and<br />exposes Chrome extension<br />APIs.</div>"]
    style 2 fill:#999999,stroke:#6b6b6b,color:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      13[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side storage for<br />capture and visit queues in<br />chrome.storage.local plus<br />durable media tasks and<br />fetched blobs in IndexedDB.</div>")]
      style 13 fill:#2f95c8,stroke:#20688c,color:#ffffff
      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      5["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
      style 5 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    5-. "<div>Uses tab, scripting, storage,<br />alarms, debugger, and runtime<br />APIs from</div><div style='font-size: 70%'>[Chrome extension APIs]</div>" .->2
    5-. "<div>Queues captures, lifecycle<br />events, media tasks, and<br />blobs in</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13
    5-. "<div>Posts /capture,<br />/visit-events, media<br />metadata, and raw blob<br />uploads to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->14
    14-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    14-. "<div>Reads and writes text<br />snapshots in</div><div style='font-size: 70%'>[Filesystem]</div>" .->29

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-CaptureContainers.mmd`](diagrams/structurizr-CaptureContainers.mmd) |
| Mermaid SVG | [`structurizr-CaptureContainers.svg`](diagrams/structurizr-CaptureContainers.svg) |
| Mermaid PNG | [`structurizr-CaptureContainers.png`](diagrams/structurizr-CaptureContainers.png) |
| DOT source | [`structurizr-CaptureContainers.dot`](diagrams/dot/structurizr-CaptureContainers.dot) |
| Graphviz SVG | [`structurizr-CaptureContainers.svg`](diagrams/dot-rendered/structurizr-CaptureContainers.svg) |
| Graphviz PNG | [`structurizr-CaptureContainers.png`](diagrams/dot-rendered/structurizr-CaptureContainers.png) |


---

## Credentialed Media Sidecar Flow

> C4 view `CredentialedMediaSidecarFlow`.

### Diagram

![Credentialed Media Sidecar Flow](diagrams/dot-rendered/structurizr-CredentialedMediaSidecarFlow.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Dynamic View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      13[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side storage for<br />capture and visit queues in<br />chrome.storage.local plus<br />durable media tasks and<br />fetched blobs in IndexedDB.</div>")]
      style 13 fill:#2f95c8,stroke:#20688c,color:#ffffff
      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
      5["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
      style 5 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff

    5-. "<div>1. Reads due media task</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13
    5-. "<div>2. Fetches source URL with<br />Chrome cookie envelope</div><div style='font-size: 70%'>[DOM; fetch(credentials: include)]</div>" .->3
    5-. "<div>3. Persists fetched blob<br />until upload succeeds</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13
    5-. "<div>4. PUTs raw blob to<br />/media-artifacts/{id}/blob</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->14
    14-. "<div>5. Writes blob if MIME and<br />cache gates allow</div><div style='font-size: 70%'>[Filesystem]</div>" .->30
    14-. "<div>6. Updates artifact<br />status=stored, hash, byte<br />size, and task state</div><div style='font-size: 70%'>[sqlite3]</div>" .->28

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-CredentialedMediaSidecarFlow.mmd`](diagrams/structurizr-CredentialedMediaSidecarFlow.mmd) |
| Mermaid SVG | [`structurizr-CredentialedMediaSidecarFlow.svg`](diagrams/structurizr-CredentialedMediaSidecarFlow.svg) |
| Mermaid PNG | [`structurizr-CredentialedMediaSidecarFlow.png`](diagrams/structurizr-CredentialedMediaSidecarFlow.png) |
| DOT source | [`structurizr-CredentialedMediaSidecarFlow.dot`](diagrams/dot/structurizr-CredentialedMediaSidecarFlow.dot) |
| Graphviz SVG | [`structurizr-CredentialedMediaSidecarFlow.svg`](diagrams/dot-rendered/structurizr-CredentialedMediaSidecarFlow.svg) |
| Graphviz PNG | [`structurizr-CredentialedMediaSidecarFlow.png`](diagrams/dot-rendered/structurizr-CredentialedMediaSidecarFlow.png) |


---

## Daemon Doctor Components

> C4 view `DaemonDoctorComponents`.

### Diagram

![Daemon Doctor Components](diagrams/dot-rendered/structurizr-DaemonDoctorComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        15["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server]</div><div style='font-size: 80%; margin-top:10px'>Routes loopback API requests,<br />serves UI assets, enforces<br />bearer auth for memory/admin<br />APIs, and applies CORS for<br />allowed origins.</div>"]
        style 15 fill:#85bbf0,stroke:#1168bd,color:#000000
        24["<div style='font-weight: bold'>Ops Doctor and Audit</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Reports health, DB integrity,<br />FTS consistency, runtime<br />paths, storage counts, media<br />queue status, and writes<br />metadata-only audit events to<br />SQLite.</div>"]
        style 24 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes health and audit work<br />to</div><div style='font-size: 70%'></div>" .->24
    24-. "<div>Checks integrity and counts<br />in</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    24-. "<div>Counts text blob files in</div><div style='font-size: 70%'>[Filesystem]</div>" .->29
    24-. "<div>Counts media blob files in</div><div style='font-size: 70%'>[Filesystem]</div>" .->30

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonDoctorComponents.mmd`](diagrams/structurizr-DaemonDoctorComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonDoctorComponents.svg`](diagrams/structurizr-DaemonDoctorComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonDoctorComponents.png`](diagrams/structurizr-DaemonDoctorComponents.png) |
| DOT source | [`structurizr-DaemonDoctorComponents.dot`](diagrams/dot/structurizr-DaemonDoctorComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonDoctorComponents.svg`](diagrams/dot-rendered/structurizr-DaemonDoctorComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonDoctorComponents.png`](diagrams/dot-rendered/structurizr-DaemonDoctorComponents.png) |


---

## Daemon Forget Components

> C4 view `DaemonForgetComponents`.

### Diagram

![Daemon Forget Components](diagrams/dot-rendered/structurizr-DaemonForgetComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        15["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server]</div><div style='font-size: 80%; margin-top:10px'>Routes loopback API requests,<br />serves UI assets, enforces<br />bearer auth for memory/admin<br />APIs, and applies CORS for<br />allowed origins.</div>"]
        style 15 fill:#85bbf0,stroke:#1168bd,color:#000000
        23["<div style='font-weight: bold'>Forget Pipeline</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Deletes URL/domain-scoped<br />memory rows, FTS entries,<br />clean-text blobs, media<br />blobs, lifecycle rows, and<br />records deletion receipts.</div>"]
        style 23 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes forget requests to</div><div style='font-size: 70%'></div>" .->23
    23-. "<div>Deletes rows and records<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    23-. "<div>Deletes text blobs from</div><div style='font-size: 70%'>[Filesystem]</div>" .->29
    23-. "<div>Deletes media blobs from</div><div style='font-size: 70%'>[Filesystem]</div>" .->30

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonForgetComponents.mmd`](diagrams/structurizr-DaemonForgetComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonForgetComponents.svg`](diagrams/structurizr-DaemonForgetComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonForgetComponents.png`](diagrams/structurizr-DaemonForgetComponents.png) |
| DOT source | [`structurizr-DaemonForgetComponents.dot`](diagrams/dot/structurizr-DaemonForgetComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonForgetComponents.svg`](diagrams/dot-rendered/structurizr-DaemonForgetComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonForgetComponents.png`](diagrams/dot-rendered/structurizr-DaemonForgetComponents.png) |


---

## Daemon Ingest Components

> C4 view `DaemonIngestComponents`.

### Diagram

![Daemon Ingest Components](diagrams/dot-rendered/structurizr-DaemonIngestComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        15["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server]</div><div style='font-size: 80%; margin-top:10px'>Routes loopback API requests,<br />serves UI assets, enforces<br />bearer auth for memory/admin<br />APIs, and applies CORS for<br />allowed origins.</div>"]
        style 15 fill:#85bbf0,stroke:#1168bd,color:#000000
        19["<div style='font-weight: bold'>Ingest Pipeline</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Normalizes URLs, computes<br />document/snapshot IDs, stores<br />visits/snapshots/chunks/FTS<br />rows, writes clean text<br />blobs, and records media<br />references.</div>"]
        style 19 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes accepted captures to</div><div style='font-size: 70%'></div>" .->19
    19-. "<div>Writes capture rows and FTS<br />to</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    19-. "<div>Writes text snapshots to</div><div style='font-size: 70%'>[Filesystem]</div>" .->29

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonIngestComponents.mmd`](diagrams/structurizr-DaemonIngestComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonIngestComponents.svg`](diagrams/structurizr-DaemonIngestComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonIngestComponents.png`](diagrams/structurizr-DaemonIngestComponents.png) |
| DOT source | [`structurizr-DaemonIngestComponents.dot`](diagrams/dot/structurizr-DaemonIngestComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonIngestComponents.svg`](diagrams/dot-rendered/structurizr-DaemonIngestComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonIngestComponents.png`](diagrams/dot-rendered/structurizr-DaemonIngestComponents.png) |


---

## Daemon Lifecycle Components

> C4 view `DaemonLifecycleComponents`.

### Diagram

![Daemon Lifecycle Components](diagrams/dot-rendered/structurizr-DaemonLifecycleComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        15["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server]</div><div style='font-size: 80%; margin-top:10px'>Routes loopback API requests,<br />serves UI assets, enforces<br />bearer auth for memory/admin<br />APIs, and applies CORS for<br />allowed origins.</div>"]
        style 15 fill:#85bbf0,stroke:#1168bd,color:#000000
        20["<div style='font-weight: bold'>Lifecycle Pipeline</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Stores metadata-only tab<br />lifecycle events and updates<br />visit dwell seconds<br />idempotently.</div>"]
        style 20 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes lifecycle events to</div><div style='font-size: 70%'></div>" .->20
    20-. "<div>Writes lifecycle and dwell to</div><div style='font-size: 70%'>[sqlite3]</div>" .->28

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonLifecycleComponents.mmd`](diagrams/structurizr-DaemonLifecycleComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonLifecycleComponents.svg`](diagrams/structurizr-DaemonLifecycleComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonLifecycleComponents.png`](diagrams/structurizr-DaemonLifecycleComponents.png) |
| DOT source | [`structurizr-DaemonLifecycleComponents.dot`](diagrams/dot/structurizr-DaemonLifecycleComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonLifecycleComponents.svg`](diagrams/dot-rendered/structurizr-DaemonLifecycleComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonLifecycleComponents.png`](diagrams/dot-rendered/structurizr-DaemonLifecycleComponents.png) |


---

## Daemon Media Components

> C4 view `DaemonMediaComponents`.

### Diagram

![Daemon Media Components](diagrams/dot-rendered/structurizr-DaemonMediaComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        15["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server]</div><div style='font-size: 80%; margin-top:10px'>Routes loopback API requests,<br />serves UI assets, enforces<br />bearer auth for memory/admin<br />APIs, and applies CORS for<br />allowed origins.</div>"]
        style 15 fill:#85bbf0,stroke:#1168bd,color:#000000
        21["<div style='font-weight: bold'>Media Artifact Manager</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Records media references,<br />validates blob uploads,<br />enforces MIME/size/cache<br />gates, writes blobs<br />atomically, queues public<br />fetch tasks, and purges or<br />rehydrates cache entries.</div>"]
        style 21 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes media requests to</div><div style='font-size: 70%'></div>" .->21
    21-. "<div>Updates media rows and tasks<br />in</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    21-. "<div>Writes, serves, evicts, and<br />purges blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->30

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonMediaComponents.mmd`](diagrams/structurizr-DaemonMediaComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonMediaComponents.svg`](diagrams/structurizr-DaemonMediaComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonMediaComponents.png`](diagrams/structurizr-DaemonMediaComponents.png) |
| DOT source | [`structurizr-DaemonMediaComponents.dot`](diagrams/dot/structurizr-DaemonMediaComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonMediaComponents.svg`](diagrams/dot-rendered/structurizr-DaemonMediaComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonMediaComponents.png`](diagrams/dot-rendered/structurizr-DaemonMediaComponents.png) |


---

## Daemon Media Worker Containers

> C4 view `DaemonMediaWorkerContainers`.

### Diagram

![Daemon Media Worker Containers](diagrams/dot-rendered/structurizr-DaemonMediaWorkerContainers.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Container View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      25["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
      style 25 fill:#438dd5,stroke:#2e6295,color:#ffffff
      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    25-. "<div>Leases and updates media<br />tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    25-. "<div>Fetches public media and HLS<br />from</div><div style='font-size: 70%'>[HTTP(S), data URLs]</div>" .->3
    25-. "<div>Writes fetched media blobs to</div><div style='font-size: 70%'>[Filesystem]</div>" .->30

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonMediaWorkerContainers.mmd`](diagrams/structurizr-DaemonMediaWorkerContainers.mmd) |
| Mermaid SVG | [`structurizr-DaemonMediaWorkerContainers.svg`](diagrams/structurizr-DaemonMediaWorkerContainers.svg) |
| Mermaid PNG | [`structurizr-DaemonMediaWorkerContainers.png`](diagrams/structurizr-DaemonMediaWorkerContainers.png) |
| DOT source | [`structurizr-DaemonMediaWorkerContainers.dot`](diagrams/dot/structurizr-DaemonMediaWorkerContainers.dot) |
| Graphviz SVG | [`structurizr-DaemonMediaWorkerContainers.svg`](diagrams/dot-rendered/structurizr-DaemonMediaWorkerContainers.svg) |
| Graphviz PNG | [`structurizr-DaemonMediaWorkerContainers.png`](diagrams/dot-rendered/structurizr-DaemonMediaWorkerContainers.png) |


---

## Daemon Migration Components

> C4 view `DaemonMigrationComponents`.

### Diagram

![Daemon Migration Components](diagrams/dot-rendered/structurizr-DaemonMigrationComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        15["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server]</div><div style='font-size: 80%; margin-top:10px'>Routes loopback API requests,<br />serves UI assets, enforces<br />bearer auth for memory/admin<br />APIs, and applies CORS for<br />allowed origins.</div>"]
        style 15 fill:#85bbf0,stroke:#1168bd,color:#000000
        16["<div style='font-weight: bold'>Database Migration Kernel</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Validates exact schema<br />fingerprints, ordered<br />migration names/checksums,<br />and PRAGMA user_version;<br />applies transactional steps<br />and backup-gates destructive<br />changes.</div>"]
        style 16 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Requires compatible<br />initialized schema through</div><div style='font-size: 70%'></div>" .->16
    16-. "<div>Validates and advances schema<br />ledger/fingerprint in</div><div style='font-size: 70%'>[sqlite3 online backup + transactions]</div>" .->28

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonMigrationComponents.mmd`](diagrams/structurizr-DaemonMigrationComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonMigrationComponents.svg`](diagrams/structurizr-DaemonMigrationComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonMigrationComponents.png`](diagrams/structurizr-DaemonMigrationComponents.png) |
| DOT source | [`structurizr-DaemonMigrationComponents.dot`](diagrams/dot/structurizr-DaemonMigrationComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonMigrationComponents.svg`](diagrams/dot-rendered/structurizr-DaemonMigrationComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonMigrationComponents.png`](diagrams/dot-rendered/structurizr-DaemonMigrationComponents.png) |


---

## Daemon Policy Components

> C4 view `DaemonPolicyComponents`.

### Diagram

![Daemon Policy Components](diagrams/dot-rendered/structurizr-DaemonPolicyComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        15["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server]</div><div style='font-size: 80%; margin-top:10px'>Routes loopback API requests,<br />serves UI assets, enforces<br />bearer auth for memory/admin<br />APIs, and applies CORS for<br />allowed origins.</div>"]
        style 15 fill:#85bbf0,stroke:#1168bd,color:#000000
        17["<div style='font-weight: bold'>Policy Engine</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Evaluates<br />all/recall/balanced/strict<br />capture mode decisions and<br />redacts URL/title/body text<br />outside all mode.</div>"]
        style 17 fill:#85bbf0,stroke:#1168bd,color:#000000
        18["<div style='font-weight: bold'>Policy Store</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + SQLite]</div><div style='font-size: 80%; margin-top:10px'>Persists and evaluates<br />explicit local block-domain<br />and URL-prefix rules for<br />every policy mode.</div>"]
        style 18 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

    end

    15-. "<div>Gets capture decisions from</div><div style='font-size: 70%'></div>" .->17
    15-. "<div>Manages policy rules through</div><div style='font-size: 70%'></div>" .->18
    17-. "<div>Combines static mode with<br />rules from</div><div style='font-size: 70%'></div>" .->18

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonPolicyComponents.mmd`](diagrams/structurizr-DaemonPolicyComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonPolicyComponents.svg`](diagrams/structurizr-DaemonPolicyComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonPolicyComponents.png`](diagrams/structurizr-DaemonPolicyComponents.png) |
| DOT source | [`structurizr-DaemonPolicyComponents.dot`](diagrams/dot/structurizr-DaemonPolicyComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonPolicyComponents.svg`](diagrams/dot-rendered/structurizr-DaemonPolicyComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonPolicyComponents.png`](diagrams/dot-rendered/structurizr-DaemonPolicyComponents.png) |


---

## Daemon Public Media Worker Flow

> C4 view `DaemonPublicMediaWorkerFlow`.

### Diagram

![Daemon Public Media Worker Flow](diagrams/dot-rendered/structurizr-DaemonPublicMediaWorkerFlow.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Dynamic View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      25["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
      style 25 fill:#438dd5,stroke:#2e6295,color:#ffffff
      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff

    25-. "<div>1. Claims due daemon-public<br />media_fetch_tasks</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    25-. "<div>2. Fetches public media or<br />HLS assets without Chrome<br />cookies</div><div style='font-size: 70%'>[HTTP(S), data URLs]</div>" .->3
    25-. "<div>3. Writes fetched or<br />assembled blob when gates<br />allow</div><div style='font-size: 70%'>[Filesystem]</div>" .->30
    25-. "<div>4. Marks task/artifact<br />stored, retrying, skipped,<br />expired, or failed with<br />reason</div><div style='font-size: 70%'>[sqlite3]</div>" .->28

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonPublicMediaWorkerFlow.mmd`](diagrams/structurizr-DaemonPublicMediaWorkerFlow.mmd) |
| Mermaid SVG | [`structurizr-DaemonPublicMediaWorkerFlow.svg`](diagrams/structurizr-DaemonPublicMediaWorkerFlow.svg) |
| Mermaid PNG | [`structurizr-DaemonPublicMediaWorkerFlow.png`](diagrams/structurizr-DaemonPublicMediaWorkerFlow.png) |
| DOT source | [`structurizr-DaemonPublicMediaWorkerFlow.dot`](diagrams/dot/structurizr-DaemonPublicMediaWorkerFlow.dot) |
| Graphviz SVG | [`structurizr-DaemonPublicMediaWorkerFlow.svg`](diagrams/dot-rendered/structurizr-DaemonPublicMediaWorkerFlow.svg) |
| Graphviz PNG | [`structurizr-DaemonPublicMediaWorkerFlow.png`](diagrams/dot-rendered/structurizr-DaemonPublicMediaWorkerFlow.png) |


---

## Daemon Read Components

> C4 view `DaemonReadComponents`.

### Diagram

![Daemon Read Components](diagrams/dot-rendered/structurizr-DaemonReadComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        15["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server]</div><div style='font-size: 80%; margin-top:10px'>Routes loopback API requests,<br />serves UI assets, enforces<br />bearer auth for memory/admin<br />APIs, and applies CORS for<br />allowed origins.</div>"]
        style 15 fill:#85bbf0,stroke:#1168bd,color:#000000
        22["<div style='font-weight: bold'>Search and Read Model</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + SQLite FTS5]</div><div style='font-size: 80%; margin-top:10px'>Provides exact FTS search,<br />recent captures, timeline,<br />document detail, snapshot<br />detail, and media artifact<br />detail views.</div>"]
        style 22 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes read requests to</div><div style='font-size: 70%'></div>" .->22
    22-. "<div>Reads metadata and FTS from</div><div style='font-size: 70%'>[SQLite FTS5]</div>" .->28
    22-. "<div>Reads full snapshot text from</div><div style='font-size: 70%'>[Filesystem]</div>" .->29
    22-. "<div>Checks and serves media files<br />from</div><div style='font-size: 70%'>[Filesystem]</div>" .->30

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonReadComponents.mmd`](diagrams/structurizr-DaemonReadComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonReadComponents.svg`](diagrams/structurizr-DaemonReadComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonReadComponents.png`](diagrams/structurizr-DaemonReadComponents.png) |
| DOT source | [`structurizr-DaemonReadComponents.dot`](diagrams/dot/structurizr-DaemonReadComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonReadComponents.svg`](diagrams/dot-rendered/structurizr-DaemonReadComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonReadComponents.png`](diagrams/dot-rendered/structurizr-DaemonReadComponents.png) |


---

## Daily Driver Deployment

> C4 view `DailyDriverDeployment`.

### Diagram

![Daily Driver Deployment](diagrams/dot-rendered/structurizr-DailyDriverDeployment.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph TB
  linkStyle default fill:#ffffff

  subgraph diagram ["Deployment View: Browser Memory Daemon - Daily-driver local"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 88 ["Local workstation"]
      style 88 fill:#ffffff,stroke:#444444,color:#444444

      subgraph 89 ["Windows user profile"]
        style 89 fill:#ffffff,stroke:#444444,color:#444444

        subgraph 90 ["Windows Chrome daily-driver profile"]
          style 90 fill:#ffffff,stroke:#444444,color:#444444

          91["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
          style 91 fill:#438dd5,stroke:#2e6295,color:#ffffff
          94["<div style='font-weight: bold'>Local Web UI</div><div style='font-size: 70%; margin-top: 0px'>[Container: HTML/CSS/JavaScript served by daemon]</div><div style='font-size: 80%; margin-top:10px'>Static browser UI for exact<br />search, recent/timeline<br />views, document/snapshot<br />detail, media artifact<br />opening, policy rules,<br />doctor, and forget-domain<br />operations.</div>"]
          style 94 fill:#438dd5,stroke:#2e6295,color:#ffffff
        end

      end

      subgraph 96 ["WSL2 Ubuntu"]
        style 96 fill:#ffffff,stroke:#444444,color:#444444

        subgraph 102 ["WSL shell"]
          style 102 fill:#ffffff,stroke:#444444,color:#444444

        end

        subgraph 105 ["WSL XDG runtime data paths"]
          style 105 fill:#ffffff,stroke:#444444,color:#444444

          106[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
          style 106 fill:#2f95c8,stroke:#20688c,color:#ffffff
        end

        subgraph 111 ["WSL-mounted NAS blob root"]
          style 111 fill:#ffffff,stroke:#444444,color:#444444

          112[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
          style 112 fill:#2f95c8,stroke:#20688c,color:#ffffff
          114[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
          style 114 fill:#2f95c8,stroke:#20688c,color:#ffffff
        end

        subgraph 97 ["systemd --user services"]
          style 97 fill:#ffffff,stroke:#444444,color:#444444

          101["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
          style 101 fill:#438dd5,stroke:#2e6295,color:#ffffff
          98["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
          style 98 fill:#438dd5,stroke:#2e6295,color:#ffffff
        end

      end

    end

    94-. "<div>Calls authenticated read,<br />admin, media, and forget APIs<br />on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->98
    98-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->106
    101-. "<div>Leases and updates media<br />tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->106
    98-. "<div>Reads and writes text<br />snapshots in</div><div style='font-size: 70%'>[Filesystem]</div>" .->112
    98-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->114
    101-. "<div>Writes fetched media blobs to</div><div style='font-size: 70%'>[Filesystem]</div>" .->114
    91-. "<div>Posts /capture,<br />/visit-events, media<br />metadata, and raw blob<br />uploads to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->98

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DailyDriverDeployment.mmd`](diagrams/structurizr-DailyDriverDeployment.mmd) |
| Mermaid SVG | [`structurizr-DailyDriverDeployment.svg`](diagrams/structurizr-DailyDriverDeployment.svg) |
| Mermaid PNG | [`structurizr-DailyDriverDeployment.png`](diagrams/structurizr-DailyDriverDeployment.png) |
| DOT source | [`structurizr-DailyDriverDeployment.dot`](diagrams/dot/structurizr-DailyDriverDeployment.dot) |
| Graphviz SVG | [`structurizr-DailyDriverDeployment.svg`](diagrams/dot-rendered/structurizr-DailyDriverDeployment.svg) |
| Graphviz PNG | [`structurizr-DailyDriverDeployment.png`](diagrams/dot-rendered/structurizr-DailyDriverDeployment.png) |


---

## Extension Capture Components

> C4 view `ExtensionCaptureComponents`.

### Diagram

![Extension Capture Components](diagrams/dot-rendered/structurizr-ExtensionCaptureComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - Chrome MV3 Extension"]
    style diagram fill:#ffffff,stroke:#ffffff

    2["<div style='font-weight: bold'>Windows Chrome</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>The Windows Chrome runtime<br />that loads web pages, hosts<br />the MV3 extension, runs the<br />local UI in a tab, and<br />exposes Chrome extension<br />APIs.</div>"]
    style 2 fill:#999999,stroke:#6b6b6b,color:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 5 ["Chrome MV3 Extension"]
        style 5 fill:#ffffff,stroke:#2e6295,color:#2e6295

        12["<div style='font-weight: bold'>Popup and Options UI</div><div style='font-size: 70%; margin-top: 0px'>[Component: HTML/JavaScript]</div><div style='font-size: 80%; margin-top:10px'>Lets the operator view<br />status, pause/resume capture,<br />select policy mode, and<br />trigger local controls from<br />the extension.</div>"]
        style 12 fill:#85bbf0,stroke:#1168bd,color:#000000
        6["<div style='font-weight: bold'>Manifest and Permission Envelope</div><div style='font-size: 70%; margin-top: 0px'>[Component: manifest.json]</div><div style='font-size: 80%; margin-top:10px'>Declares MV3 permissions,<br />host permissions, service<br />worker, popup, and options<br />entrypoints.</div>"]
        style 6 fill:#85bbf0,stroke:#1168bd,color:#000000
        7["<div style='font-weight: bold'>Extractor</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript]</div><div style='font-size: 80%; margin-top:10px'>Traverses visible DOM text<br />and discovers image/video<br />references while applying the<br />selected policy mode.</div>"]
        style 7 fill:#85bbf0,stroke:#1168bd,color:#000000
        8["<div style='font-weight: bold'>Content Script</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript content script]</div><div style='font-size: 80%; margin-top:10px'>Schedules initial, delayed,<br />and SPA captures; tracks<br />scroll; sends capture and<br />inline blob upload messages<br />to the service worker.</div>"]
        style 8 fill:#85bbf0,stroke:#1168bd,color:#000000
        9["<div style='font-weight: bold'>Service Worker</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript MV3 service worker]</div><div style='font-size: 80%; margin-top:10px'>Owns daemon transport, bearer<br />token use, capture and visit<br />queues, lifecycle state,<br />media queue draining, and CDP<br />recorder orchestration.</div>"]
        style 9 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      13[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side storage for<br />capture and visit queues in<br />chrome.storage.local plus<br />durable media tasks and<br />fetched blobs in IndexedDB.</div>")]
      style 13 fill:#2f95c8,stroke:#20688c,color:#ffffff
      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    8-. "<div>Builds capture payloads with</div><div style='font-size: 70%'></div>" .->7
    8-. "<div>Sends captures and inline<br />blobs to</div><div style='font-size: 70%'>[chrome.runtime.sendMessage]</div>" .->9
    9-. "<div>Queues captures in<br />chrome.storage.local and<br />media tasks/blobs in<br />IndexedDB</div><div style='font-size: 70%'></div>" .->13
    9-. "<div>Delivers /capture,<br />/visit-events, media<br />metadata, and raw blobs to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT]</div>" .->14
    12-. "<div>Updates pause, policy, token,<br />and controls through</div><div style='font-size: 70%'>[chrome.storage.local, runtime messages]</div>" .->9
    12-. "<div>Checks health and triggers<br />forget/policy actions on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->14

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-ExtensionCaptureComponents.mmd`](diagrams/structurizr-ExtensionCaptureComponents.mmd) |
| Mermaid SVG | [`structurizr-ExtensionCaptureComponents.svg`](diagrams/structurizr-ExtensionCaptureComponents.svg) |
| Mermaid PNG | [`structurizr-ExtensionCaptureComponents.png`](diagrams/structurizr-ExtensionCaptureComponents.png) |
| DOT source | [`structurizr-ExtensionCaptureComponents.dot`](diagrams/dot/structurizr-ExtensionCaptureComponents.dot) |
| Graphviz SVG | [`structurizr-ExtensionCaptureComponents.svg`](diagrams/dot-rendered/structurizr-ExtensionCaptureComponents.svg) |
| Graphviz PNG | [`structurizr-ExtensionCaptureComponents.png`](diagrams/dot-rendered/structurizr-ExtensionCaptureComponents.png) |


---

## Extension Media Components

> C4 view `ExtensionMediaComponents`.

### Diagram

![Extension Media Components](diagrams/dot-rendered/structurizr-ExtensionMediaComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph TB
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - Chrome MV3 Extension"]
    style diagram fill:#ffffff,stroke:#ffffff

    2["<div style='font-weight: bold'>Windows Chrome</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>The Windows Chrome runtime<br />that loads web pages, hosts<br />the MV3 extension, runs the<br />local UI in a tab, and<br />exposes Chrome extension<br />APIs.</div>"]
    style 2 fill:#999999,stroke:#6b6b6b,color:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 5 ["Chrome MV3 Extension"]
        style 5 fill:#ffffff,stroke:#2e6295,color:#2e6295

        10["<div style='font-weight: bold'>Browser Media Queue Adapter</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Persists media tasks and<br />fetched blobs in IndexedDB so<br />browser-side media<br />fetch/upload can survive MV3<br />worker suspension.</div>"]
        style 10 fill:#85bbf0,stroke:#1168bd,color:#000000
        11["<div style='font-weight: bold'>CDP Recorder</div><div style='font-size: 70%; margin-top: 0px'>[Component: Chrome DevTools Protocol]</div><div style='font-size: 80%; margin-top:10px'>Uses chrome.debugger on<br />configured X/Twitter tabs to<br />capture video.twimg.com HLS<br />manifests and media segments<br />before they become opaque<br />blob player URLs.</div>"]
        style 11 fill:#85bbf0,stroke:#1168bd,color:#000000
        9["<div style='font-weight: bold'>Service Worker</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript MV3 service worker]</div><div style='font-size: 80%; margin-top:10px'>Owns daemon transport, bearer<br />token use, capture and visit<br />queues, lifecycle state,<br />media queue draining, and CDP<br />recorder orchestration.</div>"]
        style 9 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      13[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side storage for<br />capture and visit queues in<br />chrome.storage.local plus<br />durable media tasks and<br />fetched blobs in IndexedDB.</div>")]
      style 13 fill:#2f95c8,stroke:#20688c,color:#ffffff
      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    9-. "<div>Queues captures in<br />chrome.storage.local and<br />media tasks/blobs in<br />IndexedDB</div><div style='font-size: 70%'></div>" .->13
    9-. "<div>Delivers /capture,<br />/visit-events, media<br />metadata, and raw blobs to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT]</div>" .->14
    9-. "<div>Persists and drains media<br />work through</div><div style='font-size: 70%'></div>" .->10
    10-. "<div>Reads and writes media<br />tasks/blobs in</div><div style='font-size: 70%'>[IndexedDB]</div>" .->13
    9-. "<div>Detects CDP media candidates<br />with</div><div style='font-size: 70%'></div>" .->11
    11-. "<div>Receives Network events from</div><div style='font-size: 70%'>[chrome.debugger/CDP]</div>" .->2
    11-. "<div>Uploads CDP media rows and<br />blobs to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT]</div>" .->14

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-ExtensionMediaComponents.mmd`](diagrams/structurizr-ExtensionMediaComponents.mmd) |
| Mermaid SVG | [`structurizr-ExtensionMediaComponents.svg`](diagrams/structurizr-ExtensionMediaComponents.svg) |
| Mermaid PNG | [`structurizr-ExtensionMediaComponents.png`](diagrams/structurizr-ExtensionMediaComponents.png) |
| DOT source | [`structurizr-ExtensionMediaComponents.dot`](diagrams/dot/structurizr-ExtensionMediaComponents.dot) |
| Graphviz SVG | [`structurizr-ExtensionMediaComponents.svg`](diagrams/dot-rendered/structurizr-ExtensionMediaComponents.svg) |
| Graphviz PNG | [`structurizr-ExtensionMediaComponents.png`](diagrams/dot-rendered/structurizr-ExtensionMediaComponents.png) |


---

## Fast Capture Flow

> C4 view `FastCaptureFlow`.

### Diagram

![Fast Capture Flow](diagrams/dot-rendered/structurizr-FastCaptureFlow.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Dynamic View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      13[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side storage for<br />capture and visit queues in<br />chrome.storage.local plus<br />durable media tasks and<br />fetched blobs in IndexedDB.</div>")]
      style 13 fill:#2f95c8,stroke:#20688c,color:#ffffff
      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      5["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
      style 5 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    1["<div style='font-weight: bold'>Operator</div><div style='font-size: 70%; margin-top: 0px'>[Person]</div><div style='font-size: 80%; margin-top:10px'>Sole local operator who<br />browses with Windows Chrome<br />and searches, reviews, and<br />deletes local browser-memory<br />records.</div>"]
    style 1 fill:#08427b,stroke:#052e56,color:#ffffff
    2["<div style='font-weight: bold'>Windows Chrome</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>The Windows Chrome runtime<br />that loads web pages, hosts<br />the MV3 extension, runs the<br />local UI in a tab, and<br />exposes Chrome extension<br />APIs.</div>"]
    style 2 fill:#999999,stroke:#6b6b6b,color:#ffffff

    1-. "<div>1. Browses a web page</div><div style='font-size: 70%'></div>" .->2
    5-. "<div>2. Runs content script and<br />service worker inside active<br />tab</div><div style='font-size: 70%'>[Chrome extension APIs]</div>" .->2
    5-. "<div>3. POSTs /capture with<br />visible text, metadata, and<br />media refs</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->14
    14-. "<div>4. Stores document, visit,<br />snapshot, chunks, FTS, media<br />refs, and tasks</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    14-. "<div>5. Writes clean-text snapshot<br />blob</div><div style='font-size: 70%'>[Filesystem]</div>" .->29
    14-. "<div>6. Returns<br />document/snapshot/artifact<br />IDs before lazy media bytes</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->5
    5-. "<div>7. Queues browser-side media<br />tasks for later fetch/upload</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-FastCaptureFlow.mmd`](diagrams/structurizr-FastCaptureFlow.mmd) |
| Mermaid SVG | [`structurizr-FastCaptureFlow.svg`](diagrams/structurizr-FastCaptureFlow.svg) |
| Mermaid PNG | [`structurizr-FastCaptureFlow.png`](diagrams/structurizr-FastCaptureFlow.png) |
| DOT source | [`structurizr-FastCaptureFlow.dot`](diagrams/dot/structurizr-FastCaptureFlow.dot) |
| Graphviz SVG | [`structurizr-FastCaptureFlow.svg`](diagrams/dot-rendered/structurizr-FastCaptureFlow.svg) |
| Graphviz PNG | [`structurizr-FastCaptureFlow.png`](diagrams/dot-rendered/structurizr-FastCaptureFlow.png) |


---

## Ops Containers

> C4 view `OpsContainers`.

### Diagram

![Ops Containers](diagrams/dot-rendered/structurizr-OpsContainers.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Container View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
      26["<div style='font-weight: bold'>Local Web UI</div><div style='font-size: 70%; margin-top: 0px'>[Container: HTML/CSS/JavaScript served by daemon]</div><div style='font-size: 80%; margin-top:10px'>Static browser UI for exact<br />search, recent/timeline<br />views, document/snapshot<br />detail, media artifact<br />opening, policy rules,<br />doctor, and forget-domain<br />operations.</div>"]
      style 26 fill:#438dd5,stroke:#2e6295,color:#ffffff
      27["<div style='font-weight: bold'>CLI</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python argparse]</div><div style='font-size: 80%; margin-top:10px'>Command-line interface for<br />serving the daemon, migration<br />check/execute,<br />health/doctor/search/recent/timeline/detail,<br />policy/forget, capture<br />fixtures, media worker, and<br />media cache operations.</div>"]
      style 27 fill:#438dd5,stroke:#2e6295,color:#ffffff
      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    26-. "<div>Calls authenticated read,<br />admin, media, and forget APIs<br />on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->14
    27-. "<div>Calls health, read, admin,<br />capture-fixture, and forget<br />APIs on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->14
    27-. "<div>Runs migration, media-worker,<br />and media-cache commands<br />against</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    27-. "<div>Purges and rehydrates media<br />blobs through</div><div style='font-size: 70%'>[Filesystem]</div>" .->30
    14-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->28
    14-. "<div>Reads and writes text<br />snapshots in</div><div style='font-size: 70%'>[Filesystem]</div>" .->29
    14-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->30

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-OpsContainers.mmd`](diagrams/structurizr-OpsContainers.mmd) |
| Mermaid SVG | [`structurizr-OpsContainers.svg`](diagrams/structurizr-OpsContainers.svg) |
| Mermaid PNG | [`structurizr-OpsContainers.png`](diagrams/structurizr-OpsContainers.png) |
| DOT source | [`structurizr-OpsContainers.dot`](diagrams/dot/structurizr-OpsContainers.dot) |
| Graphviz SVG | [`structurizr-OpsContainers.svg`](diagrams/dot-rendered/structurizr-OpsContainers.svg) |
| Graphviz PNG | [`structurizr-OpsContainers.png`](diagrams/dot-rendered/structurizr-OpsContainers.png) |


---

## System Context

> C4 view `SystemContext`.

### Diagram

![System Context](diagrams/dot-rendered/structurizr-SystemContext.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["System Context View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    1["<div style='font-weight: bold'>Operator</div><div style='font-size: 70%; margin-top: 0px'>[Person]</div><div style='font-size: 80%; margin-top:10px'>Sole local operator who<br />browses with Windows Chrome<br />and searches, reviews, and<br />deletes local browser-memory<br />records.</div>"]
    style 1 fill:#08427b,stroke:#052e56,color:#ffffff
    2["<div style='font-weight: bold'>Windows Chrome</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>The Windows Chrome runtime<br />that loads web pages, hosts<br />the MV3 extension, runs the<br />local UI in a tab, and<br />exposes Chrome extension<br />APIs.</div>"]
    style 2 fill:#999999,stroke:#6b6b6b,color:#ffffff
    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff
    4["<div style='font-weight: bold'>Browser Memory Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>Local-first personal recall<br />system that captures Windows<br />Chrome page text and media<br />references, stores them in<br />WSL, and exposes exact<br />search, timeline, detail,<br />deletion, diagnostics, and<br />media cache operations.</div>"]
    style 4 fill:#1168bd,stroke:#0b4884,color:#ffffff

    1-. "<div>Browses web pages with</div><div style='font-size: 70%'></div>" .->2
    1-. "<div>Searches, reviews, and<br />deletes local browser memory<br />through</div><div style='font-size: 70%'></div>" .->4
    2-. "<div>Loads pages and media from</div><div style='font-size: 70%'>[HTTPS]</div>" .->3
    4-. "<div>Runs its MV3 extension inside<br />and uses APIs from</div><div style='font-size: 70%'></div>" .->2
    4-. "<div>Captures page refs and<br />fetches browser-side or<br />public media from</div><div style='font-size: 70%'>[Chrome DOM/fetch; WSL HTTP(S), data URLs; no Chrome cookies in WSL]</div>" .->3

  end
```

</details>

### Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-SystemContext.mmd`](diagrams/structurizr-SystemContext.mmd) |
| Mermaid SVG | [`structurizr-SystemContext.svg`](diagrams/structurizr-SystemContext.svg) |
| Mermaid PNG | [`structurizr-SystemContext.png`](diagrams/structurizr-SystemContext.png) |
| DOT source | [`structurizr-SystemContext.dot`](diagrams/dot/structurizr-SystemContext.dot) |
| Graphviz SVG | [`structurizr-SystemContext.svg`](diagrams/dot-rendered/structurizr-SystemContext.svg) |
| Graphviz PNG | [`structurizr-SystemContext.png`](diagrams/dot-rendered/structurizr-SystemContext.png) |
