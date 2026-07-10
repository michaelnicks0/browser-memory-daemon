from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from browser_memory_daemon.backup_ops import BackupError, create_backup, restore_backup
from browser_memory_daemon.blob_store import BlobStore
from browser_memory_daemon.cli import main as cli_main
from browser_memory_daemon.config import RuntimeConfig
from browser_memory_daemon.db import audit, connect, init_db
from browser_memory_daemon.forget import forget
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.ops import snapshot_detail
from browser_memory_daemon.search import search_memory


def _runtime_config(root: Path, *, token: str) -> RuntimeConfig:
    cfg = RuntimeConfig(
        api_token=token,
        policy_mode="all",
        config_root=root / "config",
        data_root=root,
        state_root=root / "state",
        blob_root=root / "blobs",
        derivative_root=root / "blobs",
        media_root_path=root / "blobs" / "media",
        media_spool_root=None,
    )
    cfg.ensure_dirs()
    return cfg


def _source_runtime(tmp_path: Path) -> tuple[RuntimeConfig, dict]:
    cfg = _runtime_config(tmp_path / "source-runtime", token="source-token")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        conn.execute("PRAGMA wal_autocheckpoint = 0")
        stored = ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "url": "https://backup.example/entry",
                    "canonical_url": "https://backup.example/entry",
                    "title": "Backup fixture",
                    "text": "Backup restore searchable proof with complete SQLite authority.",
                    "captured_at": "2026-07-10T12:00:00Z",
                    "browser_profile": "pytest",
                    "visit_id": "visit-backup",
                }
            ),
        )
        conn.commit()
    return cfg, stored


def _refresh_database_manifest(bundle: Path) -> None:
    database = bundle / "database" / "memory.sqlite3"
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = next(entry for entry in manifest["files"] if entry["kind"] == "sqlite-database")
    content = database.read_bytes()
    item["bytes"] = len(content)
    item["sha256"] = hashlib.sha256(content).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_backup_create_is_dry_run_first_and_manifest_excludes_media_and_secrets(tmp_path):
    cfg, stored = _source_runtime(tmp_path)
    media_file = cfg.media_root / "not-backed-up.bin"
    media_file.parent.mkdir(parents=True, exist_ok=True)
    media_file.write_bytes(b"disposable-media")
    destination = tmp_path / "backup-bundle"

    preview = create_backup(cfg, destination, execute=False)
    assert preview["dry_run"] is True
    assert preview["destination"] == str(destination.resolve())
    assert not destination.exists()

    with connect(cfg.db_path) as writer:
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        audit_id = audit(writer, "backup.wal-proof", {"fixture": True})
        writer.commit()
        wal_path = Path(f"{cfg.db_path}-wal")
        assert wal_path.is_file() and wal_path.stat().st_size > 0
        created = create_backup(cfg, destination, execute=True)
    assert created["dry_run"] is False
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format_version"] == 1
    assert manifest["database"]["schema_version"] >= 11
    assert manifest["inclusions"] == {"sqlite_database": True, "clean_text_derivatives": False}
    assert [item["kind"] for item in manifest["files"]] == ["sqlite-database"]
    assert manifest["exclusions"] == [
        "api-token-and-config",
        "chrome-profile-and-extension-copy",
        "media-cache",
        "media-spool",
    ]
    manifest_text = json.dumps(manifest, sort_keys=True)
    assert "source-token" not in manifest_text
    assert "Backup restore searchable proof" not in manifest_text
    assert "https://backup.example" not in manifest_text
    assert media_file.name not in manifest_text
    assert created["database"]["integrity_check"] == "ok"
    assert created["database"]["fts_integrity_check"] == "ok"
    assert created["database"]["missing_authoritative_text"] == 0
    with sqlite3.connect(destination / "database" / "memory.sqlite3") as backup_conn:
        assert backup_conn.execute("SELECT COUNT(*) FROM audit_events WHERE id = ?", (audit_id,)).fetchone()[0] == 1
    assert stored["snapshot_id"]


def test_backup_restore_recreates_search_detail_and_forget_without_media_cache(tmp_path):
    cfg, stored = _source_runtime(tmp_path)
    bundle = tmp_path / "backup-bundle"
    create_backup(cfg, bundle, execute=True)
    destination = tmp_path / "restored-runtime"

    preview = restore_backup(bundle, destination, execute=False)
    assert preview["dry_run"] is True
    assert not destination.exists()
    restored = restore_backup(bundle, destination, execute=True)
    assert restored["database"]["integrity_check"] == "ok"
    assert restored["database"]["foreign_key_violations"] == 0
    assert restored["database"]["fts_orphans"] == 0

    restored_cfg = _runtime_config(destination, token="restored-token")
    with connect(restored_cfg.db_path) as conn:
        results = search_memory(conn, "searchable proof", limit=10)
        assert results and results[0]["snapshot_id"] == stored["snapshot_id"]
        detail = snapshot_detail(conn, restored_cfg, stored["snapshot_id"])
        assert "complete SQLite authority" in detail["text"]
        assert detail["observations"]
        forgotten = forget(conn, restored_cfg, domain="backup.example")
        assert forgotten["forgotten"] is True
        assert search_memory(conn, "searchable proof", limit=10) == []
    assert not restored_cfg.media_root.exists()


def test_restore_rejects_tampered_bundle_and_existing_destination_without_mutation(tmp_path):
    cfg, _stored = _source_runtime(tmp_path)
    with pytest.raises(BackupError, match="explicit absolute"):
        create_backup(cfg, Path("relative-backup"), execute=False)
    overlapping = cfg.data_root / "nested-backup"
    with pytest.raises(BackupError, match="must not overlap"):
        create_backup(cfg, overlapping, execute=True)
    assert not overlapping.exists()

    bundle = tmp_path / "backup-bundle"
    create_backup(cfg, bundle, execute=True)
    database = bundle / "database" / "memory.sqlite3"
    tampered = bytearray(database.read_bytes())
    tampered[-1] ^= 0x01
    database.write_bytes(tampered)
    tampered_destination = tmp_path / "tampered-restore"
    with pytest.raises(BackupError, match="hash mismatch"):
        restore_backup(bundle, tampered_destination, execute=True)
    assert not tampered_destination.exists()

    clean_bundle = tmp_path / "clean-bundle"
    create_backup(cfg, clean_bundle, execute=True)
    existing = tmp_path / "existing-runtime"
    existing.mkdir()
    sentinel = existing / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(BackupError, match="destination already exists"):
        restore_backup(clean_bundle, existing, execute=True)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_restore_rejects_traversal_and_symlinked_bundle_paths(tmp_path):
    cfg, _stored = _source_runtime(tmp_path)
    traversal_bundle = tmp_path / "traversal-bundle"
    create_backup(cfg, traversal_bundle, execute=True)
    manifest_path = traversal_bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../memory.sqlite3"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BackupError, match="invalid manifest path"):
        restore_backup(traversal_bundle, tmp_path / "traversal-restore", execute=False)

    clean_bundle = tmp_path / "clean-symlink-source"
    create_backup(cfg, clean_bundle, execute=True)
    source_link = tmp_path / "bundle-link"
    source_link.symlink_to(clean_bundle, target_is_directory=True)
    with pytest.raises(BackupError, match="not a symlink"):
        restore_backup(source_link, tmp_path / "link-restore", execute=False)

    child_link_bundle = tmp_path / "child-link-bundle"
    create_backup(cfg, child_link_bundle, execute=True)
    external_database_dir = tmp_path / "external-database"
    external_database_dir.mkdir()
    (child_link_bundle / "database" / "memory.sqlite3").replace(external_database_dir / "memory.sqlite3")
    (child_link_bundle / "database").rmdir()
    (child_link_bundle / "database").symlink_to(external_database_dir, target_is_directory=True)
    with pytest.raises(BackupError, match="contains a symlink"):
        restore_backup(child_link_bundle, tmp_path / "child-link-restore", execute=False)


def test_restore_rejects_truncated_and_newer_schema_databases_after_manifest_verification(tmp_path):
    cfg, _stored = _source_runtime(tmp_path)
    truncated_bundle = tmp_path / "truncated-bundle"
    create_backup(cfg, truncated_bundle, execute=True)
    truncated_database = truncated_bundle / "database" / "memory.sqlite3"
    truncated_database.write_bytes(truncated_database.read_bytes()[:256])
    _refresh_database_manifest(truncated_bundle)
    truncated_destination = tmp_path / "truncated-restore"
    with pytest.raises(BackupError, match="SQLite backup smoke failed"):
        restore_backup(truncated_bundle, truncated_destination, execute=True)
    assert not truncated_destination.exists()

    newer_bundle = tmp_path / "newer-bundle"
    create_backup(cfg, newer_bundle, execute=True)
    newer_database = newer_bundle / "database" / "memory.sqlite3"
    with sqlite3.connect(newer_database) as conn:
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    Path(f"{newer_database}-wal").unlink(missing_ok=True)
    Path(f"{newer_database}-shm").unlink(missing_ok=True)
    _refresh_database_manifest(newer_bundle)
    newer_destination = tmp_path / "newer-restore"
    with pytest.raises(BackupError, match="schema smoke"):
        restore_backup(newer_bundle, newer_destination, execute=True)
    assert not newer_destination.exists()


def test_atomic_publication_refuses_a_destination_created_after_preflight(tmp_path):
    import browser_memory_daemon.backup_ops as backup_ops

    stage = tmp_path / ".bundle.staging"
    stage.mkdir()
    (stage / "manifest.json").write_text("staged", encoding="utf-8")
    destination = tmp_path / "bundle"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(BackupError, match="destination appeared"):
        backup_ops._publish_directory(stage, destination)
    assert stage.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_interrupted_restore_removes_staging_and_never_publishes_destination(tmp_path, monkeypatch):
    import browser_memory_daemon.backup_ops as backup_ops

    cfg, _stored = _source_runtime(tmp_path)
    bundle = tmp_path / "interrupted-bundle"
    create_backup(cfg, bundle, execute=True)
    original_copy_stream = backup_ops._copy_stream

    def interrupted_copy(source, destination):
        original_copy_stream(source, destination)
        raise OSError("injected restore interruption")

    monkeypatch.setattr(backup_ops, "_copy_stream", interrupted_copy)
    destination = tmp_path / "interrupted-restore"
    with pytest.raises(BackupError, match="backup restore failed: injected restore interruption"):
        restore_backup(bundle, destination, execute=True)
    assert not destination.exists()
    assert list(tmp_path.glob(".interrupted-restore.staging-*")) == []


def test_backup_optionally_includes_only_referenced_contained_derivatives(tmp_path):
    cfg, stored = _source_runtime(tmp_path)
    locator = f"{stored['snapshot_id']}.txt"
    derivative = BlobStore(cfg.clean_text_root).write_text(locator, "Backup restore searchable proof with complete SQLite authority.")
    orphan = BlobStore(cfg.clean_text_root).write_text("orphan.txt", "not referenced")
    with connect(cfg.db_path) as conn:
        with conn:
            conn.execute(
                "UPDATE snapshots SET cleaned_text_path = ?, cleaned_text_locator = ? WHERE id = ?",
                (str(derivative), locator, stored["snapshot_id"]),
            )
    bundle = tmp_path / "backup-with-derivatives"
    create_backup(cfg, bundle, execute=True, include_derivatives=True)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["inclusions"]["clean_text_derivatives"] is True
    assert [item["kind"] for item in manifest["files"]] == ["sqlite-database", "clean-text-derivative"]
    assert orphan.name not in json.dumps(manifest)

    destination = tmp_path / "restored-with-derivatives"
    restore_backup(bundle, destination, execute=True)
    restored_cfg = _runtime_config(destination, token="restored-token")
    assert (restored_cfg.clean_text_root / locator).read_text(encoding="utf-8").startswith("Backup restore")
    assert not (restored_cfg.clean_text_root / orphan.name).exists()


def test_backup_cli_is_dry_run_first_for_create_and_restore(tmp_path, capsys, monkeypatch):
    for name in ("BMD_BLOB_ROOT", "BMD_DERIVATIVE_ROOT", "BMD_MEDIA_ROOT", "BMD_MEDIA_SPOOL_ROOT"):
        monkeypatch.delenv(name, raising=False)
    cfg, _stored = _source_runtime(tmp_path)
    bundle = tmp_path / "cli-bundle"
    base = ["--runtime-root", str(cfg.data_root), "--token", cfg.api_token]
    assert cli_main([*base, "backup", "create", "--destination", str(bundle)]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert not bundle.exists()
    assert cli_main([*base, "backup", "create", "--destination", str(bundle), "--execute"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is False

    destination = tmp_path / "cli-restore"
    assert cli_main(
        [*base, "backup", "restore", "--source", str(bundle), "--destination", str(destination)]
    ) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert not destination.exists()

    overlap = cfg.data_root / "restore-inside-active-runtime"
    assert cli_main(
        [*base, "backup", "restore", "--source", str(bundle), "--destination", str(overlap)]
    ) == 1
    assert "must not overlap" in json.loads(capsys.readouterr().out)["error"]
    assert not overlap.exists()

    empty_runtime = tmp_path / "empty-runtime"
    missing_base = ["--runtime-root", str(empty_runtime), "--token", "empty-token"]
    missing_bundle = tmp_path / "missing-source-bundle"
    assert cli_main([*missing_base, "backup", "create", "--destination", str(missing_bundle)]) == 1
    assert "does not exist" in json.loads(capsys.readouterr().out)["error"]
    assert not (empty_runtime / "browser-memory.sqlite3").exists()
    assert not missing_bundle.exists()
