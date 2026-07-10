# Daemon Forget Components

> Generated Markdown wrapper for C4 view `DaemonForgetComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Forget Components](../dot-rendered/structurizr-DaemonForgetComponents.svg)

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
        22["<div style='font-weight: bold'>Forget Pipeline</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Deletes URL/domain-scoped<br />memory rows, FTS entries,<br />clean-text blobs, media<br />blobs, lifecycle rows, and<br />records deletion receipts.</div>"]
        style 22 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      27[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for sources,<br />documents, visits, visit<br />events, snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 27 fill:#2f95c8,stroke:#20688c,color:#ffffff
      28[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
      style 28 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes forget requests to</div><div style='font-size: 70%'></div>" .->22
    22-. "<div>Deletes rows and records<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->27
    22-. "<div>Deletes text blobs from</div><div style='font-size: 70%'>[Filesystem]</div>" .->28
    22-. "<div>Deletes media blobs from</div><div style='font-size: 70%'>[Filesystem]</div>" .->29

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonForgetComponents.mmd`](../structurizr-DaemonForgetComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonForgetComponents.svg`](../structurizr-DaemonForgetComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonForgetComponents.png`](../structurizr-DaemonForgetComponents.png) |
| DOT source | [`structurizr-DaemonForgetComponents.dot`](../dot/structurizr-DaemonForgetComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonForgetComponents.svg`](../dot-rendered/structurizr-DaemonForgetComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonForgetComponents.png`](../dot-rendered/structurizr-DaemonForgetComponents.png) |
