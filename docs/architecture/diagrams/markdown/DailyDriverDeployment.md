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

    subgraph 116 ["Local workstation"]
      style 116 fill:#ffffff,stroke:#444444,color:#444444

      subgraph 117 ["Windows user profile"]
        style 117 fill:#ffffff,stroke:#444444,color:#444444

        subgraph 118 ["Windows Chrome daily-driver profile"]
          style 118 fill:#ffffff,stroke:#444444,color:#444444

          119["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
          style 119 fill:#438dd5,stroke:#2e6295,color:#ffffff
          122["<div style='font-weight: bold'>Local Web UI</div><div style='font-size: 70%; margin-top: 0px'>[Container: HTML/CSS/JavaScript served by daemon]</div><div style='font-size: 80%; margin-top:10px'>Static browser UI for exact<br />search, recent/timeline<br />views, document/snapshot<br />detail, media artifact<br />opening, policy rules,<br />doctor, and forget-domain<br />operations.</div>"]
          style 122 fill:#438dd5,stroke:#2e6295,color:#ffffff
        end

      end

      subgraph 124 ["WSL2 Ubuntu"]
        style 124 fill:#ffffff,stroke:#444444,color:#444444

        subgraph 125 ["systemd --user services"]
          style 125 fill:#ffffff,stroke:#444444,color:#444444

          126["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, durable<br />forget, and static UI<br />serving.</div>"]
          style 126 fill:#438dd5,stroke:#2e6295,color:#ffffff
          129["<div style='font-weight: bold'>WSL Media Worker</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11 CLI loop]</div><div style='font-size: 80%; margin-top:10px'>Long-running systemd user<br />worker that leases<br />daemon-public media fetch<br />tasks, fetches public<br />media/HLS without Chrome<br />cookies, classifies terminal<br />states, and updates artifact<br />rows.</div>"]
          style 129 fill:#438dd5,stroke:#2e6295,color:#ffffff
        end

        subgraph 131 ["WSL shell"]
          style 131 fill:#ffffff,stroke:#444444,color:#444444

        end

        subgraph 134 ["WSL XDG runtime data paths"]
          style 134 fill:#ffffff,stroke:#444444,color:#444444

          135[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
          style 135 fill:#2f95c8,stroke:#20688c,color:#ffffff
          139[("<div style='font-weight: bold'>Local Derivative Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Reconstructible compatibility<br />evidence such as<br />pre-version-9 clean-text<br />sidecars; new captures create<br />no text sidecars.</div>")]
          style 139 fill:#2f95c8,stroke:#20688c,color:#ffffff
          142[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
          style 142 fill:#2f95c8,stroke:#20688c,color:#ffffff
        end

        subgraph 147 ["WSL-mounted guarded media root"]
          style 147 fill:#ffffff,stroke:#444444,color:#444444

          148[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
          style 148 fill:#2f95c8,stroke:#20688c,color:#ffffff
        end

      end

    end

    119-. "<div>Posts /capture,<br />/visit-events, media<br />metadata, and raw blob<br />uploads to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->126
    122-. "<div>Calls authenticated read,<br />admin, media, and forget APIs<br />on</div><div style='font-size: 70%'>[HTTP/JSON]</div>" .->126
    129-. "<div>Runs bounded lease/retry task<br />workflow through</div><div style='font-size: 70%'></div>" .->126
    126-. "<div>Reads and writes metadata,<br />FTS, tasks, audit, and<br />receipts in</div><div style='font-size: 70%'>[sqlite3]</div>" .->135
    129-. "<div>Leases and updates media<br />tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->135
    126-. "<div>Reads or deletes legacy text<br />sidecars when required</div><div style='font-size: 70%'>[Filesystem]</div>" .->139
    126-. "<div>Stores and serves media<br />during guarded-root outages<br />in</div><div style='font-size: 70%'>[Filesystem]</div>" .->142
    129-. "<div>Writes fetched media during<br />guarded-root outages to</div><div style='font-size: 70%'>[Filesystem]</div>" .->142
    126-. "<div>Stores, serves, purges, and<br />rehydrates media blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->148
    129-. "<div>Writes fetched media blobs to</div><div style='font-size: 70%'>[Filesystem]</div>" .->148

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
