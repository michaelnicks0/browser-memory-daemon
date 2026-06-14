# Credentialed Media Sidecar Flow

> Generated Markdown wrapper for C4 view `CredentialedMediaSidecarFlow`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from architecture/workspace.dsl. -->

## Diagram

![Credentialed Media Sidecar Flow](../dot-rendered/structurizr-CredentialedMediaSidecarFlow.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Dynamic View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      13[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side storage for<br />capture and visit queues in<br />chrome.storage.local plus<br />durable media tasks and<br />fetched blobs in IndexedDB.</div>")]
      style 13 fill:#2f95c8,stroke:#20688c,color:#ffffff
      14["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, forget,<br />and static UI serving.</div>"]
      style 14 fill:#438dd5,stroke:#2e6295,color:#ffffff
      27[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable relational and<br />full-text store for sources,<br />documents, visits, visit<br />events, snapshots, chunks,<br />chunks_fts, media artifacts,<br />media fetch tasks, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 27 fill:#2f95c8,stroke:#20688c,color:#ffffff
      29[("<div style='font-weight: bold'>Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded and disposable<br />filesystem cache for stored<br />image/video/audio blobs with<br />purge/rehydrate semantics<br />that preserve media refs,<br />hashes, status reasons, and<br />provenance when bytes are<br />absent or purged.</div>")]
      style 29 fill:#2f95c8,stroke:#20688c,color:#ffffff
      5["<div style='font-weight: bold'>Chrome MV3 Extension</div><div style='font-size: 70%; margin-top: 0px'>[Container: JavaScript, Chrome Manifest V3]</div><div style='font-size: 80%; margin-top:10px'>Captures visible page text,<br />media references, tab<br />lifecycle events, and<br />browser-side media bytes from<br />Windows Chrome; queues work<br />durably and posts to the WSL<br />daemon.</div>"]
      style 5 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff

    5-. "<div>1. Reads due media task</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13
    5-. "<div>2. Fetches source URL with<br />Chrome cookie envelope</div><div style='font-size: 70%'>[DOM; fetch(credentials: include)]</div>" .->3
    5-. "<div>3. Persists fetched blob<br />until upload succeeds</div><div style='font-size: 70%'>[chrome.storage.local + IndexedDB]</div>" .->13
    5-. "<div>4. PUTs raw blob to<br />/media-artifacts/{id}/blob</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765]</div>" .->14
    14-. "<div>5. Writes blob if MIME and<br />cache gates allow</div><div style='font-size: 70%'>[Filesystem]</div>" .->29
    14-. "<div>6. Updates artifact<br />status=stored, hash, byte<br />size, and task state</div><div style='font-size: 70%'>[sqlite3]</div>" .->27

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-CredentialedMediaSidecarFlow.mmd`](../structurizr-CredentialedMediaSidecarFlow.mmd) |
| Mermaid SVG | [`structurizr-CredentialedMediaSidecarFlow.svg`](../structurizr-CredentialedMediaSidecarFlow.svg) |
| Mermaid PNG | [`structurizr-CredentialedMediaSidecarFlow.png`](../structurizr-CredentialedMediaSidecarFlow.png) |
| DOT source | [`structurizr-CredentialedMediaSidecarFlow.dot`](../dot/structurizr-CredentialedMediaSidecarFlow.dot) |
| Graphviz SVG | [`structurizr-CredentialedMediaSidecarFlow.svg`](../dot-rendered/structurizr-CredentialedMediaSidecarFlow.svg) |
| Graphviz PNG | [`structurizr-CredentialedMediaSidecarFlow.png`](../dot-rendered/structurizr-CredentialedMediaSidecarFlow.png) |
