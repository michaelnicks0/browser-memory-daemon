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

  subgraph diagram ["Browser Memory Daemon - WSL Loopback HTTP Daemon - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    57[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 57 fill:#2f95c8,stroke:#20688c,color:#ffffff
    58[("<div style='font-weight: bold'>Local Derivative Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Reconstructible compatibility<br />evidence such as<br />pre-version-9 clean-text<br />sidecars; new captures create<br />no text sidecars.</div>")]
    style 58 fill:#2f95c8,stroke:#20688c,color:#ffffff
    59[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
    style 59 fill:#2f95c8,stroke:#20688c,color:#ffffff
    60[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
    style 60 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 23 ["WSL Loopback HTTP Daemon"]
      style 23 fill:#ffffff,stroke:#2e6295,color:#2e6295

      24["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server + route descriptors]</div><div style='font-size: 80%; margin-top:10px'>Adapts BaseHTTPRequestHandler<br />requests through immutable<br />method/path descriptors with<br />static precedence; owns auth,<br />parsing, compatible<br />status/error responses,<br />request IDs, common security<br />headers, redaction-safe<br />telemetry, bounded response<br />streaming, disconnect<br />cleanup, CORS, and finite UI<br />assets.</div>"]
      style 24 fill:#85bbf0,stroke:#1168bd,color:#000000
      25["<div style='font-weight: bold'>Application Use Cases</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Provides request-independent<br />capture, lifecycle, read,<br />forget, policy, doctor, and<br />media use cases; owns<br />database-ready checks,<br />transaction/audit boundaries,<br />asynchronous media kickoff,<br />and upload/download resource<br />leases without importing HTTP<br />request or response types.</div>"]
      style 25 fill:#85bbf0,stroke:#1168bd,color:#000000
      39["<div style='font-weight: bold'>Contained BlobStore</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python filesystem boundary]</div><div style='font-size: 80%; margin-top:10px'>Prefers root-relative<br />locators with contained<br />legacy fallback; streams<br />unique stages with size/hash<br />accounting; atomically<br />commits; and contains blob<br />read, stat, and delete<br />operations.</div>"]
      style 39 fill:#85bbf0,stroke:#1168bd,color:#000000
      41["<div style='font-weight: bold'>Search and Read Model</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + SQLite FTS5]</div><div style='font-size: 80%; margin-top:10px'>Provides exact FTS search<br />plus SQLite-authoritative<br />text detail and<br />observation-first<br />recent/timeline/document/snapshot/media<br />views with explicit legacy<br />fallbacks.</div>"]
      style 41 fill:#85bbf0,stroke:#1168bd,color:#000000
      42["<div style='font-weight: bold'>HTTP X Observation Export Adapter</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Serves authenticated cursor<br />pages through the shared<br />query-only export core<br />without application<br />readiness, migrations, or<br />audit writes.</div>"]
      style 42 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    24-. "<div>Invokes explicit<br />request-independent use cases<br />through</div><div style='font-size: 70%'></div>" .->25
    25-. "<div>Executes read requests<br />through</div><div style='font-size: 70%'></div>" .->41
    24-. "<div>Serves authenticated GET<br />/exports/x-observations<br />through</div><div style='font-size: 70%'></div>" .->42
    41-. "<div>Reads metadata and FTS from</div><div style='font-size: 70%'>[SQLite FTS5]</div>" .->57
    42-. "<div>Reads validated<br />observation/evidence pages<br />without writes or audit</div><div style='font-size: 70%'>[SQLite mode=ro + query_only]</div>" .->57
    41-. "<div>Reads only legacy text<br />sidecars and checks media<br />files through</div><div style='font-size: 70%'></div>" .->39
    39-. "<div>Reads, stats, reconciles, and<br />deletes legacy text sidecars<br />in</div><div style='font-size: 70%'>[Filesystem]</div>" .->58
    39-. "<div>Stages, commits, reads,<br />stats, and deletes media<br />blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->59
    39-. "<div>Stages, commits, reads,<br />stats, and deletes spooled<br />media in</div><div style='font-size: 70%'>[Filesystem]</div>" .->60
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
