# Ops Containers

> Generated Markdown wrapper for C4 view `OpsContainers`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Ops Containers](../dot-rendered/structurizr-OpsContainers.svg)

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
      27["<div style='font-weight: bold'>Local Web UI</div><div style='font-size: 70%; margin-top: 0px'>[Container: HTML/CSS/JavaScript served by daemon]</div><div style='font-size: 80%; margin-top:10px'>Static browser UI for exact<br />search, recent/timeline<br />views, document/snapshot<br />detail, media artifact<br />opening, policy rules,<br />doctor, and forget-domain<br />operations.</div>"]
      style 27 fill:#438dd5,stroke:#2e6295,color:#ffffff
      28["<div style='font-weight: bold'>CLI</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python argparse]</div><div style='font-size: 80%; margin-top:10px'>Command-line interface for<br />serving the daemon, migration<br />and snapshot-text<br />reconciliation,<br />health/doctor/search/recent/timeline/detail,<br />policy/forget, capture<br />fixtures, media worker, and<br />media cache operations.</div>"]
      style 28 fill:#438dd5,stroke:#2e6295,color:#ffffff
      29[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      30[("<div style='font-weight: bold'>Legacy Clean Text Sidecars</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Compatibility-only filesystem<br />evidence for pre-version-9<br />snapshots; new captures<br />create no text sidecars.</div>")]
      style 30 fill:#2f95c8,stroke:#20688c,color:#ffffff
      31[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 31 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    27-. "<div>Calls authenticated read,<br />admin, media, and forget APIs<br />on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->14
    28-. "<div>Calls health, read, admin,<br />capture-fixture, and forget<br />APIs on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->14
    28-. "<div>Runs migration, media-worker,<br />and media-cache commands<br />against</div><div style='font-size: 70%'>[sqlite3]</div>" .->29
    28-. "<div>Purges and rehydrates media<br />blobs through</div><div style='font-size: 70%'>[Filesystem]</div>" .->31
    14-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->29
    14-. "<div>Reads or deletes legacy text<br />sidecars when required</div><div style='font-size: 70%'>[Filesystem]</div>" .->30
    14-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->31

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-OpsContainers.mmd`](../structurizr-OpsContainers.mmd) |
| Mermaid SVG | [`structurizr-OpsContainers.svg`](../structurizr-OpsContainers.svg) |
| Mermaid PNG | [`structurizr-OpsContainers.png`](../structurizr-OpsContainers.png) |
| DOT source | [`structurizr-OpsContainers.dot`](../dot/structurizr-OpsContainers.dot) |
| Graphviz SVG | [`structurizr-OpsContainers.svg`](../dot-rendered/structurizr-OpsContainers.svg) |
| Graphviz PNG | [`structurizr-OpsContainers.png`](../dot-rendered/structurizr-OpsContainers.png) |
