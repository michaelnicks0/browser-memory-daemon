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

    subgraph 88 ["Local workstation"]
      style 88 fill:#ffffff,stroke:#444444,color:#444444

      subgraph 89 ["Windows user profile"]
        style 89 fill:#ffffff,stroke:#444444,color:#444444

        subgraph 90 ["Windows Chrome daily-driver profile"]
          style 90 fill:#ffffff,stroke:#444444,color:#444444

          91["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
          style 91 fill:#438dd5,stroke:#2e6295,color:#ffffff
          94["<div style='font-weight: bold'>Local Web UI</div><div style='font-size: 70%; margin-top: 0px'>[Container: HTML/CSS/JavaScript served by daemon]</div><div style='font-size: 80%; margin-top:10px'>Static browser UI for exact<br />search, recent/timeline<br />views, document/snapshot<br />detail, media artifact<br />opening, policy rules,<br />doctor, and forget-domain<br />operations.</div>"]
          style 94 fill:#438dd5,stroke:#2e6295,color:#ffffff
        end

      end

      subgraph 96 ["WSL2 Ubuntu"]
        style 96 fill:#ffffff,stroke:#444444,color:#444444

        subgraph 102 ["WSL shell"]
          style 102 fill:#ffffff,stroke:#444444,color:#444444

        end

        subgraph 105 ["WSL XDG runtime data paths"]
          style 105 fill:#ffffff,stroke:#444444,color:#444444

          106[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for migration<br />ledger, sources, documents,<br />visits, capture observations,<br />URL claims, visit events,<br />snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
          style 106 fill:#2f95c8,stroke:#20688c,color:#ffffff
        end

        subgraph 111 ["WSL-mounted NAS blob root"]
          style 111 fill:#ffffff,stroke:#444444,color:#444444

          112[("<div style='font-weight: bold'>Clean Text Blob Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Filesystem store for snapshot<br />text blobs under the<br />configured WSL-visible blob<br />root.</div>")]
          style 112 fill:#2f95c8,stroke:#20688c,color:#ffffff
          114[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs under<br />the configured WSL-visible<br />blob root, with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
          style 114 fill:#2f95c8,stroke:#20688c,color:#ffffff
        end

        subgraph 97 ["systemd --user services"]
          style 97 fill:#ffffff,stroke:#444444,color:#444444

          101["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
          style 101 fill:#438dd5,stroke:#2e6295,color:#ffffff
          98["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
          style 98 fill:#438dd5,stroke:#2e6295,color:#ffffff
        end

      end

    end

    94-. "<div>Calls authenticated read,<br />admin, media, and forget APIs<br />on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->98
    98-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->106
    101-. "<div>Leases and updates media<br />tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->106
    98-. "<div>Reads and writes text<br />snapshots in</div><div style='font-size: 70%'>[Filesystem]</div>" .->112
    98-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->114
    101-. "<div>Writes fetched media blobs to</div><div style='font-size: 70%'>[Filesystem]</div>" .->114
    91-. "<div>Posts /capture,<br />/visit-events, media<br />metadata, and raw blob<br />uploads to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->98

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
