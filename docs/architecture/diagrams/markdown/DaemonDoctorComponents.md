# Daemon Doctor Components

> Generated Markdown wrapper for C4 view `DaemonDoctorComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Doctor Components](../dot-rendered/structurizr-DaemonDoctorComponents.svg)

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
        25["<div style='font-weight: bold'>Blob Lifecycle and Storage Reconciler</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Persists<br />committed/tombstoned/missing/deleted/blocked/failed<br />blob state; serializes<br />deletion processors; retries<br />tombstones; and dry-run<br />detects missing refs, in-root<br />orphans, and stale stages.</div>"]
        style 25 fill:#85bbf0,stroke:#1168bd,color:#000000
        28["<div style='font-weight: bold'>Ops Doctor and Audit</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Reports health, DB integrity,<br />FTS consistency, blob<br />lifecycle/pending deletion<br />state, runtime paths, storage<br />counts, media queue status,<br />and writes metadata-only<br />audit events to SQLite.</div>"]
        style 28 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      33[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 33 fill:#2f95c8,stroke:#20688c,color:#ffffff
      34[("<div style='font-weight: bold'>Local Derivative Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Reconstructible compatibility<br />evidence such as<br />pre-version-9 clean-text<br />sidecars; new captures create<br />no text sidecars.</div>")]
      style 34 fill:#2f95c8,stroke:#20688c,color:#ffffff
      35[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
      style 35 fill:#2f95c8,stroke:#20688c,color:#ffffff
      36[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
      style 36 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    25-. "<div>Reads and advances durable<br />blob lifecycle records in</div><div style='font-size: 70%'>[sqlite3]</div>" .->33
    28-. "<div>Checks integrity and counts<br />in</div><div style='font-size: 70%'>[sqlite3]</div>" .->33
    28-. "<div>Reads pending deletion and<br />lifecycle health from</div><div style='font-size: 70%'></div>" .->25
    28-. "<div>Counts text blob files in</div><div style='font-size: 70%'>[Filesystem]</div>" .->34
    28-. "<div>Counts media blob files in</div><div style='font-size: 70%'>[Filesystem]</div>" .->35
    28-. "<div>Reports filesystem bytes,<br />reservations, and capacity<br />for</div><div style='font-size: 70%'>[Filesystem]</div>" .->36
    15-. "<div>Routes health and audit work<br />to</div><div style='font-size: 70%'></div>" .->28

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonDoctorComponents.mmd`](../structurizr-DaemonDoctorComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonDoctorComponents.svg`](../structurizr-DaemonDoctorComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonDoctorComponents.png`](../structurizr-DaemonDoctorComponents.png) |
| DOT source | [`structurizr-DaemonDoctorComponents.dot`](../dot/structurizr-DaemonDoctorComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonDoctorComponents.svg`](../dot-rendered/structurizr-DaemonDoctorComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonDoctorComponents.png`](../dot-rendered/structurizr-DaemonDoctorComponents.png) |
