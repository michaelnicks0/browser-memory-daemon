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

  subgraph diagram ["Browser Memory Daemon - WSL Loopback HTTP Daemon - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    49[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 49 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 22 ["WSL Loopback HTTP Daemon"]
      style 22 fill:#ffffff,stroke:#2e6295,color:#2e6295

      23["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server + route descriptors]</div><div style='font-size: 80%; margin-top:10px'>Adapts BaseHTTPRequestHandler<br />requests through immutable<br />method/path descriptors with<br />static precedence; owns auth,<br />parsing, compatible<br />status/error responses,<br />request IDs, common security<br />headers, redaction-safe<br />telemetry, bounded response<br />streaming, disconnect<br />cleanup, CORS, and finite UI<br />assets.</div>"]
      style 23 fill:#85bbf0,stroke:#1168bd,color:#000000
      24["<div style='font-weight: bold'>Application Use Cases</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Provides request-independent<br />capture, lifecycle, read,<br />forget, policy, doctor, and<br />media use cases; owns<br />database-ready checks,<br />transaction/audit boundaries,<br />asynchronous media kickoff,<br />and upload/download resource<br />leases without importing HTTP<br />request or response types.</div>"]
      style 24 fill:#85bbf0,stroke:#1168bd,color:#000000
      29["<div style='font-weight: bold'>Lifecycle Pipeline</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Stores claimed/resolved tab<br />lifecycle identity,<br />reconciles delayed captures,<br />validates active intervals,<br />and derives visit dwell from<br />interval unions.</div>"]
      style 29 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    23-. "<div>Invokes explicit<br />request-independent use cases<br />through</div><div style='font-size: 70%'></div>" .->24
    24-. "<div>Records lifecycle events<br />through</div><div style='font-size: 70%'></div>" .->29
    29-. "<div>Writes lifecycle identity and<br />interval-union dwell to</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
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
