workspace "Browser Memory Daemon" "Current-state C4 architecture for the local-first Windows Chrome to WSL browser recall system; planned target requirements remain in requirements/catalog.toml until implemented." {
    model {
        operator = person "Operator" "Sole local operator who browses with Windows Chrome and searches, reviews, and deletes local browser-memory records."

        windowsChrome = softwareSystem "Windows Chrome" "The Windows Chrome runtime that loads web pages, hosts the MV3 extension, runs the local UI in a tab, and exposes Chrome extension APIs." {
            tags "External"
        }

        webSites = softwareSystem "Web Sites and Media Origins" "External web pages, image/video URLs, and media CDNs that Chrome loads or that sidecars fetch as page-related media." {
            tags "External"
        }

        browserMemoryDaemon = softwareSystem "Browser Memory Daemon" "Local-first personal recall system that captures Windows Chrome page text and media references, stores them in WSL, and exposes exact search, timeline, detail, deletion, diagnostics, and media cache operations." {
            chromeExtension = container "Chrome MV3 Extension" "Captures visible page text, media references, tab lifecycle events, and browser-side media bytes from Windows Chrome; queues work durably and posts to the WSL daemon." "JavaScript, Chrome Manifest V3" {
                manifestEnvelope = component "Manifest and Permission Envelope" "Declares MV3 permissions, host permissions, service worker, popup, and options entrypoints." "manifest.json" "Current"
                extractor = component "Extractor" "Traverses visible DOM text and discovers image/video references while applying the selected policy mode." "JavaScript" "Current"
                contentScript = component "Content Script" "Schedules initial, delayed, and SPA captures; tracks scroll; sends capture and inline blob upload messages to the service worker." "JavaScript content script" "Current"
                serviceWorker = component "Service Worker" "Owns daemon transport, bearer token use, capture and visit queues, stable observation/navigation identity, lifecycle state, media queue draining, and CDP recorder orchestration." "JavaScript MV3 service worker" "Current"
                browserMediaQueue = component "Browser Media Queue Adapter" "Persists media tasks and fetched blobs in IndexedDB so browser-side media fetch/upload can survive MV3 worker suspension." "JavaScript + IndexedDB" "Current"
                cdpRecorder = component "CDP Recorder" "Uses chrome.debugger on configured X/Twitter tabs to capture video.twimg.com HLS manifests and media segments before they become opaque blob player URLs." "Chrome DevTools Protocol" "Current"
                popupOptions = component "Popup and Options UI" "Lets the operator view status, pause/resume capture, select policy mode, and trigger local controls from the extension." "HTML/JavaScript" "Current"
            }

            extensionBrowserStorage = container "Extension Browser Storage" "Browser-side storage for capture and visit queues in chrome.storage.local plus durable media tasks and fetched blobs in IndexedDB." "chrome.storage.local + IndexedDB" {
                tags "Data Store"
            }

            wslLoopbackDaemon = container "WSL Loopback HTTP Daemon" "Authenticated loopback HTTP API that handles capture, visit events, media artifact upload/fetch/purge, exact search, recent/timeline/detail, policy rules, doctor, forget, and static UI serving." "Python 3.11, ThreadingHTTPServer" {
                httpRouter = component "HTTP Request Router" "Routes loopback API requests, serves UI assets, enforces bearer auth for memory/admin APIs, and applies CORS for allowed origins." "Python http.server" "Current"
                migrationKernel = component "Database Migration Kernel" "Validates exact schema fingerprints, ordered migration names/checksums, and PRAGMA user_version; applies transactional steps, backup-gates destructive changes, and expands capture observations, URL claims, media-observation provenance, and claimed lifecycle identity through version 7." "Python + sqlite3" "Current"
                policyEngine = component "Policy Engine" "Evaluates all/recall/balanced/strict capture mode decisions and redacts URL/title/body text outside all mode." "Python" "Current"
                policyStore = component "Policy Store" "Persists and evaluates explicit local block-domain and URL-prefix rules for every policy mode." "Python + SQLite" "Current"
                ingestPipeline = component "Ingest Pipeline" "Normalizes observed URLs, computes document/snapshot IDs, stores visits/observations/snapshots/chunks/FTS rows, records non-authoritative URL claims, writes clean text blobs, and links media references to observations." "Python + sqlite3" "Current"
                lifecyclePipeline = component "Lifecycle Pipeline" "Stores claimed/resolved tab lifecycle identity, reconciles delayed captures, validates active intervals, and derives visit dwell from interval unions." "Python + sqlite3" "Current"
                mediaManager = component "Media Artifact Manager" "Records media references, validates blob uploads, enforces MIME/size/cache gates, writes blobs atomically, queues public fetch tasks, and purges or rehydrates cache entries." "Python + sqlite3 + filesystem" "Current"
                blobStore = component "Contained BlobStore" "Resolves legacy locators under configured roots; streams unique stages with size/hash accounting; atomically commits; and contains blob read, stat, and delete operations." "Python filesystem boundary" "Current"
                searchReadModel = component "Search and Read Model" "Provides exact FTS search plus observation-first recent/timeline/document/snapshot/media detail views with an explicit ambiguous legacy fallback." "Python + SQLite FTS5" "Current"
                forgetPipeline = component "Forget Pipeline" "Deletes URL/domain-scoped memory rows, FTS entries, clean-text blobs, media blobs, lifecycle rows, and records deletion receipts." "Python + sqlite3" "Current"
                opsDoctor = component "Ops Doctor and Audit" "Reports health, DB integrity, FTS consistency, runtime paths, storage counts, media queue status, and writes metadata-only audit events to SQLite." "Python + sqlite3" "Current"
            }

            mediaWorker = container "WSL Media Worker" "Long-running systemd user worker that leases daemon-public media fetch tasks, fetches public media/HLS without Chrome cookies, classifies terminal states, and updates artifact rows." "Python 3.11 CLI loop"

            localWebUi = container "Local Web UI" "Static browser UI for exact search, recent/timeline views, document/snapshot detail, media artifact opening, policy rules, doctor, and forget-domain operations." "HTML/CSS/JavaScript served by daemon"

            cli = container "CLI" "Command-line interface for serving the daemon, migration check/execute, health/doctor/search/recent/timeline/detail, policy/forget, capture fixtures, media worker, and media cache operations." "Python argparse"

            sqliteDatabase = container "SQLite + FTS5 Database" "Durable relational and full-text store for migration ledger, sources, documents, visits, capture observations, URL claims, visit events, snapshots, chunks, chunks_fts, media artifacts and observation links, media fetch tasks, policy rules, audit events, and deletion receipts." "SQLite with FTS5" {
                tags "Database", "Data Store"
            }

            cleanTextBlobStore = container "Clean Text Blob Store" "Filesystem store for snapshot text blobs under the configured WSL-visible blob root." "WSL or NAS-mounted filesystem" {
                tags "Data Store"
            }

            mediaBlobCache = container "Media Blob Cache" "Bounded and disposable filesystem cache for stored image/video/audio blobs under the configured WSL-visible blob root, with purge/rehydrate semantics that preserve media refs, hashes, status reasons, and provenance when bytes are absent or purged." "WSL or NAS-mounted filesystem" {
                tags "Data Store"
            }

        }

        operator -> windowsChrome "Browses web pages with"
        operator -> browserMemoryDaemon "Searches, reviews, and deletes local browser memory through"
        windowsChrome -> webSites "Loads pages and media from" "HTTPS"
        browserMemoryDaemon -> windowsChrome "Runs its MV3 extension inside and uses APIs from"
        browserMemoryDaemon -> webSites "Captures page refs and fetches browser-side or public media from" "Chrome DOM/fetch; WSL HTTP(S), data URLs; no Chrome cookies in WSL"

        chromeExtension -> windowsChrome "Uses tab, scripting, storage, alarms, debugger, and runtime APIs from" "Chrome extension APIs"
        chromeExtension -> webSites "Extracts DOM refs and fetches queued credentialed media from" "DOM; fetch(credentials: include)"
        chromeExtension -> extensionBrowserStorage "Queues identity-decorated captures, lifecycle events, media tasks, and blobs in" "chrome.storage.local + IndexedDB"
        chromeExtension -> wslLoopbackDaemon "Posts /capture, /visit-events, media metadata, and raw blob uploads to" "Bearer HTTP/JSON; raw HTTP PUT over 127.0.0.1:8765"

        localWebUi -> wslLoopbackDaemon "Calls authenticated read, admin, media, and forget APIs on" "HTTP/JSON"
        cli -> wslLoopbackDaemon "Calls health, read, admin, capture-fixture, and forget APIs on" "HTTP/JSON"
        cli -> sqliteDatabase "Runs migration, media-worker, and media-cache commands against" "sqlite3"
        cli -> mediaBlobCache "Purges and rehydrates media blobs through" "Filesystem"

        wslLoopbackDaemon -> sqliteDatabase "Reads and writes metadata, FTS, tasks, audit, and receipts in" "sqlite3"
        wslLoopbackDaemon -> cleanTextBlobStore "Reads and writes text snapshots in" "Filesystem"
        wslLoopbackDaemon -> mediaBlobCache "Stores, serves, purges, and rehydrates media blobs in" "Filesystem"
        mediaWorker -> sqliteDatabase "Leases and updates media tasks in" "sqlite3"
        mediaWorker -> webSites "Fetches public media and HLS from" "HTTP(S), data URLs"
        mediaWorker -> mediaBlobCache "Writes fetched media blobs to" "Filesystem"

        contentScript -> extractor "Builds capture payloads with"
        contentScript -> serviceWorker "Sends captures and inline blobs to" "chrome.runtime.sendMessage"
        serviceWorker -> extensionBrowserStorage "Queues captures in chrome.storage.local and media tasks/blobs in IndexedDB"
        serviceWorker -> wslLoopbackDaemon "Delivers /capture, /visit-events, media metadata, and raw blobs to" "Bearer HTTP/JSON; raw HTTP PUT"
        serviceWorker -> browserMediaQueue "Persists and drains media work through"
        browserMediaQueue -> extensionBrowserStorage "Reads and writes media tasks/blobs in" "IndexedDB"
        serviceWorker -> cdpRecorder "Detects CDP media candidates with"
        serviceWorker -> webSites "Fetches credentialed media from" "fetch(credentials: include)"
        cdpRecorder -> windowsChrome "Receives Network events from" "chrome.debugger/CDP"
        cdpRecorder -> wslLoopbackDaemon "Uploads CDP media rows and blobs to" "Bearer HTTP/JSON; raw HTTP PUT"
        popupOptions -> serviceWorker "Updates pause, policy, token, and controls through" "chrome.storage.local, runtime messages"
        popupOptions -> wslLoopbackDaemon "Checks health and triggers forget/policy actions on" "HTTP/JSON"

        httpRouter -> policyEngine "Gets capture decisions from"
        httpRouter -> migrationKernel "Requires compatible initialized schema through"
        httpRouter -> policyStore "Manages policy rules through"
        httpRouter -> ingestPipeline "Routes accepted captures to"
        httpRouter -> lifecyclePipeline "Routes lifecycle events to"
        httpRouter -> mediaManager "Routes media requests to"
        httpRouter -> searchReadModel "Routes read requests to"
        httpRouter -> forgetPipeline "Routes forget requests to"
        httpRouter -> opsDoctor "Routes health and audit work to"
        policyEngine -> policyStore "Combines static mode with rules from"
        ingestPipeline -> sqliteDatabase "Writes capture rows and FTS to" "sqlite3"
        ingestPipeline -> blobStore "Stages and commits clean-text snapshots through"
        ingestPipeline -> mediaManager "Records media refs through"
        lifecyclePipeline -> sqliteDatabase "Writes lifecycle identity and interval-union dwell to" "sqlite3"
        mediaManager -> sqliteDatabase "Updates media rows and tasks in" "sqlite3"
        mediaManager -> blobStore "Stages, commits, reads, evicts, and purges media through"
        searchReadModel -> sqliteDatabase "Reads metadata and FTS from" "SQLite FTS5"
        searchReadModel -> blobStore "Reads text and checks media files through"
        forgetPipeline -> sqliteDatabase "Deletes rows and records receipts in" "sqlite3"
        forgetPipeline -> blobStore "Deletes contained text and media blobs through"
        blobStore -> cleanTextBlobStore "Stages, commits, reads, stats, and deletes text blobs in" "Filesystem"
        blobStore -> mediaBlobCache "Stages, commits, reads, stats, and deletes media blobs in" "Filesystem"
        opsDoctor -> sqliteDatabase "Checks integrity and counts in" "sqlite3"
        opsDoctor -> cleanTextBlobStore "Counts text blob files in" "Filesystem"
        opsDoctor -> mediaBlobCache "Counts media blob files in" "Filesystem"
        migrationKernel -> sqliteDatabase "Validates and advances schema ledger/fingerprint in" "sqlite3 online backup + transactions"

        dailyDriver = deploymentEnvironment "Daily-driver local" {
            workstation = deploymentNode "Local workstation" "Windows workstation running Windows Chrome and WSL2." "Windows + WSL2" {
                windowsProfile = deploymentNode "Windows user profile" "Windows-local browser-memory-daemon artifacts and Chrome runtime." "Windows profile" {
                    windowsChromeNode = deploymentNode "Windows Chrome daily-driver profile" "Manual Load unpacked or Reload hosts the extension and local UI tab." "Google Chrome MV3" {
                        containerInstance chromeExtension
                        containerInstance extensionBrowserStorage
                        containerInstance localWebUi
                    }
                    extensionCopy = infrastructureNode "Windows unpacked extension copy" "Built extension copy under %LOCALAPPDATA%\\browser-memory-daemon\\extension containing the local daemon token." "Windows filesystem"
                }
                wslNode = deploymentNode "WSL2 Ubuntu" "WSL-owned services, config, and durable data paths." "Ubuntu + systemd --user" {
                    systemdUser = deploymentNode "systemd --user services" "User services installed by scripts/install-daily-driver.sh." "systemd --user" {
                        containerInstance wslLoopbackDaemon
                        containerInstance mediaWorker
                    }
                    wslCliNode = deploymentNode "WSL shell" "Operator shell for CLI commands and verification." "Bash + Python" {
                        containerInstance cli
                    }
                    xdgData = deploymentNode "WSL XDG runtime data paths" "Durable DB/config/state under ~/.config, ~/.local/share, and ~/.local/state, outside the repo." "WSL filesystem" {
                        containerInstance sqliteDatabase
                        tokenFile = infrastructureNode "Protected token/env files" "~/.config/browser-memory-daemon/token and env supply the daemon token and policy mode." "Filesystem, chmod 600/700"

                    }
                    nasBlobRoot = deploymentNode "WSL-mounted NAS blob root" "Configured BMD_BLOB_ROOT mount for clean-text and media blob files." "NAS mount of TrueNAS ZFS dataset" {
                        containerInstance cleanTextBlobStore
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
            autoLayout tb
        }

        container browserMemoryDaemon "DaemonMediaWorkerContainers" {
            include webSites
            include mediaWorker
            include sqliteDatabase
            include mediaBlobCache
            autoLayout lr
        }

        container browserMemoryDaemon "OpsContainers" {
            include localWebUi
            include cli
            include wslLoopbackDaemon
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            autoLayout lr
        }

        component chromeExtension "ExtensionCaptureComponents" {
            include manifestEnvelope
            include extractor
            include contentScript
            include serviceWorker
            include popupOptions
            include extensionBrowserStorage
            include wslLoopbackDaemon
            include windowsChrome
            autoLayout lr
        }

        component chromeExtension "ExtensionMediaComponents" {
            include serviceWorker
            include browserMediaQueue
            include cdpRecorder
            include extensionBrowserStorage
            include wslLoopbackDaemon
            include windowsChrome
            autoLayout tb
        }

        component wslLoopbackDaemon "DaemonPolicyComponents" {
            include httpRouter
            include policyEngine
            include policyStore
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonIngestComponents" {
            include httpRouter
            include ingestPipeline
            include sqliteDatabase
            include cleanTextBlobStore
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonLifecycleComponents" {
            include httpRouter
            include lifecyclePipeline
            include sqliteDatabase
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonMediaComponents" {
            include httpRouter
            include mediaManager
            include sqliteDatabase
            include mediaBlobCache
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonReadComponents" {
            include httpRouter
            include searchReadModel
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonForgetComponents" {
            include httpRouter
            include forgetPipeline
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonDoctorComponents" {
            include httpRouter
            include opsDoctor
            include sqliteDatabase
            include cleanTextBlobStore
            include mediaBlobCache
            autoLayout lr
        }

        component wslLoopbackDaemon "DaemonMigrationComponents" {
            include httpRouter
            include migrationKernel
            include sqliteDatabase
            autoLayout lr
        }

        dynamic browserMemoryDaemon "FastCaptureFlow" {
            operator -> windowsChrome "Browses a web page"
            chromeExtension -> windowsChrome "Runs content script and service worker inside active tab"
            chromeExtension -> wslLoopbackDaemon "POSTs /capture with visible text, metadata, and media refs"
            wslLoopbackDaemon -> sqliteDatabase "Stores document, visit, snapshot, chunks, FTS, media refs, and tasks"
            wslLoopbackDaemon -> cleanTextBlobStore "Writes clean-text snapshot blob"
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
