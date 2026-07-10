# Daemon Media Components

> Generated Markdown wrapper for C4 view `DaemonMediaComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Media Components](../dot-rendered/structurizr-DaemonMediaComponents.svg)

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

      28[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, capture observations,<br />URL claims, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
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

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonMediaComponents.mmd`](../structurizr-DaemonMediaComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonMediaComponents.svg`](../structurizr-DaemonMediaComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonMediaComponents.png`](../structurizr-DaemonMediaComponents.png) |
| DOT source | [`structurizr-DaemonMediaComponents.dot`](../dot/structurizr-DaemonMediaComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonMediaComponents.svg`](../dot-rendered/structurizr-DaemonMediaComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonMediaComponents.png`](../dot-rendered/structurizr-DaemonMediaComponents.png) |
