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

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        23["<div style='font-weight: bold'>Media Task Repository</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Creates deterministic tasks,<br />preserves terminal state,<br />atomically leases due work,<br />recovers stale leases, and<br />applies bounded retry/backoff<br />outcomes independently from<br />media transport.</div>"]
        style 23 fill:#85bbf0,stroke:#1168bd,color:#000000
        27["<div style='font-weight: bold'>Media Operator and Reconciliation Workflow</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Owns scoped dry-run-first<br />budget requeue plus bounded<br />current-state CDP/blob and<br />stored-task reconciliation.</div>"]
        style 27 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      34["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
      style 34 fill:#438dd5,stroke:#2e6295,color:#ffffff
      36["<div style='font-weight: bold'>CLI</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python argparse]</div><div style='font-size: 80%; margin-top:10px'>Command-line interface for<br />serving the daemon,<br />migration, snapshot-text and<br />storage reconciliation,<br />manifest-backed<br />backup/restore, media-spool<br />status/drain,<br />health/doctor/search/recent/timeline/detail,<br />policy/forget, capture<br />fixtures, media worker, and<br />media cache operations.</div>"]
      style 36 fill:#438dd5,stroke:#2e6295,color:#ffffff
      38[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 38 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    23-. "<div>Creates, leases, and advances<br />media tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->38
    27-. "<div>Resets explicitly selected<br />tasks and closes bounded<br />stale stored work through</div><div style='font-size: 70%'></div>" .->23
    27-. "<div>Reads and updates scoped<br />media artifact/task state in</div><div style='font-size: 70%'>[sqlite3]</div>" .->38
    36-. "<div>Runs migration, media-worker,<br />media-cache, media-spool, and<br />storage-reconcile commands<br />against</div><div style='font-size: 70%'>[sqlite3]</div>" .->38
    36-. "<div>Previews or executes scoped<br />budget requeue through</div><div style='font-size: 70%'></div>" .->27
    34-. "<div>Leases and updates media<br />tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->38
    34-. "<div>Runs bounded lease/retry task<br />workflow through</div><div style='font-size: 70%'></div>" .->23
    34-. "<div>Runs bounded current-state<br />reconciliation through</div><div style='font-size: 70%'></div>" .->27

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
