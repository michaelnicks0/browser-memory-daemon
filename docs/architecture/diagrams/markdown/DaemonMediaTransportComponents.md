# Daemon Media Transport Components

> Generated Markdown wrapper for C4 view `DaemonMediaTransportComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Media Transport Components](../dot-rendered/structurizr-DaemonMediaTransportComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - WSL Loopback HTTP Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 14 ["WSL Loopback HTTP Daemon"]
        style 14 fill:#ffffff,stroke:#2e6295,color:#2e6295

        21["<div style='font-weight: bold'>Media Artifact Manager</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Provides the compatibility<br />API, records media<br />references, normalizes<br />bounded blob uploads,<br />delegates guarded public<br />transport, and drains<br />verified spool bytes without<br />coupling text ingest to media<br />availability.</div>"]
        style 21 fill:#85bbf0,stroke:#1168bd,color:#000000
        24["<div style='font-weight: bold'>Media Artifact Store</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + BlobStore]</div><div style='font-size: 80%; margin-top:10px'>Owns artifact rows, unique<br />staged publication,<br />failed-write compensation,<br />contained reads, cache<br />admission, oldest-first<br />eviction, purge/rehydration,<br />and lifecycle<br />registration/tombstones.</div>"]
        style 24 fill:#85bbf0,stroke:#1168bd,color:#000000
        25["<div style='font-weight: bold'>Guarded Media Fetch</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python stdlib urllib + socket]</div><div style='font-size: 80%; margin-top:10px'>Owns HTTP/data transport,<br />public-address validation,<br />redirect revalidation,<br />no-referrer requests,<br />response-byte limits, and<br />shared deadlines.</div>"]
        style 25 fill:#85bbf0,stroke:#1168bd,color:#000000
        26["<div style='font-weight: bold'>Bounded HLS Transport</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Parses bounded playlists,<br />selects variants, expands<br />init maps/segments through<br />the guarded fetch boundary,<br />and assembles bytes within<br />depth/request/deadline<br />limits.</div>"]
        style 26 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

    end

    25-. "<div>Delegates detected playlists<br />for bounded parsing and<br />assembly to</div><div style='font-size: 70%'></div>" .->26
    25-. "<div>Validates and fetches public<br />media from</div><div style='font-size: 70%'>[HTTP(S), no Referer or Chrome cookies]</div>" .->3
    26-. "<div>Fetches every variant, init<br />map, and segment through</div><div style='font-size: 70%'></div>" .->25
    21-. "<div>Publishes, resolves, purges,<br />and rehydrates artifacts<br />through</div><div style='font-size: 70%'></div>" .->24
    21-. "<div>Delegates daemon-public media<br />transport to</div><div style='font-size: 70%'></div>" .->25

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonMediaTransportComponents.mmd`](../structurizr-DaemonMediaTransportComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonMediaTransportComponents.svg`](../structurizr-DaemonMediaTransportComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonMediaTransportComponents.png`](../structurizr-DaemonMediaTransportComponents.png) |
| DOT source | [`structurizr-DaemonMediaTransportComponents.dot`](../dot/structurizr-DaemonMediaTransportComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonMediaTransportComponents.svg`](../dot-rendered/structurizr-DaemonMediaTransportComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonMediaTransportComponents.png`](../dot-rendered/structurizr-DaemonMediaTransportComponents.png) |
