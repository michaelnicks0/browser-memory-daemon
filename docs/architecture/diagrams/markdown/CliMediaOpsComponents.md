# Cli Media Ops Components

> Generated Markdown wrapper for C4 view `CliMediaOpsComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Cli Media Ops Components](../dot-rendered/structurizr-CliMediaOpsComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - CLI - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    57[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 57 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 51 ["CLI"]
      style 51 fill:#ffffff,stroke:#2e6295,color:#2e6295

      54["<div style='font-weight: bold'>Media Cache Requeue Operator</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Previews or executes<br />explicitly scoped<br />dry-run-first budget requeue<br />through in-process media<br />repository functions.</div>"]
      style 54 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    54-. "<div>Reads and updates explicitly<br />scoped media artifact/task<br />state in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-CliMediaOpsComponents.mmd`](../structurizr-CliMediaOpsComponents.mmd) |
| Mermaid SVG | [`structurizr-CliMediaOpsComponents.svg`](../structurizr-CliMediaOpsComponents.svg) |
| Mermaid PNG | [`structurizr-CliMediaOpsComponents.png`](../structurizr-CliMediaOpsComponents.png) |
| DOT source | [`structurizr-CliMediaOpsComponents.dot`](../dot/structurizr-CliMediaOpsComponents.dot) |
| Graphviz SVG | [`structurizr-CliMediaOpsComponents.svg`](../dot-rendered/structurizr-CliMediaOpsComponents.svg) |
| Graphviz PNG | [`structurizr-CliMediaOpsComponents.png`](../dot-rendered/structurizr-CliMediaOpsComponents.png) |
