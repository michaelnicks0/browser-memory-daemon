# Extension Outbox Components

> Generated Markdown wrapper for C4 view `ExtensionOutboxComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Extension Outbox Components](../dot-rendered/structurizr-ExtensionOutboxComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - Chrome MV3 Extension"]
    style diagram fill:#ffffff,stroke:#ffffff

    2["<div style='font-weight: bold'>Windows Chrome</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>The Windows Chrome runtime<br />that loads web pages, hosts<br />the MV3 extension, runs the<br />local UI in a tab, and<br />exposes Chrome extension<br />APIs.</div>"]
    style 2 fill:#999999,stroke:#6b6b6b,color:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 5 ["Chrome MV3 Extension"]
        style 5 fill:#ffffff,stroke:#2e6295,color:#2e6295

        10["<div style='font-weight: bold'>Capture and Lifecycle Outbox</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Persists capture and<br />lifecycle messages as<br />independently sequenced<br />IndexedDB rows with atomic<br />enqueue/claim/checkpoint/ack/retry,<br />stale-claim recovery, legacy<br />queue import, item admission<br />limits, and serialized-byte<br />accounting.</div>"]
        style 10 fill:#85bbf0,stroke:#1168bd,color:#000000
        8["<div style='font-weight: bold'>Content Script</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript content script]</div><div style='font-size: 80%; margin-top:10px'>Schedules initial, delayed,<br />reinjected, and SPA captures;<br />computes full deterministic<br />SHA-256 capture digests;<br />tracks scroll; and sends<br />capture and inline blob<br />upload messages to the<br />service worker.</div>"]
        style 8 fill:#85bbf0,stroke:#1168bd,color:#000000
        9["<div style='font-weight: bold'>Service Worker</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript MV3 service worker]</div><div style='font-size: 80%; margin-top:10px'>Orchestrates daemon<br />transport, bearer token use,<br />stable observation/navigation<br />identity, lifecycle state,<br />outbox and media drains,<br />alarms, and CDP recorder<br />integration.</div>"]
        style 9 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      14[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side IndexedDB<br />storage for transactional<br />capture/lifecycle outbox rows<br />plus specialized durable<br />media tasks/blobs;<br />chrome.storage.local retains<br />typed configuration,<br />lifecycle tab state,<br />aggregate telemetry, and<br />one-version queue fallback<br />only.</div>")]
      style 14 fill:#2f95c8,stroke:#20688c,color:#ffffff
      15["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback HTTP<br />API that handles capture,<br />visit events, media artifact<br />upload/fetch/purge, exact<br />search,<br />recent/timeline/detail,<br />policy rules, doctor, durable<br />forget, and static UI<br />serving.</div>"]
      style 15 fill:#438dd5,stroke:#2e6295,color:#ffffff
    end

    8-. "<div>Sends captures and inline<br />blobs to</div><div style='font-size: 70%'>[chrome.runtime.sendMessage]</div>" .->9
    9-. "<div>Enqueues, drains,<br />checkpoints, retries, and<br />recovers capture/lifecycle<br />work through</div><div style='font-size: 70%'></div>" .->10
    10-. "<div>Reads and writes sequenced<br />capture/lifecycle rows and<br />migration metadata in</div><div style='font-size: 70%'>[IndexedDB]</div>" .->14
    9-. "<div>Persists typed configuration,<br />lifecycle tab state,<br />aggregate telemetry, and<br />one-version queue fallback in</div><div style='font-size: 70%'>[chrome.storage.local]</div>" .->14
    9-. "<div>Delivers /capture,<br />/visit-events, media<br />metadata, and raw blobs to</div><div style='font-size: 70%'>[Bearer HTTP/JSON; raw HTTP PUT]</div>" .->15

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-ExtensionOutboxComponents.mmd`](../structurizr-ExtensionOutboxComponents.mmd) |
| Mermaid SVG | [`structurizr-ExtensionOutboxComponents.svg`](../structurizr-ExtensionOutboxComponents.svg) |
| Mermaid PNG | [`structurizr-ExtensionOutboxComponents.png`](../structurizr-ExtensionOutboxComponents.png) |
| DOT source | [`structurizr-ExtensionOutboxComponents.dot`](../dot/structurizr-ExtensionOutboxComponents.dot) |
| Graphviz SVG | [`structurizr-ExtensionOutboxComponents.svg`](../dot-rendered/structurizr-ExtensionOutboxComponents.svg) |
| Graphviz PNG | [`structurizr-ExtensionOutboxComponents.png`](../dot-rendered/structurizr-ExtensionOutboxComponents.png) |
