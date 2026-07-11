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

      subgraph 22 ["WSL Loopback HTTP Daemon"]
        style 22 fill:#ffffff,stroke:#2e6295,color:#2e6295

        23["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server + route descriptors]</div><div style='font-size: 80%; margin-top:10px'>Matches immutable method/path<br />descriptors with static<br />precedence, maps typed<br />compatible errors, applies<br />opaque request IDs and common<br />security headers, emits<br />redaction-safe<br />route/status/latency<br />telemetry, streams media in<br />bounded chunks with<br />disconnect cleanup, serves UI<br />assets, enforces bearer auth<br />for memory/admin APIs, and<br />applies CORS for allowed<br />origins.</div>"]
        style 23 fill:#85bbf0,stroke:#1168bd,color:#000000
        39["<div style='font-weight: bold'>Blob Lifecycle and Storage Reconciler</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Persists<br />committed/tombstoned/missing/deleted/blocked/failed<br />blob state; serializes<br />deletion processors; retries<br />tombstones; and dry-run<br />detects missing refs, in-root<br />orphans, and stale stages.</div>"]
        style 39 fill:#85bbf0,stroke:#1168bd,color:#000000
        42["<div style='font-weight: bold'>Ops Doctor and Audit</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Reports health, DB integrity,<br />FTS consistency, blob<br />lifecycle/pending deletion<br />state, runtime paths, storage<br />counts, media queue status,<br />and writes metadata-only<br />audit events to SQLite.</div>"]
        style 42 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      47[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 47 fill:#2f95c8,stroke:#20688c,color:#ffffff
      48[("<div style='font-weight: bold'>Local Derivative Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Reconstructible compatibility<br />evidence such as<br />pre-version-9 clean-text<br />sidecars; new captures create<br />no text sidecars.</div>")]
      style 48 fill:#2f95c8,stroke:#20688c,color:#ffffff
      49[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
      style 49 fill:#2f95c8,stroke:#20688c,color:#ffffff
      50[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
      style 50 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    23-. "<div>Routes health and audit work<br />to</div><div style='font-size: 70%'></div>" .->42
    39-. "<div>Reads and advances durable<br />blob lifecycle records in</div><div style='font-size: 70%'>[sqlite3]</div>" .->47
    42-. "<div>Checks integrity and counts<br />in</div><div style='font-size: 70%'>[sqlite3]</div>" .->47
    42-. "<div>Reads pending deletion and<br />lifecycle health from</div><div style='font-size: 70%'></div>" .->39
    42-. "<div>Counts text blob files in</div><div style='font-size: 70%'>[Filesystem]</div>" .->48
    42-. "<div>Counts media blob files in</div><div style='font-size: 70%'>[Filesystem]</div>" .->49
    42-. "<div>Reports filesystem bytes,<br />reservations, and capacity<br />for</div><div style='font-size: 70%'>[Filesystem]</div>" .->50

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
