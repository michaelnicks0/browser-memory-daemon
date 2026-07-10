from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from . import __version__
from .blob_store import BlobStore, BlobStoreError, prefer_relative_locator
from .config import RuntimeConfig
from .migrations import LATEST_SCHEMA_VERSION, MIGRATIONS, MigrationError, migration_status, schema_fingerprint

_FORMAT_VERSION = 1
_DATABASE_BUNDLE_PATH = "database/memory.sqlite3"
_DERIVATIVE_PREFIX = "derivatives/clean-text/"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
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
        raise BackupError("atomic no-replace directory publication is unavailable on this platform")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(stage), -100, os.fsencode(destination), 1) == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise BackupError(f"destination appeared before publication: {destination}")
    raise OSError(error_number, os.strerror(error_number), str(destination))


def _publish_and_sync(stage: Path, destination: Path) -> None:
    _publish_directory(stage, destination)
    try:
        _fsync_dir(destination.parent)
    except OSError as exc:
        raise BackupError(
            f"destination was published but parent-directory fsync failed; inspect before retrying: {destination}"
        ) from exc


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    with os.fdopen(fd, "wb") as target:
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


def _write_private_text(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _secure_tree_modes(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BackupError(f"staging tree contains a symlink: {path.relative_to(root)}")
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    os.chmod(root, 0o700)


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


def _reject_symlink_components(path: Path, *, label: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise BackupError(f"{label} must not contain symlink components: {current}")


def _resolved_new_destination(path: Path, *, forbidden: tuple[Path, ...] = ()) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise BackupError("destination must be an explicit absolute path")
    _reject_symlink_components(expanded.parent, label="destination parent")
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


def _validated_source_database(config: RuntimeConfig) -> tuple[Path, tuple[int, int]]:
    source = config.db_path.expanduser()
    if source.is_symlink():
        raise BackupError("source SQLite database must not be a symlink")
    try:
        source_stat = os.lstat(source)
        data_root = config.data_root.expanduser().resolve(strict=True)
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise BackupError("source SQLite database does not exist") from exc
    if not stat.S_ISREG(source_stat.st_mode):
        raise BackupError("source SQLite database must be a regular file")
    if resolved.parent != data_root:
        raise BackupError("source SQLite database is outside the configured data root")
    return source, (source_stat.st_dev, source_stat.st_ino)


def _assert_source_identity(source: Path, expected: tuple[int, int]) -> None:
    try:
        current = os.lstat(source)
    except OSError as exc:
        raise BackupError("source SQLite database changed during backup") from exc
    if stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != expected:
        raise BackupError("source SQLite database changed during backup")


def _database_summary(db_path: Path, *, read_only: bool = False) -> dict[str, Any]:
    if read_only:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
    else:
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
        if read_only:
            fts_integrity = "relationship-check-only"
        else:
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
        and (fts_integrity == "ok" or read_only)
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


def _backup_database(source: Path, destination: Path, *, source_identity: tuple[int, int]) -> None:
    _assert_source_identity(source, source_identity)
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
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
    _assert_source_identity(source, source_identity)
    with destination.open("rb") as handle:
        os.fsync(handle.fileno())


def _derivative_rows(db_path: Path, *, read_only: bool = False) -> list[sqlite3.Row]:
    if read_only:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
    else:
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
    source_database, source_identity = _validated_source_database(config)
    try:
        migration = migration_status(config)
    except MigrationError as exc:
        raise BackupError(f"source SQLite database is not migration-compatible: {exc}") from exc
    if not migration["ready"]:
        raise BackupError("source SQLite database is not migration-compatible")
    _assert_source_identity(source_database, source_identity)
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
        stage.mkdir(mode=0o700)
        (stage / "database").mkdir(mode=0o700)
        database_path = stage / _DATABASE_BUNDLE_PATH
        _backup_database(source_database, database_path, source_identity=source_identity)
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
        _write_private_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        _secure_tree_modes(stage)
        _fsync_tree_directories(stage)
        _publish_and_sync(stage, destination)
    except BackupError:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        shutil.rmtree(stage, ignore_errors=True)
        raise BackupError(f"backup creation failed: {exc}") from exc
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
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


def _manifest_nonempty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BackupError(f"invalid backup manifest {field}")
    return value


def _manifest_sha256(value: Any) -> str:
    digest = _manifest_nonempty_string(value, field="sha256").lower()
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise BackupError("invalid backup manifest sha256")
    return digest


def _validate_manifest_provenance(manifest: dict[str, Any]) -> None:
    version = manifest.get("format_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != _FORMAT_VERSION:
        raise BackupError("unsupported backup manifest format")
    created_at = _manifest_nonempty_string(manifest.get("created_at"), field="created_at")
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BackupError("invalid backup manifest created_at") from exc
    if parsed.tzinfo is None:
        raise BackupError("invalid backup manifest created_at")
    _manifest_nonempty_string(manifest.get("application_version"), field="application_version")
    _manifest_nonempty_string(manifest.get("policy_mode"), field="policy_mode")
    if not isinstance(manifest.get("database"), dict):
        raise BackupError("invalid backup manifest database summary")


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
    try:
        manifest_path = _bundle_file_path(source, PurePosixPath("manifest.json"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BackupError("backup manifest is missing or invalid") from exc
    if not isinstance(manifest, dict):
        raise BackupError("backup manifest root must be an object")
    _validate_manifest_provenance(manifest)
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
        expected_hash = _manifest_sha256(item.get("sha256"))
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
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


def _validate_database_claim(claimed: Any, actual: dict[str, Any]) -> None:
    if not isinstance(claimed, dict):
        raise BackupError("invalid backup manifest database summary")
    if not isinstance(claimed.get("ready"), bool):
        raise BackupError("invalid backup manifest database summary: ready")
    for field in ("integrity_check", "schema_fingerprint"):
        _manifest_nonempty_string(claimed.get(field), field=f"database.{field}")
    for field in (
        "foreign_key_violations",
        "chunks_missing_fts",
        "fts_orphans",
        "missing_authoritative_text",
        "schema_version",
    ):
        _manifest_nonnegative_int(claimed.get(field), field=f"database.{field}")
    counts = claimed.get("counts")
    if not isinstance(counts, dict) or not all(isinstance(key, str) for key in counts):
        raise BackupError("invalid backup manifest database summary: counts")
    for key, value in counts.items():
        _manifest_nonnegative_int(value, field=f"database.counts.{key}")
    for field in (
        "ready",
        "integrity_check",
        "foreign_key_violations",
        "chunks_missing_fts",
        "fts_orphans",
        "missing_authoritative_text",
        "schema_version",
        "schema_fingerprint",
        "counts",
    ):
        if claimed.get(field) != actual.get(field):
            raise BackupError(f"backup manifest database summary mismatch: {field}")


def _derivative_restore_normalizations(
    db_path: Path,
    files: list[dict[str, Any]],
    *,
    included: bool,
) -> list[tuple[str, str]]:
    derivative_items = [item for item in files if item["kind"] == "clean-text-derivative"]
    if not included:
        if derivative_items:
            raise BackupError("derivative manifest files do not match inclusion policy")
        return []
    by_path = {str(item["path"]): item for item in derivative_items}
    used: set[str] = set()
    normalizations: list[tuple[str, str]] = []
    for row in _derivative_rows(db_path, read_only=True):
        locator = str(row["cleaned_text_locator"] or "")
        legacy_path = str(row["cleaned_text_path"] or "")
        expected_hash = str(row["text_hash"] or "").lower()
        candidates: list[dict[str, Any]] = []
        if locator:
            candidates = [item for path, item in by_path.items() if path == f"{_DERIVATIVE_PREFIX}{locator}"]
        elif legacy_path:
            candidates = [
                item
                for path, item in by_path.items()
                if legacy_path.replace("\\", "/").endswith(f"/{path[len(_DERIVATIVE_PREFIX):]}")
            ]
        candidates = [item for item in candidates if str(item["sha256"]).lower() == expected_hash]
        if len(candidates) != 1:
            raise BackupError(f"derivative manifest does not match referenced snapshot: {row['id']}")
        item = candidates[0]
        path = str(item["path"])
        used.add(path)
        normalizations.append((str(row["id"]), path[len(_DERIVATIVE_PREFIX) :]))
    if used != set(by_path):
        raise BackupError("derivative manifest does not match database references")
    return normalizations


def _normalize_restored_derivatives(db_path: Path, rows: list[tuple[str, str]]) -> None:
    if not rows:
        return
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executemany(
                "UPDATE snapshots SET cleaned_text_path = NULL, cleaned_text_locator = ? WHERE id = ?",
                [(locator, snapshot_id) for snapshot_id, locator in rows],
            )
    finally:
        conn.close()


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
    database_item = next(item for item in files if item["kind"] == "sqlite-database")
    bundled_database = _bundle_file_path(source, PurePosixPath(database_item["path"]))
    verified_database = _database_summary(bundled_database, read_only=True)
    if not verified_database["ready"]:
        raise BackupError("backup database failed integrity, FTS, text, or schema smoke")
    _validate_database_claim(manifest.get("database"), verified_database)
    derivative_normalizations = _derivative_restore_normalizations(
        bundled_database,
        files,
        included=bool(manifest["inclusions"]["clean_text_derivatives"]),
    )
    preview = {
        "dry_run": not execute,
        "source": str(source),
        "destination": str(destination),
        "file_count": len(files),
        "manifest_created_at": manifest.get("created_at"),
        "database": verified_database,
    }
    if not execute:
        return preview

    stage = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    if stage.exists():
        raise BackupError("restore staging path collision")
    try:
        stage.mkdir(mode=0o700)
        restore_config = _restore_config(stage)
        restore_config.data_root.mkdir(parents=True, exist_ok=True)
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
        _normalize_restored_derivatives(restore_config.db_path, derivative_normalizations)
        database = _database_summary(restore_config.db_path)
        if not database["ready"]:
            raise BackupError("restored database failed integrity, FTS, text, or schema smoke")
        _secure_tree_modes(stage)
        _fsync_tree_directories(stage)
        _publish_and_sync(stage, destination)
    except BackupError:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        shutil.rmtree(stage, ignore_errors=True)
        raise BackupError(f"backup restore failed: {exc}") from exc
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {**preview, "dry_run": False, "database": database}
