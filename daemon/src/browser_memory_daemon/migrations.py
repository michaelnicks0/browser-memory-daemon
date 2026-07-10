from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time
import uuid

from .config import RuntimeConfig
from .db import connect
from .migration_steps import MIGRATIONS, MigrationStep, migration_checksum


LEDGER_TABLE = "schema_migrations"
V1_SCHEMA_FINGERPRINT = str(MIGRATIONS[0].schema_fingerprint)
LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version
MIN_BACKUP_HEADROOM_BYTES = 16 * 1024 * 1024
LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


class MigrationError(RuntimeError):
    pass


class MigrationCompatibilityError(MigrationError):
    pass


class MigrationPreflightError(MigrationError):
    pass


class MigrationExecutionError(MigrationError):
    def __init__(self, message: str, *, backup_path: Path | None = None):
        super().__init__(message)
        self.backup_path = backup_path


def _validated_steps(steps: Sequence[MigrationStep]) -> tuple[MigrationStep, ...]:
    ordered = tuple(steps)
    versions = [step.version for step in ordered]
    expected = list(range(1, len(ordered) + 1))
    if versions != expected:
        raise MigrationCompatibilityError(
            f"migration versions must be ordered and contiguous: expected {expected}, got {versions}"
        )
    names = [step.name for step in ordered]
    if len(set(names)) != len(names):
        raise MigrationCompatibilityError("migration names must be unique")

    def is_sha256(value: str) -> bool:
        return len(value) == 64 and all(character in "0123456789abcdef" for character in value)

    if any(not is_sha256(step.checksum) for step in ordered):
        raise MigrationCompatibilityError("migration checksums must be SHA-256 hex digests")
    if ordered[0].schema_fingerprint is None:
        raise MigrationCompatibilityError("migration version 1 must declare its schema fingerprint")
    if any(
        step.schema_fingerprint is not None and not is_sha256(step.schema_fingerprint)
        for step in ordered
    ):
        raise MigrationCompatibilityError("declared schema fingerprints must be SHA-256 hex digests")
    return ordered


def _schema_rows(conn: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for row in conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type, name"
    ).fetchall():
        object_type, name, table_name, sql = tuple(row)
        if name.startswith("sqlite_") or name == LEDGER_TABLE or name.startswith("chunks_fts_"):
            continue
        rows.append((object_type, name, table_name, " ".join(sql.split())))
    return rows


def schema_fingerprint(conn: sqlite3.Connection) -> str:
    material = json.dumps(
        _schema_rows(conn), separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _ledger_exists(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table' AND name = ?",
            (LEDGER_TABLE,),
        ).fetchone()[0]
        == 1
    )


def _status_from_connection(
    conn: sqlite3.Connection, *, steps: Sequence[MigrationStep]
) -> dict:
    ordered = _validated_steps(steps)
    latest = ordered[-1].version
    expected_by_version = {step.version: step for step in ordered}
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if user_version > latest:
        raise MigrationCompatibilityError(
            f"database has newer schema version {user_version}; this binary supports {latest}"
        )

    rows = _schema_rows(conn)
    fingerprint = schema_fingerprint(conn) if rows else None
    ledger_exists = _ledger_exists(conn)
    applied_rows: list[sqlite3.Row | tuple] = []
    applied_versions: list[int] = []
    if ledger_exists:
        try:
            applied_rows = conn.execute(
                "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
            ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise MigrationCompatibilityError(f"invalid migration ledger schema: {exc}") from exc
        applied_versions = [int(row["version"] if isinstance(row, sqlite3.Row) else row[0]) for row in applied_rows]
        if applied_versions:
            maximum = max(applied_versions)
            if maximum > latest:
                raise MigrationCompatibilityError(
                    f"migration ledger contains newer schema version {maximum}; this binary supports {latest}"
                )
            expected_versions = list(range(1, maximum + 1))
            if applied_versions != expected_versions:
                raise MigrationCompatibilityError(
                    f"migration ledger is not contiguous: expected {expected_versions}, got {applied_versions}"
                )
            for row in applied_rows:
                version = int(row["version"] if isinstance(row, sqlite3.Row) else row[0])
                name = str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
                checksum = str(row["checksum"] if isinstance(row, sqlite3.Row) else row[2])
                expected_step = expected_by_version[version]
                if name != expected_step.name:
                    raise MigrationCompatibilityError(
                        f"migration name mismatch at version {version}: expected {expected_step.name}, got {name}"
                    )
                if checksum != expected_step.checksum:
                    raise MigrationCompatibilityError(
                        f"migration checksum mismatch at version {version}: expected {expected_step.checksum}, got {checksum}"
                    )
        maximum = max(applied_versions, default=0)
        if user_version != maximum:
            raise MigrationCompatibilityError(
                f"PRAGMA user_version {user_version} does not match migration ledger version {maximum}"
            )
        expected_fingerprint = (
            next(
                step.schema_fingerprint
                for step in reversed(ordered[:maximum])
                if step.schema_fingerprint is not None
            )
            if maximum
            else None
        )
        if maximum >= 1 and fingerprint != expected_fingerprint:
            raise MigrationCompatibilityError(
                f"schema fingerprint mismatch: expected {expected_fingerprint}, got {fingerprint}"
            )
        state = "current" if maximum == latest else ("pending" if maximum else "uninitialized")
        current_version = maximum
    else:
        if user_version != 0:
            raise MigrationCompatibilityError(
                f"unversioned database has unexpected PRAGMA user_version {user_version}"
            )
        if not rows:
            state = "uninitialized"
            current_version = 0
        elif fingerprint == V1_SCHEMA_FINGERPRINT:
            state = "unversioned-current"
            current_version = 0
        else:
            raise MigrationCompatibilityError(
                f"unrecognized unversioned schema fingerprint: {fingerprint}"
            )

    pending = [step for step in ordered if step.version > current_version]
    return {
        "compatible": True,
        "ready": state == "current",
        "state": state,
        "current_version": current_version,
        "latest_version": latest,
        "user_version": user_version,
        "schema_fingerprint": fingerprint,
        "pending_versions": [step.version for step in pending],
        "pending_migrations": [
            {
                "version": step.version,
                "name": step.name,
                "checksum": step.checksum,
                "destructive": step.destructive,
            }
            for step in pending
        ],
        "backup_required": any(step.destructive for step in pending),
    }


def _read_only_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_wal_mode(conn: sqlite3.Connection) -> None:
    for attempt in range(7):
        try:
            mode = str(conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]).lower()
            if mode != "wal":
                raise MigrationCompatibilityError(f"SQLite refused WAL journal mode: {mode}")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 6:
                raise
            time.sleep(0.05 * (2**attempt))


def migration_status(
    config: RuntimeConfig, *, steps: Sequence[MigrationStep] = MIGRATIONS
) -> dict:
    ordered = _validated_steps(steps)
    if not config.db_path.exists():
        return {
            "compatible": True,
            "ready": False,
            "state": "uninitialized",
            "current_version": 0,
            "latest_version": ordered[-1].version,
            "user_version": 0,
            "schema_fingerprint": None,
            "pending_versions": [step.version for step in ordered],
            "pending_migrations": [
                {
                    "version": step.version,
                    "name": step.name,
                    "checksum": step.checksum,
                    "destructive": step.destructive,
                }
                for step in ordered
            ],
            "backup_required": any(step.destructive for step in ordered),
        }
    try:
        with _read_only_connection(config.db_path) as conn:
            return _status_from_connection(conn, steps=ordered)
    except MigrationError:
        raise
    except sqlite3.DatabaseError as exc:
        raise MigrationCompatibilityError(f"cannot inspect SQLite migration state: {exc}") from exc


def _sql_statements(script: str) -> Iterable[str]:
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                yield statement
            buffer = ""
    if buffer.strip():
        raise MigrationCompatibilityError("migration SQL ends with an incomplete statement")


def _insert_ledger_row(conn: sqlite3.Connection, step: MigrationStep) -> None:
    conn.execute(
        "INSERT INTO schema_migrations(version, name, checksum) VALUES (?, ?, ?)",
        (step.version, step.name, step.checksum),
    )
    conn.execute(f"PRAGMA user_version = {step.version}")


def _apply_step(
    conn: sqlite3.Connection,
    step: MigrationStep,
    *,
    backup_path: Path | None,
) -> bool:
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(LEDGER_SQL)
        existing = conn.execute(
            "SELECT name, checksum FROM schema_migrations WHERE version = ?",
            (step.version,),
        ).fetchone()
        if existing is not None:
            if existing["name"] != step.name or existing["checksum"] != step.checksum:
                raise MigrationCompatibilityError(
                    f"concurrent migration history mismatch at version {step.version}"
                )
            conn.commit()
            return False
        for statement in _sql_statements(step.sql):
            conn.execute(statement)
        if step.apply is not None:
            step.apply(conn)
        _insert_ledger_row(conn, step)
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        raise MigrationExecutionError(
            f"migration {step.version} ({step.name}) failed: {exc}",
            backup_path=backup_path,
        ) from exc


def _stamp_unversioned_v1(conn: sqlite3.Connection, step: MigrationStep) -> bool:
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(LEDGER_SQL)
        existing = conn.execute(
            "SELECT name, checksum FROM schema_migrations WHERE version = 1"
        ).fetchone()
        if existing is not None:
            if existing["name"] != step.name or existing["checksum"] != step.checksum:
                raise MigrationCompatibilityError("concurrent version-1 stamp history mismatch")
            conn.commit()
            return False
        _insert_ledger_row(conn, step)
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        raise MigrationExecutionError(f"failed to stamp validated version 1 schema: {exc}") from exc


def _source_bytes(db_path: Path) -> int:
    return sum(
        path.stat().st_size
        for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm"))
        if path.exists()
    )


def _preflight_backup_headroom(
    config: RuntimeConfig,
    *,
    disk_usage_fn: Callable[[Path], object],
) -> None:
    required = max(MIN_BACKUP_HEADROOM_BYTES, _source_bytes(config.db_path) * 2)
    free = int(getattr(disk_usage_fn(config.state_root), "free"))
    if free < required:
        raise MigrationPreflightError(
            f"insufficient disk headroom for migration backup: required {required} bytes, available {free}"
        )


def _online_backup(conn: sqlite3.Connection, config: RuntimeConfig) -> Path:
    backup_dir = config.state_root / "migration-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"memory-v{conn.execute('PRAGMA user_version').fetchone()[0]}-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
    destination = sqlite3.connect(backup_path)
    try:
        conn.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise MigrationPreflightError("online migration backup failed SQLite integrity_check")
        if destination.execute("PRAGMA foreign_key_check").fetchall():
            raise MigrationPreflightError("online migration backup failed foreign_key_check")
    except sqlite3.DatabaseError as exc:
        raise MigrationPreflightError(f"online migration backup failed: {exc}") from exc
    finally:
        destination.close()
    return backup_path


def migrate_database(
    config: RuntimeConfig,
    *,
    execute: bool = False,
    allow_destructive: bool = False,
    steps: Sequence[MigrationStep] = MIGRATIONS,
    disk_usage_fn: Callable[[Path], object] = shutil.disk_usage,
) -> dict:
    ordered = _validated_steps(steps)
    if not execute:
        return migration_status(config, steps=ordered)

    config.ensure_dirs()
    applied_versions: list[int] = []
    stamped_versions: list[int] = []
    backup_path: Path | None = None
    try:
        with connect(config.db_path) as conn:
            _ensure_wal_mode(conn)
            status = _status_from_connection(conn, steps=ordered)
            if status["state"] == "unversioned-current":
                if _stamp_unversioned_v1(conn, ordered[0]):
                    stamped_versions.append(1)
                status = _status_from_connection(conn, steps=ordered)

            pending = [step for step in ordered if step.version > status["current_version"]]
            for step in pending:
                if step.destructive:
                    if not allow_destructive:
                        raise MigrationPreflightError(
                            f"migration {step.version} ({step.name}) is destructive and requires explicit migrate --execute"
                        )
                    if backup_path is None:
                        _preflight_backup_headroom(config, disk_usage_fn=disk_usage_fn)
                        backup_path = _online_backup(conn, config)
                if _apply_step(conn, step, backup_path=backup_path):
                    applied_versions.append(step.version)

            final = _status_from_connection(conn, steps=ordered)
    except MigrationError:
        raise
    except sqlite3.DatabaseError as exc:
        raise MigrationCompatibilityError(f"cannot apply SQLite migrations: {exc}") from exc
    final.update(
        {
            "applied_versions": applied_versions,
            "stamped_versions": stamped_versions,
            "backup_path": str(backup_path) if backup_path else None,
        }
    )
    return final


def migrate(config: RuntimeConfig) -> dict:
    """Compatibility wrapper for applying non-destructive startup migrations."""
    return migrate_database(config, execute=True)


__all__ = [
    "LATEST_SCHEMA_VERSION",
    "MIGRATIONS",
    "V1_SCHEMA_FINGERPRINT",
    "MigrationCompatibilityError",
    "MigrationError",
    "MigrationExecutionError",
    "MigrationPreflightError",
    "MigrationStep",
    "migrate",
    "migrate_database",
    "migration_checksum",
    "migration_status",
    "schema_fingerprint",
]