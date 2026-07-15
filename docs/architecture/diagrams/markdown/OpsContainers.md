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

  subgraph diagram ["Browser Memory Daemon - Containers"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 5 ["Browser Memory Daemon"]
      style 5 fill:#ffffff,stroke:#0b4884,color:#0b4884

      23["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback API<br />for capture, read/admin/media<br />operations, and query-only<br />bmd.x-observations v1 export.</div>"]
      style 23 fill:#438dd5,stroke:#2e6295,color:#ffffff
      50["<div style='font-weight: bold'>Local Web UI</div><div style='font-size: 70%; margin-top: 0px'>[Container: HTML/CSS/JavaScript served by daemon]</div><div style='font-size: 80%; margin-top:10px'>Static browser UI for exact<br />search, recent/timeline<br />views, document/snapshot<br />detail, media artifact<br />opening, policy rules,<br />doctor, and forget-domain<br />operations.</div>"]
      style 50 fill:#438dd5,stroke:#2e6295,color:#ffffff
      51["<div style='font-weight: bold'>CLI</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python argparse]</div><div style='font-size: 80%; margin-top:10px'>Command-line interface for<br />serving/admin operations,<br />direct storage/health<br />workflows, and standalone<br />mutation-free X observation<br />export.</div>"]
      style 51 fill:#438dd5,stroke:#2e6295,color:#ffffff
      57[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
      style 57 fill:#2f95c8,stroke:#20688c,color:#ffffff
      58[("<div style='font-weight: bold'>Local Derivative Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Reconstructible compatibility<br />evidence such as<br />pre-version-9 clean-text<br />sidecars; new captures create<br />no text sidecars.</div>")]
      style 58 fill:#2f95c8,stroke:#20688c,color:#ffffff
      59[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
      style 59 fill:#2f95c8,stroke:#20688c,color:#ffffff
      60[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
      style 60 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    51-. "<div>Optionally copies referenced<br />contained derivatives from</div><div style='font-size: 70%'>[Filesystem]</div>" .->58
    50-. "<div>Calls authenticated read,<br />admin, media, and forget APIs<br />on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->23
    51-. "<div>Calls health, read, admin,<br />capture-fixture, and forget<br />APIs on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->23
    51-. "<div>Runs direct migration,<br />export, media, storage,<br />health, backup, and restore<br />workflows against</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    51-. "<div>Purges and rehydrates media<br />blobs through</div><div style='font-size: 70%'>[Filesystem]</div>" .->59
    51-. "<div>Reports and drains bounded<br />outage bytes through</div><div style='font-size: 70%'>[Filesystem]</div>" .->60
    23-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    23-. "<div>Reads or deletes legacy text<br />sidecars when required</div><div style='font-size: 70%'>[Filesystem]</div>" .->58
    23-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->59
    23-. "<div>Stores and serves media<br />during guarded-root outages<br />in</div><div style='font-size: 70%'>[Filesystem]</div>" .->60
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
