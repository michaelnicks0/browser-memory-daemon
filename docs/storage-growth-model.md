# Browser Memory Daemon Storage Growth Model

> **Audience:** Operators and future maintainers
> **Scope:** Estimate how large the current Chrome → WSL browser-memory daemon will grow under real browsing.
> **Status:** ✅ Public sizing model using representative daemon/storage assumptions; local empirical source data is intentionally not included.

---

## TL;DR

The implementation is **text-first** with optional bounded media blobs. Text/FTS growth remains manageable; media is intentionally cache-like and now has explicit size gates plus purge/rehydrate controls. Blob bytes can be moved to a configured WSL-visible NAS root with `BMD_BLOB_ROOT` while SQLite/FTS stays under the WSL runtime root.

Using a representative daily-driver baseline and the daemon's current storage multiplier, the most realistic planning range is:

| Usage posture | Assumption | Expected growth |
|---|---:|---:|
| Light / filtered day | 100 snapshots/day, current mean text size | ~1.6 GB/year |
| Actual-ish baseline | ~250 snapshots/day, current mean text size | ~4.0 GB/year |
| Busy baseline | ~350 snapshots/day, current mean text size | ~5.6 GB/year |
| Heavy browsing | 500 snapshots/day, current mean text size | ~8.1 GB/year |
| Very heavy / dynamic pages | 500 snapshots/day, p90 text size | ~23.7 GB/year |
| Extreme | 1000 snapshots/day, p90 text size | ~47.4 GB/year |

Practical expectation for **text/FTS** remains **5–15 GB/year** under normal-heavy browsing. Media blobs are separate from this estimate: defaults cap individual artifacts at 250 MB, per-snapshot media at 1 GB, per-domain media at 10 GB, and total media cache at 100 GB. Domain/global media budgets are rolling caches: oldest blobs are evicted first while refs/text remain.

---

## Representative inputs

The model intentionally avoids publishing local browsing history, URLs, domains, or live daemon row counts. It uses representative extracted-text sizes from early daemon measurements plus code-level storage behavior:

| Input | Planning value | Why it matters |
|---|---:|---|
| Median extracted text per snapshot | 3.6 KiB | Light pages and deduped captures. |
| Mean extracted text per snapshot | 7.1 KiB | Primary planning case. |
| p90 extracted text per snapshot | 20.9 KiB | Dynamic/social/search pages with more visible text. |
| Mean chunks per snapshot | 4.58 | Drives `chunks` and FTS storage growth. |
| Runtime multiplier | ~6.5x extracted text | Accounts for clean text blobs, SQLite chunk text, FTS shadow/index tables, metadata, and audit/lifecycle rows. |

---

## Where the bytes go

The largest durable text/FTS consumers are expected to be:

| Component | Relative size | Role |
|---|---:|---|
| `chunks` | High | Searchable chunk text + metadata. |
| `chunks_fts_content` | High | FTS content shadow copy. |
| `chunks_fts_data` | Medium | FTS index data. |
| `audit_events` | Low/medium | Capture/search/visit audit metadata. |
| `visit_events` | Low | Dwell/lifecycle metadata. |
| `snapshots` | Low | Snapshot metadata. |
| `visits` | Low | Visit metadata. |
| `documents` | Low | Document identity metadata. |

Planning storage multiplier:

```text
runtime bytes / clean extracted text bytes ≈ 6.5x
```

That multiplier is high because the system stores text multiple ways:

1. clean snapshot blob;
2. chunk text in SQLite;
3. FTS content shadow table;
4. FTS index data;
5. metadata tables and indexes;
6. audit/lifecycle rows;
7. early fixed SQLite overhead.

As the DB grows, fixed overhead will amortize, but **5–7x extracted text** is the right planning range unless the schema is optimized.

---

## Planning usage baseline

Interpretation for any daily-driver browser profile:

- Chrome History visits are not exactly daemon snapshots.
- A single page can produce several daemon snapshots due delayed capture / SPA changes.
- Repeated unchanged pages dedupe into visits without duplicating snapshot/chunk/FTS rows.
- Using **250–350 snapshots/day** is a reasonable baseline range for a busy daily-driver profile.
- Using **500 snapshots/day** is a reasonable heavy/day planning point.

---

## Growth scenarios

Assumptions:

```text
storage = snapshots_per_day × extracted_text_bytes_per_snapshot × 6.5
```

| Snapshots/day | Text case | Avg text | MB/day | GB/30d | GB/year |
|---:|---|---:|---:|---:|---:|
| 100 | Median current | 3.6 KiB | 2.26 | 0.07 | 0.81 |
| 100 | Mean current | 7.1 KiB | 4.52 | 0.13 | 1.61 |
| 100 | p90 current | 20.9 KiB | 13.29 | 0.39 | 4.74 |
| 250 | Median current | 3.6 KiB | 5.65 | 0.17 | 2.02 |
| 250 | Mean current | 7.1 KiB | 11.31 | 0.33 | 4.03 |
| 250 | p90 current | 20.9 KiB | 33.24 | 0.97 | 11.85 |
| 350 | Mean current | 7.1 KiB | 15.83 | 0.46 | 5.64 |
| 350 | p90 current | 20.9 KiB | 46.53 | 1.36 | 16.59 |
| 500 | Mean current | 7.1 KiB | 22.61 | 0.66 | 8.06 |
| 500 | p90 current | 20.9 KiB | 66.47 | 1.95 | 23.69 |
| 1000 | Mean current | 7.1 KiB | 45.23 | 1.33 | 16.12 |
| 1000 | p90 current | 20.9 KiB | 132.95 | 3.89 | 47.39 |

Planning baseline estimates using current mean text size:

| Assumption | MB/day | GB/month | GB/year |
|---|---:|---:|---:|
| 249 snapshots/day — mean unique URL/day | 11.27 | 0.33 | 4.02 |
| 343 snapshots/day — mean visits/day | 15.51 | 0.45 | 5.53 |
| 499 snapshots/day — p75 visits/day | 22.57 | 0.66 | 8.04 |

---

## Future feature impact

### Embeddings / vector search

No embeddings exist yet. If added later, rough incremental storage at 250 snapshots/day and current 4.58 chunks/snapshot:

| Embedding format | Extra MB/day | Extra GB/year |
|---|---:|---:|
| 1536-d float32 | 6.72 | 2.39 |
| 1536-d float16 | 3.36 | 1.20 |
| 768-d float32 | 3.36 | 1.20 |
| 1536-d int8 | 1.68 | 0.60 |

Embeddings are not the scary part if stored compactly. They are likely **+0.5–3 GB/year** for normal use.

### Full HTML, screenshots, assets

These would change the model completely:

| Feature | Likely impact |
|---|---|
| Full HTML snapshots | Could be 5–50x current text-only storage depending on pages. |
| Screenshots | Easily hundreds of KB to multiple MB per page. |
| Images/assets/video cache | Now implemented as a bounded, purgeable cache. Defaults still allow large growth under media-heavy browsing, but per-artifact/snapshot/domain/global gates prevent unbounded accumulation. |

Recommendation: keep the daemon **text-first** unless a specific future feature needs richer capture.

---

## Main growth drivers

1. **Snapshots/day** — highest-leverage variable.
2. **Dynamic recapture** — SPAs, social feeds, video pages, account portals can produce multiple snapshots.
3. **Extracted text size** — social/feed/search/video pages include sidebars, recommendations, comments, and page chrome.
4. **FTS duplication** — `chunks` + `chunks_fts_content` + `chunks_fts_data` are the biggest DB components.
5. **Audit/lifecycle verbosity** — currently small, but can grow indefinitely.
6. **No retention policy** — intentional for exact recall, but means monotonic growth.

---

## Optimization options that preserve recall

These reduce bytes without silently dropping memories.

| Option | Recall impact | Expected benefit | Notes |
|---|---|---:|---|
| Add daily storage metrics / watchdog | None | Operational visibility | First thing to do. |
| Periodic SQLite `VACUUM` / `optimize` | None | Recovers free pages, improves FTS | Manual or scheduled. |
| Use FTS5 external-content table | None if implemented carefully | Save ~20–35% DB size | Removes `chunks_fts_content` duplication. |
| Stop storing both full clean blob and chunk text | Low if detail view reconstructs from chunks | Save ~10–25% total | Need verify exact reconstruction. |
| Compress clean-text blobs with zstd/gzip | None if transparent | Small/moderate | Blob is currently smaller than DB text+FTS. |
| Bound audit retention or compact audit to summaries | Low for recall; affects ops history | Small/moderate | Keep capture/search evidence if desired. |
| Domain/day rollup stats | None | Visibility | Helps spot runaway domains. |

Do **not** start by deleting pages or filtering domains if the product goal is exact recall. Start with observability and storage efficiency.

---

## Recommended operating plan

### Short term

- Add a `storage stats` CLI/API endpoint:
  - DB bytes / WAL bytes / blob bytes;
  - documents / visits / snapshots / chunks / events;
  - daily growth slope;
  - top domains by snapshot count and text bytes.
- Add local warning thresholds for durable text/DB growth:
  - warn at 10 GB, 25 GB, 50 GB;
  - do not auto-delete text/FTS memories. Media blobs are already a rolling cache under the configured domain/global media caps.

### Medium term

- Migrate FTS to external-content mode if the DB grows beyond ~10 GB.
- Add `sqlite optimize` / `VACUUM` maintenance command.
- Add optional export/backup before any compaction work.

### Long term

- If semantic search lands, store embeddings compactly (`float16` or quantized) unless quality demands float32.
- Avoid screenshots/assets unless explicitly scoped; they dominate storage.

---

## Bottom line

For the current local-first all-mode setup:

```text
Expected:  ~4–8 GB/year
Likely planning envelope: 5–15 GB/year
Heavy/dynamic edge: 20–50 GB/year
```

That is acceptable for workstation storage. The right next move is **storage observability**, not capture reduction.
