# Browser Memory Daemon CLI UX Contract

> **Audience:** operators, tests, and future CLI/API maintainers.
> **Source of truth:** `daemon/src/browser_memory_daemon/cli.py` plus live `--help`.
> **Status:** ✅ Current command surface documented.

---

## Invocation shape

The CLI requires Python 3.11+.

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  [--host HOST] \
  [--port PORT] \
  [--token TOKEN] \
  [--runtime-root PATH] \
  [--blob-root PATH] \
  [--derivative-root PATH] \
  [--media-root PATH] \
  [--media-spool-root PATH] \
  [--policy-mode all|recall|balanced|strict] \
  COMMAND [COMMAND_ARGS]
```

Global defaults:

| Flag/env | Default | Notes |
|---|---|---|
| `--host` / `BMD_HOST` | `127.0.0.1` | Loopback only unless explicitly changed. |
| `--port` / `BMD_PORT` | `8765` | Daily-driver default. |
| `--token` / `BMD_API_TOKEN` | required | Test mode can synthesize, production cannot. |
| `--runtime-root` / `BMD_RUNTIME_ROOT` | XDG paths | Tests/e2e use temp runtime roots. |
| `--blob-root` / `BMD_BLOB_ROOT` | `<runtime-root>/blobs` | Compatibility parent for legacy layouts; SQLite/WAL remains local. |
| `--derivative-root` / `BMD_DERIVATIVE_ROOT` | `<blob-root>` compatibility default | Reconstructible derivative placement, including legacy clean-text sidecars. Set explicitly only with a reviewed legacy-sidecar migration. |
| `--media-root` / `BMD_MEDIA_ROOT` | `<blob-root>/media` | Final disposable media bytes. Explicit external roots require mount and identity-marker verification. |
| `--media-spool-root` / `BMD_MEDIA_SPOOL_ROOT` | disabled | Local durable outage spool; must be under the runtime data root and paired with positive `BMD_MAX_MEDIA_SPOOL_BYTES`. |
| `BMD_MAX_MEDIA_SPOOL_BYTES` | `0` | Hard spool cap. A positive value and spool root must be configured together. |
| `BMD_MEDIA_ROOT_IDENTITY` | unset | Expected exact content of `.bmd-media-root-id`; required for guarded external roots. |
| `BMD_REQUIRE_MEDIA_ROOT_MOUNT` | `0` | Forces mount/identity guarding even for a compatibility-root layout. Explicit external media roots are guarded regardless. |
| `--policy-mode` / `BMD_POLICY_MODE` | `all` | Daily-driver default is maximum recall. |

---

## Commands

| Command | Purpose | Output |
|---|---|---|
| `serve` | Start the loopback daemon. | Human startup line; process stays running. |
| `health` | Fetch `/health`. | Raw JSON string. |
| `migrate --check` | Read-only schema fingerprint, version, ledger checksum, and pending-step report. | Pretty JSON; exits `0` when current, `2` when compatible work is pending, and `1` when incompatible. |
| `migrate --execute` | Apply pending ordered migrations. Future destructive steps require disk headroom and a verified online backup. | Pretty JSON including applied/stamped versions and backup path when applicable. |
| `doctor [--storage-census]` | Fetch `/doctor`; default uses fast DB-derived storage counts, `--storage-census` opts into an exact filesystem walk. | Pretty JSON. |
| `daily-driver-health [--journal-since WINDOW] [--extension-dir PATH] [--powershell PATH] [--skip-windows-loopback] [--no-fail]` | Redaction-safe daily-driver snapshot across services, loopback, journals, DB freshness, media queue, storage, and extension artifact state. | Pretty JSON. Exits non-zero on hard errors unless `--no-fail` is set. |
| `recent --limit N` | Recent capture observations with contemporaneous snapshot snippets; explicit ambiguous legacy-visit fallback. | Pretty JSON list. |
| `timeline [--date YYYY-MM-DD] [--after ISO] [--before ISO] [--limit N]` | Observation-first capture timeline plus a visit-deduplicated bounded summary. | Pretty JSON. |
| `document DOCUMENT_ID` | Document details including observations and untrusted URL claims. | Pretty JSON. |
| `snapshot SNAPSHOT_ID` | Snapshot details, text, and exact referencing observations. | Pretty JSON. |
| `search QUERY [--limit N]` | Exact FTS query. | Pretty JSON search results. |
| `policy-rules [--block-domain DOMAIN] [--block-url-prefix URL]` | List or add block-domain / URL-prefix rule. | Pretty JSON. Applies in every mode, including `all`. |
| `forget [--domain DOMAIN] [--url URL]` | Delete memory by exactly one selector: literal domain hostname or absolute URL. | Pretty JSON deletion receipt. |
| `capture-fixture --url URL --title TITLE --text TEXT` | Synthetic capture through HTTP API. | Pretty JSON ingest result. |
| `media-worker [--once|--loop] [--limit N] [--interval SEC]` | Run daemon public-media worker manually or as service. | Pretty JSON for `--once`; long-running loop for `--loop`. |
| `media-cache purge [--domain DOMAIN] [--document-id ID] [--snapshot-id ID] [--older-than ISO] [--max-bytes-to-purge N] [--dry-run|--execute] [--rehydrate]` | Dry-run/execute media blob cache purge without deleting text/FTS/ref rows. | Pretty JSON purge summary. |
| `media-cache rehydrate [--domain DOMAIN] [--document-id ID] [--snapshot-id ID] [--limit N]` | Queue/refetch purged public media refs. | Pretty JSON worker summary. |
| `media-cache requeue --reason {snapshot-budget,storage-budget,all-budget} [--domain DOMAIN] [--document-id ID] [--snapshot-id ID] [--limit N] [--dry-run|--execute]` | Preview or execute a bounded retry of terminal budget skips after an operator policy/cap change. At least one scope is required. | Pretty JSON selection/update summary; dry-run by default. |
| `blob-root migrate [--from-root PATH] [--execute] [--remove-source]` | Dry-run by default; copies DB-referenced clean-text/media blobs to the configured root and rewrites paths only with `--execute`. | Pretty JSON migration summary. `--remove-source` remains an explicit post-copy action. |
| `snapshot-text reconcile [--limit N] [--execute]` | Dry-run by default; promotes only exact hash-verified chunk reconstructions or contained legacy sidecars into SQLite complete-text authority. | Pretty JSON with scanned/resolved/applied/source/unresolved counts. `--execute` is required to mutate rows. |
| `media-spool status` | Report final-root readiness plus configured cap, DB-backed artifact/reservation counts, filesystem-accounted bytes, and available capacity. | Pretty JSON; read-only. |
| `media-spool drain [--limit N] [--execute]` | Preview or execute bounded spool-to-media-root transitions. | Dry-run by default. Execute streams and verifies size/SHA-256, commits the SQLite tier switch, then removes the spool source. |
| `storage reconcile [--limit N] [--stale-stage-seconds N] [--execute]` | Preview or execute contained blob convergence across pending tombstones, missing references, in-root orphans, and stale stages. | Dry-run by default. Exit `0` when no retryable tombstones remain; exit `2` when deletion work remains blocked/failed. |
| `backup create --destination ABS_PATH [--include-derivatives] [--execute]` | Preview or atomically create a manifest-backed SQLite-authoritative local bundle. | Dry-run by default. Source DB must be real/contained; output is private `0700`/`0600`; media/spool/secrets are excluded; optional derivatives are reference- and hash-verified. |
| `backup restore --source ABS_PATH --destination ABS_PATH [--execute]` | Validate or restore a bundle into an absent explicit runtime root. | Dry-run performs immutable SQLite/schema/FTS/FK/manifest validation without creating the destination. Execute publishes a private runtime and rejects existing destinations or any path/hash/semantic mismatch. |

---

## Exit/error contract

| Condition | Expected behavior |
|---|---|
| Missing production token | `load_config` raises and CLI exits non-zero. |
| Unauthorized API call | HTTP `401`; CLI surfaces exception/non-zero. |
| Compatible migration work pending | `migrate --check` prints the pending ordered steps and exits `2` without creating or mutating the database. |
| Migration incompatibility/failure | `migrate` prints JSON with `compatible=false`, `ready=false`, and a redaction-safe error, then exits `1`. |
| `daily-driver-health` hard error | Prints JSON with `ok=false` and exits `1`; use `--no-fail` for report-only collection. |
| Pending blob deletion | Forget/purge JSON reports pending work; `doctor` is degraded and `storage reconcile --execute` exits `2` until blocked/failed records converge. |
| Bad capture payload | HTTP `400` with JSON error. |
| Blocked capture by static policy or explicit local rule | HTTP `200`, `{"stored": false, "blocked": true, "reason": "..."}`. |
| `all` mode capture | Stores unredacted payload when payload is otherwise parseable. |
| Forget by neither URL nor domain, or both URL and domain | CLI exits with parser error; HTTP API returns `400` from daemon validation. |

---

## Examples

Start a dev daemon in all mode:

```bash
PYTHONPATH=daemon/src BMD_API_TOKEN=dev-token \
  python3.11 -m browser_memory_daemon --token dev-token --policy-mode all serve
```

Search daily-driver memory:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  search "example" --limit 10
```

Run the aggregate daily-driver health snapshot:

```bash
./scripts/daily-driver-health.sh
```

Report-only mode for diagnostics without failing the shell command:

```bash
./scripts/daily-driver-health.sh --no-fail
```

Add block rules:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  policy-rules --block-domain example.com

PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  policy-rules --block-url-prefix http://127.0.0.1:32400/
```

Forget a domain. Domain selectors are literal hostnames and delete that host plus subdomains:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  forget --domain example.com
```

Forget one URL. URL selectors follow storage policy: `all` mode matches the literal stored URL; non-`all` modes match the redacted URL representation used during ingest. Receipts redact sensitive selector values:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  forget --url 'https://example.com/article?token=...'
```

Media cache dry-run:

```bash
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
  --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" \
  media-cache purge --domain linkedin.com --dry-run
```

---

## Stability notes

- CLI output is currently JSON but not formally versioned.
- `capture-fixture` exists for tests/smoke checks, not browser capture replacement.
- `migrate --check/--execute`, `blob-root migrate`, `snapshot-text reconcile`, and `storage reconcile` are current repository migration/reconciliation helpers; dry-run remains the default for filesystem-backed reconciliation.
- `storage reconcile` never traverses an unavailable external media root and never deletes outside configured roots.
- `backup create` and `backup restore` require absolute paths and are dry-run first. Create rejects active runtime/storage overlap and symlinked destination parents; restore never overwrites or merges an existing destination.
- Backup defaults to private SQLite plus manifest files. Tokens/config, Chrome state, final media, and spool bytes are excluded; `--include-derivatives` adds only referenced contained clean-text sidecars and restore normalizes legacy absolute references.
- Future CLI changes should update this contract and `daemon/tests/e2e/test_cli_admin.py` together.
