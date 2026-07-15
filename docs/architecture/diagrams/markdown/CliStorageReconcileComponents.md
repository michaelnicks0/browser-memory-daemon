# Cli Storage Reconcile Components

> Generated Markdown wrapper for C4 view `CliStorageReconcileComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Cli Storage Reconcile Components](../dot-rendered/structurizr-CliStorageReconcileComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Browser Memory Daemon - CLI - Components"]
    style diagram fill:#ffffff,stroke:#ffffff

    57[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable text/metadata<br />authority including migration<br />ledger, capture observations,<br />and immutable observation<br />ingest sequences.</div>")]
    style 57 fill:#2f95c8,stroke:#20688c,color:#ffffff
    58[("<div style='font-weight: bold'>Local Derivative Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Reconstructible compatibility<br />evidence such as<br />pre-version-9 clean-text<br />sidecars; new captures create<br />no text sidecars.</div>")]
    style 58 fill:#2f95c8,stroke:#20688c,color:#ffffff
    59[("<div style='font-weight: bold'>Guarded Media Blob Cache</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL-visible local or NAS-mounted filesystem]</div><div style='font-size: 80%; margin-top:10px'>Bounded disposable<br />image/video/audio bytes under<br />the configured media root;<br />explicit external roots<br />require mount and<br />identity-marker proof before<br />access.</div>")]
    style 59 fill:#2f95c8,stroke:#20688c,color:#ffffff
    60[("<div style='font-weight: bold'>Bounded Local Media Spool</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Opt-in durable outage buffer<br />beneath the local WSL data<br />root; admission counts<br />committed files and distinct<br />in-flight SQLite<br />reservations, and drain<br />verifies bytes before tier<br />transition/source cleanup.</div>")]
    style 60 fill:#2f95c8,stroke:#20688c,color:#ffffff

    subgraph 51 ["CLI"]
      style 51 fill:#ffffff,stroke:#2e6295,color:#2e6295

      55["<div style='font-weight: bold'>Storage Reconcile Operator</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python + sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Previews or executes bounded<br />contained convergence across<br />durable tombstones, missing<br />references, in-root orphans,<br />and stale stages.</div>"]
      style 55 fill:#85bbf0,stroke:#1168bd,color:#000000
    end

    55-. "<div>Reads and advances durable<br />blob lifecycle records in</div><div style='font-size: 70%'>[sqlite3]</div>" .->57
    55-. "<div>Inventories and converges<br />contained legacy derivatives<br />in</div><div style='font-size: 70%'>[Filesystem]</div>" .->58
    55-. "<div>Inventories and converges<br />contained final media in</div><div style='font-size: 70%'>[Filesystem]</div>" .->59
    55-. "<div>Inventories and converges<br />contained outage bytes in</div><div style='font-size: 70%'>[Filesystem]</div>" .->60
  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-CliStorageReconcileComponents.mmd`](../structurizr-CliStorageReconcileComponents.mmd) |
| Mermaid SVG | [`structurizr-CliStorageReconcileComponents.svg`](../structurizr-CliStorageReconcileComponents.svg) |
| Mermaid PNG | [`structurizr-CliStorageReconcileComponents.png`](../structurizr-CliStorageReconcileComponents.png) |
| DOT source | [`structurizr-CliStorageReconcileComponents.dot`](../dot/structurizr-CliStorageReconcileComponents.dot) |
| Graphviz SVG | [`structurizr-CliStorageReconcileComponents.svg`](../dot-rendered/structurizr-CliStorageReconcileComponents.svg) |
| Graphviz PNG | [`structurizr-CliStorageReconcileComponents.png`](../dot-rendered/structurizr-CliStorageReconcileComponents.png) |
