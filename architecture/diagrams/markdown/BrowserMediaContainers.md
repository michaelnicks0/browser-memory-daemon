# Browser Media Containers

> Generated Markdown wrapper for C4 view `BrowserMediaContainers`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from architecture/workspace.dsl. -->

## Diagram

![Browser Media Containers](../dot-rendered/structurizr-BrowserMediaContainers.svg)

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
      27[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for sources,<br />documents, visits, visit<br />events, snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 27 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      5["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
      style 5 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    5-. "<div>Extracts DOM refs and fetches<br />queued credentialed media<br />from</div><div style='font-size: 70%'>[DOM; fetch(credentials: include)]</div>" .->3
    5-. "<div>Queues captures, lifecycle<br />events, media tasks, and<br />blobs in</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13
    5-. "<div>Posts /capture,<br />/visit-events, media<br />metadata, and raw blob<br />uploads to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->14
    14-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->27
    14-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->29

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-BrowserMediaContainers.mmd`](../structurizr-BrowserMediaContainers.mmd) |
| Mermaid SVG | [`structurizr-BrowserMediaContainers.svg`](../structurizr-BrowserMediaContainers.svg) |
| Mermaid PNG | [`structurizr-BrowserMediaContainers.png`](../structurizr-BrowserMediaContainers.png) |
| DOT source | [`structurizr-BrowserMediaContainers.dot`](../dot/structurizr-BrowserMediaContainers.dot) |
| Graphviz SVG | [`structurizr-BrowserMediaContainers.svg`](../dot-rendered/structurizr-BrowserMediaContainers.svg) |
| Graphviz PNG | [`structurizr-BrowserMediaContainers.png`](../dot-rendered/structurizr-BrowserMediaContainers.png) |
