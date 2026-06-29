# System Context

> Generated Markdown wrapper for C4 view `SystemContext`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![System Context](../dot-rendered/structurizr-SystemContext.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["System Context View: Browser Memory Daemon"]
    style diagram fill:#ffffff,stroke:#ffffff

    1["<div style='font-weight: bold'>Operator</div><div style='font-size: 70%; margin-top: 0px'>[Person]</div><div style='font-size: 80%; margin-top:10px'>Sole local operator who<br />browses with Windows Chrome<br />and searches, reviews, and<br />deletes local browser-memory<br />records.</div>"]
    style 1 fill:#08427b,stroke:#052e56,color:#ffffff
    2["<div style='font-weight: bold'>Windows Chrome</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>The Windows Chrome runtime<br />that loads web pages, hosts<br />the MV3 extension, runs the<br />local UI in a tab, and<br />exposes Chrome extension<br />APIs.</div>"]
    style 2 fill:#999999,stroke:#6b6b6b,color:#ffffff
    3["<div style='font-weight: bold'>Web Sites and Media Origins</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>External web pages,<br />image/video URLs, and media<br />CDNs that Chrome loads or<br />that sidecars fetch as<br />page-related media.</div>"]
    style 3 fill:#999999,stroke:#6b6b6b,color:#ffffff
    4["<div style='font-weight: bold'>Browser Memory Daemon</div><div style='font-size: 70%; margin-top: 0px'>[Software System]</div><div style='font-size: 80%; margin-top:10px'>Local-first personal recall<br />system that captures Windows<br />Chrome page text and media<br />references, stores them in<br />WSL, and exposes exact<br />search, timeline, detail,<br />deletion, diagnostics, and<br />media cache operations.</div>"]
    style 4 fill:#1168bd,stroke:#0b4884,color:#ffffff

    1-. "<div>Browses web pages with</div><div style='font-size: 70%'></div>" .->2
    1-. "<div>Searches, reviews, and<br />deletes local browser memory<br />through</div><div style='font-size: 70%'></div>" .->4
    2-. "<div>Loads pages and media from</div><div style='font-size: 70%'>[HTTPS]</div>" .->3
    4-. "<div>Runs its MV3 extension inside<br />and uses APIs from</div><div style='font-size: 70%'></div>" .->2
    4-. "<div>Captures page refs and<br />fetches browser-side or<br />public media from</div><div style='font-size: 70%'>[Chrome DOM/fetch; WSL HTTP(S), data URLs; no Chrome cookies in WSL]</div>" .->3

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-SystemContext.mmd`](../structurizr-SystemContext.mmd) |
| Mermaid SVG | [`structurizr-SystemContext.svg`](../structurizr-SystemContext.svg) |
| Mermaid PNG | [`structurizr-SystemContext.png`](../structurizr-SystemContext.png) |
| DOT source | [`structurizr-SystemContext.dot`](../dot/structurizr-SystemContext.dot) |
| Graphviz SVG | [`structurizr-SystemContext.svg`](../dot-rendered/structurizr-SystemContext.svg) |
| Graphviz PNG | [`structurizr-SystemContext.png`](../dot-rendered/structurizr-SystemContext.png) |
