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

  subgraph diagram ["Browser Memory Daemon - WSL Loopback HTTP Daemon - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    57[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 57 fill:#2f95c8,stroke:#20688c,color:#ffffff
    59[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
    style 59 fill:#2f95c8,stroke:#20688c,color:#ffffff
    60[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
    style 60 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 23 ["WSL Loopback HTTP Daemon"]
      style 23 fill:#ffffff,stroke:#2e6295,color:#2e6295

      24["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server + route descriptors]</div><div style='font-size: 80%; margin-top:10px'>Adapts BaseHTTPRequestHandler<br />requests through immutable<br />method/path descriptors with<br />static precedence; owns auth,<br />parsing, compatible<br />status/error responses,<br />request IDs, common security<br />headers, redaction-safe<br />telemetry, bounded response<br />streaming, disconnect<br />cleanup, CORS, and finite UI<br />assets.</div>"]
      style 24 fill:#85bbf0,stroke:#1168bd,color:#000000
      25["<div style='font-weight: bold'>Application Use Cases</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Provides request-independent<br />capture, lifecycle, read,<br />forget, policy, doctor, and<br />media use cases; owns<br />database-ready checks,<br />transaction/audit boundaries,<br />asynchronous media kickoff,<br />and upload/download resource<br />leases without importing HTTP<br />request or response types.</div>"]
      style 25 fill:#85bbf0,stroke:#1168bd,color:#000000
      31["<div style='font-weight: bold'>Media Artifact Manager</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Provides the compatibility<br />API, records media<br />references, streams bounded<br />blob uploads, and delegates<br />guarded public transport<br />without coupling text ingest<br />to media availability.</div>"]
      style 31 fill:#85bbf0,stroke:#1168bd,color:#000000
      32["<div style='font-weight: bold'>Media State Model</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Owns caller-visible and<br />internal artifact/task status<br />taxonomies, fetch-error<br />classification, and explicit<br />ordinary versus force-reset<br />transition matrices.</div>"]
      style 32 fill:#85bbf0,stroke:#1168bd,color:#000000
      33["<div style='font-weight: bold'>Media Task Repository</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3]</div><div style='font-size: 80%; margin-top:10px'>Creates deterministic tasks,<br />preserves terminal state,<br />atomically leases due work,<br />recovers stale leases, and<br />applies bounded retry/backoff<br />outcomes independently from<br />media transport.</div>"]
      style 33 fill:#85bbf0,stroke:#1168bd,color:#000000
      34["<div style='font-weight: bold'>Media Artifact Store</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + BlobStore]</div><div style='font-size: 80%; margin-top:10px'>Owns artifact rows,<br />transactional cross-process<br />cache reservations, unique<br />streamed publication,<br />failed-write compensation,<br />contained reads, cache<br />admission, oldest-first<br />eviction, purge/rehydration,<br />and lifecycle<br />registration/tombstones.</div>"]
      style 34 fill:#85bbf0,stroke:#1168bd,color:#000000
      35["<div style='font-weight: bold'>Media Transport Coordinator</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Classifies direct versus HLS<br />responses, applies the<br />aggregate HLS request budget<br />from the first network open,<br />enforces playlist sniffing<br />and byte caps, and<br />coordinates bounded streamed<br />assembly.</div>"]
      style 35 fill:#85bbf0,stroke:#1168bd,color:#000000
      36["<div style='font-weight: bold'>Guarded Media Fetch</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python stdlib urllib + socket]</div><div style='font-size: 80%; margin-top:10px'>Owns streamed HTTP/data<br />transport, public-address<br />validation, redirect<br />revalidation, no-referrer<br />requests, response-byte<br />limits, process request/byte<br />leases, and shared deadlines.</div>"]
      style 36 fill:#85bbf0,stroke:#1168bd,color:#000000
      37["<div style='font-weight: bold'>Bounded HLS Transport</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Parses bounded playlists,<br />selects variants, expands<br />init maps/segments through<br />the guarded fetch boundary,<br />and streams assembly within<br />aggregate<br />byte/depth/request/deadline<br />limits.</div>"]
      style 37 fill:#85bbf0,stroke:#1168bd,color:#000000
      38["<div style='font-weight: bold'>Media Process Resource Budget</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python threading.Condition]</div><div style='font-size: 80%; margin-top:10px'>Bounds active media requests<br />and in-flight bytes across<br />threads within one daemon or<br />worker process; exposes<br />aggregate counters and<br />releases leases on failure or<br />cancellation.</div>"]
      style 38 fill:#85bbf0,stroke:#1168bd,color:#000000
      39["<div style='font-weight: bold'>Contained BlobStore</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python filesystem boundary]</div><div style='font-size: 80%; margin-top:10px'>Prefers root-relative<br />locators with contained<br />legacy fallback; streams<br />unique stages with size/hash<br />accounting; atomically<br />commits; and contains blob<br />read, stat, and delete<br />operations.</div>"]
      style 39 fill:#85bbf0,stroke:#1168bd,color:#000000
      40["<div style='font-weight: bold'>Blob Lifecycle and Storage Reconciler</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Persists<br />committed/tombstoned/missing/deleted/blocked/failed<br />blob state; serializes<br />deletion processors; retries<br />tombstones; and dry-run<br />detects missing refs, in-root<br />orphans, and stale stages.</div>"]
      style 40 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    24-. "<div>Invokes explicit<br />request-independent use cases<br />through</div><div style='font-size: 70%'></div>" .->25
    24-. "<div>Leases bounded JSON media<br />request admission through</div><div style='font-size: 70%'></div>" .->38
    25-. "<div>Coordinates media requests<br />through</div><div style='font-size: 70%'></div>" .->31
    25-. "<div>Leases bounded media upload<br />and response capacity through</div><div style='font-size: 70%'></div>" .->38
    31-. "<div>Classifies artifact outcomes<br />and transition intent through</div><div style='font-size: 70%'></div>" .->32
    31-. "<div>Creates and claims durable<br />media work through</div><div style='font-size: 70%'></div>" .->33
    31-. "<div>Publishes, resolves, purges,<br />and rehydrates artifacts<br />through</div><div style='font-size: 70%'></div>" .->34
    31-. "<div>Delegates daemon-public media<br />orchestration to</div><div style='font-size: 70%'></div>" .->35
    31-. "<div>Updates media artifact rows<br />in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    33-. "<div>Validates task status<br />vocabulary and retry<br />classification through</div><div style='font-size: 70%'></div>" .->32
    33-. "<div>Creates, leases, and advances<br />media tasks in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    34-. "<div>Uses artifact status<br />vocabulary from</div><div style='font-size: 70%'></div>" .->32
    34-. "<div>Marks stored/skipped outcomes<br />and ensures retryable fetch<br />work through</div><div style='font-size: 70%'></div>" .->33
    34-. "<div>Reserves cache capacity and<br />advances media artifact rows<br />transactionally in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    34-. "<div>Stages unique candidates,<br />resolves contained reads, and<br />deletes failed candidates<br />through</div><div style='font-size: 70%'></div>" .->39
    34-. "<div>Registers committed blobs and<br />tombstones replacement,<br />eviction, and purge bytes<br />through</div><div style='font-size: 70%'></div>" .->40
    35-. "<div>Streams the initial response<br />and every direct artifact<br />through</div><div style='font-size: 70%'></div>" .->36
    35-. "<div>Delegates detected playlists<br />for bounded parsing and<br />assembly to</div><div style='font-size: 70%'></div>" .->37
    35-. "<div>Leases aggregate transfer<br />bytes through</div><div style='font-size: 70%'></div>" .->38
    36-. "<div>Leases each active HTTP<br />request through</div><div style='font-size: 70%'></div>" .->38
    37-. "<div>Fetches every variant, init<br />map, and segment through</div><div style='font-size: 70%'></div>" .->36
    31-. "<div>Checks current artifact<br />presence and resolves<br />contained storage through</div><div style='font-size: 70%'></div>" .->39
    40-. "<div>Reads and advances durable<br />blob lifecycle records in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    40-. "<div>Resolves, deletes, and<br />inventories contained bytes<br />through</div><div style='font-size: 70%'></div>" .->39
    39-. "<div>Stages, commits, reads,<br />stats, and deletes media<br />blobs in</div><div style='font-size: 70%'>[Filesystem]</div>" .->59
    39-. "<div>Stages, commits, reads,<br />stats, and deletes spooled<br />media in</div><div style='font-size: 70%'>[Filesystem]</div>" .->60
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
