# Cli X Observation Export Components

> Generated Markdown wrapper for C4 view `CliXObservationExportComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Cli X Observation Export Components](../dot-rendered/structurizr-CliXObservationExportComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - CLI - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    4["<div style='font-weight: bold'>Passive X Observation Consumer</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>A downstream local<br />integration that reads<br />versioned body-safe<br />observation pages without<br />gaining capture, migration,<br />or mutation authority.</div>"]
    style 4 fill:#999999,stroke:#6b6b6b,color:#ffffff
    57[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 57 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 51 ["CLI"]
      style 51 fill:#ffffff,stroke:#2e6295,color:#2e6295

      52["<div style='font-weight: bold'>CLI X Observation Export Adapter</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Opens the existing database<br />directly through the shared<br />query-only export core<br />without daemon readiness,<br />migrations, token<br />requirements, or audit<br />writes.</div>"]
      style 52 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    52-. "<div>Reads validated<br />observation/evidence pages<br />without writes or audit</div><div style='font-size: 70%'>[SQLite mode=ro + query_only]</div>" .->57
    52-. "<div>Emits losslessly cursorable<br />body-safe pages for</div><div style='font-size: 70%'>[JSON stdout]</div>" .->4
  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-CliXObservationExportComponents.mmd`](../structurizr-CliXObservationExportComponents.mmd) |
| Mermaid SVG | [`structurizr-CliXObservationExportComponents.svg`](../structurizr-CliXObservationExportComponents.svg) |
| Mermaid PNG | [`structurizr-CliXObservationExportComponents.png`](../structurizr-CliXObservationExportComponents.png) |
| DOT source | [`structurizr-CliXObservationExportComponents.dot`](../dot/structurizr-CliXObservationExportComponents.dot) |
| Graphviz SVG | [`structurizr-CliXObservationExportComponents.svg`](../dot-rendered/structurizr-CliXObservationExportComponents.svg) |
| Graphviz PNG | [`structurizr-CliXObservationExportComponents.png`](../dot-rendered/structurizr-CliXObservationExportComponents.png) |
