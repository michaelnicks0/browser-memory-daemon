# Daemon Ingest Components

> Generated Markdown wrapper for C4 view `DaemonIngestComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Ingest Components](../dot-rendered/structurizr-DaemonIngestComponents.svg)

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
        19["<div style='font-weight: bold'>Ingest Pipeline</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Normalizes observed URLs,<br />computes document/snapshot<br />IDs, atomically stores<br />complete cleaned text plus<br />visits/observations/snapshots/chunks/FTS<br />rows, records<br />non-authoritative URL claims,<br />and links media references<br />without touching blob<br />storage.</div>"]
        style 19 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      33[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 33 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    15-. "<div>Routes accepted captures to</div><div style='font-size: 70%'></div>" .->19
    19-. "<div>Atomically writes complete<br />cleaned text, capture rows,<br />and FTS to</div><div style='font-size: 70%'>[sqlite3]</div>" .->33

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonIngestComponents.mmd`](../structurizr-DaemonIngestComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonIngestComponents.svg`](../structurizr-DaemonIngestComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonIngestComponents.png`](../structurizr-DaemonIngestComponents.png) |
| DOT source | [`structurizr-DaemonIngestComponents.dot`](../dot/structurizr-DaemonIngestComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonIngestComponents.svg`](../dot-rendered/structurizr-DaemonIngestComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonIngestComponents.png`](../dot-rendered/structurizr-DaemonIngestComponents.png) |
