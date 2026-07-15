# Daemon Storage Reconcile Components

> Generated Markdown wrapper for C4 view `DaemonStorageReconcileComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Storage Reconcile Components](../dot-rendered/structurizr-DaemonStorageReconcileComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - WSL Loopback HTTP Daemon - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    47["<div style='font-weight: bold'>CLI</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python argparse]</div><div style='font-size: 80%; margin-top:10px'>Command-line interface for<br />serving/admin operations plus<br />standalone mutation-free X<br />observation export.</div>"]
    style 47 fill:#438dd5,stroke:#2e6295,color:#ffffff
    49[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 49 fill:#2f95c8,stroke:#20688c,color:#ffffff
    50[("<div style='font-weight: bold'>Local Derivative Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Reconstructible compatibility<br />evidence such as<br />pre-version-9 clean-text<br />sidecars; new captures create<br />no text sidecars.</div>")]
    style 50 fill:#2f95c8,stroke:#20688c,color:#ffffff
    51[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
    style 51 fill:#2f95c8,stroke:#20688c,color:#ffffff
    52[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
    style 52 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 22 ["WSL Loopback HTTP Daemon"]
      style 22 fill:#ffffff,stroke:#2e6295,color:#2e6295

      39["<div style='font-weight: bold'>Contained BlobStore</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python filesystem boundary]</div><div style='font-size: 80%; margin-top:10px'>Prefers root-relative<br />locators with contained<br />legacy fallback; streams<br />unique stages with size/hash<br />accounting; atomically<br />commits; and contains blob<br />read, stat, and delete<br />operations.</div>"]
      style 39 fill:#85bbf0,stroke:#1168bd,color:#000000
      40["<div style='font-weight: bold'>Blob Lifecycle and Storage Reconciler</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Persists<br />committed/tombstoned/missing/deleted/blocked/failed<br />blob state; serializes<br />deletion processors; retries<br />tombstones; and dry-run<br />detects missing refs, in-root<br />orphans, and stale stages.</div>"]
      style 40 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    40-. "<div>Reads and advances durable<br />blob lifecycle records in</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
    40-. "<div>Resolves, deletes, and<br />inventories contained bytes<br />through</div><div style='font-size: 70%'></div>" .->39
    39-. "<div>Reads, stats, reconciles, and<br />deletes legacy text sidecars<br />in</div><div style='font-size: 70%'>[Filesystem]</div>" .->50
    39-. "<div>Stages, commits, reads,<br />stats, and deletes media<br />blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->51
    39-. "<div>Stages, commits, reads,<br />stats, and deletes spooled<br />media in</div><div style='font-size: 70%'>[Filesystem]</div>" .->52
    47-. "<div>Optionally copies referenced<br />contained derivatives from</div><div style='font-size: 70%'>[Filesystem]</div>" .->50
    47-. "<div>Runs migration, media-worker,<br />media-cache, media-spool, and<br />storage-reconcile commands<br />against</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
    47-. "<div>Previews or executes<br />contained storage convergence<br />through</div><div style='font-size: 70%'></div>" .->40
    47-. "<div>Purges and rehydrates media<br />blobs through</div><div style='font-size: 70%'>[Filesystem]</div>" .->51
    47-. "<div>Reports and drains bounded<br />outage bytes through</div><div style='font-size: 70%'>[Filesystem]</div>" .->52
  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonStorageReconcileComponents.mmd`](../structurizr-DaemonStorageReconcileComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonStorageReconcileComponents.svg`](../structurizr-DaemonStorageReconcileComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonStorageReconcileComponents.png`](../structurizr-DaemonStorageReconcileComponents.png) |
| DOT source | [`structurizr-DaemonStorageReconcileComponents.dot`](../dot/structurizr-DaemonStorageReconcileComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonStorageReconcileComponents.svg`](../dot-rendered/structurizr-DaemonStorageReconcileComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonStorageReconcileComponents.png`](../dot-rendered/structurizr-DaemonStorageReconcileComponents.png) |
