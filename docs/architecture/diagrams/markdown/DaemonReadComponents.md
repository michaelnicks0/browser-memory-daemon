# Daemon Read Components

> Generated Markdown wrapper for C4 view `DaemonReadComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Read Components](../dot-rendered/structurizr-DaemonReadComponents.svg)

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
        38["<div style='font-weight: bold'>Contained BlobStore</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python filesystem boundary]</div><div style='font-size: 80%; margin-top:10px'>Prefers root-relative<br />locators with contained<br />legacy fallback; streams<br />unique stages with size/hash<br />accounting; atomically<br />commits; and contains blob<br />read, stat, and delete<br />operations.</div>"]
        style 38 fill:#85bbf0,stroke:#1168bd,color:#000000
        40["<div style='font-weight: bold'>Search and Read Model</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + SQLite FTS5]</div><div style='font-size: 80%; margin-top:10px'>Provides exact FTS search<br />plus SQLite-authoritative<br />text detail and<br />observation-first<br />recent/timeline/document/snapshot/media<br />views with explicit legacy<br />fallbacks.</div>"]
        style 40 fill:#85bbf0,stroke:#1168bd,color:#000000
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

    23-. "<div>Routes read requests to</div><div style='font-size: 70%'></div>" .->40
    40-. "<div>Reads metadata and FTS from</div><div style='font-size: 70%'>[SQLite FTS5]</div>" .->47
    40-. "<div>Reads only legacy text<br />sidecars and checks media<br />files through</div><div style='font-size: 70%'></div>" .->38
    38-. "<div>Reads, stats, reconciles, and<br />deletes legacy text sidecars<br />in</div><div style='font-size: 70%'>[Filesystem]</div>" .->48
    38-. "<div>Stages, commits, reads,<br />stats, and deletes media<br />blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->49
    38-. "<div>Stages, commits, reads,<br />stats, and deletes spooled<br />media in</div><div style='font-size: 70%'>[Filesystem]</div>" .->50

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonReadComponents.mmd`](../structurizr-DaemonReadComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonReadComponents.svg`](../structurizr-DaemonReadComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonReadComponents.png`](../structurizr-DaemonReadComponents.png) |
| DOT source | [`structurizr-DaemonReadComponents.dot`](../dot/structurizr-DaemonReadComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonReadComponents.svg`](../dot-rendered/structurizr-DaemonReadComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonReadComponents.png`](../dot-rendered/structurizr-DaemonReadComponents.png) |
