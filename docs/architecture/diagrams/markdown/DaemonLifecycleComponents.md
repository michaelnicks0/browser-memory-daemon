# Daemon Lifecycle Components

> Generated Markdown wrapper for C4 view `DaemonLifecycleComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Lifecycle Components](../dot-rendered/structurizr-DaemonLifecycleComponents.svg)

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
        20["<div style='font-weight: bold'>Lifecycle Pipeline</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Stores claimed/resolved tab<br />lifecycle identity,<br />reconciles delayed captures,<br />validates active intervals,<br />and derives visit dwell from<br />interval unions.</div>"]
        style 20 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      31[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 31 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes lifecycle events to</div><div style='font-size: 70%'></div>" .->20
    20-. "<div>Writes lifecycle identity and<br />interval-union dwell to</div><div style='font-size: 70%'>[sqlite3]</div>" .->31

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonLifecycleComponents.mmd`](../structurizr-DaemonLifecycleComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonLifecycleComponents.svg`](../structurizr-DaemonLifecycleComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonLifecycleComponents.png`](../structurizr-DaemonLifecycleComponents.png) |
| DOT source | [`structurizr-DaemonLifecycleComponents.dot`](../dot/structurizr-DaemonLifecycleComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonLifecycleComponents.svg`](../dot-rendered/structurizr-DaemonLifecycleComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonLifecycleComponents.png`](../dot-rendered/structurizr-DaemonLifecycleComponents.png) |
