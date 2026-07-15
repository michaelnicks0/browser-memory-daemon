# Daemon Public Media Worker Flow

> Generated Markdown wrapper for C4 view `DaemonPublicMediaWorkerFlow`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Public Media Worker Flow](../dot-rendered/structurizr-DaemonPublicMediaWorkerFlow.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - Dynamic"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      45["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that first drains one<br />bounded spool-recovery batch<br />when the guarded final root<br />is ready, then leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
      style 45 fill:#438dd5,stroke:#2e6295,color:#ffffff
      49[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
      style 49 fill:#2f95c8,stroke:#20688c,color:#ffffff
      51[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
      style 51 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff

    45-. "<div>1. Claims due daemon-public<br />media_fetch_tasks</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
    45-. "<div>2. Fetches public media or<br />HLS assets without Chrome<br />cookies</div><div style='font-size: 70%'>[HTTP(S), data URLs]</div>" .->3
    45-. "<div>3. Writes fetched or<br />assembled blob when gates<br />allow</div><div style='font-size: 70%'>[Filesystem]</div>" .->51
    45-. "<div>4. Marks task/artifact<br />stored, retrying, skipped,<br />expired, or failed with<br />reason</div><div style='font-size: 70%'>[sqlite3]</div>" .->49
  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonPublicMediaWorkerFlow.mmd`](../structurizr-DaemonPublicMediaWorkerFlow.mmd) |
| Mermaid SVG | [`structurizr-DaemonPublicMediaWorkerFlow.svg`](../structurizr-DaemonPublicMediaWorkerFlow.svg) |
| Mermaid PNG | [`structurizr-DaemonPublicMediaWorkerFlow.png`](../structurizr-DaemonPublicMediaWorkerFlow.png) |
| DOT source | [`structurizr-DaemonPublicMediaWorkerFlow.dot`](../dot/structurizr-DaemonPublicMediaWorkerFlow.dot) |
| Graphviz SVG | [`structurizr-DaemonPublicMediaWorkerFlow.svg`](../dot-rendered/structurizr-DaemonPublicMediaWorkerFlow.svg) |
| Graphviz PNG | [`structurizr-DaemonPublicMediaWorkerFlow.png`](../dot-rendered/structurizr-DaemonPublicMediaWorkerFlow.png) |
