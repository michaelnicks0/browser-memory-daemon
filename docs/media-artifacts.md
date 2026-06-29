# Media Artifacts — Durable Image/Video Sidecars

> **Audience:** Operator and future maintainers  
> **Scope:** Store page images/videos as related artifacts next to text/FTS snapshots.  
> **Status:** ✅ Implemented: fast text/ref capture, browser lazy media queue, raw blob upload, CDP recorder, HLS/audio sidecars, daemon public worker, rolling cache gates, and purge/rehydrate controls.
> **Architecture:** see [`ARCHITECTURE.md#durable-media-sidecar-architecture`](ARCHITECTURE.md#durable-media-sidecar-architecture) for the consolidated design rationale.

---

## Goal

The browser-memory daemon stores media that appeared on a captured page as **related artifacts** for reference while keeping text recall fast and reliable.

This is intentionally **not OCR** and **not media indexing**:

```text
page text  → chunks + FTS
page media → media_artifacts rows + optional blob files
```

A search hit still comes from FTS text. The hit can then show that the same snapshot had related images/videos and expose stored local media from the UI/API.

---

## What gets captured

The Chrome content script extracts media references from:

| DOM source | Stored artifact type | Notes |
|---|---|---|
| `<img>` | `image:content` | Uses `currentSrc`/`src`, alt/title, dimensions. |
| `<picture><source srcset>` | `image:content` | Uses the first srcset candidate. |
| `<video poster>` | `image:poster` | Poster image stored as an image artifact. |
| `<video src>` / `<video><source src>` | `video:content` | Direct video source is stored if fetchable and under caps. |
| Performance resource timing video entries | `video:content` | Preserved even when image refs fill the cap, so late-loaded direct video resources do not get crowded out by thumbnails. |
| HLS `.m3u8` playlists | `video:content` | Browser sidecar leaves them for the daemon; the daemon resolves master/media playlists, concatenates init + segment bytes, and stores best-effort local `video/mp4`/`video/mp2t` artifacts plus audio-only rendition sidecars as `audio/*` blobs. |
| CDP network media responses | `video:cdp-segment` / `video:cdp-manifest` | On by default, operator-disableable path: on X/Twitter tabs the extension uses `chrome.debugger` + CDP `Network` events to capture `video.twimg.com` HLS manifests and media segments before they disappear behind `blob:` player URLs. |

Quality skips retained:

- hidden media elements are skipped;
- 1×1 tracking-pixel-like images are skipped;
- at most 50 media refs per page capture are stored, but discovered video refs are prioritized over images when the page exceeds the cap;
- huge inline data URLs are not embedded in the `/capture` payload.

---

## Storage model

```text
document → snapshot → media_artifacts
         ↘ visit ↗

media_fetch_tasks → media_artifacts
blobs/media/<artifact_id>.<ext>
```

Key fields:

| Field | Purpose |
|---|---|
| `document_id` | Parent document. |
| `snapshot_id` | Exact text snapshot the media appeared with. |
| `visit_id` | Visit that generated/uploaded the artifact when known. |
| `media_type` | `image` or `video`. |
| `role` | `content`, `poster`, or `source`. |
| `source_url` | Original media URL, redacted outside `all` mode. |
| `mime_type` | Response or DOM MIME type. |
| `width`, `height`, `duration_seconds` | DOM metadata. |
| `capture_status` | `referenced`, `metadata-only`, `queued`, `fetching`, `fetched`, `uploading`, `stored`, `retrying`, `failed`, `skipped`, `expired`, or `purged`. |
| `status_reason` | Terminal or diagnostic reason, e.g. `media-too-large`, `fetch-status-403`, `cache-purged:domain:x.com`, `cache-evicted:domain-oldest`, `covered-by-cdp-recorder`, `opaque-browser-blob`. |
| `file_path` | Local blob path when binary is currently stored. |
| `content_sha256`, `byte_size` | Blob provenance retained even after cache purge. |

Binary files live under:

```text
~/.local/share/browser-memory-daemon/blobs/media/
```

---

## Capture flow

```mermaid
sequenceDiagram
  participant CS as Content script
  participant SW as Extension service worker
  participant IDB as Extension IndexedDB
  participant D as WSL daemon API
  participant MW as WSL media worker
  participant DB as SQLite + blobs

  CS->>CS: extract visible text + media refs
  CS->>SW: BMD_CAPTURE payload
  SW->>D: POST /capture text + media refs
  D->>DB: store text snapshot + FTS + media_artifacts refs
  D->>DB: enqueue daemon-public media_fetch_tasks
  D-->>SW: document_id + snapshot_id + artifact IDs
  SW->>IDB: enqueue browser media tasks
  SW-->>CS: capture complete + artifact IDs
  CS->>SW: optional inline blob/data media bytes from page context
  SW->>D: PUT /media-artifacts/{artifact_id}/blob

  par Browser lazy sidecar
    IDB->>SW: due media task
    SW->>SW: fetch source URL with Chrome cookies
    SW->>IDB: persist fetched blob until upload succeeds
    SW->>D: PUT /media-artifacts/{artifact_id}/blob
    D->>DB: atomic blob write + status=stored
    SW->>IDB: delete completed task
  and Daemon lazy sidecar
    MW->>DB: lease daemon-public task
    MW->>MW: public fetch without Chrome cookies
    MW->>DB: atomic blob write or terminal status/reason
  end
```

Important properties:

- `/capture` stores text/FTS and media reference rows without waiting on media bytes.
- Credentialed media fetch happens inside Chrome; cookies are **not** exported to WSL.
- WSL daemon media worker backfills public `http:`, `https:`, and `data:` refs.
- HLS `.m3u8` playlist URLs are daemon-owned, not browser-queue-owned: the worker follows master playlists to a variant playlist, downloads init/segment bytes within the artifact cap, and stores the assembled bytes as local video. Audio-only HLS renditions are also stored as audio MIME sidecars (`audio/mp4`, etc.) while retaining `media_type='video'` provenance.
- CDP recorder lane: when enabled and an active tab matches the configured recorder domains (`x.com`, `twitter.com` by default), the extension attaches `chrome.debugger`, enables CDP `Network`, records `video.twimg.com` manifest/segment responses, creates `media_artifacts` rows with `cdp_recorder=true`, and either uploads the response body directly or lets the daemon HLS backfill worker assemble the manifest. This captures media before X exposes only transient `blob:` URLs; same-snapshot or same-page/time-window `blob:` video rows are labeled `covered-by-cdp-recorder` when stored CDP bytes exist.
- Content scripts opportunistically fetch `blob:`/inline media while the renderer page is alive and send bytes through the service worker; this is the only reliable path for simple transient browser blob URLs. Remaining uncovered `blob:` videos are kept as `referenced:opaque-browser-blob`, not failures.
- If media cannot be fetched, the reference row remains with an explicit classified status/reason. `failed` is reserved for unexpected/unclassified bugs; terminal remote conditions are normalized to `skipped`, `expired`, or `retrying`.
- Browser queue tasks in `fetching` or `uploading` become due again after a stale processing window, so MV3 service-worker suspension does not strand them permanently.
- Chrome shows a normal “extension is debugging this browser” indicator while the CDP recorder is attached. The recorder remains enabled by default for X/Twitter video completeness, but the options page can disable it when banner-free browsing matters more. Attachment is domain-gated to configured X/Twitter tabs and media-host-gated to `video.twimg.com`.

---

## API

### `/capture` response includes artifact IDs

`/capture` stores media refs and returns stable artifact metadata so the browser sidecar can enqueue durable upload work:

```json
{
  "stored": true,
  "document_id": "doc_...",
  "snapshot_id": "snap_...",
  "media_ref_count": 2,
  "media_artifacts": [
    {
      "artifact_id": "media_...",
      "document_id": "doc_...",
      "snapshot_id": "snap_...",
      "media_type": "image",
      "role": "content",
      "source_url": "https://example.com/hero.png"
    }
  ]
}
```

### Raw blob upload

Primary browser lazy sidecar path:

```http
PUT /media-artifacts/<artifact_id>/blob
Authorization: Bearer ***
Content-Type: image/png
X-BMD-Document-ID: doc_...
X-BMD-Snapshot-ID: snap_...
```

The daemon size/MIME/cache gates the blob, writes through `blobs/media/.tmp`, then atomically renames to the final file.

### Compatibility JSON artifact upload

Kept for compatibility and tests:

```http
POST /media-artifacts
Authorization: Bearer ***
Content-Type: application/json
```

```json
{
  "document_id": "doc_...",
  "snapshot_id": "snap_...",
  "media_type": "image",
  "source_url": "https://example.com/hero.png",
  "mime_type": "image/png",
  "content_base64": "..."
}
```

If `content_base64` is omitted, the row is metadata-only.

### Fetch pending public refs

Manual/backfill path:

```http
POST /media-artifacts/fetch-pending
Authorization: Bearer ***
Content-Type: application/json
```

```json
{"domain": "x.com", "limit": 100}
```

### Queue status

```http
GET /media-artifacts/queue-status?limit=50
Authorization: Bearer ***
```

Returns artifact status counts, task status counts, stored bytes, configured cache gates, and recent non-stored artifacts.

### Purge media cache

```http
POST /media-artifacts/purge-cache
Authorization: Bearer ***
Content-Type: application/json
```

```json
{
  "domain": "linkedin.com",
  "dry_run": true,
  "rehydrate": false
}
```

Purge removes blob files and marks artifacts `purged`; it does **not** delete text/FTS/media refs. If `rehydrate=true`, eligible daemon-public tasks are reset to `pending` for best-effort refetch.

CLI wrappers:

```bash
TOKEN="$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)"
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon --token "$TOKEN" media-cache purge --domain linkedin.com --dry-run
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon --token "$TOKEN" media-cache purge --domain linkedin.com --execute --rehydrate
PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon --token "$TOKEN" media-worker --once --limit 100
```

### Retrieve media artifact

```http
GET /media-artifacts/<artifact_id>
Authorization: Bearer ***
```

Returns the stored binary with its MIME type if available. If the artifact has no current file, the endpoint returns `404` with artifact metadata.

---

## Limits and caveats

| Limit | Value / behavior |
|---|---|
| Media refs per capture | 50 |
| Max binary artifact | 250 MB by default |
| Max media JSON upload | 40 MB |
| Browser lazy sidecar | Extension IndexedDB queue, `chrome.alarms`, fetch with `credentials: include`, raw `PUT` upload |
| Daemon lazy sidecar | `browser-memory-media-worker.service`, public fetch only, no Chrome cookies |
| Manual fetch-pending call limit | 100 artifacts |
| Daemon-supported fetch schemes | `http:`, `https:`, `data:` |
| Browser inline/blob upload schemes | `blob:` and `data:` when the content script can read bytes before page teardown |
| Unsupported/hard schemes | browser-internal URLs, opaque streaming, DRM, media-source streams with no readable file/blob |

Cache gates:

| Gate | Default |
|---|---:|
| Per artifact | 250 MB |
| Per snapshot | 1 GB |
| Per domain | 10 GB |
| Global media cache | 100 GB |
| Minimum priority | 0 |

Cache gates are enforced before byte storage. Per-domain and global cache gates are rolling: when a new artifact would exceed either budget, the daemon evicts the oldest stored blobs in that scope first (`cache-evicted:domain-oldest` or `cache-evicted:global-oldest`) while preserving text, refs, hashes, byte history, and DB rows.

Video caveat:

- Direct small video files can be stored by the daemon or browser sidecar.
- HLS `.m3u8` playlists can be stored by the daemon as best-effort assembled segment bytes; audio-only HLS renditions are stored as `audio/*` sidecars while retaining video provenance.
- Small readable `blob:` videos can now be stored by the content script while the page is alive.
- Streaming video pages may still expose DASH/DRM/MSE media-source streams or transient `blob:` URLs. If Chrome does not expose readable bytes to the content script and the daemon cannot resolve a public HLS/direct URL, those remain references rather than skipped failures.

---

## Verification

Implemented gates:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
cd extension && npm test && npm run build
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-e2e.sh
BMD_PYTHON="${BMD_PYTHON:-python}" BMD_REAL_CHROME_POLICY_MODE=strict ./scripts/run-real-chrome-e2e.sh
./scripts/secret-scan.sh
git diff --check -- .
```

Real Chrome e2e verifies:

- synthetic page text appears in FTS;
- public and cookie-required image artifacts are extracted from DOM;
- browser lazy sidecar fetches with Chrome cookie envelope using a no-store fetch path;
- content-script inline upload stores a real Chrome `blob:` video fixture;
- raw `PUT /media-artifacts/{id}/blob` stores local files;
- stale `fetching`/`uploading` tasks are re-eligible instead of stranded;
- extension capture/lifecycle/media queues drain empty;
- daemon task rows reach `succeeded`;
- strict policy still blocks sensitive/local fixture pages.
