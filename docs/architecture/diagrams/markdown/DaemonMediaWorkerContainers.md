# Daemon Media Worker Containers

> Generated Markdown wrapper for C4 view `DaemonMediaWorkerContainers`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Media Worker Containers](../dot-rendered/structurizr-DaemonMediaWorkerContainers.svg)

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

      24["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
      style 24 fill:#438dd5,stroke:#2e6295,color:#ffffff
      27[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for sources,<br />documents, visits, visit<br />events, snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 27 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    24-. "<div>Leases and updates media<br />tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->27
    24-. "<div>Fetches public media and HLS<br />from</div><div style='font-size: 70%'>[HTTP(S), data URLs]</div>" .->3
    24-. "<div>Writes fetched media blobs to</div><div style='font-size: 70%'>[Filesystem]</div>" .->29

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonMediaWorkerContainers.mmd`](../structurizr-DaemonMediaWorkerContainers.mmd) |
| Mermaid SVG | [`structurizr-DaemonMediaWorkerContainers.svg`](../structurizr-DaemonMediaWorkerContainers.svg) |
| Mermaid PNG | [`structurizr-DaemonMediaWorkerContainers.png`](../structurizr-DaemonMediaWorkerContainers.png) |
| DOT source | [`structurizr-DaemonMediaWorkerContainers.dot`](../dot/structurizr-DaemonMediaWorkerContainers.dot) |
| Graphviz SVG | [`structurizr-DaemonMediaWorkerContainers.svg`](../dot-rendered/structurizr-DaemonMediaWorkerContainers.svg) |
| Graphviz PNG | [`structurizr-DaemonMediaWorkerContainers.png`](../dot-rendered/structurizr-DaemonMediaWorkerContainers.png) |
