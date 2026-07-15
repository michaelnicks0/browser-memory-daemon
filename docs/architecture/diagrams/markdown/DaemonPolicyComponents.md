# Daemon Policy Components

> Generated Markdown wrapper for C4 view `DaemonPolicyComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Daemon Policy Components](../dot-rendered/structurizr-DaemonPolicyComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - WSL Loopback HTTP Daemon - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 22 ["WSL Loopback HTTP Daemon"]
      style 22 fill:#ffffff,stroke:#2e6295,color:#2e6295

      23["<div style='font-weight: bold'>HTTP Request Router</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python http.server + route descriptors]</div><div style='font-size: 80%; margin-top:10px'>Adapts BaseHTTPRequestHandler<br />requests through immutable<br />method/path descriptors with<br />static precedence; owns auth,<br />parsing, compatible<br />status/error responses,<br />request IDs, common security<br />headers, redaction-safe<br />telemetry, bounded response<br />streaming, disconnect<br />cleanup, CORS, and finite UI<br />assets.</div>"]
      style 23 fill:#85bbf0,stroke:#1168bd,color:#000000
      24["<div style='font-weight: bold'>Application Use Cases</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Provides request-independent<br />capture, lifecycle, read,<br />forget, policy, doctor, and<br />media use cases; owns<br />database-ready checks,<br />transaction/audit boundaries,<br />asynchronous media kickoff,<br />and upload/download resource<br />leases without importing HTTP<br />request or response types.</div>"]
      style 24 fill:#85bbf0,stroke:#1168bd,color:#000000
      26["<div style='font-weight: bold'>Policy Engine</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python]</div><div style='font-size: 80%; margin-top:10px'>Evaluates<br />all/recall/balanced/strict<br />capture mode decisions and<br />redacts URL/title/body text<br />outside all mode.</div>"]
      style 26 fill:#85bbf0,stroke:#1168bd,color:#000000
      27["<div style='font-weight: bold'>Policy Store</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + SQLite]</div><div style='font-size: 80%; margin-top:10px'>Persists and evaluates<br />explicit local block-domain<br />and URL-prefix rules for<br />every policy mode.</div>"]
      style 27 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    23-. "<div>Invokes explicit<br />request-independent use cases<br />through</div><div style='font-size: 70%'></div>" .->24
    24-. "<div>Gets capture decisions from</div><div style='font-size: 70%'></div>" .->26
    24-. "<div>Manages policy rules through</div><div style='font-size: 70%'></div>" .->27
    26-. "<div>Combines static mode with<br />rules from</div><div style='font-size: 70%'></div>" .->27
  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-DaemonPolicyComponents.mmd`](../structurizr-DaemonPolicyComponents.mmd) |
| Mermaid SVG | [`structurizr-DaemonPolicyComponents.svg`](../structurizr-DaemonPolicyComponents.svg) |
| Mermaid PNG | [`structurizr-DaemonPolicyComponents.png`](../structurizr-DaemonPolicyComponents.png) |
| DOT source | [`structurizr-DaemonPolicyComponents.dot`](../dot/structurizr-DaemonPolicyComponents.dot) |
| Graphviz SVG | [`structurizr-DaemonPolicyComponents.svg`](../dot-rendered/structurizr-DaemonPolicyComponents.svg) |
| Graphviz PNG | [`structurizr-DaemonPolicyComponents.png`](../dot-rendered/structurizr-DaemonPolicyComponents.png) |
