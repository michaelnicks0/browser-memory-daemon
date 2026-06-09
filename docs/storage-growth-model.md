# Browser Memory Daemon Storage Growth Model

> **Audience:** Operator and future maintainers
> **Scope:** Estimate how large the current Chrome → WSL browser-memory daemon will grow under real browsing.
> **Status:** ✅ Initial empirical model from live daemon DB + local Chrome History aggregates.

---

## TL;DR

The current implementation is **text-only plus SQLite/FTS**, so growth is manageable.

Using Operator's recent Chrome History baseline and the daemon's current storage multiplier, the most realistic planning range is:

| Usage posture | Assumption | Expected growth |
|---|---:|---:|
| Light / filtered day | 100 snapshots/day, current mean text size | ~1.6 GB/year |
| Actual-ish baseline | ~250 snapshots/day, current mean text size | ~4.0 GB/year |
| Busy baseline | ~350 snapshots/day, current mean text size | ~5.6 GB/year |
| Heavy browsing | 500 snapshots/day, current mean text size | ~8.1 GB/year |
| Very heavy / dynamic pages | 500 snapshots/day, p90 text size | ~23.7 GB/year |
| Extreme | 1000 snapshots/day, p90 text size | ~47.4 GB/year |

Practical expectation: **5–15 GB/year** for current text-only exact recall, with heavy/dynamic browsing pushing above that. This is not a disk-space crisis on a workstation, but it is enough to justify a storage monitor, periodic `VACUUM`/compaction, and later schema optimization.

---

## Data sources used

| Source | What was measured | Notes |
|---|---|---|
| Live daemon DB | Current row counts, SQLite page stats, FTS/table sizes, clean-text blob sizes | `~/.local/share/browser-memory-daemon/browser-memory.sqlite3` |
| Live daemon blob tree | Clean text files under `blobs/clean-text/` | File sizes only; no content dumped. |
| Chrome History copy | 1/3/7/14/30/90 day visit and unique-URL aggregates | Copied locked DB to temp; aggregate counts only; no URLs/domains written here. |
| Current code behavior | Text-only extraction, chunking, FTS5 duplication, lifecycle metadata | No screenshots, no full HTML, no assets, no embeddings yet. |

---

## Current live storage snapshot

Measured current daemon state:

| Metric | Value |
|---|---:|
| Documents | 20 |
| Visits | 37 |
| Snapshots | 53 |
| Chunks | 243 |
| Visit events | 72 |
| Audit events | 281 |
| Main SQLite DB | 2.03 MiB |
| Clean-text blobs | 0.37 MiB |
| Runtime root total | 2.40 MiB |
| SQLite free pages | 70 |

Current extracted-text distribution:

| Text per snapshot | Bytes | Approx KiB |
|---|---:|---:|
| Median | 3,649 | 3.6 KiB |
| Mean | 7,296 | 7.1 KiB |
| p75 | 10,850 | 10.6 KiB |
| p90 | 21,447 | 20.9 KiB |
| p95 | 29,048 | 28.4 KiB |
| Max | 29,065 | 28.4 KiB |

Chunking distribution:

| Chunks per snapshot | Value |
|---|---:|
| Median | 2 |
| Mean | 4.58 |
| p75 | 7 |
| p90 | 12 |
| p95 | 17 |
| Max | 17 |

---

## Where the bytes go

Current SQLite `dbstat` top storage consumers:

| Component | Bytes | Role |
|---|---:|---|
| `chunks` | 610,304 | Searchable chunk text + metadata. |
| `chunks_fts_content` | 593,920 | FTS content shadow copy. |
| `chunks_fts_data` | 274,432 | FTS index data. |
| `audit_events` | 69,632 | Capture/search/visit audit metadata. |
| `visit_events` | 36,864 | Dwell/lifecycle metadata. |
| `snapshots` | 24,576 | Snapshot metadata. |
| `visits` | 20,480 | Visit metadata. |
| `documents` | 12,288 | Document identity metadata. |

Current storage multiplier:

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

## Operator's Chrome usage baseline

Recent Chrome History aggregate counts:

| Window | Visits | Unique URL IDs | Rough hosts |
|---|---:|---:|---:|
| Last 1 day | 365 | 218 | 37 |
| Last 3 days | 1,159 | 737 | 70 |
| Last 7 days | 1,159 | 737 | 70 |
| Last 14 days | 2,551 | 1,689 | 139 |
| Last 30 days | 8,917 | 5,780 | 374 |
| Last 90 days | 29,738 | 22,251 | 752 |

30-day daily distribution:

| Daily aggregate | Visits/day | Unique URLs/day |
|---|---:|---:|
| Mean | 343 | 249 |
| Median | 382 | 285 |
| p75 | 499 | 354 |
| p90 | 543 | 426 |
| Max | 601 | 431 |

Interpretation:

- Chrome History visits are not exactly daemon snapshots.
- A single page can produce several daemon snapshots due delayed capture / SPA changes.
- Repeated unchanged pages dedupe into visits without duplicating snapshot/chunk/FTS rows.
- Using **250–350 snapshots/day** is a reasonable baseline range for current browsing.
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

Chrome-history-driven estimates using current mean text size:

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
| Images/assets/video cache | Unbounded; can become tens/hundreds of GB quickly. |

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
- Add a local warning threshold only:
  - warn at 10 GB, 25 GB, 50 GB;
  - never auto-delete.

### Medium term

- Migrate FTS to external-content mode if the DB grows beyond ~10 GB.
- Add `sqlite optimize` / `VACUUM` maintenance command.
- Add optional export/backup before any compaction work.

### Long term

- If semantic search lands, store embeddings compactly (`float16` or quantized) unless quality demands float32.
- Avoid screenshots/assets unless explicitly scoped; they dominate storage.

---

## Bottom line

For Operator's current local-first all-mode setup:

```text
Expected:  ~4–8 GB/year
Likely planning envelope: 5–15 GB/year
Heavy/dynamic edge: 20–50 GB/year
```

That is acceptable for workstation storage. The right next move is **storage observability**, not capture reduction.
