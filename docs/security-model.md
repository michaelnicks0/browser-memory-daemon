# Security and Policy Model

> **Audience:** operator and maintainers.
> **Status:** ✅ Adjustable policy modes implemented.
> **Default:** `all` — maximum personal recall, no built-in URL policy filtering or daemon redaction; explicit local block rules still apply.

---

## Core boundary

The daemon is local-first and WSL-resident. It assumes captured page text may be private and may contain hostile prompt-injection text. It does **not** assume a multi-user enterprise DLP posture.

| Boundary | Current control |
|---|---|
| Network | Daemon binds to `127.0.0.1` by default; daemon-public media fetches reject non-global/private destinations unless explicitly allowlisted. |
| API auth | Bearer token required for memory/admin APIs. |
| Health/UI shell | `/health` and `/ui` are public loopback only; `/ui` rejects non-loopback `Host` headers and includes a same-origin token bootstrap for operator UX, while static assets stay token-free. |
| Durable storage | WSL XDG paths; repo and Chrome profile are not storage roots; DB blob paths are validated against configured roots before read/serve/delete operations; explicit external media roots require mount and identity-marker proof; an optional local spool is contained under the WSL data root and hard-capped; durable deletion intents preserve retry work across crashes. |
| Browser bridge | Content scripts message the service worker; the worker owns daemon fetch/auth and drains transactional capture/lifecycle plus specialized media IndexedDB queues. |
| Agent safety | Captured page text is untrusted evidence, never instructions. |

---

## Policy modes

| Mode | Purpose | Filtering | Redaction | Notes |
|---|---|---:|---:|---|
| `all` | Maximum personal recall. | Built-in URL filters off; explicit local block rules on; DOM skip retained | ❌ Off | Default. |
| `recall` | Broad recall with minimal protective boundaries. | ⚠️ Minimal | ✅ On | Blocks incognito/internal/file/non-web schemes. |
| `balanced` | Practical privacy with less overblocking than strict. | ✅ Moderate | ✅ On | Blocks private hosts, known high-risk domains, and high-risk query keys. |
| `strict` | Legacy broad privacy filtering. | ✅ Broad | ✅ On | Keyword-heavy domain/path/query blocks. |

---

## `all` mode risk acceptance

`all` intentionally stores original URL/title/body text without daemon redaction and without built-in URL/domain/path/query filtering. It still applies explicit local block rules and conservatively skips explicit/computed/ancestor-hidden, transparent, form, editable, script, style, and noscript light-DOM text. Shadow roots and pseudo-element content are outside the extraction contract. This is an operator-selected personal recall mode.

Known consequences:

- visible/exposed page secrets can be stored and indexed;
- account, email, chat, health, payment, and local/private pages can be stored;
- only explicit local block rules narrow capture;
- Chrome platform restrictions still apply where extension injection is refused.

Mitigations that remain even in `all`:

- loopback-only daemon bind by default;
- bearer auth for memory/admin APIs;
- runtime data is outside the repo;
- secret scan protects committed repo content;
- forget-by-domain/URL can delete stored memory after the fact; URL forget uses the literal selector in `all` mode but redacts selector values in receipts. Receipt and byte-deletion tombstones commit with the relational cascade, and incomplete byte removal is reported as pending rather than complete.

---

## Non-`all` redaction

In `recall`, `balanced`, and `strict`, redaction runs before DB/FTS/blob storage for:

- private-key blocks;
- bearer-token-shaped strings;
- `api_key` / `secret` / `token` assignment shapes;
- SSN-shaped strings;
- credit-card-like digit runs;
- URL username/password;
- sensitive query values and fragments;
- opaque long path/token segments.

---

## Current controls

- API token required for `/capture`, `/visit-events`, `/media-artifacts/*`, `/search`, `/ready`, `/recent`, `/timeline`, `/documents/{id}`, `/snapshots/{id}`, `/policy/*`, `/doctor`, and `/forget`.
- HTTP errors retain a compatible top-level `error` string and add stable `error_code` values. Validation messages remain bounded client feedback; SQLite details, filesystem paths, and unexpected exception text are replaced with generic 5xx messages rather than returned to callers.
- Every response carries an opaque server-generated request ID and common no-store/CSP/frame/referrer/permissions/content-type protections. Structured request telemetry contains only request ID, method, descriptor route name, status, integer latency, and safe error code; it excludes raw paths, queries, URLs, origins, client addresses, headers, bearer values, payloads, captured content, and exception prose.
- `/health` exposes minimal daemon status plus `policy_mode`.
- Daily-driver install stores the daemon API token in protected WSL config files and injects it into the Windows-local extension artifact; the token is never committed.
- Capture and lifecycle payloads are durable browser-profile data in a versioned IndexedDB outbox. Atomic token-checked claims recover after MV3 suspension; the extracted telemetry boundary recursively drops payload/text/body/content/URL/token/header fields and redacts URL-shaped error substrings before `chrome.storage.local` writes. Legacy `chrome.storage.local` queue arrays are imported before deletion and remain only as a one-version failure fallback.
- Typed extension state keeps visit/navigation state and minimal CDP capture provenance (`document_id`, `snapshot_id`, `visit_id`, and observed page URL) in `chrome.storage.local` so worker restart can reconstruct ownership. It excludes page text, titles, media bodies, cookies, request headers, and tokens; tab close or an observed URL change clears the CDP context.
- Fetched browser media remains in a separate versioned IndexedDB task/blob queue. Atomic task-batch and blob/state transitions enforce a 500-task and 512 MiB aggregate boundary; terminal failures are quarantined for 24 hours and then removed in bounded transactions. Media telemetry exposes aggregate counts and bytes only.
- Token rotation is supported:

  ```bash
  BMD_ROTATE_TOKEN=1 BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
  ```

- Local web UI is served from loopback at `/ui`; the HTML bootstrap embeds the current daemon token so the dashboard auto-loads without manual paste. Requests with non-loopback `Host` headers are rejected, static JS/CSS assets remain token-free, and every memory/admin API call still requires the bearer token.
- Configure final media separately with `BMD_MEDIA_ROOT`. Explicit external roots, or roots guarded with `BMD_REQUIRE_MEDIA_ROOT_MOUNT=1`, require a non-root mount and `.bmd-media-root-id` whose exact content matches `BMD_MEDIA_ROOT_IDENTITY`. The daemon checks this boundary before media access and does not create the external media root during startup. `BMD_REQUIRE_BLOB_ROOT_MOUNT` remains a compatibility guard.
- A media-root outage never blocks local SQLite text/provenance capture. Optional fallback requires both a local `BMD_MEDIA_SPOOL_ROOT` beneath the data root and positive `BMD_MAX_MEDIA_SPOOL_BYTES`; no implicit or unbounded shadow fallback exists. Admission counts committed/orphaned spool files and distinct in-flight SQLite reservations so same-artifact concurrent writers cannot collapse capacity accounting.
- Forget, media purge, and eviction first persist contained locators in `blob_storage_records`. Failed or blocked bytes are not served, remain in budget accounting, degrade doctor status, and are retried only through the dry-run-first `storage reconcile` operator surface. Reconciliation does not follow outside-root paths or unavailable external roots.
- Daemon-public media fetch uses a no-cookie, no-`Referer`, HTTP(S)-only egress guard. Every direct URL, redirect target, HLS variant playlist, init map, and segment is resolved and rejected by default if it maps to loopback, private, link-local, unspecified, multicast, reserved, or otherwise non-global address space. Private destinations require explicit `BMD_MEDIA_PUBLIC_FETCH_ALLOW_PRIVATE_HOSTS` configuration. Potential HLS video transport claims its aggregate request budget before the first open, applies the playlist cap from final URL/MIME or bounded magic-prefix sniffing, and enforces the shared deadline before and after every response-body read while tightening the socket timeout to the remaining interval.
- Media request and byte use is process-bounded by positive `BMD_MAX_MEDIA_CONCURRENT_REQUESTS` and `BMD_MAX_MEDIA_INFLIGHT_BYTES`; the byte cap must admit at least one maximum artifact. Raw upload/download and public fetch/HLS paths stream through bounded chunks and release leases on cancellation or failure. SQLite version 13 cache reservations separately serialize committed-plus-reserved snapshot/domain/global admission across daemon and worker processes, with expired crash reservations removed by the next admission attempt. Aggregate queue telemetry exposes no captured content, URL, or storage path.
- Complete cleaned text and capture provenance commit atomically to local SQLite. New captures create no text sidecar. Legacy text promotion accepts only SHA-256 matches from ordered chunks or an in-root regular sidecar resolved through `BlobStore`; arbitrary database paths and hash mismatches remain unresolved.
- Media and legacy-sidecar blob operations are root-scoped through `BlobStore`: writes use unique streaming stages, optional size/hash checks, file and parent-directory `fsync`, and atomic replace; media filenames use hashed storage stems; and read/serve/stat/purge/forget/migration flows refuse stale or tampered DB locators. Media rows identify `media-root` or `spool` ownership and keep root-relative plus contained absolute compatibility locators. Reads fail closed rather than downgrading when a preferred locator is invalid. Spool drain verifies size/hash, commits the tier transition, then removes the source.
- Deletion UX requires explicit browser confirmation before UI/popup forget-domain calls, and the daemon returns deletion receipts. Destructive forget accepts exactly one selector; domain selectors must be literal hostnames, and URL selectors match the active policy's storage representation while keeping receipt scopes redaction-safe.

---

## Current limitations

| Limit | Status |
|---|---|
| Native messaging hardening | Not implemented. |
| Semantic embeddings | Not implemented. |
| Encrypted backups | Not implemented. |
| Rich allow/redact/metadata-only rules | Not implemented. |
| Retention/compaction | Not implemented. |
| Cloud processing | Not implemented and should not be added without explicit approval. |
