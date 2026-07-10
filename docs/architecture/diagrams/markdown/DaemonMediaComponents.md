# Daemon Media Components

> Generated Markdown wrapper for C4 view `DaemonMediaComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Media Components](../dot-rendered/structurizr-DaemonMediaComponents.svg)

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
        21["<div style='font-weight: bold'>Media Artifact Manager</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Provides the compatibility<br />API, records media<br />references, normalizes<br />bounded blob uploads,<br />coordinates public fetch/HLS<br />work, and drains verified<br />spool bytes without coupling<br />text ingest to media<br />availability.</div>"]
        style 21 fill:#85bbf0,stroke:#1168bd,color:#000000
        22["<div style='font-weight: bold'>Media State Model</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Owns caller-visible and<br />internal artifact/task status<br />taxonomies, fetch-error<br />classification, and explicit<br />ordinary versus force-reset<br />transition matrices.</div>"]
        style 22 fill:#85bbf0,stroke:#1168bd,color:#000000
        23["<div style='font-weight: bold'>Media Task Repository</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Creates deterministic tasks,<br />preserves terminal state,<br />atomically leases due work,<br />recovers stale leases, and<br />applies bounded retry/backoff<br />outcomes independently from<br />media transport.</div>"]
        style 23 fill:#85bbf0,stroke:#1168bd,color:#000000
        24["<div style='font-weight: bold'>Media Artifact Store</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + BlobStore]</div><div style='font-size: 80%; margin-top:10px'>Owns artifact rows, unique<br />staged publication,<br />failed-write compensation,<br />contained reads, cache<br />admission, oldest-first<br />eviction, purge/rehydration,<br />and lifecycle<br />registration/tombstones.</div>"]
        style 24 fill:#85bbf0,stroke:#1168bd,color:#000000
        25["<div style='font-weight: bold'>Contained BlobStore</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python filesystem boundary]</div><div style='font-size: 80%; margin-top:10px'>Prefers root-relative<br />locators with contained<br />legacy fallback; streams<br />unique stages with size/hash<br />accounting; atomically<br />commits; and contains blob<br />read, stat, and delete<br />operations.</div>"]
        style 25 fill:#85bbf0,stroke:#1168bd,color:#000000
        26["<div style='font-weight: bold'>Blob Lifecycle and Storage Reconciler</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Persists<br />committed/tombstoned/missing/deleted/blocked/failed<br />blob state; serializes<br />deletion processors; retries<br />tombstones; and dry-run<br />detects missing refs, in-root<br />orphans, and stale stages.</div>"]
        style 26 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      34[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 34 fill:#2f95c8,stroke:#20688c,color:#ffffff
      36[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
      style 36 fill:#2f95c8,stroke:#20688c,color:#ffffff
      37[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
      style 37 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    24-. "<div>Stages unique candidates and<br />contains artifact commits,<br />reads, stats, and deletes<br />through</div><div style='font-size: 70%'></div>" .->25
    24-. "<div>Registers committed bytes,<br />tombstones<br />replacements/purges/evictions,<br />and observes deletion<br />outcomes through</div><div style='font-size: 70%'></div>" .->26
    21-. "<div>Checks current artifact<br />presence during fetch<br />orchestration and drains<br />spool bytes through</div><div style='font-size: 70%'></div>" .->25
    26-. "<div>Reads and advances durable<br />blob lifecycle records in</div><div style='font-size: 70%'>[sqlite3]</div>" .->34
    26-. "<div>Resolves, deletes, and<br />inventories contained bytes<br />through</div><div style='font-size: 70%'></div>" .->25
    25-. "<div>Stages, commits, reads,<br />stats, and deletes media<br />blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->36
    25-. "<div>Stages, commits, reads,<br />stats, and deletes spooled<br />media in</div><div style='font-size: 70%'>[Filesystem]</div>" .->37
    15-. "<div>Routes media requests to</div><div style='font-size: 70%'></div>" .->21
    21-. "<div>Classifies artifact outcomes<br />and transition intent through</div><div style='font-size: 70%'></div>" .->22
    21-. "<div>Creates and claims durable<br />media work through</div><div style='font-size: 70%'></div>" .->23
    21-. "<div>Publishes, resolves, purges,<br />and rehydrates artifacts<br />through</div><div style='font-size: 70%'></div>" .->24
    21-. "<div>Updates media artifact rows<br />in</div><div style='font-size: 70%'>[sqlite3]</div>" .->34
    23-. "<div>Validates task status<br />vocabulary and retry<br />classification through</div><div style='font-size: 70%'></div>" .->22
    23-. "<div>Creates, leases, and advances<br />media tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->34
    24-. "<div>Uses artifact status<br />vocabulary from</div><div style='font-size: 70%'></div>" .->22
    24-. "<div>Marks stored/skipped outcomes<br />and ensures retryable fetch<br />work through</div><div style='font-size: 70%'></div>" .->23
    24-. "<div>Counts and advances media<br />artifact rows in</div><div style='font-size: 70%'>[sqlite3]</div>" .->34

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonMediaComponents.mmd`](../structurizr-DaemonMediaComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonMediaComponents.svg`](../structurizr-DaemonMediaComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonMediaComponents.png`](../structurizr-DaemonMediaComponents.png) |
| DOT source | [`structurizr-DaemonMediaComponents.dot`](../dot/structurizr-DaemonMediaComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonMediaComponents.svg`](../dot-rendered/structurizr-DaemonMediaComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonMediaComponents.png`](../dot-rendered/structurizr-DaemonMediaComponents.png) |
