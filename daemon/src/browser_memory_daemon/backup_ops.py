from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from . import __version__
from .blob_store import BlobStore, BlobStoreError, prefer_relative_locator
from .config import RuntimeConfig
from .migrations import LATEST_SCHEMA_VERSION, MIGRATIONS, MigrationError, migration_status, schema_fingerprint

_FORMAT_VERSION = 1
_DATABASE_BUNDLE_PATH = "database/memory.sqlite3"
_DERIVATIVE_PREFIX = "derivatives/clean-text/"
_EXCLUSIONS = [
    "api-token-and-config",
    "chrome-profile-and-extension-copy",
    "media-cache",
    "media-spool",
]


class BackupError(RuntimeError):
    pass


def _publish_directory(stage: Path, destination: Path) -> None:
    """Atomically publish without replacing a destination created after preflight."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:  # pragma: no cover - WSL/Linux provides renameat2
        if destination.exists() or destination.is_symlink():
            raise BackupError(f"destination appeared before publication: {destination}")
        os.rename(stage, destination)
        return
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(stage), -100, os.fsencode(destination), 1) == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise BackupError(f"destination appeared before publication: {destination}")
    raise OSError(error_number, os.strerror(error_number), str(destination))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_stream(source: BinaryIO, destination: Path) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with destination.open("xb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        target.flush()
        os.fsync(target.fileno())
    return size, digest.hexdigest()


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_tree_directories(root: Path) -> None:
    directories = [path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_dir(directory)
    _fsync_dir(root)


def _resolved_new_destination(path: Path, *, forbidden: tuple[Path, ...] = ()) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise BackupError("destination must be an explicit absolute path")
    try:
        parent = expanded.parent.resolve(strict=True)
    except OSError as exc:
        raise BackupError(f"destination parent does not exist: {expanded.parent}") from exc
    destination = parent / expanded.name
    if destination.exists() or destination.is_symlink():
        raise BackupError(f"destination already exists: {destination}")
    for raw_root in forbidden:
        root = raw_root.expanduser().resolve(strict=False)
        if destination == root or destination.is_relative_to(root) or root.is_relative_to(destination):
            raise BackupError("destination must not overlap an active runtime or storage root")
    return destination


def _runtime_roots(config: RuntimeConfig) -> tuple[Path, ...]:
    roots = [
        config.config_root,
        config.data_root,
        config.state_root,
        config.blob_root,
        config.clean_text_root,
        config.media_root,
    ]
    if config.media_spool_root is not None:
        roots.append(config.media_spool_root)
    return tuple(roots)


def _database_summary(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_key_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        chunks_missing_fts = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE id NOT IN (SELECT chunk_id FROM chunks_fts)"
            ).fetchone()["n"]
        )
        fts_orphans = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM chunks_fts WHERE chunk_id NOT IN (SELECT id FROM chunks)"
            ).fetchone()["n"]
        )
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('integrity-check')")
        conn.rollback()
        fts_integrity = "ok"
        missing_text = int(
            conn.execute("SELECT COUNT(*) AS n FROM snapshots WHERE cleaned_text IS NULL").fetchone()["n"]
        )
        schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        fingerprint = schema_fingerprint(conn)
        counts = {
            table: int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
            for table in ("documents", "visits", "snapshots", "chunks", "media_artifacts", "deletion_receipts")
        }
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"SQLite backup smoke failed: {exc}") from exc
    finally:
        conn.close()
    expected_fingerprint = MIGRATIONS[-1].schema_fingerprint
    ready = (
        integrity == "ok"
        and foreign_key_violations == 0
        and chunks_missing_fts == 0
        and fts_orphans == 0
        and fts_integrity == "ok"
        and missing_text == 0
        and schema_version == LATEST_SCHEMA_VERSION
        and fingerprint == expected_fingerprint
    )
    return {
        "ready": ready,
        "integrity_check": integrity,
        "foreign_key_violations": foreign_key_violations,
        "chunks_missing_fts": chunks_missing_fts,
        "fts_orphans": fts_orphans,
        "fts_integrity_check": fts_integrity,
        "missing_authoritative_text": missing_text,
        "schema_version": schema_version,
        "schema_fingerprint": fingerprint,
        "counts": counts,
    }


def _backup_database(source: Path, destination: Path) -> None:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    source_conn = sqlite3.connect(source_uri, uri=True)
    target_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(target_conn)
        target_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        target_conn.commit()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"SQLite online backup failed: {exc}") from exc
    finally:
        target_conn.close()
        source_conn.close()
    with destination.open("rb") as handle:
        os.fsync(handle.fileno())


def _derivative_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT id, cleaned_text_path, cleaned_text_locator, text_hash
            FROM snapshots
            WHERE COALESCE(cleaned_text_locator, '') != '' OR COALESCE(cleaned_text_path, '') != ''
            ORDER BY id
            """
        ).fetchall()
    finally:
        conn.close()


def _copy_derivatives(config: RuntimeConfig, db_path: Path, stage: Path) -> list[dict[str, Any]]:
    store = BlobStore(config.clean_text_root)
    files: list[dict[str, Any]] = []
    copied: dict[str, dict[str, Any]] = {}
    for row in _derivative_rows(db_path):
        locator = prefer_relative_locator(row["cleaned_text_locator"], row["cleaned_text_path"])
        resolution = store.resolve(locator, require_file=True)
        if resolution.status != "ok" or resolution.path is None:
            raise BackupError(f"referenced clean-text derivative is unavailable or outside its root: {row['id']}")
        try:
            relative = store.relative_locator(resolution.path)
            source = store.open(relative)
        except (BlobStoreError, RuntimeError) as exc:
            raise BackupError(f"cannot open referenced clean-text derivative: {row['id']}") from exc
        bundle_path = f"{_DERIVATIVE_PREFIX}{relative}"
        expected_hash = str(row["text_hash"] or "").lower()
        existing = copied.get(bundle_path)
        if existing is not None:
            if expected_hash and existing["sha256"] != expected_hash:
                raise BackupError(f"shared clean-text derivative hash mismatch: {row['id']}")
            continue
        with source:
            size, digest = _copy_stream(source, stage / PurePosixPath(bundle_path))
        if expected_hash and digest != expected_hash:
            raise BackupError(f"clean-text derivative hash mismatch: {row['id']}")
        item = {
            "path": bundle_path,
            "kind": "clean-text-derivative",
            "bytes": size,
            "sha256": digest,
        }
        copied[bundle_path] = item
        files.append(item)
    return files


def create_backup(
    config: RuntimeConfig,
    destination: Path,
    *,
    execute: bool,
    include_derivatives: bool = False,
) -> dict[str, Any]:
    destination = _resolved_new_destination(Path(destination), forbidden=_runtime_roots(config))
    if not config.db_path.is_file():
        raise BackupError("source SQLite database does not exist")
    try:
        migration = migration_status(config)
    except MigrationError as exc:
        raise BackupError(f"source SQLite database is not migration-compatible: {exc}") from exc
    if not migration["ready"]:
        raise BackupError("source SQLite database is not migration-compatible")
    preview = {
        "dry_run": not execute,
        "destination": str(destination),
        "include_derivatives": bool(include_derivatives),
        "exclusions": list(_EXCLUSIONS),
    }
    if not execute:
        return preview

    stage = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    if stage.exists():
        raise BackupError("backup staging path collision")
    try:
        (stage / "database").mkdir(parents=True)
        database_path = stage / _DATABASE_BUNDLE_PATH
        _backup_database(config.db_path, database_path)
        database = _database_summary(database_path)
        if not database["ready"]:
            raise BackupError("online backup failed database integrity or compatibility smoke")
        database_file = {
            "path": _DATABASE_BUNDLE_PATH,
            "kind": "sqlite-database",
            "bytes": database_path.stat().st_size,
            "sha256": _sha256_file(database_path),
        }
        files = [database_file]
        if include_derivatives:
            files.extend(_copy_derivatives(config, database_path, stage))
        manifest = {
            "format_version": _FORMAT_VERSION,
            "created_at": _utc_now(),
            "application_version": __version__,
            "policy_mode": config.policy_mode,
            "database": database,
            "files": files,
            "inclusions": {
                "sqlite_database": True,
                "clean_text_derivatives": bool(include_derivatives),
            },
            "exclusions": list(_EXCLUSIONS),
        }
        manifest_path = stage / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with manifest_path.open("rb") as handle:
            os.fsync(handle.fileno())
        _fsync_tree_directories(stage)
        _publish_directory(stage, destination)
        _fsync_dir(destination.parent)
    except BackupError:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        shutil.rmtree(stage, ignore_errors=True)
        raise BackupError(f"backup creation failed: {exc}") from exc
    return {
        **preview,
        "dry_run": False,
        "manifest": str(destination / "manifest.json"),
        "database": database,
        "file_count": len(files),
    }


def _safe_manifest_path(raw: Any) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise BackupError(f"invalid manifest path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise BackupError(f"invalid manifest path: {raw!r}")
    return path


def _manifest_nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BackupError(f"invalid backup manifest {field}")
    return int(value)


def _bundle_file_path(source: Path, relative: PurePosixPath) -> Path:
    candidate = source
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise BackupError(f"backup path contains a symlink: {relative.as_posix()}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise BackupError(f"backup file is missing: {relative.as_posix()}") from exc
    if not resolved.is_relative_to(source) or not resolved.is_file():
        raise BackupError(f"backup file is missing or not regular: {relative.as_posix()}")
    return resolved


def _load_and_verify_bundle(source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if source.is_symlink() or not source.is_dir():
        raise BackupError("backup source must be a real directory")
    manifest_path = source / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError("backup manifest is missing or invalid") from exc
    if not isinstance(manifest, dict):
        raise BackupError("backup manifest root must be an object")
    if manifest.get("format_version") != _FORMAT_VERSION:
        raise BackupError("unsupported backup manifest format")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise BackupError("backup manifest contains no files")
    verified: list[dict[str, Any]] = []
    declared: set[str] = {"manifest.json"}
    database_count = 0
    derivative_count = 0
    for item in files:
        if not isinstance(item, dict):
            raise BackupError("invalid backup manifest file entry")
        relative = _safe_manifest_path(item.get("path"))
        relative_text = relative.as_posix()
        if relative_text in declared:
            raise BackupError(f"duplicate backup manifest path: {relative_text}")
        declared.add(relative_text)
        path = _bundle_file_path(source, relative)
        expected_size = _manifest_nonnegative_int(item.get("bytes"), field="byte count")
        if path.stat().st_size != expected_size:
            raise BackupError(f"backup file size mismatch: {relative_text}")
        actual_hash = _sha256_file(path)
        if actual_hash != str(item.get("sha256", "")).lower():
            raise BackupError(f"backup file hash mismatch: {relative_text}")
        kind = str(item.get("kind", ""))
        if kind == "sqlite-database":
            database_count += 1
            if relative_text != _DATABASE_BUNDLE_PATH:
                raise BackupError("database backup path is not canonical")
        elif kind == "clean-text-derivative":
            derivative_count += 1
            if not relative_text.startswith(_DERIVATIVE_PREFIX):
                raise BackupError("derivative backup path is not canonical")
        else:
            raise BackupError(f"unsupported backup file kind: {kind}")
        verified.append({**item, "path": relative_text, "kind": kind})
    if database_count != 1:
        raise BackupError("backup manifest must contain exactly one SQLite database")
    inclusions = manifest.get("inclusions")
    if not isinstance(inclusions, dict) or inclusions.get("sqlite_database") is not True:
        raise BackupError("backup manifest inclusion flags do not match declared files")
    derivative_inclusion = inclusions.get("clean_text_derivatives")
    if not isinstance(derivative_inclusion, bool) or (derivative_count > 0 and not derivative_inclusion):
        raise BackupError("backup manifest inclusion flags do not match declared files")
    if manifest.get("exclusions") != _EXCLUSIONS:
        raise BackupError("backup manifest exclusions do not match the supported format")
    actual = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    extras = sorted(actual - declared)
    if extras:
        raise BackupError(f"backup bundle contains undeclared files: {extras[0]}")
    return manifest, verified


def _restore_config(root: Path) -> RuntimeConfig:
    data_root = root
    blob_root = data_root / "blobs"
    return RuntimeConfig(
        api_token="restore-smoke",
        policy_mode="all",
        config_root=root / "config",
        data_root=data_root,
        state_root=root / "state",
        blob_root=blob_root,
        derivative_root=blob_root,
        media_root_path=blob_root / "media",
        media_spool_root=None,
    )


def restore_backup(
    source: Path,
    destination: Path,
    *,
    execute: bool,
    active_config: RuntimeConfig | None = None,
) -> dict[str, Any]:
    source_input = Path(source).expanduser()
    if not source_input.is_absolute():
        raise BackupError("backup source must be an explicit absolute path")
    if source_input.is_symlink():
        raise BackupError("backup source must be a real directory, not a symlink")
    try:
        source = source_input.resolve(strict=True)
    except OSError as exc:
        raise BackupError("backup source does not exist") from exc
    forbidden = (source,) if active_config is None else (source, *_runtime_roots(active_config))
    destination = _resolved_new_destination(Path(destination), forbidden=forbidden)
    manifest, files = _load_and_verify_bundle(source)
    preview = {
        "dry_run": not execute,
        "source": str(source),
        "destination": str(destination),
        "file_count": len(files),
        "manifest_created_at": manifest.get("created_at"),
    }
    if not execute:
        return preview

    stage = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    if stage.exists():
        raise BackupError("restore staging path collision")
    try:
        restore_config = _restore_config(stage)
        restore_config.data_root.mkdir(parents=True)
        for item in files:
            source_path = _bundle_file_path(source, PurePosixPath(item["path"]))
            if item["kind"] == "sqlite-database":
                target_path = restore_config.db_path
            else:
                locator = item["path"][len(_DERIVATIVE_PREFIX) :]
                resolution = BlobStore(restore_config.clean_text_root).resolve(locator, require_file=False)
                if resolution.status != "ok" or resolution.path is None:
                    raise BackupError("restored derivative locator escapes destination")
                target_path = resolution.path
            with source_path.open("rb") as handle:
                size, digest = _copy_stream(handle, target_path)
            if size != int(item["bytes"]) or digest != str(item["sha256"]).lower():
                raise BackupError(f"restored file verification failed: {item['path']}")
        database = _database_summary(restore_config.db_path)
        if not database["ready"]:
            raise BackupError("restored database failed integrity, FTS, text, or schema smoke")
        _fsync_tree_directories(stage)
        _publish_directory(stage, destination)
        _fsync_dir(destination.parent)
    except BackupError:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        shutil.rmtree(stage, ignore_errors=True)
        raise BackupError(f"backup restore failed: {exc}") from exc
    return {**preview, "dry_run": False, "database": database}
