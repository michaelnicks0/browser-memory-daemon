# Fast Capture Flow

> Generated Markdown wrapper for C4 view `FastCaptureFlow`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Fast Capture Flow](../dot-rendered/structurizr-FastCaptureFlow.svg)

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
      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, durable<br />forget, and static UI<br />serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
      31[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 31 fill:#2f95c8,stroke:#20688c,color:#ffffff
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
    14-. "<div>4. Atomically stores complete<br />cleaned text, provenance,<br />chunks, FTS, media refs, and<br />tasks</div><div style='font-size: 70%'>[sqlite3]</div>" .->31
    14-. "<div>5. Returns<br />document/snapshot/artifact<br />IDs before lazy media bytes</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->5
    5-. "<div>6. Queues browser-side media<br />tasks for later fetch/upload</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-FastCaptureFlow.mmd`](../structurizr-FastCaptureFlow.mmd) |
| Mermaid SVG | [`structurizr-FastCaptureFlow.svg`](../structurizr-FastCaptureFlow.svg) |
| Mermaid PNG | [`structurizr-FastCaptureFlow.png`](../structurizr-FastCaptureFlow.png) |
| DOT source | [`structurizr-FastCaptureFlow.dot`](../dot/structurizr-FastCaptureFlow.dot) |
| Graphviz SVG | [`structurizr-FastCaptureFlow.svg`](../dot-rendered/structurizr-FastCaptureFlow.svg) |
| Graphviz PNG | [`structurizr-FastCaptureFlow.png`](../dot-rendered/structurizr-FastCaptureFlow.png) |
