# Browser Memory Daemon Architecture Model

This directory contains the C4 model-as-code for the Browser Memory Daemon repo.

- Canonical source: [`workspace.dsl`](workspace.dsl)
- Markdown diagram entrypoint: [`diagrams/README.md`](diagrams/README.md)
- Per-view Markdown diagrams: [`diagrams/markdown/`](diagrams/markdown/)
- Lightweight text exports: [`diagrams/*.mmd`](diagrams/) after Mermaid export
- Visual-review exports: [`diagrams/*.png`](diagrams/), [`diagrams/*.svg`](diagrams/), and Graphviz renders under [`diagrams/dot-rendered/`](diagrams/dot-rendered/)
- Existing narrative architecture: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
- Existing Mermaid visual atlas: [`../docs/DIAGRAMS.md`](../docs/DIAGRAMS.md)

## Scope

The model covers the current local daily-driver architecture:

```text
Windows Chrome MV3 extension
  -> WSL loopback HTTP daemon
  -> SQLite + FTS5 + text/media blob stores
  -> local UI / CLI / media worker
```

The system boundary is **Browser Memory Daemon**, including the owned Chrome extension, WSL daemon, WSL media worker, local UI, CLI, database, and blob stores. Windows Chrome and web/media origins are modeled as external systems.

## Views

| View key | C4 level | Purpose |
|---|---|---|
| `SystemContext` | C1 System Context | Operator, Chrome runtime, web/media origins, and the Browser Memory Daemon boundary. |
| `CaptureContainers` | C2 Container | Fast capture/storage path: Chrome, extension, extension browser storage, daemon, SQLite/FTS, and clean-text blob store. |
| `BrowserMediaContainers` | C2 Container | Browser-side media path: extension browser storage, daemon media APIs, SQLite artifact rows, media cache, and web/media origins. |
| `DaemonMediaWorkerContainers` | C2 Container | Daemon-public media worker path: worker, SQLite tasks, media cache, and public web/media origins. |
| `OpsContainers` | C2 Container | Operator surfaces and stores: local UI, CLI, daemon, SQLite/FTS, text blobs, and media cache. |
| `ExtensionCaptureComponents` | C3 Component | MV3 extension capture internals: manifest, extractor, content script, service worker, daemon delivery, and browser queue. |
| `ExtensionMediaComponents` | C3 Component | MV3 extension media internals: service worker, media queue adapter, CDP recorder, Chrome APIs, browser queue, and daemon upload. |
| `DaemonPolicyComponents` | C3 Component | WSL daemon policy internals: router/auth, static policy engine, and persistent block rules. |
| `DaemonIngestComponents` | C3 Component | WSL daemon ingest internals: router, ingest pipeline, SQLite/FTS rows, and text blobs. |
| `DaemonLifecycleComponents` | C3 Component | WSL daemon lifecycle internals: router, lifecycle pipeline, and SQLite dwell/event rows. |
| `DaemonMediaComponents` | C3 Component | WSL daemon media internals: router, media manager, SQLite task/artifact rows, and media cache. |
| `DaemonReadComponents` | C3 Component | WSL daemon read internals: router, search/read model, SQLite/FTS, text blobs, and media cache. |
| `DaemonForgetComponents` | C3 Component | WSL daemon deletion internals: router, forget pipeline, SQLite receipts, text blobs, and media cache. |
| `DaemonDoctorComponents` | C3 Component | WSL daemon diagnostics internals: router, doctor/audit, SQLite checks, and storage counts. |
| `FastCaptureFlow` | Dynamic | Fast text/ref capture path that stores FTS recall before lazy media bytes. |
| `CredentialedMediaSidecarFlow` | Dynamic | Browser-side media fetch/upload path that keeps Chrome cookies inside Chrome. |
| `DaemonPublicMediaWorkerFlow` | Dynamic | Public no-cookie daemon media backfill path. |
| `DailyDriverDeployment` | Deployment | Local workstation daily-driver topology: Windows Chrome, WSL systemd user services, and WSL XDG data paths. |

## Render and validate

Using Structurizr CLI:

```bash
STRUCTURIZR_CLI=${STRUCTURIZR_CLI:-/tmp/structurizr-cli/structurizr.sh}
"$STRUCTURIZR_CLI" validate -workspace architecture/workspace.dsl

# Mermaid text exports plus SVG/PNG renders.
find architecture/diagrams -maxdepth 1 -type f \( -name '*.mmd' -o -name '*.svg' -o -name '*.png' \) -delete
JAVA_TOOL_OPTIONS='-Djava.awt.headless=true' \
  "$STRUCTURIZR_CLI" export -workspace architecture/workspace.dsl -format mermaid -output architecture/diagrams

cat > /tmp/bmd-mermaid-config.json <<'JSON'
{"securityLevel":"loose","htmlLabels":true}
JSON
for f in architecture/diagrams/*.mmd; do
  npx --yes @mermaid-js/mermaid-cli -c /tmp/bmd-mermaid-config.json -i "$f" -o "${f%.mmd}.svg"
  npx --yes @mermaid-js/mermaid-cli -c /tmp/bmd-mermaid-config.json -i "$f" -o "${f%.mmd}.png" -b transparent
done

python3 /home/user/.hermes/skills/software-development/c4-structurizr-architecture/scripts/structurizr-diagrams-to-markdown.py \
  --diagrams-dir architecture/diagrams \
  --workspace architecture/workspace.dsl \
  --title "Browser Memory Daemon Architecture Diagrams"

# Graphviz/DOT exports for stakeholder-readable relationship-label placement.
rm -rf architecture/diagrams/dot architecture/diagrams/dot-rendered
mkdir -p architecture/diagrams/dot architecture/diagrams/dot-rendered
JAVA_TOOL_OPTIONS='-Djava.awt.headless=true' \
  "$STRUCTURIZR_CLI" export -workspace architecture/workspace.dsl -format dot -output architecture/diagrams/dot
for file in architecture/diagrams/dot/*.dot; do
  base=$(basename "$file" .dot)
  dot -Tsvg "$file" -o "architecture/diagrams/dot-rendered/$base.svg"
  dot -Tpng "$file" -o "architecture/diagrams/dot-rendered/$base.png"
done
```

The Mermaid, DOT, SVG, PNG, and Markdown exports are derived artifacts. Refresh them from `workspace.dsl`; do not treat them as the source of truth. Use `diagrams/README.md` and `diagrams/markdown/*.md` as the Markdown-first human reading surface. The `JAVA_TOOL_OPTIONS` setting keeps Structurizr CLI export headless-friendly under WSL. For visual review, prefer `diagrams/dot-rendered/*.svg`/`*.png` when Mermaid label routing is cramped.

## Source grounding

Primary source evidence used for this model:

| Claim | Evidence |
|---|---|
| Windows Chrome is the browser surface and WSL owns durable storage. | `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/daily-driver-deployment.md` |
| Default policy mode is `all`; non-all modes redact/filter. | `README.md`, `docs/security-model.md`, `daemon/src/browser_memory_daemon/policy.py`, `extension/src/extractor.js` |
| Capture transport is extension service worker to authenticated loopback HTTP, using JSON for metadata/capture APIs and raw `PUT` for blob uploads. | `docs/api.md`, `daemon/src/browser_memory_daemon/app.py`, `extension/src/service_worker.js` |
| Fast capture stores documents, visits, snapshots, chunks, FTS rows, and media refs. | `daemon/src/browser_memory_daemon/ingest.py`, `daemon/src/browser_memory_daemon/schema.sql` |
| Extension browser storage keeps capture/visit queues in `chrome.storage.local` and durable media tasks/blobs in IndexedDB. | `extension/src/service_worker.js`, `extension/src/media_queue.js` |
| Credentialed media fetch stays inside Chrome; raw blobs upload to WSL. | `docs/media-artifacts.md`, `extension/src/service_worker.js`, `daemon/src/browser_memory_daemon/media.py` |
| Daemon media worker leases public media tasks and writes blob/status updates. | `daemon/src/browser_memory_daemon/media_worker.py`, `daemon/src/browser_memory_daemon/media.py` |
| Local UI and CLI are operator surfaces; CLI read/admin commands use daemon APIs, while media-worker/cache commands also run direct SQLite/filesystem paths. | `ui/app.js`, `daemon/src/browser_memory_daemon/cli.py`, `docs/daily-driver-deployment.md` |
| Daily-driver deployment uses WSL systemd user services and Windows unpacked extension copy. | `scripts/install-daily-driver.sh`, `docs/daily-driver-deployment.md` |

## Assumptions and TBDs

- Deployment view is limited to the documented **Daily-driver local** Local workstation topology. No separate staging/production topology is modeled.
- Non-runtime deployment artifacts such as the Windows unpacked extension copy, protected token/env files, and audit log are modeled in the DSL but excluded from the rendered deployment view to keep the runtime topology legible.
- Semantic/vector search, MCP/Hermes integration, native messaging transport, encrypted backup/restore, and multi-source importers are explicitly pending and are not modeled as current runtime containers.
- Chrome extension manual Load unpacked/Reload is an operational step, not a runtime container.
- Media blobs are modeled as a bounded disposable cache; text/FTS/media refs remain authoritative.
- Captured page text is untrusted evidence and must not be treated as agent instructions.
