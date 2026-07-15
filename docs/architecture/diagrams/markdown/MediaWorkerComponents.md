# Media Worker Components

> Generated Markdown wrapper for C4 view `MediaWorkerComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Media Worker Components](../dot-rendered/structurizr-MediaWorkerComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - WSL Media Worker - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff
    57[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 57 fill:#2f95c8,stroke:#20688c,color:#ffffff
    59[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
    style 59 fill:#2f95c8,stroke:#20688c,color:#ffffff
    60[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
    style 60 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 45 ["WSL Media Worker"]
      style 45 fill:#ffffff,stroke:#2e6295,color:#2e6295

      46["<div style='font-weight: bold'>Media Worker Loop</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Orders one bounded automatic<br />spool-recovery pass, bounded<br />current-state reconciliation,<br />and one bounded public-media<br />task pass; records<br />redaction-safe outcomes.</div>"]
      style 46 fill:#85bbf0,stroke:#1168bd,color:#000000
      47["<div style='font-weight: bold'>Automatic Spool Recovery</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Checks guarded-root<br />readiness, streams and<br />hash-verifies destination<br />bytes, commits the SQLite<br />tier switch and deletion<br />intent, then removes the<br />local source.</div>"]
      style 47 fill:#85bbf0,stroke:#1168bd,color:#000000
      48["<div style='font-weight: bold'>Current-State Media Reconciliation</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Closes bounded stale stored<br />work and reconciles current<br />CDP/blob coverage through<br />in-process repository<br />functions before due-task<br />leasing.</div>"]
      style 48 fill:#85bbf0,stroke:#1168bd,color:#000000
      49["<div style='font-weight: bold'>Public Media Task Runner</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Leases due daemon-public<br />tasks, runs guarded<br />direct/HLS fetch without<br />Chrome cookies, applies<br />process budgets, and records<br />terminal or retry state.</div>"]
      style 49 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    49-. "<div>Publishes admitted outage<br />bytes in</div><div style='font-size: 70%'>[Filesystem]</div>" .->60
    48-. "<div>Reads and advances current<br />artifact/task state in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    46-. "<div>Runs one bounded recovery<br />batch before new fetch work<br />through</div><div style='font-size: 70%'></div>" .->47
    46-. "<div>Runs bounded current-state<br />cleanup before due-task<br />leasing through</div><div style='font-size: 70%'></div>" .->48
    46-. "<div>Runs one bounded due-task<br />batch through</div><div style='font-size: 70%'></div>" .->49
    47-. "<div>Commits tier transitions and<br />durable deletion intent in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    47-. "<div>Reads and removes<br />authoritative local outage<br />bytes from</div><div style='font-size: 70%'>[Filesystem]</div>" .->60
    47-. "<div>Streams and verifies<br />recovered destination bytes<br />in</div><div style='font-size: 70%'>[Filesystem]</div>" .->59
    49-. "<div>Leases tasks and records<br />artifact outcomes in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    49-. "<div>Fetches guarded direct/HLS<br />media from</div><div style='font-size: 70%'>[HTTP(S), data URLs]</div>" .->3
    49-. "<div>Publishes admitted final<br />bytes in</div><div style='font-size: 70%'>[Filesystem]</div>" .->59
  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-MediaWorkerComponents.mmd`](../structurizr-MediaWorkerComponents.mmd) |
| Mermaid SVG | [`structurizr-MediaWorkerComponents.svg`](../structurizr-MediaWorkerComponents.svg) |
| Mermaid PNG | [`structurizr-MediaWorkerComponents.png`](../structurizr-MediaWorkerComponents.png) |
| DOT source | [`structurizr-MediaWorkerComponents.dot`](../dot/structurizr-MediaWorkerComponents.dot) |
| Graphviz SVG | [`structurizr-MediaWorkerComponents.svg`](../dot-rendered/structurizr-MediaWorkerComponents.svg) |
| Graphviz PNG | [`structurizr-MediaWorkerComponents.png`](../dot-rendered/structurizr-MediaWorkerComponents.png) |
