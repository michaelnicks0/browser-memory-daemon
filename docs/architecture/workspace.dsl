workspace "Browser Memory Daemon" "Current-state C4 architecture for the local-first Windows Chrome to WSL browser recall system; planned target requirements remain in requirements/catalog.toml until implemented." {
    model {
        operator = person "Operator" "Sole local operator who browses with Windows Chrome and searches, reviews, and deletes local browser-memory records."

        windowsChrome = softwareSystem "Windows Chrome" "The Windows Chrome runtime that loads web pages, hosts the MV3 extension, runs the local UI in a tab, and exposes Chrome extension APIs." {
            tags "External"
        }

        webSites = softwareSystem "Web Sites and Media Origins" "External web pages, image/video URLs, and media CDNs that Chrome loads or that sidecars fetch as page-related media." {
            tags "External"
        }

        passiveObservationConsumer = softwareSystem "Passive X Observation Consumer" "A downstream local integration that reads versioned body-safe observation pages without gaining capture, migration, or mutation authority." {
            tags "External"
        }

        browserMemoryDaemon = softwareSystem "Browser Memory Daemon" "Local-first personal recall system that captures Windows Chrome page text/media and exports versioned body-safe X observations." {
            chromeExtension = container "Chrome MV3 Extension" "Captures visible page text, media references, tab lifecycle events, and browser-side media bytes from Windows Chrome; queues work durably and posts to the WSL daemon." "JavaScript, Chrome Manifest V3" {
                manifestEnvelope = component "Manifest and Permission Envelope" "Declares MV3 permissions, host permissions, service worker, popup, and options entrypoints." "manifest.json" "Current"
                extractor = component "Extractor" "Traverses rendered light-DOM text with computed-style and ancestor visibility checks, discovers image/video references, and applies the selected policy mode." "JavaScript" "Current"
                contentScript = component "Content Script" "Schedules initial, delayed, reinjected, and SPA captures; computes full deterministic SHA-256 capture digests; tracks scroll; and sends capture and inline blob upload messages to the service worker." "JavaScript content script" "Current"
                serviceWorker = component "Service Worker" "Composes extension modules and registers MV3 message, tab, window, debugger, alarm, startup, and installation listeners." "JavaScript MV3 service worker" "Current"
                configStore = component "Extension Config Store" "Owns typed configuration defaults/migration plus durable visit and minimal CDP capture-context maps." "JavaScript + chrome.storage.local" "Current"
                visitTracker = component "Visit Tracker" "Owns tab/navigation identity, active-segment lifecycle state, deterministic lifecycle event identity, and capture decoration." "JavaScript" "Current"
                injectionController = component "Injection Controller" "Reconstructs active-tab injection after worker restart and idempotently injects the complete ordered content-script set." "JavaScript + chrome.scripting" "Current"
                captureBridge = component "Capture and Lifecycle Bridge" "Owns daemon delivery, transactional outbox import/admission/drain/checkpoint/retry, legacy fallback, media compensation, and queue status." "JavaScript" "Current"
                mediaBridge = component "Credentialed Media Bridge" "Owns browser credentialed fetch, inline/CDP blob upload, specialized media queue drain/retry, and terminal cleanup." "JavaScript" "Current"
                extensionTelemetry = component "Extension Telemetry" "Persists aggregate bridge/queue/CDP status after recursively removing captured fields and redacting URL-shaped errors." "JavaScript + chrome.storage.local" "Current"
                captureLifecycleOutbox = component "Capture and Lifecycle Outbox" "Persists capture and lifecycle messages as independently sequenced IndexedDB rows with atomic enqueue/claim/checkpoint/ack/retry, stale-claim recovery, legacy queue import, item admission limits, and serialized-byte accounting." "JavaScript + IndexedDB" "Current"
                browserMediaQueue = component "Browser Media Queue Adapter" "Persists media tasks and fetched blobs in versioned IndexedDB with atomic batch/blob transitions, count/byte quotas, stale-processing recovery, and bounded terminal quarantine cleanup." "JavaScript + IndexedDB" "Current"
                cdpRecorder = component "CDP Recorder" "Classifies configured X/Twitter video.twimg.com HLS manifests and media segments before they become opaque blob player URLs." "Chrome DevTools Protocol" "Current"
                cdpSession = component "CDP Session Controller" "Restores minimal capture provenance, reconciles debugger attachments, correlates Network events, retrieves bounded bodies, and dispatches media across MV3 worker restarts." "JavaScript + chrome.debugger" "Current"
                popupOptions = component "Popup and Options UI" "Lets the operator view status, pause/resume capture, select policy mode, and trigger local controls from the extension." "HTML/JavaScript" "Current"
            }

            extensionBrowserStorage = container "Extension Browser Storage" "Browser-side IndexedDB storage for transactional capture/lifecycle outbox rows plus specialized durable media tasks/blobs; chrome.storage.local retains typed configuration, lifecycle tab state, minimal CDP capture context, aggregate telemetry, and one-version queue fallback only." "chrome.storage.local + IndexedDB" {
                tags "Data Store"
            }

            wslLoopbackDaemon = container "WSL Loopback HTTP Daemon" "Authenticated loopback API for capture, read/admin/media operations, and query-only bmd.x-observations v1 export." "Python 3.11, ThreadingHTTPServer" {
                httpRouter = component "HTTP Request Router" "Adapts BaseHTTPRequestHandler requests through immutable method/path descriptors with static precedence; owns auth, parsing, compatible status/error responses, request IDs, common security headers, redaction-safe telemetry, bounded response streaming, disconnect cleanup, CORS, and finite UI assets." "Python http.server + route descriptors" "Current"
                applicationUseCases = component "Application Use Cases" "Provides request-independent capture, lifecycle, read, forget, policy, doctor, and media use cases; owns database-ready checks, transaction/audit boundaries, asynchronous media kickoff, and upload/download resource leases without importing HTTP request or response types." "Python" "Current"
                migrationKernel = component "Database Migration Kernel" "Validates exact ledgers/fingerprints and applies transactional steps through version 14, including immutable observation ingest sequences." "Python + sqlite3" "Current"
                policyEngine = component "Policy Engine" "Evaluates all/recall/balanced/strict capture mode decisions and redacts URL/title/body text outside all mode." "Python" "Current"
                policyStore = component "Policy Store" "Persists and evaluates explicit local block-domain and URL-prefix rules for every policy mode." "Python + SQLite" "Current"
                ingestPipeline = component "Ingest Pipeline" "Normalizes observed URLs, computes document/snapshot IDs, atomically stores complete cleaned text plus visits/observations/snapshots/chunks/FTS rows, records non-authoritative URL claims, and links media references without touching blob storage." "Python + sqlite3" "Current"
                lifecyclePipeline = component "Lifecycle Pipeline" "Stores claimed/resolved tab lifecycle identity, reconciles delayed captures, validates active intervals, and derives visit dwell from interval unions." "Python + sqlite3" "Current"
                mediaManager = component "Media Artifact Manager" "Provides the compatibility API, records media references, streams bounded blob uploads, and delegates guarded public transport without coupling text ingest to media availability." "Python + sqlite3 + filesystem" "Current"
                mediaStateModel = component "Media State Model" "Owns caller-visible and internal artifact/task status taxonomies, fetch-error classification, and explicit ordinary versus force-reset transition matrices." "Python" "Current"
                mediaTaskRepository = component "Media Task Repository" "Creates deterministic tasks, preserves terminal state, atomically leases due work, recovers stale leases, and applies bounded retry/backoff outcomes independently from media transport." "Python + sqlite3" "Current"
                mediaArtifactStore = component "Media Artifact Store" "Owns artifact rows, transactional cross-process cache reservations, unique streamed publication, failed-write compensation, contained reads, cache admission, oldest-first eviction, purge/rehydration, and lifecycle registration/tombstones." "Python + sqlite3 + BlobStore" "Current"
                mediaTransportCoordinator = component "Media Transport Coordinator" "Classifies direct versus HLS responses, applies the aggregate HLS request budget from the first network open, enforces playlist sniffing and byte caps, and coordinates bounded streamed assembly." "Python" "Current"
                guardedMediaFetch = component "Guarded Media Fetch" "Owns streamed HTTP/data transport, public-address validation, redirect revalidation, no-referrer requests, response-byte limits, process request/byte leases, and shared deadlines." "Python stdlib urllib + socket" "Current"
                mediaHlsTransport = component "Bounded HLS Transport" "Parses bounded playlists, selects variants, expands init maps/segments through the guarded fetch boundary, and streams assembly within aggregate byte/depth/request/deadline limits." "Python" "Current"
                mediaResourceBudget = component "Media Process Resource Budget" "Bounds active media requests and in-flight bytes across threads within one daemon or worker process; exposes aggregate counters and releases leases on failure or cancellation." "Python threading.Condition" "Current"
                blobStore = component "Contained BlobStore" "Prefers root-relative locators with contained legacy fallback; streams unique stages with size/hash accounting; atomically commits; and contains blob read, stat, and delete operations." "Python filesystem boundary" "Current"
                storageReconciler = component "Blob Lifecycle and Storage Reconciler" "Persists committed/tombstoned/missing/deleted/blocked/failed blob state; serializes deletion processors; retries tombstones; and dry-run detects missing refs, in-root orphans, and stale stages." "Python + sqlite3 + filesystem" "Current"
                searchReadModel = component "Search and Read Model" "Provides exact FTS search plus SQLite-authoritative text detail and observation-first recent/timeline/document/snapshot/media views with explicit legacy fallbacks." "Python + SQLite FTS5" "Current"
                xObservationHttpExport = component "HTTP X Observation Export Adapter" "Serves authenticated cursor pages through the shared query-only export core without application readiness, migrations, or audit writes." "Python + sqlite3" "Current"
                forgetPipeline = component "Forget Pipeline" "Plans literal policy-aware URL/domain scope with non-mutating cross-authority counts and a selected-record guard; bounded execution commits relational deletion, minimized receipt, and blob tombstones, then reports complete only after required bytes converge." "Python + sqlite3" "Current"
                opsDoctor = component "Ops Doctor and Audit" "Reports health, DB integrity, FTS consistency, blob lifecycle/pending deletion state, runtime paths, storage counts, media queue status, and writes metadata-only audit events to SQLite." "Python + sqlite3" "Current"
            }

            mediaWorker = container "WSL Media Worker" "Long-running systemd user worker that loads storage/media modules in-process, first drains one bounded spool-recovery batch when the guarded final root is ready, then leases daemon-public media fetch tasks without calling the HTTP daemon." "Python 3.11 CLI loop" {
                mediaWorkerLoop = component "Media Worker Loop" "Orders one bounded automatic spool-recovery pass, bounded current-state reconciliation, and one bounded public-media task pass; records redaction-safe outcomes." "Python" "Current"
                automaticSpoolRecovery = component "Automatic Spool Recovery" "Checks guarded-root readiness, streams and hash-verifies destination bytes, commits the SQLite tier switch and deletion intent, then removes the local source." "Python + sqlite3 + filesystem" "Current"
                currentMediaReconciliation = component "Current-State Media Reconciliation" "Closes bounded stale stored work and reconciles current CDP/blob coverage through in-process repository functions before due-task leasing." "Python + sqlite3" "Current"
                publicMediaTaskRunner = component "Public Media Task Runner" "Leases due daemon-public tasks, runs guarded direct/HLS fetch without Chrome cookies, applies process budgets, and records terminal or retry state." "Python + sqlite3" "Current"
            }

            localWebUi = container "Local Web UI" "Static browser UI for exact search, recent/timeline views, document/snapshot detail, media artifact opening, policy rules, doctor, and forget-domain operations." "HTML/CSS/JavaScript served by daemon"

            cli = container "CLI" "Command-line interface for serving/admin operations, direct storage/health workflows, and standalone mutation-free X observation export." "Python argparse" {
                xObservationCliExport = component "CLI X Observation Export Adapter" "Opens the existing database directly through the shared query-only export core without daemon readiness, migrations, token requirements, or audit writes." "Python + sqlite3" "Current"
                dailyDriverHealth = component "Daily-Driver Health" "Scores daemon/worker readiness, database and spool state, guarded-root identity/headroom, systemd restart/journal budgets, protected token/env/unit files, and Windows extension-copy consistency without exposing secrets." "Python + systemd/Windows artifact inspection" "Current"
                mediaOpsCli = component "Media Cache Requeue Operator" "Previews or executes explicitly scoped dry-run-first budget requeue through in-process media repository functions." "Python + sqlite3" "Current"
                storageReconcileCli = component "Storage Reconcile Operator" "Previews or executes bounded contained convergence across durable tombstones, missing references, in-root orphans, and stale stages." "Python + sqlite3 + filesystem" "Current"
                backupRestore = component "Backup and Restore Operator" "Creates dry-run-first SQLite online backup bundles with redaction-safe SHA-256 manifests and verifies them into absent runtime roots; optionally carries referenced derivatives and excludes API token/config, Chrome profile/extension copy, media cache, and spool." "Python sqlite3 + filesystem" "Current"
            }

            sqliteDatabase = container "SQLite + FTS5 Database" "Durable text/metadata authority including migration ledger, capture observations, and immutable observation ingest sequences." "SQLite with FTS5" {
                tags "Database", "Data Store"
            }

            cleanTextBlobStore = container "Local Derivative Store" "Reconstructible compatibility evidence such as pre-version-9 clean-text sidecars; new captures create no text sidecars." "WSL local filesystem" {
                tags "Data Store"
            }

            mediaBlobCache = container "Guarded Media Blob Cache" "Bounded disposable image/video/audio bytes under the configured media root; explicit external roots require mount and identity-marker proof before access." "WSL-visible local or NAS-mounted filesystem" {
                tags "Data Store"
            }

            mediaSpool = container "Bounded Local Media Spool" "Opt-in durable outage buffer beneath the local WSL data root; admission counts committed files and distinct in-flight SQLite reservations, and drain verifies bytes before tier transition/source cleanup." "WSL local filesystem" {
                tags "Data Store"
            }

            localBackupBundles = container "Local Backup Bundles" "Operator-selected local directories containing an online SQLite snapshot, redaction-safe hash manifest, and optional referenced derivatives; media, spool, and secrets excluded by default." "Local filesystem" {
                tags "Data Store"
            }

            restoredRuntimeRoot = container "Restored Runtime Root" "An explicit absent destination that is privately staged, manifest/schema/semantic verified, and atomically published with restored SQLite authority and optional referenced derivatives only." "Local filesystem" {
                tags "Data Store"
            }

        }

        operator -> windowsChrome "Browses web pages with"
        operator -> browserMemoryDaemon "Searches, reviews, and deletes local browser memory through"
        operator -> cli "Runs local health, export, storage, backup, and restore workflows through"
        windowsChrome -> webSites "Loads pages and media from" "HTTPS"
        passiveObservationConsumer -> wslLoopbackDaemon "Reads authenticated versioned body-safe observation pages from" "HTTP/JSON"
        browserMemoryDaemon -> windowsChrome "Runs its MV3 extension inside and uses APIs from"
        browserMemoryDaemon -> webSites "Captures page refs and fetches browser-side or public media from" "Chrome DOM/fetch; WSL HTTP(S), data URLs; no Chrome cookies in WSL"

        chromeExtension -> windowsChrome "Uses tab, scripting, storage, alarms, debugger, and runtime APIs from" "Chrome extension APIs"
        chromeExtension -> webSites "Extracts DOM refs and fetches queued credentialed media from" "DOM; fetch(credentials: include)"
        chromeExtension -> extensionBrowserStorage "Persists configuration, lifecycle tab state, aggregate telemetry, capture/lifecycle outbox rows, media tasks, and blobs in" "chrome.storage.local + IndexedDB"
        chromeExtension -> wslLoopbackDaemon "Posts /capture, /visit-events, media metadata, and raw blob uploads to" "Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765"

        localWebUi -> wslLoopbackDaemon "Calls authenticated read, admin, media, and forget APIs on" "HTTP/JSON"
        cli -> wslLoopbackDaemon "Calls health, read, admin, capture-fixture, and forget APIs on" "HTTP/JSON"
        cli -> sqliteDatabase "Runs direct migration, export, media, storage, health, backup, and restore workflows against" "sqlite3"
        cli -> mediaBlobCache "Purges and rehydrates media blobs through" "Filesystem"
        cli -> mediaSpool "Reports and drains bounded outage bytes through" "Filesystem"
        cli -> localBackupBundles "Previews, creates, verifies, and restores text-first bundles through" "Filesystem"
        cli -> passiveObservationConsumer "Emits versioned body-safe observation pages for" "JSON stdout"

        wslLoopbackDaemon -> sqliteDatabase "Reads and writes metadata, FTS, tasks, audit, and receipts in" "sqlite3"
        wslLoopbackDaemon -> cleanTextBlobStore "Reads or deletes legacy text sidecars when required" "Filesystem"
        wslLoopbackDaemon -> mediaBlobCache "Stores, serves, purges, and rehydrates media blobs in" "Filesystem"
        wslLoopbackDaemon -> mediaSpool "Stores and serves media during guarded-root outages in" "Filesystem"
        mediaWorker -> sqliteDatabase "Leases and updates media tasks in" "sqlite3"
        mediaWorker -> webSites "Fetches public media and HLS from" "HTTP(S), data URLs"
        mediaWorker -> mediaBlobCache "Writes fetched media blobs to" "Filesystem"
        mediaWorker -> mediaSpool "Writes fetched media during guarded-root outages to" "Filesystem"

        mediaWorkerLoop -> automaticSpoolRecovery "Runs one bounded recovery batch before new fetch work through"
        mediaWorkerLoop -> currentMediaReconciliation "Runs bounded current-state cleanup before due-task leasing through"
        mediaWorkerLoop -> publicMediaTaskRunner "Runs one bounded due-task batch through"
        automaticSpoolRecovery -> sqliteDatabase "Commits tier transitions and durable deletion intent in" "sqlite3"
        automaticSpoolRecovery -> mediaSpool "Reads and removes authoritative local outage bytes from" "Filesystem"
        automaticSpoolRecovery -> mediaBlobCache "Streams and verifies recovered destination bytes in" "Filesystem"
        publicMediaTaskRunner -> sqliteDatabase "Leases tasks and records artifact outcomes in" "sqlite3"
        publicMediaTaskRunner -> webSites "Fetches guarded direct/HLS media from" "HTTP(S), data URLs"
        publicMediaTaskRunner -> mediaBlobCache "Publishes admitted final bytes in" "Filesystem"
        publicMediaTaskRunner -> mediaSpool "Publishes admitted outage bytes in" "Filesystem"
        currentMediaReconciliation -> sqliteDatabase "Reads and advances current artifact/task state in" "sqlite3"
        mediaOpsCli -> sqliteDatabase "Reads and updates explicitly scoped media artifact/task state in" "sqlite3"

        contentScript -> extractor "Builds capture payloads with"
        contentScript -> serviceWorker "Sends captures and inline blobs to" "chrome.runtime.sendMessage"
        serviceWorker -> configStore "Reads typed settings and durable restart state through"
        serviceWorker -> visitTracker "Delegates navigation identity and lifecycle accounting to"
        serviceWorker -> injectionController "Delegates idempotent active-tab reconstruction to"
        configStore -> extensionBrowserStorage "Reads and writes typed settings and restart state in" "chrome.storage.local"
        visitTracker -> configStore "Persists tab/navigation lifecycle state through"
        injectionController -> windowsChrome "Injects the ordered extractor/digest/content-script set into" "chrome.scripting"
        serviceWorker -> captureBridge "Delegates capture/lifecycle delivery and durable drains to"
        serviceWorker -> mediaBridge "Delegates credentialed media delivery and durable drains to"
        serviceWorker -> extensionTelemetry "Creates the redaction-safe telemetry boundary through"
        captureBridge -> captureLifecycleOutbox "Enqueues, drains, checkpoints, retries, and recovers capture/lifecycle work through"
        captureBridge -> extensionBrowserStorage "Imports and preserves the one-version queue fallback in" "chrome.storage.local"
        captureBridge -> mediaBridge "Dispatches post-capture media compensation through"
        captureBridge -> wslLoopbackDaemon "Delivers /capture and /visit-events to" "Bearer HTTP/JSON"
        captureBridge -> extensionTelemetry "Records aggregate outbox status through"
        captureLifecycleOutbox -> extensionBrowserStorage "Reads and writes sequenced capture/lifecycle rows and migration metadata in" "IndexedDB"
        mediaBridge -> browserMediaQueue "Persists and drains media work through"
        mediaBridge -> wslLoopbackDaemon "Delivers media metadata and raw blobs to" "Bearer HTTP/JSON; raw HTTP PUT"
        mediaBridge -> webSites "Fetches credentialed media from" "fetch(credentials: include)"
        mediaBridge -> extensionTelemetry "Records aggregate media status through"
        browserMediaQueue -> extensionBrowserStorage "Reads and writes media tasks/blobs in" "IndexedDB"
        extensionTelemetry -> extensionBrowserStorage "Persists sanitized aggregate status in" "chrome.storage.local"
        serviceWorker -> cdpSession "Delegates debugger attachment, event correlation, and restart reconciliation to"
        cdpSession -> configStore "Persists minimal per-tab capture context through"
        cdpSession -> cdpRecorder "Uses configured media-response classification from"
        cdpSession -> mediaBridge "Dispatches bounded CDP media rows and bodies through"
        cdpSession -> extensionTelemetry "Records sanitized debugger status through"
        cdpRecorder -> windowsChrome "Classifies Network events received through" "chrome.debugger/CDP"
        popupOptions -> serviceWorker "Updates pause, policy, token, and controls through" "chrome.storage.local, runtime messages"
        popupOptions -> wslLoopbackDaemon "Checks health and triggers forget/policy actions on" "HTTP/JSON"

        httpRouter -> applicationUseCases "Invokes explicit request-independent use cases through"
        httpRouter -> mediaResourceBudget "Leases bounded JSON media request admission through"
        applicationUseCases -> policyEngine "Gets capture decisions from"
        applicationUseCases -> migrationKernel "Requires compatible initialized schema through"
        applicationUseCases -> policyStore "Manages policy rules through"
        applicationUseCases -> ingestPipeline "Commits accepted captures through"
        applicationUseCases -> lifecyclePipeline "Records lifecycle events through"
        applicationUseCases -> mediaManager "Coordinates media requests through"
        applicationUseCases -> mediaResourceBudget "Leases bounded media upload and response capacity through"
        applicationUseCases -> searchReadModel "Executes read requests through"
        httpRouter -> xObservationHttpExport "Serves authenticated GET /exports/x-observations through"
        applicationUseCases -> forgetPipeline "Executes forget requests through"
        applicationUseCases -> opsDoctor "Executes health and audit work through"
        policyEngine -> policyStore "Combines static mode with rules from"
        ingestPipeline -> sqliteDatabase "Atomically writes complete cleaned text, capture rows, and FTS to" "sqlite3"
        ingestPipeline -> mediaManager "Records media refs through"
        lifecyclePipeline -> sqliteDatabase "Writes lifecycle identity and interval-union dwell to" "sqlite3"
        mediaManager -> mediaStateModel "Classifies artifact outcomes and transition intent through"
        mediaManager -> mediaTaskRepository "Creates and claims durable media work through"
        mediaManager -> mediaArtifactStore "Publishes, resolves, purges, and rehydrates artifacts through"
        mediaManager -> mediaTransportCoordinator "Delegates daemon-public media orchestration to"
        mediaManager -> sqliteDatabase "Updates media artifact rows in" "sqlite3"
        mediaTaskRepository -> mediaStateModel "Validates task status vocabulary and retry classification through"
        mediaTaskRepository -> sqliteDatabase "Creates, leases, and advances media tasks in" "sqlite3"
        mediaArtifactStore -> mediaStateModel "Uses artifact status vocabulary from"
        mediaArtifactStore -> mediaTaskRepository "Marks stored/skipped outcomes and ensures retryable fetch work through"
        mediaArtifactStore -> sqliteDatabase "Reserves cache capacity and advances media artifact rows transactionally in" "sqlite3"
        mediaArtifactStore -> blobStore "Stages unique candidates, resolves contained reads, and deletes failed candidates through"
        mediaArtifactStore -> storageReconciler "Registers committed blobs and tombstones replacement, eviction, and purge bytes through"
        mediaTransportCoordinator -> guardedMediaFetch "Streams the initial response and every direct artifact through"
        mediaTransportCoordinator -> mediaHlsTransport "Delegates detected playlists for bounded parsing and assembly to"
        mediaTransportCoordinator -> mediaResourceBudget "Leases aggregate transfer bytes through"
        guardedMediaFetch -> mediaResourceBudget "Leases each active HTTP request through"
        guardedMediaFetch -> webSites "Validates and fetches public media from" "HTTP(S), no Referer or Chrome cookies"
        mediaHlsTransport -> guardedMediaFetch "Fetches every variant, init map, and segment through"
        mediaManager -> blobStore "Checks current artifact presence and resolves contained storage through"
        searchReadModel -> sqliteDatabase "Reads metadata and FTS from" "SQLite FTS5"
        xObservationHttpExport -> sqliteDatabase "Reads validated observation/evidence pages without writes or audit" "SQLite mode=ro + query_only"
        searchReadModel -> blobStore "Reads only legacy text sidecars and checks media files through"
        forgetPipeline -> sqliteDatabase "Atomically deletes rows and records receipts/tombstones in" "sqlite3"
        forgetPipeline -> storageReconciler "Processes post-commit contained blob deletion through"
        storageReconciler -> sqliteDatabase "Reads and advances durable blob lifecycle records in" "sqlite3"
        storageReconciler -> blobStore "Resolves, deletes, and inventories contained bytes through"
        blobStore -> cleanTextBlobStore "Reads, stats, reconciles, and deletes legacy text sidecars in" "Filesystem"
        blobStore -> mediaBlobCache "Stages, commits, reads, stats, and deletes media blobs in" "Filesystem"
        blobStore -> mediaSpool "Stages, commits, reads, stats, and deletes spooled media in" "Filesystem"
        opsDoctor -> sqliteDatabase "Checks integrity and counts in" "sqlite3"
        opsDoctor -> storageReconciler "Reads pending deletion and lifecycle health from"
        opsDoctor -> cleanTextBlobStore "Counts text blob files in" "Filesystem"
        opsDoctor -> mediaBlobCache "Counts media blob files in" "Filesystem"
        opsDoctor -> mediaSpool "Reports filesystem bytes, reservations, and capacity for" "Filesystem"
        migrationKernel -> sqliteDatabase "Validates and advances schema ledger/fingerprint in" "sqlite3 online backup + transactions"
        backupRestore -> sqliteDatabase "Creates and validates online SQLite snapshots from" "sqlite3 backup API"
        backupRestore -> cleanTextBlobStore "Optionally copies referenced contained derivatives from" "Filesystem"
        backupRestore -> localBackupBundles "Atomically publishes and verifies manifests/files in" "Filesystem + SHA-256"
        backupRestore -> restoredRuntimeRoot "Stages, validates, and atomically publishes verified restore output in" "Filesystem + SHA-256"
        xObservationCliExport -> sqliteDatabase "Reads validated observation/evidence pages without writes or audit" "SQLite mode=ro + query_only"
        xObservationCliExport -> passiveObservationConsumer "Emits losslessly cursorable body-safe pages for" "JSON stdout"
        dailyDriverHealth -> wslLoopbackDaemon "Checks authenticated daemon readiness through" "HTTP/JSON"
        dailyDriverHealth -> sqliteDatabase "Checks schema, integrity, counts, and storage headroom for" "sqlite3"
        dailyDriverHealth -> mediaBlobCache "Checks guarded-root identity, readiness, and capacity for" "Filesystem"
        dailyDriverHealth -> mediaSpool "Checks reservations, filesystem accounting, capacity, and latest automatic drain for" "Filesystem"
        storageReconcileCli -> sqliteDatabase "Reads and advances durable blob lifecycle records in" "sqlite3"
        storageReconcileCli -> cleanTextBlobStore "Inventories and converges contained legacy derivatives in" "Filesystem"
        storageReconcileCli -> mediaBlobCache "Inventories and converges contained final media in" "Filesystem"
        storageReconcileCli -> mediaSpool "Inventories and converges contained outage bytes in" "Filesystem"

        dailyDriver = deploymentEnvironment "Daily-driver local" {
            workstation = deploymentNode "Local workstation" "Windows workstation running Windows Chrome and WSL2." "Windows + WSL2" {
                windowsProfile = deploymentNode "Windows user profile" "Windows-local browser-memory-daemon artifacts and Chrome runtime." "Windows profile" {
                    windowsChromeNode = deploymentNode "Windows Chrome daily-driver profile" "Manual Load unpacked or Reload hosts the extension and local UI tab." "Google Chrome MV3" {
                        containerInstance chromeExtension
                        containerInstance extensionBrowserStorage
                        containerInstance localWebUi
                    }
                    extensionCopy = infrastructureNode "Windows unpacked extension copy" "Validated adjacent-stage artifact atomically swapped under %LOCALAPPDATA%\\browser-memory-daemon\\extension; prior bytes remain rollback authority until readiness passes." "Windows filesystem"
                }
                wslNode = deploymentNode "WSL2 Ubuntu" "WSL-owned services, config, and durable data paths." "Ubuntu + systemd --user" {
                    systemdUser = deploymentNode "systemd --user services" "Staged units installed by scripts/install-daily-driver.sh; daemon readiness precedes worker restart, failed readiness restores prior units/service state, and BMD has no hard dependency on the external media mount." "systemd --user" {
                        containerInstance wslLoopbackDaemon
                        containerInstance mediaWorker
                    }
                    wslCliNode = deploymentNode "WSL shell" "Operator shell for direct CLI workflows, including daily-driver health, query-only export, storage convergence, backup, and restore." "Bash + Python" {
                        containerInstance cli
                    }
                    xdgData = deploymentNode "WSL XDG runtime data paths" "Durable DB/config/state under ~/.config, ~/.local/share, and ~/.local/state, outside the repo." "WSL filesystem" {
                        containerInstance sqliteDatabase
                        containerInstance cleanTextBlobStore
                        containerInstance mediaSpool
                        tokenFile = infrastructureNode "Protected token/env files" "~/.config/browser-memory-daemon/token and env supply the daemon token and policy mode." "Filesystem, chmod 600/700"

                    }
                    nasBlobRoot = deploymentNode "WSL-mounted guarded media root" "Configured BMD_MEDIA_ROOT mount for disposable media with expected identity marker." "NAS mount of TrueNAS ZFS dataset" {
                        containerInstance mediaBlobCache
                    }
                }
            }
        }
    }

    views {
        systemContext browserMemoryDaemon "SystemContext" {
            include *
            autoLayout lr
        }

        container browserMemoryDaemon "CaptureContainers" {
            include windowsChrome
            include chromeExtension
            include extensionBrowserStorage
            include wslLoopbackDaemon
            include sqliteDatabase
            include cleanTextBlobStore
            autoLayout tb
        }

        container browserMemoryDaemon "BrowserMediaContainers" {
            include webSites
            include chromeExtension
            include extensionBrowserStorage
            include wslLoopbackDaemon
            include sqliteDatabase
            include mediaBlobCache
            include mediaSpool
            autoLayout tb
        }

        container browserMemoryDaemon "DaemonMediaWorkerContainers" {
            include webSites
            include mediaWorker
            include sqliteDatabase
            include mediaBlobCache
            include mediaSpool
            autoLayout lr
        }

        component mediaWorker "MediaWorkerComponents" {
            include mediaWorkerLoop
            include automaticSpoolRecovery
            include currentMediaReconciliation
            include publicMediaTaskRunner
            include sqliteDatabase
            include mediaBlobCache
            include mediaSpool
            include webSites
            autoLayout lr
        }

        container browserMemoryDaemon "OpsContainers" {
            include localWebUi
            include cli
            include wslLoopbackDaemon
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            include mediaSpool
            autoLayout lr
        }

        component chromeExtension "ExtensionCaptureComponents" {
            include manifestEnvelope
            include extractor
            include contentScript
            include serviceWorker
            include configStore
            include visitTracker
            include injectionController
            include captureBridge
            include mediaBridge
            include extensionTelemetry
            include captureLifecycleOutbox
            include cdpSession
            include popupOptions
            include extensionBrowserStorage
            include wslLoopbackDaemon
            include windowsChrome
            autoLayout tb
        }

        component chromeExtension "ExtensionOutboxComponents" {
            include contentScript
            include serviceWorker
            include configStore
            include captureBridge
            include extensionTelemetry
            include captureLifecycleOutbox
            include extensionBrowserStorage
            include wslLoopbackDaemon
            include windowsChrome
            autoLayout lr
        }

        component chromeExtension "ExtensionMediaComponents" {
            include serviceWorker
            include configStore
            include captureBridge
            include mediaBridge
            include extensionTelemetry
            include browserMediaQueue
            include cdpRecorder
            include cdpSession
            include extensionBrowserStorage
            include wslLoopbackDaemon
            include windowsChrome
            autoLayout tb
        }

        component wslLoopbackDaemon "DaemonPolicyComponents" {
            include httpRouter
            include applicationUseCases
            include policyEngine
            include policyStore
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonIngestComponents" {
            include httpRouter
            include applicationUseCases
            include ingestPipeline
            include sqliteDatabase
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonLifecycleComponents" {
            include httpRouter
            include applicationUseCases
            include lifecyclePipeline
            include sqliteDatabase
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonMediaComponents" {
            include httpRouter
            include applicationUseCases
            include mediaManager
            include mediaStateModel
            include mediaTaskRepository
            include mediaArtifactStore
            include mediaTransportCoordinator
            include guardedMediaFetch
            include mediaHlsTransport
            include mediaResourceBudget
            include storageReconciler
            include blobStore
            include sqliteDatabase
            include mediaBlobCache
            include mediaSpool
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonMediaTransportComponents" {
            include mediaManager
            include mediaTransportCoordinator
            include guardedMediaFetch
            include mediaHlsTransport
            include mediaArtifactStore
            include mediaResourceBudget
            include webSites
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonMediaResourceComponents" {
            include httpRouter
            include applicationUseCases
            include mediaManager
            include mediaTaskRepository
            include mediaArtifactStore
            include mediaTransportCoordinator
            include guardedMediaFetch
            include mediaHlsTransport
            include mediaResourceBudget
            include blobStore
            include sqliteDatabase
            autoLayout lr
        }

        component cli "CliMediaOpsComponents" {
            include mediaOpsCli
            include sqliteDatabase
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonReadComponents" {
            include httpRouter
            include applicationUseCases
            include searchReadModel
            include xObservationHttpExport
            include blobStore
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            include mediaSpool
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonForgetComponents" {
            include httpRouter
            include applicationUseCases
            include forgetPipeline
            include storageReconciler
            include blobStore
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            include mediaSpool
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonDoctorComponents" {
            include httpRouter
            include applicationUseCases
            include opsDoctor
            include storageReconciler
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            include mediaSpool
            autoLayout lr
        }

        component cli "CliStorageReconcileComponents" {
            include storageReconcileCli
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            include mediaSpool
            autoLayout lr
        }

        component cli "CliBackupRestoreComponents" {
            include backupRestore
            include sqliteDatabase
            include cleanTextBlobStore
            include localBackupBundles
            include restoredRuntimeRoot
            autoLayout lr
        }

        component cli "CliXObservationExportComponents" {
            include xObservationCliExport
            include sqliteDatabase
            include passiveObservationConsumer
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonMigrationComponents" {
            include httpRouter
            include applicationUseCases
            include migrationKernel
            include sqliteDatabase
            autoLayout lr
        }

        dynamic browserMemoryDaemon "FastCaptureFlow" {
            operator -> windowsChrome "Browses a web page"
            chromeExtension -> windowsChrome "Runs content script and service worker inside active tab"
            chromeExtension -> wslLoopbackDaemon "POSTs /capture with visible text, metadata, and media refs"
            wslLoopbackDaemon -> sqliteDatabase "Atomically stores complete cleaned text, provenance, chunks, FTS, media refs, and tasks"
            wslLoopbackDaemon -> chromeExtension "Returns document/snapshot/artifact IDs before lazy media bytes"
            chromeExtension -> extensionBrowserStorage "Queues browser-side media tasks for later fetch/upload"
            autoLayout lr
        }

        dynamic browserMemoryDaemon "CredentialedMediaSidecarFlow" {
            chromeExtension -> extensionBrowserStorage "Reads due media task"
            chromeExtension -> webSites "Fetches source URL with Chrome cookie envelope"
            chromeExtension -> extensionBrowserStorage "Persists fetched blob until upload succeeds"
            chromeExtension -> wslLoopbackDaemon "PUTs raw blob to /media-artifacts/{id}/blob"
            wslLoopbackDaemon -> mediaBlobCache "Writes blob if MIME and cache gates allow"
            wslLoopbackDaemon -> sqliteDatabase "Updates artifact status=stored, hash, byte size, and task state"
            autoLayout lr
        }

        dynamic browserMemoryDaemon "DaemonPublicMediaWorkerFlow" {
            mediaWorker -> sqliteDatabase "Claims due daemon-public media_fetch_tasks"
            mediaWorker -> webSites "Fetches public media or HLS assets without Chrome cookies"
            mediaWorker -> mediaBlobCache "Writes fetched or assembled blob when gates allow"
            mediaWorker -> sqliteDatabase "Marks task/artifact stored, retrying, skipped, expired, or failed with reason"
            autoLayout lr
        }

        dynamic browserMemoryDaemon "AutomaticSpoolRecoveryFlow" {
            mediaWorker -> mediaSpool "After guarded-root readiness, selects one bounded batch of authoritative spooled bytes"
            mediaWorker -> mediaBlobCache "Streams and atomically commits destination bytes after size and SHA-256 verification"
            mediaWorker -> sqliteDatabase "Commits the storage-tier switch and spool deletion intent"
            mediaWorker -> mediaSpool "Removes the local source only after the tier switch commits"
            autoLayout lr
        }

        dynamic browserMemoryDaemon "DailyDriverHealthFlow" {
            operator -> cli "Runs daily-driver health to inspect protected artifacts plus systemd restart and journal budgets"
            cli -> wslLoopbackDaemon "Checks authenticated daemon readiness over HTTP"
            cli -> sqliteDatabase "Checks schema, integrity, counts, and storage headroom"
            cli -> mediaBlobCache "Checks guarded-root identity, readiness, and capacity"
            cli -> mediaSpool "Checks reservations, filesystem accounting, capacity, and latest automatic drain"
            autoLayout lr
        }

        dynamic browserMemoryDaemon "XObservationExportFlow" {
            passiveObservationConsumer -> wslLoopbackDaemon "Requests one authenticated cursor page over HTTP"
            wslLoopbackDaemon -> sqliteDatabase "Reads through the query-only export core without audit writes"
            operator -> cli "Runs standalone export without daemon readiness or token bootstrap"
            cli -> sqliteDatabase "Opens the existing database mode=ro/query_only"
            cli -> passiveObservationConsumer "Emits the same schema-versioned body-safe page on stdout"
            autoLayout lr
        }

        deployment browserMemoryDaemon "Daily-driver local" "DailyDriverDeployment" {
            include *
            exclude extensionBrowserStorage
            exclude cli
            exclude extensionCopy
            exclude tokenFile

            autoLayout tb
        }

        styles {
            element "Person" {
                shape Person
                background "#08427b"
                color "#ffffff"
            }
            element "Software System" {
                background "#1168bd"
                color "#ffffff"
            }
            element "Container" {
                background "#438dd5"
                color "#ffffff"
            }
            element "Component" {
                background "#85bbf0"
                color "#000000"
            }
            element "External" {
                background "#999999"
                color "#ffffff"
            }
            element "Database" {
                shape Cylinder
                background "#2f95c8"
                color "#ffffff"
            }
            element "Data Store" {
                shape Cylinder
                background "#2f95c8"
                color "#ffffff"
            }
            element "Current" {
                stroke "#1168bd"
                strokeWidth 2
            }
            element "Target" {
                background "#fff3cd"
                color "#4d3b00"
                stroke "#d39e00"
                border Dashed
            }
        }
    }
}
