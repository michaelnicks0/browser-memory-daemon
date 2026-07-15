# Browser Media Containers

> Generated Markdown wrapper for C4 view `BrowserMediaContainers`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Browser Media Containers](../dot-rendered/structurizr-BrowserMediaContainers.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph TB
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - Containers"]
    style diagram fill:#ffffff,stroke:#ffffff

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      21[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side IndexedDB<br />storage for transactional<br />capture/lifecycle outbox rows<br />plus specialized durable<br />media tasks/blobs;<br />chrome.storage.local retains<br />typed configuration,<br />lifecycle tab state, minimal<br />CDP capture context,<br />aggregate telemetry, and<br />one-version queue fallback<br />only.</div>")]
      style 21 fill:#2f95c8,stroke:#20688c,color:#ffffff
      22["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback API<br />for capture, read/admin/media<br />operations, and query-only<br />bmd.x-observations v1 export.</div>"]
      style 22 fill:#438dd5,stroke:#2e6295,color:#ffffff
      49[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
      style 49 fill:#2f95c8,stroke:#20688c,color:#ffffff
      5["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
      style 5 fill:#438dd5,stroke:#2e6295,color:#ffffff
      51[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
      style 51 fill:#2f95c8,stroke:#20688c,color:#ffffff
      52[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
      style 52 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    22-. "<div>Validates and fetches public<br />media from</div><div style='font-size: 70%'>[HTTP(S), no Referer or Chrome cookies]</div>" .->3
    5-. "<div>Extracts DOM refs and fetches<br />queued credentialed media<br />from</div><div style='font-size: 70%'>[DOM; fetch(credentials: include)]</div>" .->3
    5-. "<div>Persists configuration,<br />lifecycle tab state,<br />aggregate telemetry,<br />capture/lifecycle outbox<br />rows, media tasks, and blobs<br />in</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->21
    5-. "<div>Posts /capture,<br />/visit-events, media<br />metadata, and raw blob<br />uploads to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->22
    22-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
    22-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->51
    22-. "<div>Stores and serves media<br />during guarded-root outages<br />in</div><div style='font-size: 70%'>[Filesystem]</div>" .->52
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
