# Daily Driver Deployment

> Generated Markdown wrapper for C4 view `DailyDriverDeployment`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daily Driver Deployment](../dot-rendered/structurizr-DailyDriverDeployment.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph TB
  linkStyle default fill:#ffffff

  subgraph diagram ["Deployment View: Browser Memory Daemon - Daily-driver local"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 85 ["Local workstation"]
      style 85 fill:#ffffff,stroke:#444444,color:#444444

      subgraph 86 ["Windows user profile"]
        style 86 fill:#ffffff,stroke:#444444,color:#444444

        subgraph 87 ["Windows Chrome daily-driver profile"]
          style 87 fill:#ffffff,stroke:#444444,color:#444444

          88["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
          style 88 fill:#438dd5,stroke:#2e6295,color:#ffffff
          91["<div style='font-weight: bold'>Local Web UI</div><div style='font-size: 70%; margin-top: 0px'>[Container: HTML/CSS/JavaScript served by daemon]</div><div style='font-size: 80%; margin-top:10px'>Static browser UI for exact<br />search, recent/timeline<br />views, document/snapshot<br />detail, media artifact<br />opening, policy rules,<br />doctor, and forget-domain<br />operations.</div>"]
          style 91 fill:#438dd5,stroke:#2e6295,color:#ffffff
        end

      end

      subgraph 93 ["WSL2 Ubuntu"]
        style 93 fill:#ffffff,stroke:#444444,color:#444444

        subgraph 102 ["WSL XDG runtime data paths"]
          style 102 fill:#ffffff,stroke:#444444,color:#444444

          103[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for sources,<br />documents, visits, visit<br />events, snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
          style 103 fill:#2f95c8,stroke:#20688c,color:#ffffff
        end

        subgraph 108 ["WSL-mounted NAS blob root"]
          style 108 fill:#ffffff,stroke:#444444,color:#444444

          109[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
          style 109 fill:#2f95c8,stroke:#20688c,color:#ffffff
          111[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
          style 111 fill:#2f95c8,stroke:#20688c,color:#ffffff
        end

        subgraph 94 ["systemd --user services"]
          style 94 fill:#ffffff,stroke:#444444,color:#444444

          95["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
          style 95 fill:#438dd5,stroke:#2e6295,color:#ffffff
          98["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
          style 98 fill:#438dd5,stroke:#2e6295,color:#ffffff
        end

        subgraph 99 ["WSL shell"]
          style 99 fill:#ffffff,stroke:#444444,color:#444444

        end

      end

    end

    95-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->103
    98-. "<div>Leases and updates media<br />tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->103
    95-. "<div>Reads and writes text<br />snapshots in</div><div style='font-size: 70%'>[Filesystem]</div>" .->109
    95-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->111
    98-. "<div>Writes fetched media blobs to</div><div style='font-size: 70%'>[Filesystem]</div>" .->111
    88-. "<div>Posts /capture,<br />/visit-events, media<br />metadata, and raw blob<br />uploads to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->95
    91-. "<div>Calls authenticated read,<br />admin, media, and forget APIs<br />on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->95

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DailyDriverDeployment.mmd`](../structurizr-DailyDriverDeployment.mmd) |
| Mermaid SVG | [`structurizr-DailyDriverDeployment.svg`](../structurizr-DailyDriverDeployment.svg) |
| Mermaid PNG | [`structurizr-DailyDriverDeployment.png`](../structurizr-DailyDriverDeployment.png) |
| DOT source | [`structurizr-DailyDriverDeployment.dot`](../dot/structurizr-DailyDriverDeployment.dot) |
| Graphviz SVG | [`structurizr-DailyDriverDeployment.svg`](../dot-rendered/structurizr-DailyDriverDeployment.svg) |
| Graphviz PNG | [`structurizr-DailyDriverDeployment.png`](../dot-rendered/structurizr-DailyDriverDeployment.png) |
