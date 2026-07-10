# Browser Memory Daemon Tests — Verification Gates

> **Audience:** maintainers and future agents.
> **Goal:** verify policy modes, capture, storage, search, deletion, UI/API, generated docs, and real Windows Chrome behavior.
> **Runtime:** Python **3.11+** (`pyproject.toml` requires `>=3.11`). Use `BMD_PYTHON=/path/to/python3.11` when the host `python3` is older.

<!-- BEGIN GENERATED:inventory-summary -->
> **Current inventory:** 230 static test functions across 36 files — 200 daemon pytest tests + 30 extension node:test tests.
<!-- END GENERATED:inventory-summary -->

---

## Primary gates

```bash
# Local verification environment.
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt

# Hermetic network-free pre-commit gate: Ruff, strict mypy, branch coverage,
# Python/Node tests, generated inventory, secret/diff checks, and XDG sentinel.
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-fast-gate.sh

# Daemon tests — use Python 3.11+.
python -m pytest -q

# Extension tests and build.
cd extension && npm test && npm run build

# Real Windows Chrome-family e2e. Default matrix runs `all` and `strict`.
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-real-chrome-e2e.sh

# Synthetic advisory performance benchmark.
./scripts/run-performance-benchmarks.sh --small --json >/tmp/bmd_benchmark.json

# Full local gate. `run-e2e.sh` honors BMD_PYTHON, then falls back to python3.11.
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-e2e.sh

# Repo hygiene.
./scripts/secret-scan.sh
git diff --check -- .
```

`./scripts/run-fast-gate.sh` is the short network-free authority. It redirects all default user roots into `/tmp`, runs targeted Ruff and strict mypy, measures full Python branch coverage against the 80% evidence-derived floor, runs all Python/Node tests, and fails if the redirected default-XDG roots receive a file. See [`coverage-baseline.md`](coverage-baseline.md).

`./scripts/run-e2e.sh` remains the broad authority: daemon tests, extension tests/build, the real Chrome e2e matrix unless `BMD_SKIP_REAL_CHROME_E2E=1`, secret scan, and whitespace check.

`python3.11 scripts/generate_test_inventory.py --check` is a hard static gate over `requirements/catalog.toml`: it enforces unique stable IDs/aliases, explicit normative revisions, existing implementation/evidence paths, resolvable test node IDs, and validation evidence for active requirements. It also regenerates the catalog-owned requirement tables and volatile static test counts across the documentation set.

`./scripts/run-performance-benchmarks.sh --small --json` emits machine-readable synthetic benchmark evidence for ingest, search, recent/timeline/detail, read endpoint audit writes, media-worker task selection/run, and DB/WAL/blob sidecar growth. Budgets are advisory until a later ticket/ADR promotes measured thresholds to hard gates.

---

## Durability/concurrency stress harness

Use this bounded local stress harness before changing SQLite write paths, media-worker leases, capture transaction boundaries, or request-handler DB behavior:

```bash
./scripts/run-concurrency-stress.sh
```

The harness uses a temporary isolated runtime root by default. It drives concurrent public HTTP captures, lifecycle events, search/detail reads, media blob uploads, and media-worker `run_once` passes against one SQLite database. It prints JSON and exits non-zero if any operation fails, SQLite `integrity_check` is not `ok`, chunks are missing FTS rows, or expected synthetic rows are absent.

Useful knobs:

```bash
./scripts/run-concurrency-stress.sh \
  --captures 24 \
  --reader-rounds 24 \
  --media-worker-runs 8 \
  --max-workers 32
```

Use `--runtime-root PATH` only for explicit fixture roots; do not point the stress harness at the daily-driver runtime data unless you intentionally want to mutate it.

---

## Generated test inventory

<!-- BEGIN GENERATED:audit-run -->
Latest inventory: **230 static test functions** across **36 files** (200 daemon pytest; 30 extension node:test). Regenerate with `python3.11 scripts/generate_test_inventory.py --write`; enforce with `--check`. Counts are source-level test functions, not pytest parametrized case expansions.
<!-- END GENERATED:audit-run -->

## Requirements traceability gate

<!-- BEGIN GENERATED:traceability-gate -->
Traceability gate: **✅ pass**.

| Check | Result |
|---|---|
| Catalog requirements | 43 (37 active; 6 planned) |
| Duplicate stable IDs | none |
| Invalid requirement definitions | none |
| Duplicate plan/local aliases | none |
| Legacy alias errors | none |
| Missing implementation paths | none |
| Unresolved evidence/test nodes | none |
| Active requirements without validation evidence | none |
| Normative changes without revision increment | none |
| Requirements removed without catalog disposition | none |
| Catalog load errors | none |
| Static test inventory measured | 230 tests / 36 files |
<!-- END GENERATED:traceability-gate -->

### Per-file counts
<!-- BEGIN GENERATED:per-file-counts -->
| Test file | Runner | Test functions |
|---|---|---:|
| `daemon/tests/e2e/test_admin_api.py` | pytest | 3 |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | 6 |
| `daemon/tests/e2e/test_concurrency_stress.py` | pytest | 2 |
| `daemon/tests/e2e/test_daily_driver_install.py` | pytest | 2 |
| `daemon/tests/e2e/test_generate_test_inventory.py` | pytest | 4 |
| `daemon/tests/e2e/test_http_api.py` | pytest | 6 |
| `daemon/tests/e2e/test_performance_benchmarks.py` | pytest | 5 |
| `daemon/tests/e2e/test_read_model_indexes.py` | pytest | 1 |
| `daemon/tests/e2e/test_ui_dashboard_smoke.py` | pytest | 4 |
| `daemon/tests/integration/test_backup_restore.py` | pytest | 18 |
| `daemon/tests/integration/test_capture_observations.py` | pytest | 8 |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | 25 |
| `daemon/tests/integration/test_media_storage.py` | pytest | 10 |
| `daemon/tests/integration/test_media_tasks.py` | pytest | 2 |
| `daemon/tests/integration/test_media_worker.py` | pytest | 28 |
| `daemon/tests/integration/test_migrations.py` | pytest | 18 |
| `daemon/tests/integration/test_observation_reads.py` | pytest | 2 |
| `daemon/tests/integration/test_storage_reconcile.py` | pytest | 4 |
| `daemon/tests/integration/test_text_authority.py` | pytest | 2 |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | 6 |
| `daemon/tests/unit/test_blob_store.py` | pytest | 5 |
| `daemon/tests/unit/test_config.py` | pytest | 5 |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | 6 |
| `daemon/tests/unit/test_db.py` | pytest | 2 |
| `daemon/tests/unit/test_media_models.py` | pytest | 4 |
| `daemon/tests/unit/test_media_store.py` | pytest | 3 |
| `daemon/tests/unit/test_normalize.py` | pytest | 4 |
| `daemon/tests/unit/test_policy.py` | pytest | 6 |
| `daemon/tests/unit/test_policy_store.py` | pytest | 4 |
| `daemon/tests/unit/test_storage_paths.py` | pytest | 5 |
| `extension/tests/unit/cdp_recorder.test.js` | node:test | 4 |
| `extension/tests/unit/extractor.test.js` | node:test | 11 |
| `extension/tests/unit/media_queue.test.js` | node:test | 6 |
| `extension/tests/unit/queue.test.js` | node:test | 1 |
| `extension/tests/unit/service_worker.test.js` | node:test | 6 |
| `extension/tests/unit/shared.test.js` | node:test | 2 |
| **Total** |  | **230** |
<!-- END GENERATED:per-file-counts -->

<details>
<summary>Full source-level test inventory</summary>

<!-- BEGIN GENERATED:test-case-inventory -->
| File | Runner | Suite | Test function | Line | Coverage note |
|---|---|---|---|---:|---|
| `daemon/tests/e2e/test_admin_api.py` | pytest | `(module)` | `test_admin_read_apis_and_ui_assets` | 56 | Admin read apis and ui assets. |
| `daemon/tests/e2e/test_admin_api.py` | pytest | `(module)` | `test_policy_rule_blocks_future_capture_and_can_be_deleted` | 137 | Policy rule blocks future capture and can be deleted. |
| `daemon/tests/e2e/test_admin_api.py` | pytest | `(module)` | `test_url_prefix_policy_rule_applies_in_all_mode_without_blocking_all_localhost` | 179 | Url prefix policy rule applies in all mode without blocking all localhost. |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | `(module)` | `test_cli_admin_commands` | 34 | Cli admin commands. |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | `(module)` | `test_cli_migrate_check_is_read_only_then_execute_applies_pending_steps` | 97 | Cli migrate check is read only then execute applies pending steps. |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | `(module)` | `test_cli_snapshot_text_reconcile_defaults_to_dry_run` | 126 | Cli snapshot text reconcile defaults to dry run. |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | `(module)` | `test_cli_media_spool_status_and_drain_are_dry_run_safe` | 150 | Cli media spool status and drain are dry run safe. |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | `(module)` | `test_cli_storage_reconcile_defaults_to_dry_run` | 170 | Cli storage reconcile defaults to dry run. |
| `daemon/tests/e2e/test_cli_admin.py` | pytest | `(module)` | `test_cli_backup_create_and_restore_validate_then_execute` | 190 | Cli backup create and restore validate then execute. |
| `daemon/tests/e2e/test_concurrency_stress.py` | pytest | `(module)` | `test_concurrency_stress_harness_exercises_shared_sqlite_db` | 6 | Concurrency stress harness exercises shared sqlite db. |
| `daemon/tests/e2e/test_concurrency_stress.py` | pytest | `(module)` | `test_concurrency_stress_cli_prints_json_for_explicit_runtime` | 36 | Concurrency stress cli prints json for explicit runtime. |
| `daemon/tests/e2e/test_daily_driver_install.py` | pytest | `(module)` | `test_install_daily_driver_dry_run_is_non_mutating` | 11 | Install daily driver dry run is non mutating. |
| `daemon/tests/e2e/test_daily_driver_install.py` | pytest | `(module)` | `test_install_daily_driver_required_mount_guard_fails_before_writes` | 53 | Install daily driver required mount guard fails before writes. |
| `daemon/tests/e2e/test_generate_test_inventory.py` | pytest | `(module)` | `test_generate_test_inventory_reports_catalog_traceability_success` | 140 | Generate test inventory reports catalog traceability success. |
| `daemon/tests/e2e/test_generate_test_inventory.py` | pytest | `(module)` | `test_generate_test_inventory_check_fails_for_catalog_gaps` | 162 | Generate test inventory check fails for catalog gaps. |
| `daemon/tests/e2e/test_generate_test_inventory.py` | pytest | `(module)` | `test_catalog_rejects_duplicate_ids` | 188 | Catalog rejects duplicate ids. |
| `daemon/tests/e2e/test_generate_test_inventory.py` | pytest | `(module)` | `test_catalog_statement_change_requires_revision_increment` | 202 | Catalog statement change requires revision increment. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_capture_skips_request_time_db_initialization_after_startup` | 62 | Http capture skips request time db initialization after startup. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_upload_get_and_purge_use_bounded_spool_during_media_root_outage` | 94 | Http upload get and purge use bounded spool during media root outage. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_media_fetch_raw_upload_and_purge_rehydrate_controls` | 165 | Http media fetch raw upload and purge rehydrate controls. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_capture_search_forget_round_trip` | 234 | Http capture search forget round trip. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_api_contract_errors_methods_and_limits_are_json` | 349 | Http api contract errors methods and limits are json. |
| `daemon/tests/e2e/test_http_api.py` | pytest | `(module)` | `test_http_policy_rule_duplicate_creation_returns_existing_semantic_rule` | 393 | Http policy rule duplicate creation returns existing semantic rule. |
| `daemon/tests/e2e/test_performance_benchmarks.py` | pytest | `(module)` | `test_performance_benchmark_path_invariant_rejects_blob_escape` | 47 | Performance benchmark path invariant rejects blob escape. |
| `daemon/tests/e2e/test_performance_benchmarks.py` | pytest | `(module)` | `test_performance_benchmark_subprocess_does_not_write_default_home_blob_root` | 64 | Performance benchmark subprocess does not write default home blob root. |
| `daemon/tests/e2e/test_performance_benchmarks.py` | pytest | `(module)` | `test_performance_benchmark_temp_runtime_cleanup_stays_inside_tmp_home` | 100 | Performance benchmark temp runtime cleanup stays inside tmp home. |
| `daemon/tests/e2e/test_performance_benchmarks.py` | pytest | `(module)` | `test_performance_benchmark_json_output_is_structured` | 132 | Performance benchmark json output is structured. |
| `daemon/tests/e2e/test_performance_benchmarks.py` | pytest | `(module)` | `test_performance_benchmark_human_summary_is_compact` | 169 | Performance benchmark human summary is compact. |
| `daemon/tests/e2e/test_read_model_indexes.py` | pytest | `(module)` | `test_read_model_ordered_queries_use_schema_indexes` | 12 | Read model ordered queries use schema indexes. |
| `daemon/tests/e2e/test_ui_dashboard_smoke.py` | pytest | `(module)` | `test_ui_dashboard_shell_serves_bootstrap_and_core_panels` | 39 | Ui dashboard shell serves bootstrap and core panels. |
| `daemon/tests/e2e/test_ui_dashboard_smoke.py` | pytest | `(module)` | `test_ui_dashboard_static_asset_path_traversal_is_rejected` | 72 | Ui dashboard static asset path traversal is rejected. |
| `daemon/tests/e2e/test_ui_dashboard_smoke.py` | pytest | `(module)` | `test_ui_dashboard_rejects_non_loopback_host_header` | 82 | Ui dashboard rejects non loopback host header. |
| `daemon/tests/e2e/test_ui_dashboard_smoke.py` | pytest | `(module)` | `test_ui_dashboard_smoke_runner_executes_bootstrap_empty_and_error_states` | 93 | Ui dashboard smoke runner executes bootstrap empty and error states. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_backup_create_is_dry_run_first_and_manifest_excludes_media_and_secrets` | 83 | Backup create is dry run first and manifest excludes media and secrets. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_backup_restore_recreates_search_detail_and_forget_without_media_cache` | 127 | Backup restore recreates search detail and forget without media cache. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_restore_rejects_tampered_bundle_and_existing_destination_without_mutation` | 154 | Restore rejects tampered bundle and existing destination without mutation. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_restore_rejects_traversal_and_symlinked_bundle_paths` | 192 | Restore rejects traversal and symlinked bundle paths. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_restore_rejects_truncated_and_newer_schema_databases_after_manifest_verification` | 221 | Restore rejects truncated and newer schema databases after manifest verification. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_atomic_publication_refuses_a_destination_created_after_preflight` | 249 | Atomic publication refuses a destination created after preflight. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_interrupted_restore_removes_staging_and_never_publishes_destination` | 266 | Interrupted restore removes staging and never publishes destination. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_backup_optionally_includes_only_referenced_contained_derivatives` | 286 | Backup optionally includes only referenced contained derivatives. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_backup_and_restore_force_private_tree_permissions_despite_umask` | 311 | Backup and restore force private tree permissions despite umask. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_backup_rejects_symlinked_or_out_of_root_source_database` | 328 | Backup rejects symlinked or out of root source database. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_restore_rejects_symlinked_manifest_and_validates_database_during_dry_run` | 339 | Restore rejects symlinked manifest and validates database during dry run. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_restore_rejects_malformed_or_incomplete_manifest_contract` | 372 | Restore rejects malformed or incomplete manifest contract. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_restore_requires_derivative_manifest_to_match_database_and_rebases_legacy_reference` | 401 | Restore requires derivative manifest to match database and rebases legacy reference. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_restore_rejects_invalid_json_root_and_unknown_manifest_version` | 438 | Restore rejects invalid json root and unknown manifest version. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_restore_dry_run_rejects_database_semantic_mismatch_matrix` | 448 | Restore dry run rejects database semantic mismatch matrix. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_default_bundle_excludes_populated_config_state_media_spool_and_secret_bytes` | 473 | Default bundle excludes populated config state media spool and secret bytes. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_backup_interrupt_cleanup_and_post_publication_fsync_state_are_explicit` | 494 | Backup interrupt cleanup and post publication fsync state are explicit. |
| `daemon/tests/integration/test_backup_restore.py` | pytest | `(module)` | `test_backup_cli_is_dry_run_first_for_create_and_restore` | 527 | Backup cli is dry run first for create and restore. |
| `daemon/tests/integration/test_capture_observations.py` | pytest | `(module)` | `test_same_visit_records_multiple_unchanged_observations_without_replacing_visit` | 36 | Same visit records multiple unchanged observations without replacing visit. |
| `daemon/tests/integration/test_capture_observations.py` | pytest | `(module)` | `test_same_visit_changed_content_links_each_observation_to_contemporaneous_snapshot` | 86 | Same visit changed content links each observation to contemporaneous snapshot. |
| `daemon/tests/integration/test_capture_observations.py` | pytest | `(module)` | `test_multiple_visits_can_observe_one_deduplicated_snapshot` | 111 | Multiple visits can observe one deduplicated snapshot. |
| `daemon/tests/integration/test_capture_observations.py` | pytest | `(module)` | `test_out_of_order_observations_preserve_temporal_bounds_and_latest_claim_provenance` | 141 | Out of order observations preserve temporal bounds and latest claim provenance. |
| `daemon/tests/integration/test_capture_observations.py` | pytest | `(module)` | `test_media_references_keep_their_capture_observation_provenance` | 193 | Media references keep their capture observation provenance. |
| `daemon/tests/integration/test_capture_observations.py` | pytest | `(module)` | `test_observation_retry_is_idempotent_and_conflicting_reuse_fails` | 251 | Observation retry is idempotent and conflicting reuse fails. |
| `daemon/tests/integration/test_capture_observations.py` | pytest | `(module)` | `test_cross_origin_canonical_is_a_non_authoritative_claim_and_visit_fk_survives_recapture` | 301 | Cross origin canonical is a non authoritative claim and visit fk survives recapture. |
| `daemon/tests/integration/test_capture_observations.py` | pytest | `(module)` | `test_visit_id_cannot_be_reused_for_a_different_observed_navigation` | 378 | Visit id cannot be reused for a different observed navigation. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_ingest_search_redact_and_forget` | 31 | Ingest search redact and forget. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_metadata_redacted_before_fts_and_forget_by_original_url` | 58 | Metadata redacted before fts and forget by original url. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_url_path_secret_redacted_and_not_searchable` | 83 | Url path secret redacted and not searchable. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_url_userinfo_redacted_before_storage_and_fts` | 100 | Url userinfo redacted before storage and fts. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_all_mode_stores_without_redaction_and_accepts_file_urls` | 121 | All mode stores without redaction and accepts file urls. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_all_mode_forget_url_uses_literal_selector_but_redacts_receipt_scope` | 144 | All mode forget url uses literal selector but redacts receipt scope. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_forget_requires_one_literal_selector` | 171 | Forget requires one literal selector. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_artifacts_are_related_to_snapshot_not_fts_and_deleted_by_forget` | 187 | Media artifacts are related to snapshot not fts and deleted by forget. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_ingest_and_media_write_to_configured_blob_root` | 249 | Ingest and media write to configured blob root. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_blob_path_consumers_reject_db_paths_outside_configured_roots` | 306 | Blob path consumers reject db paths outside configured roots. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_blob_root_migration_copies_files_and_rewrites_db_paths` | 385 | Blob root migration copies files and rewrites db paths. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_artifact_size_gate_skips_oversized_blob` | 497 | Media artifact size gate skips oversized blob. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_global_cache_rolls_oldest_blob_when_limit_would_be_exceeded` | 533 | Media global cache rolls oldest blob when limit would be exceeded. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_domain_cache_rolls_oldest_blob_when_domain_limit_would_be_exceeded` | 560 | Media domain cache rolls oldest blob when domain limit would be exceeded. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_raw_blob_upload_rejects_truncated_body_and_infers_mime_from_url` | 581 | Raw blob upload rejects truncated body and infers mime from url. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_posted_cdp_metadata_enqueues_daemon_fetch_task` | 619 | Posted cdp metadata enqueues daemon fetch task. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_fetch_pending_media_artifacts_stores_data_url_without_indexing_media_metadata` | 657 | Fetch pending media artifacts stores data url without indexing media metadata. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_fetch_pending_media_artifacts_keeps_large_data_url_ref_intact` | 691 | Fetch pending media artifacts keeps large data url ref intact. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_media_fetch_reason_classification_keeps_remote_errors_out_of_failed_bucket` | 717 | Media fetch reason classification keeps remote errors out of failed bucket. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_forget_domain_includes_subdomains` | 724 | Forget domain includes subdomains. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_repeat_capture_dedupes_snapshot_but_adds_visit` | 740 | Repeat capture dedupes snapshot but adds visit. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_concurrent_duplicate_capture_is_idempotent_for_snapshot_chunks_and_fts` | 785 | Concurrent duplicate capture is idempotent for snapshot chunks and fts. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_changed_content_creates_new_snapshot_under_same_document` | 828 | Changed content creates new snapshot under same document. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_schema_has_planned_core_tables` | 871 | Schema has planned core tables. |
| `daemon/tests/integration/test_ingest_search_forget.py` | pytest | `(module)` | `test_capture_payload_rejects_bad_timestamp` | 893 | Capture payload rejects bad timestamp. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_unavailable_external_media_root_spools_then_drains_with_hash_verification` | 74 | Unavailable external media root spools then drains with hash verification. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_failed_first_publication_removes_new_blob_and_spool_reservation` | 161 | Failed first publication removes new blob and spool reservation. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_failed_write_transaction_start_aborts_stage_and_releases_spool_reservation` | 190 | Failed write transaction start aborts stage and releases spool reservation. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_failed_replacement_preserves_previous_blob_and_removes_candidate` | 209 | Failed replacement preserves previous blob and removes candidate. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_metadata_refresh_reports_the_preserved_stored_state` | 241 | Metadata refresh reports the preserved stored state. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_replacement_admission_excludes_current_artifact_and_preserves_it_on_row_failure` | 259 | Replacement admission excludes current artifact and preserves it on row failure. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_spool_reservations_serialize_concurrent_cap_checks` | 297 | Spool reservations serialize concurrent cap checks. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_spool_capacity_accounts_for_existing_files_and_exact_headroom` | 322 | Spool capacity accounts for existing files and exact headroom. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_concurrent_same_artifact_writers_hold_distinct_reservations` | 340 | Concurrent same artifact writers hold distinct reservations. |
| `daemon/tests/integration/test_media_storage.py` | pytest | `(module)` | `test_text_and_provenance_commit_when_external_media_has_no_spool` | 366 | Text and provenance commit when external media has no spool. |
| `daemon/tests/integration/test_media_tasks.py` | pytest | `(module)` | `test_media_task_repository_allows_only_one_concurrent_lease_owner` | 53 | Media task repository allows only one concurrent lease owner. |
| `daemon/tests/integration/test_media_tasks.py` | pytest | `(module)` | `test_media_task_repository_preserves_terminal_state_unless_force_reset` | 75 | Media task repository preserves terminal state unless force reset. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_guarded_public_fetch_rejects_dns_to_private_without_opening` | 103 | Guarded public fetch rejects dns to private without opening. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_guarded_public_fetch_rejects_ipv6_loopback_literal_without_resolving` | 125 | Guarded public fetch rejects ipv6 loopback literal without resolving. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_guarded_public_fetch_allowlisted_private_host_omits_referer` | 145 | Guarded public fetch allowlisted private host omits referer. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_guarded_public_fetch_revalidates_public_to_private_redirect` | 173 | Guarded public fetch revalidates public to private redirect. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_guarded_public_fetch_detects_redirect_loop` | 197 | Guarded public fetch detects redirect loop. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_guarded_hls_revalidates_private_child_url` | 221 | Guarded hls revalidates private child url. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_guarded_hls_enforces_total_request_budget` | 248 | Guarded hls enforces total request budget. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_processes_data_url_task_and_marks_success` | 276 | Media worker processes data url task and marks success. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_init_db_does_not_repeat_historical_media_task_seed` | 299 | Init db does not repeat historical media task seed. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_marks_pending_task_succeeded_when_artifact_already_stored` | 321 | Media worker marks pending task succeeded when artifact already stored. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_fetch_pending_media_artifacts_respects_active_lease_and_recovers_stale_lease` | 359 | Fetch pending media artifacts respects active lease and recovers stale lease. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_capture_media_fetch_on_capture_background_uses_task_leasing` | 398 | Capture media fetch on capture background uses task leasing. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_concurrent_media_blob_writes_use_distinct_temp_files` | 450 | Concurrent media blob writes use distinct temp files. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_rehydrates_purged_cache_when_source_still_fetchable` | 500 | Media worker rehydrates purged cache when source still fetchable. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_purge_media_cache_skips_db_paths_outside_media_root` | 527 | Purge media cache skips db paths outside media root. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_normalizes_terminal_failed_artifacts` | 563 | Media worker normalizes terminal failed artifacts. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_retry_backoff_releases_lease_and_waits_until_due` | 614 | Media worker retry backoff releases lease and waits until due. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_reclassifies_legacy_blob_video_skips_as_references` | 657 | Media worker reclassifies legacy blob video skips as references. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_stores_hls_master_playlist_as_video_mp4` | 738 | Media worker stores hls master playlist as video mp4. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_hls_assembly_uses_single_deadline_across_segments` | 766 | Hls assembly uses single deadline across segments. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_legacy_hls_video_unsupported_skips` | 799 | Media worker requeues legacy hls video unsupported skips. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_snapshot_budget_skips_after_cap_raise` | 831 | Media worker requeues snapshot budget skips after cap raise. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_storage_budget_skips_after_cap_raise` | 863 | Media worker requeues storage budget skips after cap raise. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_stores_hls_audio_rendition_sidecar` | 893 | Media worker stores hls audio rendition sidecar. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_legacy_hls_audio_rendition_refs` | 921 | Media worker requeues legacy hls audio rendition refs. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_requeues_cdp_hls_manifest_refs` | 951 | Media worker requeues cdp hls manifest refs. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_marks_blob_video_refs_covered_by_cdp_bytes` | 992 | Media worker marks blob video refs covered by cdp bytes. |
| `daemon/tests/integration/test_media_worker.py` | pytest | `(module)` | `test_media_worker_classifies_uncovered_blob_video_refs_as_opaque` | 1042 | Media worker classifies uncovered blob video refs as opaque. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_fresh_database_migrates_to_ordered_versioned_ledger_and_preserves_fts` | 117 | Fresh database migrates to ordered versioned ledger and preserves fts. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_unversioned_current_schema_is_stamped_then_historical_seed_runs_once` | 158 | Unversioned current schema is stamped then historical seed runs once. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_capture_observation_and_url_claim_schema_enforces_expand_contract` | 188 | Capture observation and url claim schema enforces expand contract. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_version_three_fixture_upgrades_once_to_capture_model_expand_schema` | 258 | Version three fixture upgrades once to capture model expand schema. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_version_five_backfills_only_evidence_supported_historical_relationships` | 293 | Version five backfills only evidence supported historical relationships. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_version_six_backfills_only_unambiguous_media_observation_links` | 398 | Version six backfills only unambiguous media observation links. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_version_seven_preserves_claimed_visit_identity_for_historical_events` | 500 | Version seven preserves claimed visit identity for historical events. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_version_eight_adds_nullable_relative_locators` | 562 | Version eight adds nullable relative locators. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_version_nine_backfills_hash_verified_chunks_and_new_ingest_uses_sqlite_authority` | 596 | Version nine backfills hash verified chunks and new ingest uses sqlite authority. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_version_ten_adds_media_storage_tiers_and_spool_reservations` | 651 | Version ten adds media storage tiers and spool reservations. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_version_eleven_adds_and_backfills_blob_lifecycle_records` | 697 | Version eleven adds and backfills blob lifecycle records. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_repeated_migration_is_a_noop_and_schema_has_no_recurring_repair_dml` | 761 | Repeated migration is a noop and schema has no recurring repair dml. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_concurrent_fresh_migration_applies_each_ledger_step_once` | 782 | Concurrent fresh migration applies each ledger step once. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_checksum_mismatch_and_unknown_newer_version_fail_closed` | 803 | Checksum mismatch and unknown newer version fail closed. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_unknown_unversioned_schema_is_not_stamped` | 821 | Unknown unversioned schema is not stamped. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_injected_migration_failure_rolls_back_step_and_ledger` | 835 | Injected migration failure rolls back step and ledger. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_destructive_migration_creates_online_backup_that_restores_search` | 864 | Destructive migration creates online backup that restores search. |
| `daemon/tests/integration/test_migrations.py` | pytest | `(module)` | `test_destructive_migration_refuses_insufficient_backup_headroom_before_writes` | 902 | Destructive migration refuses insufficient backup headroom before writes. |
| `daemon/tests/integration/test_observation_reads.py` | pytest | `(module)` | `test_observation_first_reads_preserve_contemporaneous_snapshots_and_unique_visit_summary` | 40 | Observation first reads preserve contemporaneous snapshots and unique visit summary. |
| `daemon/tests/integration/test_observation_reads.py` | pytest | `(module)` | `test_legacy_visit_fallback_is_explicit_and_uses_its_linked_snapshot_not_latest_document_snapshot` | 146 | Legacy visit fallback is explicit and uses its linked snapshot not latest document snapshot. |
| `daemon/tests/integration/test_storage_reconcile.py` | pytest | `(module)` | `test_forget_persists_retryable_tombstone_before_database_cascade` | 67 | Forget persists retryable tombstone before database cascade. |
| `daemon/tests/integration/test_storage_reconcile.py` | pytest | `(module)` | `test_media_purge_remains_pending_until_tombstoned_bytes_are_deleted` | 115 | Media purge remains pending until tombstoned bytes are deleted. |
| `daemon/tests/integration/test_storage_reconcile.py` | pytest | `(module)` | `test_concurrent_tombstone_processors_delete_once_and_converge` | 177 | Concurrent tombstone processors delete once and converge. |
| `daemon/tests/integration/test_storage_reconcile.py` | pytest | `(module)` | `test_storage_reconcile_reports_and_repairs_missing_orphan_and_stale_stage` | 216 | Storage reconcile reports and repairs missing orphan and stale stage. |
| `daemon/tests/integration/test_text_authority.py` | pytest | `(module)` | `test_new_capture_commits_complete_sqlite_text_without_creating_blob_root` | 12 | New capture commits complete sqlite text without creating blob root. |
| `daemon/tests/integration/test_text_authority.py` | pytest | `(module)` | `test_reconcile_promotes_only_hash_verified_contained_legacy_sidecar` | 79 | Reconcile promotes only hash verified contained legacy sidecar. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_visit_lifecycle_event_updates_dwell_and_is_idempotent` | 10 | Visit lifecycle event updates dwell and is idempotent. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_lifecycle_dwell_uses_interval_union_for_overlap_containment_adjacency_and_out_of_order` | 68 | Lifecycle dwell uses interval union for overlap containment adjacency and out of order. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_legacy_visit_lifecycle_event_without_visit_id_can_attach_by_url` | 117 | Legacy visit lifecycle event without visit id can attach by url. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_visit_lifecycle_event_without_matching_visit_stores_metadata_only` | 151 | Visit lifecycle event without matching visit stores metadata only. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_claimed_visit_identity_does_not_fall_back_by_url_and_reconciles_after_delayed_capture` | 173 | Claimed visit identity does not fall back by url and reconciles after delayed capture. |
| `daemon/tests/integration/test_visit_lifecycle.py` | pytest | `(module)` | `test_visit_lifecycle_event_validates_ranges` | 271 | Visit lifecycle event validates ranges. |
| `daemon/tests/unit/test_blob_store.py` | pytest | `(module)` | `test_blob_store_stages_streams_verifies_hash_and_commits_atomically` | 8 | Blob store stages streams verifies hash and commits atomically. |
| `daemon/tests/unit/test_blob_store.py` | pytest | `(module)` | `test_blob_store_mismatch_aborts_stage_without_publishing` | 35 | Blob store mismatch aborts stage without publishing. |
| `daemon/tests/unit/test_blob_store.py` | pytest | `(module)` | `test_blob_store_rejects_traversal_symlink_escape_and_cross_root_stage` | 47 | Blob store rejects traversal symlink escape and cross root stage. |
| `daemon/tests/unit/test_blob_store.py` | pytest | `(module)` | `test_blob_store_delete_reports_outcomes_without_touching_outside_paths` | 68 | Blob store delete reports outcomes without touching outside paths. |
| `daemon/tests/unit/test_blob_store.py` | pytest | `(module)` | `test_blob_store_concurrent_writers_publish_whole_file_and_leave_no_stages` | 82 | Blob store concurrent writers publish whole file and leave no stages. |
| `daemon/tests/unit/test_config.py` | pytest | `(module)` | `test_blob_root_can_be_moved_independently_from_runtime_root` | 7 | Blob root can be moved independently from runtime root. |
| `daemon/tests/unit/test_config.py` | pytest | `(module)` | `test_required_blob_root_mount_degrades_media_without_blocking_local_sqlite` | 28 | Required blob root mount degrades media without blocking local sqlite. |
| `daemon/tests/unit/test_config.py` | pytest | `(module)` | `test_required_blob_root_mount_allows_mounted_blob_root` | 41 | Required blob root mount allows mounted blob root. |
| `daemon/tests/unit/test_config.py` | pytest | `(module)` | `test_explicit_external_media_root_requires_mount_identity_and_marker` | 59 | Explicit external media root requires mount identity and marker. |
| `daemon/tests/unit/test_config.py` | pytest | `(module)` | `test_media_spool_requires_explicit_local_root_and_positive_cap` | 88 | Media spool requires explicit local root and positive cap. |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | `(module)` | `test_daily_driver_health_snapshot_is_aggregate_and_redaction_safe` | 81 | Daily driver health snapshot is aggregate and redaction safe. |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | `(module)` | `test_daily_driver_health_media_queue_uses_datetime_comparisons_and_reports_worker_throughput` | 159 | Daily driver health media queue uses datetime comparisons and reports worker throughput. |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | `(module)` | `test_daily_driver_health_detects_missing_extension_token` | 240 | Daily driver health detects missing extension token. |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | `(module)` | `test_daily_driver_health_reports_required_blob_mount_failure` | 274 | Daily driver health reports required blob mount failure. |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | `(module)` | `test_daily_driver_health_detects_insecure_token_permissions_and_process_args` | 314 | Daily driver health detects insecure token permissions and process args. |
| `daemon/tests/unit/test_daily_driver_health.py` | pytest | `(module)` | `test_daily_driver_health_detects_low_headroom_and_service_start_churn` | 356 | Daily driver health detects low headroom and service start churn. |
| `daemon/tests/unit/test_db.py` | pytest | `(module)` | `test_connect_uses_extended_busy_timeout` | 5 | Connect uses extended busy timeout. |
| `daemon/tests/unit/test_db.py` | pytest | `(module)` | `test_init_db_enforces_wal_and_connection_pragmas` | 12 | Init db enforces wal and connection pragmas. |
| `daemon/tests/unit/test_media_models.py` | pytest | `(module)` | `test_media_facade_preserves_public_state_and_task_symbols` | 15 | Media facade preserves public state and task symbols. |
| `daemon/tests/unit/test_media_models.py` | pytest | `(module)` | `test_media_state_taxonomy_separates_internal_storage_recovery_states_from_caller_input` | 23 | Media state taxonomy separates internal storage recovery states from caller input. |
| `daemon/tests/unit/test_media_models.py` | pytest | `(module)` | `test_media_transition_matrices_preserve_terminal_and_recovery_boundaries` | 32 | Media transition matrices preserve terminal and recovery boundaries. |
| `daemon/tests/unit/test_media_models.py` | pytest | `(module)` | `test_fetch_reason_classification_is_independent_from_media_facade` | 46 | Fetch reason classification is independent from media facade. |
| `daemon/tests/unit/test_media_store.py` | pytest | `(module)` | `test_media_facade_preserves_admission_api_identity` | 4 | Media facade preserves admission api identity. |
| `daemon/tests/unit/test_media_store.py` | pytest | `(module)` | `test_media_store_owns_blob_admission_and_accounting_helpers` | 8 | Media store owns blob admission and accounting helpers. |
| `daemon/tests/unit/test_media_store.py` | pytest | `(module)` | `test_media_facade_preserves_artifact_store_api_identity` | 13 | Media facade preserves artifact store api identity. |
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
| `daemon/tests/unit/test_policy_store.py` | pytest | `(module)` | `test_domain_rule_rejects_port_or_path_to_prevent_overbroad_localhost_blocks` | 20 | Domain rule rejects port or path to prevent overbroad localhost blocks. |
| `daemon/tests/unit/test_policy_store.py` | pytest | `(module)` | `test_url_prefix_rule_scopes_to_port_and_path` | 27 | Url prefix rule scopes to port and path. |
| `daemon/tests/unit/test_policy_store.py` | pytest | `(module)` | `test_policy_rule_creation_is_semantically_idempotent_under_concurrency` | 49 | Policy rule creation is semantically idempotent under concurrency. |
| `daemon/tests/unit/test_policy_store.py` | pytest | `(module)` | `test_init_db_rejects_schema_drift_instead_of_replaying_policy_dedupe` | 68 | Init db rejects schema drift instead of replaying policy dedupe. |
| `daemon/tests/unit/test_storage_paths.py` | pytest | `(module)` | `test_storage_identifier_grammars_and_server_stems_are_stable` | 14 | Storage identifier grammars and server stems are stable. |
| `daemon/tests/unit/test_storage_paths.py` | pytest | `(module)` | `test_contained_child_path_rejects_unsafe_parts_and_symlink_escape` | 27 | Contained child path rejects unsafe parts and symlink escape. |
| `daemon/tests/unit/test_storage_paths.py` | pytest | `(module)` | `test_contained_child_path_create_root_is_explicit` | 42 | Contained child path create root is explicit. |
| `daemon/tests/unit/test_storage_paths.py` | pytest | `(module)` | `test_resolve_db_path_reports_empty_invalid_outside_missing_and_ok` | 49 | Resolve db path reports empty invalid outside missing and ok. |
| `daemon/tests/unit/test_storage_paths.py` | pytest | `(module)` | `test_resolve_db_path_rejects_symlinked_file_outside_root` | 70 | Resolve db path rejects symlinked file outside root. |
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
| `extension/tests/unit/media_queue.test.js` | node:test | `(module)` | `media task due-state classifier rejects terminal and malformed processing states` | 46 | Media task due-state classifier rejects terminal and malformed processing states. |
| `extension/tests/unit/queue.test.js` | node:test | `(module)` | `queue preserves FIFO order` | 4 | Queue preserves FIFO order. |
| `extension/tests/unit/service_worker.test.js` | node:test | `(module)` | `service worker preserves queued captures while daemon is down and drains them after reload` | 183 | Service worker preserves queued captures while daemon is down and drains them after reload. |
| `extension/tests/unit/service_worker.test.js` | node:test | `(module)` | `service worker keeps navigation identity stable per URL state and emits a new observation per extraction` | 229 | Service worker keeps navigation identity stable per URL state and emits a new observation per extraction. |
| `extension/tests/unit/service_worker.test.js` | node:test | `(module)` | `service worker queue overflow characterization preserves old captures but drops the new capture` | 273 | Service worker queue overflow characterization preserves old captures but drops the new capture. |
| `extension/tests/unit/service_worker.test.js` | node:test | `(module)` | `service worker skips missing token and pause without mutating capture queue, then resumes` | 301 | Service worker skips missing token and pause without mutating capture queue, then resumes. |
| `extension/tests/unit/service_worker.test.js` | node:test | `(module)` | `service worker injection respects stale token, pause, and strict URL controls` | 332 | Service worker injection respects stale token, pause, and strict URL controls. |
| `extension/tests/unit/service_worker.test.js` | node:test | `(module)` | `service worker media upload retries keep fetched blob until successful upload` | 361 | Service worker media upload retries keep fetched blob until successful upload. |
| `extension/tests/unit/shared.test.js` | node:test | `(module)` | `daemon URL normalization strips trailing slashes` | 4 | Daemon URL normalization strips trailing slashes. |
| `extension/tests/unit/shared.test.js` | node:test | `(module)` | `auth headers include bearer token` | 9 | Auth headers include bearer token. |
<!-- END GENERATED:test-case-inventory -->

</details>

---

## Policy-mode verification matrix

| Mode | Daemon unit/integration | Extension unit | Real Chrome e2e |
|---|---|---|---|
| `all` | Allows formerly blocked URL surfaces unless explicitly blocked; stores unredacted fixture secrets. | Does not apply built-in URL blocks; still skips hidden/form/editable/script/style/no-script DOM text. | Default e2e matrix expects banking and localhost fixtures searchable while hidden/form text stays absent, explicit URL-prefix blocks stay absent, pause skips capture, media sidecars store, and lifecycle queues drain. |
| `recall` | Allows profile/settings and known domains; blocks incognito/internal schemes; redacts. | Allows broad `http(s)`; blocks browser/internal schemes. | Optional via `BMD_REAL_CHROME_POLICY_MODE=recall`. |
| `balanced` | Allows normal profile/settings; blocks known high-risk domains/private hosts/query secrets; redacts. | Same class in extension prefilter. | Optional via `BMD_REAL_CHROME_POLICY_MODE=balanced`. |
| `strict` | Legacy broad keyword/domain/path/query blocks; redacts. | Legacy URL/DOM skip behavior. | Default e2e matrix expects banking/private localhost fixtures absent while allowed/SPAs/media/lifecycle still work. |

Run the default all+strict real-browser matrix:

```bash
BMD_PYTHON="${BMD_PYTHON:-python}" ./scripts/run-real-chrome-e2e.sh
```

Run one mode while debugging:

```bash
BMD_PYTHON="${BMD_PYTHON:-python}" BMD_REAL_CHROME_POLICY_MODE=strict ./scripts/run-real-chrome-e2e.sh
```

Run a custom matrix:

```bash
BMD_PYTHON="${BMD_PYTHON:-python}" BMD_REAL_CHROME_MATRIX_MODES="all strict balanced recall" ./scripts/run-real-chrome-e2e.sh
```

---

## Daily-driver smoke checklist

After `./scripts/install-daily-driver.sh` and Chrome extension reload:

1. Confirm aggregate daily-driver health:

   ```bash
   ./scripts/daily-driver-health.sh
   ```

   The JSON should include `ok=true`. It is redaction-safe: it reports service state, process-argument token secrecy, loopback health, journal counts/sanitized templates, DB freshness/counts, media queue counts, storage headroom, protected token/env/unit artifact checks, and extension artifact state without dumping captured page text or token values.

   To verify install inputs without touching live services or Chrome artifacts:

   ```bash
   ./scripts/install-daily-driver.sh --dry-run
   ./scripts/install-daily-driver.sh --check
   ```

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
