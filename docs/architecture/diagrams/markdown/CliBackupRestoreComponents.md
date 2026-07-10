# Cli Backup Restore Components

> Generated Markdown wrapper for C4 view `CliBackupRestoreComponents`. Canonical model: [`workspace.dsl`](../../workspace.dsl).

<!-- Generated from Structurizr exports; refresh from docs/architecture/workspace.dsl. -->

## Diagram

![Cli Backup Restore Components](../dot-rendered/structurizr-CliBackupRestoreComponents.svg)

_Preferred Markdown display: Graphviz SVG. Mermaid source is retained below for text review._

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR
  linkStyle default fill:#ffffff

  subgraph diagram ["Component View: Browser Memory Daemon - CLI"]
    style diagram fill:#ffffff,stroke:#ffffff

    subgraph 4 ["Browser Memory Daemon"]
      style 4 fill:#ffffff,stroke:#0b4884,color:#0b4884

      subgraph 35 ["CLI"]
        style 35 fill:#ffffff,stroke:#2e6295,color:#2e6295

        36["<div style='font-weight: bold'>Backup and Restore Operator</div><div style='font-size: 70%; margin-top: 0px'>[Component: Python sqlite3 + filesystem]</div><div style='font-size: 80%; margin-top:10px'>Creates dry-run-first SQLite<br />online backup bundles with<br />redaction-safe SHA-256<br />manifests and verifies them<br />into absent runtime roots;<br />optionally carries referenced<br />derivatives and excludes<br />media/spool/secrets.</div>"]
        style 36 fill:#85bbf0,stroke:#1168bd,color:#000000
      end

      37[("<div style='font-weight: bold'>SQLite + FTS5 Database</div><div style='font-size: 70%; margin-top: 0px'>[Container: SQLite with FTS5]</div><div style='font-size: 80%; margin-top:10px'>Durable complete<br />cleaned-text, relational, and<br />full-text authority for<br />migration ledger, sources,<br />documents, visits, capture<br />observations, URL claims,<br />visit events, snapshots,<br />chunks, chunks_fts, media<br />provenance/tasks, blob<br />lifecycle records, policy<br />rules, audit events, and<br />deletion receipts.</div>")]
      style 37 fill:#2f95c8,stroke:#20688c,color:#ffffff
      38[("<div style='font-weight: bold'>Local Derivative Store</div><div style='font-size: 70%; margin-top: 0px'>[Container: WSL local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Reconstructible compatibility<br />evidence such as<br />pre-version-9 clean-text<br />sidecars; new captures create<br />no text sidecars.</div>")]
      style 38 fill:#2f95c8,stroke:#20688c,color:#ffffff
      41[("<div style='font-weight: bold'>Local Backup Bundles</div><div style='font-size: 70%; margin-top: 0px'>[Container: Local filesystem]</div><div style='font-size: 80%; margin-top:10px'>Operator-selected local<br />directories containing an<br />online SQLite snapshot,<br />redaction-safe hash manifest,<br />and optional referenced<br />derivatives; media, spool,<br />and secrets excluded by<br />default.</div>")]
      style 41 fill:#2f95c8,stroke:#20688c,color:#ffffff
    end

    36-. "<div>Creates and validates online<br />SQLite snapshots from</div><div style='font-size: 70%'>[sqlite3 backup API]</div>" .->37
    36-. "<div>Optionally copies referenced<br />contained derivatives from</div><div style='font-size: 70%'>[Filesystem]</div>" .->38
    36-. "<div>Atomically publishes and<br />verifies manifests/files in</div><div style='font-size: 70%'>[Filesystem + SHA-256]</div>" .->41

  end
```

</details>

## Derived artifacts

| Artifact | Link |
|---|---|
| Mermaid source | [`structurizr-CliBackupRestoreComponents.mmd`](../structurizr-CliBackupRestoreComponents.mmd) |
| Mermaid SVG | [`structurizr-CliBackupRestoreComponents.svg`](../structurizr-CliBackupRestoreComponents.svg) |
| Mermaid PNG | [`structurizr-CliBackupRestoreComponents.png`](../structurizr-CliBackupRestoreComponents.png) |
| DOT source | [`structurizr-CliBackupRestoreComponents.dot`](../dot/structurizr-CliBackupRestoreComponents.dot) |
| Graphviz SVG | [`structurizr-CliBackupRestoreComponents.svg`](../dot-rendered/structurizr-CliBackupRestoreComponents.svg) |
| Graphviz PNG | [`structurizr-CliBackupRestoreComponents.png`](../dot-rendered/structurizr-CliBackupRestoreComponents.png) |
