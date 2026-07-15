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

  subgraph diagram ["Browser Memory Daemon - Chrome MV3 Extension - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    2["<div style='font-weight: bold'>Windows Chrome</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>The Windows Chrome runtime<br />that loads web pages, hosts<br />the MV3 extension, runs the<br />local UI in a tab, and<br />exposes Chrome extension<br />APIs.</div>"]
    style 2 fill:#999999,stroke:#6b6b6b,color:#ffffff
    22[("<div style='font-weight: bold'>Extension Browser Storage</div><div style='font-size: 70%; margin-top: 0px'>[Container: chrome.storage.local + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Browser-side IndexedDB<br />storage for transactional<br />capture/lifecycle outbox rows<br />plus specialized durable<br />media tasks/blobs;<br />chrome.storage.local retains<br />typed configuration,<br />lifecycle tab state, minimal<br />CDP capture context,<br />aggregate telemetry, and<br />one-version queue fallback<br />only.</div>")]
    style 22 fill:#2f95c8,stroke:#20688c,color:#ffffff
    23["<div style='font-weight: bold'>WSL Loopback HTTP Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Container: Python 3.11, ThreadingHTTPServer]</div><div style='font-size: 80%; margin-top:10px'>Authenticated loopback API<br />for capture, read/admin/media<br />operations, and query-only<br />bmd.x-observations v1 export.</div>"]
    style 23 fill:#438dd5,stroke:#2e6295,color:#ffffff

    subgraph 6 ["Chrome MV3 Extension"]
      style 6 fill:#ffffff,stroke:#2e6295,color:#2e6295

      10["<div style='font-weight: bold'>Service Worker</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript MV3 service worker]</div><div style='font-size: 80%; margin-top:10px'>Composes extension modules<br />and registers MV3 message,<br />tab, window, debugger, alarm,<br />startup, and installation<br />listeners.</div>"]
      style 10 fill:#85bbf0,stroke:#1168bd,color:#000000
      11["<div style='font-weight: bold'>Extension Config Store</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript + chrome.storage.local]</div><div style='font-size: 80%; margin-top:10px'>Owns typed configuration<br />defaults/migration plus<br />durable visit and minimal CDP<br />capture-context maps.</div>"]
      style 11 fill:#85bbf0,stroke:#1168bd,color:#000000
      14["<div style='font-weight: bold'>Capture and Lifecycle Bridge</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript]</div><div style='font-size: 80%; margin-top:10px'>Owns daemon delivery,<br />transactional outbox<br />import/admission/drain/checkpoint/retry,<br />legacy fallback, media<br />compensation, and queue<br />status.</div>"]
      style 14 fill:#85bbf0,stroke:#1168bd,color:#000000
      16["<div style='font-weight: bold'>Extension Telemetry</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript + chrome.storage.local]</div><div style='font-size: 80%; margin-top:10px'>Persists aggregate<br />bridge/queue/CDP status after<br />recursively removing captured<br />fields and redacting<br />URL-shaped errors.</div>"]
      style 16 fill:#85bbf0,stroke:#1168bd,color:#000000
      17["<div style='font-weight: bold'>Capture and Lifecycle Outbox</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript + IndexedDB]</div><div style='font-size: 80%; margin-top:10px'>Persists capture and<br />lifecycle messages as<br />independently sequenced<br />IndexedDB rows with atomic<br />enqueue/claim/checkpoint/ack/retry,<br />stale-claim recovery, legacy<br />queue import, item admission<br />limits, and serialized-byte<br />accounting.</div>"]
      style 17 fill:#85bbf0,stroke:#1168bd,color:#000000
      9["<div style='font-weight: bold'>Content Script</div><div style='font-size: 70%; margin-top: 0px'>[Component: JavaScript content script]</div><div style='font-size: 80%; margin-top:10px'>Schedules initial, delayed,<br />reinjected, and SPA captures;<br />computes full deterministic<br />SHA-256 capture digests;<br />tracks scroll; and sends<br />capture and inline blob<br />upload messages to the<br />service worker.</div>"]
      style 9 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    9-. "<div>Sends captures and inline<br />blobs to</div><div style='font-size: 70%'>[chrome.runtime.sendMessage]</div>" .->10
    10-. "<div>Reads typed settings and<br />durable restart state through</div><div style='font-size: 70%'></div>" .->11
    11-. "<div>Reads and writes typed<br />settings and restart state in</div><div style='font-size: 70%'>[chrome.storage.local]</div>" .->22
    10-. "<div>Delegates capture/lifecycle<br />delivery and durable drains<br />to</div><div style='font-size: 70%'></div>" .->14
    10-. "<div>Creates the redaction-safe<br />telemetry boundary through</div><div style='font-size: 70%'></div>" .->16
    14-. "<div>Enqueues, drains,<br />checkpoints, retries, and<br />recovers capture/lifecycle<br />work through</div><div style='font-size: 70%'></div>" .->17
    14-. "<div>Imports and preserves the<br />one-version queue fallback in</div><div style='font-size: 70%'>[chrome.storage.local]</div>" .->22
    14-. "<div>Delivers /capture and<br />/visit-events to</div><div style='font-size: 70%'>[Bearer HTTP/JSON]</div>" .->23
    14-. "<div>Records aggregate outbox<br />status through</div><div style='font-size: 70%'></div>" .->16
    17-. "<div>Reads and writes sequenced<br />capture/lifecycle rows and<br />migration metadata in</div><div style='font-size: 70%'>[IndexedDB]</div>" .->22
    16-. "<div>Persists sanitized aggregate<br />status in</div><div style='font-size: 70%'>[chrome.storage.local]</div>" .->22
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
