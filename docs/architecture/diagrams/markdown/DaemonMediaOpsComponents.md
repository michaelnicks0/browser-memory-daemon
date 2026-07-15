# Daemon Media Ops Components

> Generated Markdown wrapper for C4 view `DaemonMediaOpsComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Media Ops Components](../dot-rendered/structurizr-DaemonMediaOpsComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - WSL Loopback HTTP Daemon - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    45["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that first drains one<br />bounded spool-recovery batch<br />when the guarded final root<br />is ready, then leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
    style 45 fill:#438dd5,stroke:#2e6295,color:#ffffff
    47["<div style='font-weight: bold'>CLI</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python argparse]</div><div style='font-size: 80%; margin-top:10px'>Command-line interface for<br />serving/admin operations plus<br />standalone mutation-free X<br />observation export.</div>"]
    style 47 fill:#438dd5,stroke:#2e6295,color:#ffffff
    49[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 49 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 22 ["WSL Loopback HTTP Daemon"]
      style 22 fill:#ffffff,stroke:#2e6295,color:#2e6295

      32["<div style='font-weight: bold'>Media Task Repository</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Creates deterministic tasks,<br />preserves terminal state,<br />atomically leases due work,<br />recovers stale leases, and<br />applies bounded retry/backoff<br />outcomes independently from<br />media transport.</div>"]
      style 32 fill:#85bbf0,stroke:#1168bd,color:#000000
      37["<div style='font-weight: bold'>Media Operator and Reconciliation Workflow</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Owns scoped dry-run-first<br />budget requeue plus bounded<br />current-state CDP/blob and<br />stored-task reconciliation.</div>"]
      style 37 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    32-. "<div>Creates, leases, and advances<br />media tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
    37-. "<div>Resets explicitly selected<br />tasks and closes bounded<br />stale stored work through</div><div style='font-size: 70%'></div>" .->32
    37-. "<div>Reads and updates scoped<br />media artifact/task state in</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
    47-. "<div>Runs migration, media-worker,<br />media-cache, media-spool, and<br />storage-reconcile commands<br />against</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
    47-. "<div>Previews or executes scoped<br />budget requeue through</div><div style='font-size: 70%'></div>" .->37
    45-. "<div>Leases and updates media<br />tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
    45-. "<div>Runs bounded lease/retry task<br />workflow through</div><div style='font-size: 70%'></div>" .->32
    45-. "<div>Runs bounded current-state<br />reconciliation through</div><div style='font-size: 70%'></div>" .->37
  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonMediaOpsComponents.mmd`](../structurizr-DaemonMediaOpsComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonMediaOpsComponents.svg`](../structurizr-DaemonMediaOpsComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonMediaOpsComponents.png`](../structurizr-DaemonMediaOpsComponents.png) |
| DOT source | [`structurizr-DaemonMediaOpsComponents.dot`](../dot/structurizr-DaemonMediaOpsComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonMediaOpsComponents.svg`](../dot-rendered/structurizr-DaemonMediaOpsComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonMediaOpsComponents.png`](../dot-rendered/structurizr-DaemonMediaOpsComponents.png) |
