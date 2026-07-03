# Browser Memory Daemon Tests — Verification Gates

> **Audience:** maintainers and future agents.
> **Goal:** verify policy modes, capture, storage, search, deletion, UI/API, generated docs, and real Windows Chrome behavior.
> **Runtime:** Python **3.11+** (`pyproject.toml` requires `>=3.11`). Use `BMD_PYTHON=/path/to/python3.11` when the host `python3` is older.

<!-- BEGIN GENERATED:inventory-summary -->
> **Current inventory:** 84 static test functions across 16 files — 61 daemon pytest tests + 23 extension node:test tests.
<!-- END GENERATED:inventory-summary -->

---

## Primary gates

```bash
# Local verification environment.
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt

# Daemon tests — use Python 3.11+.
python -m pytest -q

# Extension tests and build.
cd extension && npm test && npm run build

# Real Windows Chrome-family e2e.
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-real-chrome-e2e.sh

# Full local gate. `run-e2e.sh` honors BMD_PYTHON, then falls back to python3.11.
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-e2e.sh

# Repo hygiene.
./scripts/secret-scan.sh
git diff --check -- .
```

`./scripts/run-e2e.sh` runs daemon tests, extension tests/build, real Chrome e2e unless `BMD_SKIP_REAL_CHROME_E2E=1`, secret scan, and whitespace check.

---

## Generated test inventory

<!-- BEGIN GENERATED:audit-run -->
Latest inventory: **84 static test functions** across **16 files** (61 daemon pytest; 23 extension node:test). Regenerate with `python3.11 scripts/generate_test_inventory.py --write`; enforce with `--check`. Counts are source-level test functions, not pytest parametrized case expansions.
<!-- END GENERATED:audit-run -->

### Per-file counts

<!-- BEGIN GENERATED:per-file-counts -->
| Test file | Runner | Test functions |
|---|---|---:|
| `daemon/tests/e2e/test_admin_api.py` | pytest | 3 |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | 1 |
| `daemon/tests/e2e/test_http_api.py` | pytest | 3 |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | 19 |
| `daemon/tests/integration/test_media_worker.py` | pytest | 15 |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | 5 |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | 2 |
| `daemon/tests/unit/test_db.py` | pytest | 1 |
| `daemon/tests/unit/test_normalize.py` | pytest | 4 |
| `daemon/tests/unit/test_policy.py` | pytest | 6 |
| `daemon/tests/unit/test_policy_store.py` | pytest | 2 |
| `extension/tests/unit/cdp_recorder.test.js` | node:test | 4 |
| `extension/tests/unit/extractor.test.js` | node:test | 11 |
| `extension/tests/unit/media_queue.test.js` | node:test | 5 |
| `extension/tests/unit/queue.test.js` | node:test | 1 |
| `extension/tests/unit/shared.test.js` | node:test | 2 |
| **Total** |  | **84** |
<!-- END GENERATED:per-file-counts -->

<details>
<summary>Full source-level test inventory</summary>

<!-- BEGIN GENERATED:test-case-inventory -->
| File | Runner | Suite | Test function | Line | Coverage note |
|---|---|---|---|---:|---|
| `daemon/tests/e2e/test_admin_api.py` | pytest | `(module)` | `test_admin_read_apis_and_ui_assets` | 57 | Admin read apis and ui assets. |
| `daemon/tests/e2e/test_admin_api.py` | pytest | `(module)` | `test_policy_rule_blocks_future_capture_and_can_be_deleted` | 121 | Policy rule blocks future capture and can be deleted. |
| `daemon/tests/e2e/test_admin_api.py` | pytest | `(module)` | `test_url_prefix_policy_rule_applies_in_all_mode_without_blocking_all_localhost` | 163 | Url prefix policy rule applies in all mode without blocking all localhost. |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | `(module)` | `test_cli_admin_commands` | 34 | Cli admin commands. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_capture_skips_legacy_media_backfill_on_request` | 46 | Http capture skips legacy media backfill on request. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_media_fetch_raw_upload_and_purge_rehydrate_controls` | 79 | Http media fetch raw upload and purge rehydrate controls. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_capture_search_forget_round_trip` | 148 | Http capture search forget round trip. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_ingest_search_redact_and_forget` | 16 | Ingest search redact and forget. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_metadata_redacted_before_fts_and_forget_by_original_url` | 41 | Metadata redacted before fts and forget by original url. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_url_path_secret_redacted_and_not_searchable` | 64 | Url path secret redacted and not searchable. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_url_userinfo_redacted_before_storage_and_fts` | 81 | Url userinfo redacted before storage and fts. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_all_mode_stores_without_redaction_and_accepts_file_urls` | 102 | All mode stores without redaction and accepts file urls. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_artifacts_are_related_to_snapshot_not_fts_and_deleted_by_forget` | 125 | Media artifacts are related to snapshot not fts and deleted by forget. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_artifact_size_gate_skips_oversized_blob` | 185 | Media artifact size gate skips oversized blob. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_global_cache_rolls_oldest_blob_when_limit_would_be_exceeded` | 221 | Media global cache rolls oldest blob when limit would be exceeded. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_domain_cache_rolls_oldest_blob_when_domain_limit_would_be_exceeded` | 243 | Media domain cache rolls oldest blob when domain limit would be exceeded. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_raw_blob_upload_rejects_truncated_body_and_infers_mime_from_url` | 264 | Raw blob upload rejects truncated body and infers mime from url. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_posted_cdp_metadata_enqueues_daemon_fetch_task` | 302 | Posted cdp metadata enqueues daemon fetch task. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_fetch_pending_media_artifacts_stores_data_url_without_indexing_media_metadata` | 341 | Fetch pending media artifacts stores data url without indexing media metadata. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_fetch_pending_media_artifacts_keeps_large_data_url_ref_intact` | 375 | Fetch pending media artifacts keeps large data url ref intact. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_fetch_reason_classification_keeps_remote_errors_out_of_failed_bucket` | 401 | Media fetch reason classification keeps remote errors out of failed bucket. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_forget_domain_includes_subdomains` | 408 | Forget domain includes subdomains. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_repeat_capture_dedupes_snapshot_but_adds_visit` | 424 | Repeat capture dedupes snapshot but adds visit. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_changed_content_creates_new_snapshot_under_same_document` | 468 | Changed content creates new snapshot under same document. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_schema_has_planned_core_tables` | 510 | Schema has planned core tables. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_capture_payload_rejects_bad_timestamp` | 519 | Capture payload rejects bad timestamp. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_processes_data_url_task_and_marks_success` | 15 | Media worker processes data url task and marks success. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_tasks_are_seeded_when_existing_unresolved_refs_have_no_task` | 38 | Media worker tasks are seeded when existing unresolved refs have no task. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_marks_pending_task_succeeded_when_artifact_already_stored` | 61 | Media worker marks pending task succeeded when artifact already stored. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_rehydrates_purged_cache_when_source_still_fetchable` | 90 | Media worker rehydrates purged cache when source still fetchable. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_normalizes_terminal_failed_artifacts` | 117 | Media worker normalizes terminal failed artifacts. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_reclassifies_legacy_blob_video_skips_as_references` | 168 | Media worker reclassifies legacy blob video skips as references. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_stores_hls_master_playlist_as_video_mp4` | 249 | Media worker stores hls master playlist as video mp4. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_legacy_hls_video_unsupported_skips` | 276 | Media worker requeues legacy hls video unsupported skips. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_snapshot_budget_skips_after_cap_raise` | 307 | Media worker requeues snapshot budget skips after cap raise. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_storage_budget_skips_after_cap_raise` | 338 | Media worker requeues storage budget skips after cap raise. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_stores_hls_audio_rendition_sidecar` | 368 | Media worker stores hls audio rendition sidecar. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_legacy_hls_audio_rendition_refs` | 395 | Media worker requeues legacy hls audio rendition refs. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_cdp_hls_manifest_refs` | 424 | Media worker requeues cdp hls manifest refs. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_marks_blob_video_refs_covered_by_cdp_bytes` | 465 | Media worker marks blob video refs covered by cdp bytes. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_classifies_uncovered_blob_video_refs_as_opaque` | 516 | Media worker classifies uncovered blob video refs as opaque. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_visit_lifecycle_event_updates_dwell_and_is_idempotent` | 9 | Visit lifecycle event updates dwell and is idempotent. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_overlapping_lifecycle_events_do_not_double_count_dwell` | 67 | Overlapping lifecycle events do not double count dwell. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_visit_lifecycle_event_can_attach_to_latest_visit_by_url` | 114 | Visit lifecycle event can attach to latest visit by url. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_visit_lifecycle_event_without_matching_visit_stores_metadata_only` | 146 | Visit lifecycle event without matching visit stores metadata only. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_visit_lifecycle_event_validates_ranges` | 168 | Visit lifecycle event validates ranges. |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | `(module)` | `test_daily_driver_health_snapshot_is_aggregate_and_redaction_safe` | 27 | Daily driver health snapshot is aggregate and redaction safe. |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | `(module)` | `test_daily_driver_health_detects_missing_extension_token` | 100 | Daily driver health detects missing extension token. |
| `daemon/tests/unit/test_db.py` | pytest | `(module)` | `test_connect_uses_extended_busy_timeout` | 5 | Connect uses extended busy timeout. |
| `daemon/tests/unit/test_normalize.py` | pytest | `(module)` | `test_normalize_url_removes_tracking_fragment_default_port_and_sorts_query` | 4 | Normalize url removes tracking fragment default port and sorts query. |
| `daemon/tests/unit/test_normalize.py` | pytest | `(module)` | `test_normalize_url_preserves_meaningful_duplicate_query_values` | 11 | Normalize url preserves meaningful duplicate query values. |
| `daemon/tests/unit/test_normalize.py` | pytest | `(module)` | `test_normalize_url_removes_empty_default_path_only_for_missing_path` | 18 | Normalize url removes empty default path only for missing path. |
| `daemon/tests/unit/test_normalize.py` | pytest | `(module)` | `test_domain_from_url_lowercases_hostname` | 23 | Domain from url lowercases hostname. |
| `daemon/tests/unit/test_policy.py` | pytest | `(module)` | `test_strict_blocks_incognito_and_sensitive_urls` | 4 | Strict blocks incognito and sensitive urls. |
| `daemon/tests/unit/test_policy.py` | pytest | `(module)` | `test_all_mode_allows_previously_blocked_surfaces` | 29 | All mode allows previously blocked surfaces. |
| `daemon/tests/unit/test_policy.py` | pytest | `(module)` | `test_balanced_and_recall_are_less_restrictive_than_strict` | 45 | Balanced and recall are less restrictive than strict. |
| `daemon/tests/unit/test_policy.py` | pytest | `(module)` | `test_allows_public_docs_url_in_all_modes` | 53 | Allows public docs url in all modes. |
| `daemon/tests/unit/test_policy.py` | pytest | `(module)` | `test_redacts_before_storage_classes` | 59 | Redacts before storage classes. |
| `daemon/tests/unit/test_policy.py` | pytest | `(module)` | `test_redacts_url_query_and_fragment` | 70 | Redacts url query and fragment. |
| `daemon/tests/unit/test_policy_store.py` | pytest | `(module)` | `test_domain_rule_rejects_port_or_path_to_prevent_overbroad_localhost_blocks` | 18 | Domain rule rejects port or path to prevent overbroad localhost blocks. |
| `daemon/tests/unit/test_policy_store.py` | pytest | `(module)` | `test_url_prefix_rule_scopes_to_port_and_path` | 25 | Url prefix rule scopes to port and path. |
| `extension/tests/unit/cdp_recorder.test.js` | node:test | `(module)` | `CDP recorder only attaches to configured X/Twitter page domains` | 10 | CDP recorder only attaches to configured X/Twitter page domains. |
| `extension/tests/unit/cdp_recorder.test.js` | node:test | `(module)` | `CDP recorder recognizes X video segment and HLS manifest responses` | 17 | CDP recorder recognizes X video segment and HLS manifest responses. |
| `extension/tests/unit/cdp_recorder.test.js` | node:test | `(module)` | `CDP recorder builds stable artifact metadata without cookies or headers` | 40 | CDP recorder builds stable artifact metadata without cookies or headers. |
| `extension/tests/unit/cdp_recorder.test.js` | node:test | `(module)` | `CDP base64 byte estimate handles padding` | 59 | CDP base64 byte estimate handles padding. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `all mode still skips hidden/form/editable/script/style/no-script extraction surfaces` | 17 | All mode still skips hidden/form/editable/script/style/no-script extraction surfaces. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `strict mode skips form and editable elements` | 26 | Strict mode skips form and editable elements. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `URL policy modes are adjustable` | 33 | URL policy modes are adjustable. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `all mode extracts readable tree text without URL filters but skips form/editable text` | 52 | All mode extracts readable tree text without URL filters but skips form/editable text. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `strict mode extracts readable tree text without form secrets` | 69 | Strict mode extracts readable tree text without form secrets. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `real document extraction in all mode still skips hidden/form/editable surfaces` | 86 | Real document extraction in all mode still skips hidden/form/editable surfaces. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `real document extraction uses strict skip traversal` | 111 | Real document extraction uses strict skip traversal. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `real document extraction records image and video artifacts without adding media text` | 136 | Real document extraction records image and video artifacts without adding media text. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `image extraction ignores empty-src document URL fallbacks` | 179 | Image extraction ignores empty-src document URL fallbacks. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `performance video resources are preserved even when image refs fill the cap` | 202 | Performance video resources are preserved even when image refs fill the cap. |
| `extension/tests/unit/extractor.test.js` | node:test | `(module)` | `collapses whitespace` | 235 | Collapses whitespace. |
| `extension/tests/unit/media_queue.test.js` | node:test | `(module)` | `media task normalization and due ordering` | 4 | Media task normalization and due ordering. |
| `extension/tests/unit/media_queue.test.js` | node:test | `(module)` | `media queue retains fetched blob until task delete` | 13 | Media queue retains fetched blob until task delete. |
| `extension/tests/unit/media_queue.test.js` | node:test | `(module)` | `future retry is not due until next_attempt_at` | 25 | Future retry is not due until next attempt at. |
| `extension/tests/unit/media_queue.test.js` | node:test | `(module)` | `stale fetching and uploading tasks become due after processing window` | 32 | Stale fetching and uploading tasks become due after processing window. |
| `extension/tests/unit/media_queue.test.js` | node:test | `(module)` | `normalizeTask requires stable artifact id for queue callers` | 40 | NormalizeTask requires stable artifact id for queue callers. |
| `extension/tests/unit/queue.test.js` | node:test | `(module)` | `queue preserves FIFO order` | 4 | Queue preserves FIFO order. |
| `extension/tests/unit/shared.test.js` | node:test | `(module)` | `daemon URL normalization strips trailing slashes` | 4 | Daemon URL normalization strips trailing slashes. |
| `extension/tests/unit/shared.test.js` | node:test | `(module)` | `auth headers include bearer token` | 9 | Auth headers include bearer token. |
<!-- END GENERATED:test-case-inventory -->

</details>

---

## Policy-mode verification matrix

| Mode | Daemon unit/integration | Extension unit | Real Chrome e2e |
|---|---|---|---|
| `all` | Allows formerly blocked URL surfaces unless explicitly blocked; stores unredacted fixture secrets. | Does not apply built-in URL blocks; still skips hidden/form/editable/script/style/no-script DOM text. | Default e2e expects banking and localhost fixtures searchable while hidden/form text stays absent. |
| `recall` | Allows profile/settings and known domains; blocks incognito/internal schemes; redacts. | Allows broad `http(s)`; blocks browser/internal schemes. | Optional via `BMD_REAL_CHROME_POLICY_MODE=recall`. |
| `balanced` | Allows normal profile/settings; blocks known high-risk domains/private hosts/query secrets; redacts. | Same class in extension prefilter. | Optional via `BMD_REAL_CHROME_POLICY_MODE=balanced`. |
| `strict` | Legacy broad keyword/domain/path/query blocks; redacts. | Legacy URL/DOM skip behavior. | Optional via `BMD_REAL_CHROME_POLICY_MODE=strict`. |

Run a real-browser e2e in a non-default mode:

```bash
BMD_PYTHON="${BMD_PYTHON:-python}" BMD_REAL_CHROME_POLICY_MODE=strict ./scripts/run-real-chrome-e2e.sh
```

---

## Daily-driver smoke checklist

After `./scripts/install-daily-driver.sh` and Chrome extension reload:

1. Confirm aggregate daily-driver health:

   ```bash
   ./scripts/daily-driver-health.sh
   ```

   The JSON should include `ok=true`. It is redaction-safe: it reports service state, loopback health, journal counts/sanitized templates, DB freshness/counts, media queue counts, storage headroom, and extension artifact state without dumping captured page text or token values.

2. If the aggregate command reports an error, isolate daemon state:

   ```bash
   systemctl --user is-active browser-memory-daemon.service
   systemctl --user is-active browser-memory-media-worker.service
   PYTHONPATH=daemon/src python3.11 -m browser_memory_daemon \
     --token "$(tr -d '\r\n' < ~/.config/browser-memory-daemon/token)" doctor
   ```

3. If needed, isolate Windows loopback:

   ```bash
   /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe \
     -NoProfile -Command "Invoke-RestMethod http://127.0.0.1:8765/health | ConvertTo-Json -Compress"
   ```

4. Confirm popup shows:

   ```text
   mode=all paused=false
   ```

5. Browse a synthetic/harmless page and search for a unique visible string.
6. If no capture appears, check popup pause state first.

---

## Documentation and generated-artifact validation

The Markdown-to-HTML renderer needs `markdown`, `pygments`, and Mermaid CLI (`mmdc`) in the docs build environment. `requirements-dev.txt` supplies the Python side; keep installed dependencies out of committed runtime data.

Mechanical checks:

```bash
python scripts/generate_test_inventory.py --check
python scripts/generate_showcase.py --spec scripts/showcase.spec.json --check
python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
git diff --check -- .
python3.11 - <<'PY'
from pathlib import Path
bad=[]
for p in Path('docs').rglob('*.md'):
    text=p.read_text()
    if text.count(chr(96) * 3) % 2:
        bad.append(str(p))
if bad:
    raise SystemExit(f'unbalanced code fences: {bad}')
print('markdown fence check passed')
PY
```

Mermaid render check when `mmdc` is available:

```bash
npx --yes @mermaid-js/mermaid-cli --version
```

The HTML companions are generated artifacts. Do not hand-edit `*.html`; edit Markdown or `scripts/showcase.spec.json`, then regenerate and run the `--check` gates.
