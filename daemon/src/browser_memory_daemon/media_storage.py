from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from .blob_store import BlobStore, BlobStoreError, prefer_relative_locator
from .config import RuntimeConfig, has_non_root_mount_ancestor

MEDIA_ROOT_MARKER = ".bmd-media-root-id"
_COPY_CHUNK_BYTES = 1024 * 1024


class MediaStorageUnavailable(RuntimeError):
    pass


class MediaSpoolFull(MediaStorageUnavailable):
    pass


@dataclass(frozen=True)
class MediaRootReadiness:
    ok: bool
    status: str
    root: Path
    mount_required: bool
    identity_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "root": str(self.root),
            "mount_required": self.mount_required,
            "identity_required": self.identity_required,
        }


@dataclass(frozen=True)
class MediaBlobDestination:
    tier: str
    store: BlobStore
    root_status: str


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def media_root_readiness(config: RuntimeConfig) -> MediaRootReadiness:
    root = _resolved(config.media_root)
    data_root = _resolved(config.data_root)
    explicitly_external = config.media_root_path is not None and not root.is_relative_to(data_root)
    mount_required = bool(config.require_media_root_mount or config.require_blob_root_mount or explicitly_external)
    identity_required = bool(config.media_root_identity or mount_required)

    if mount_required and not has_non_root_mount_ancestor(root):
        return MediaRootReadiness(False, "mount-missing", root, mount_required, identity_required)
    if identity_required and not config.media_root_identity:
        return MediaRootReadiness(False, "identity-unconfigured", root, mount_required, identity_required)
    if identity_required:
        if not root.is_dir():
            return MediaRootReadiness(False, "root-missing", root, mount_required, identity_required)
        marker = BlobStore(root).resolve(MEDIA_ROOT_MARKER, require_file=True)
        if marker.path is None:
            return MediaRootReadiness(False, f"marker-{marker.status}", root, mount_required, identity_required)
        try:
            actual = marker.path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return MediaRootReadiness(False, "marker-unreadable", root, mount_required, identity_required)
        if actual != config.media_root_identity:
            return MediaRootReadiness(False, "identity-mismatch", root, mount_required, identity_required)
    return MediaRootReadiness(True, "ready", root, mount_required, identity_required)


def choose_media_blob_destination(config: RuntimeConfig) -> MediaBlobDestination:
    readiness = media_root_readiness(config)
    if readiness.ok:
        return MediaBlobDestination("media-root", BlobStore(config.media_root), readiness.status)
    if config.media_spool_enabled and config.media_spool_root is not None:
        return MediaBlobDestination("spool", BlobStore(config.media_spool_root), readiness.status)
    raise MediaStorageUnavailable(f"media root unavailable: {readiness.status}; bounded local spool is disabled")


def media_blob_store_and_locator(
    config: RuntimeConfig, row: Mapping[str, Any]
) -> tuple[BlobStore | None, str | None, str]:
    tier = str(row.get("storage_tier") or "media-root")
    if tier == "spool":
        if config.media_spool_root is None:
            return None, None, "spool-unconfigured"
        locator = prefer_relative_locator(row.get("spool_locator"), row.get("file_path"))
        return BlobStore(config.media_spool_root), locator, "spool"
    readiness = media_root_readiness(config)
    if not readiness.ok:
        return None, None, readiness.status
    locator = prefer_relative_locator(row.get("blob_locator"), row.get("file_path"))
    return BlobStore(config.media_root), locator, "media-root"


def _committed_spool_bytes(config: RuntimeConfig) -> int:
    if config.media_spool_root is None:
        return 0
    root = _resolved(config.media_spool_root)
    if not root.is_dir():
        return 0
    total = 0
    for candidate in root.rglob("*"):
        try:
            relative = candidate.relative_to(root)
            if ".staging" in relative.parts or candidate.is_symlink() or not candidate.is_file():
                continue
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root):
                continue
            total += int(resolved.stat().st_size)
        except (OSError, RuntimeError, ValueError):
            continue
    return total


def reserve_media_spool(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    artifact_id: str,
    reserved_bytes: int,
) -> dict[str, int | str]:
    if not config.media_spool_enabled or config.media_spool_root is None:
        raise MediaStorageUnavailable("bounded local media spool is disabled")
    if reserved_bytes <= 0:
        raise ValueError("reserved_bytes must be positive")
    reservation_id = f"spool-reservation-{uuid.uuid4().hex}"
    with conn:
        conn.execute(
            """
            INSERT INTO media_spool_reservations(reservation_id, artifact_id, reserved_bytes)
            VALUES (?, ?, ?)
            """,
            (reservation_id, artifact_id, reserved_bytes),
        )
        stored = _committed_spool_bytes(config)
        reserved = int(conn.execute("SELECT COALESCE(SUM(reserved_bytes), 0) FROM media_spool_reservations").fetchone()[0])
        projected = stored + reserved
        if projected > config.max_media_spool_bytes:
            raise MediaSpoolFull(
                f"media spool capacity exceeded: projected={projected} limit={config.max_media_spool_bytes}"
            )
    return {
        "reservation_id": reservation_id,
        "stored_bytes": stored,
        "reserved_bytes": reserved,
        "projected_bytes": projected,
    }


def release_media_spool_reservation(conn: sqlite3.Connection, reservation_id: str) -> None:
    with conn:
        conn.execute("DELETE FROM media_spool_reservations WHERE reservation_id = ?", (reservation_id,))


def media_spool_status(conn: sqlite3.Connection, config: RuntimeConfig) -> dict[str, Any]:
    stored = conn.execute(
        """
        SELECT COUNT(*) AS artifacts, COALESCE(SUM(byte_size), 0) AS bytes
        FROM media_artifacts
        WHERE storage_tier = 'spool' AND capture_status = 'stored'
        """
    ).fetchone()
    reserved = conn.execute(
        "SELECT COUNT(*) AS reservations, COALESCE(SUM(reserved_bytes), 0) AS bytes FROM media_spool_reservations"
    ).fetchone()
    readiness = media_root_readiness(config)
    filesystem_bytes = _committed_spool_bytes(config)
    accounted_bytes = filesystem_bytes + int(reserved["bytes"])
    return {
        "enabled": config.media_spool_enabled,
        "root": str(config.media_spool_root) if config.media_spool_root is not None else None,
        "limit_bytes": config.max_media_spool_bytes,
        "stored_artifacts": int(stored["artifacts"]),
        "stored_bytes": int(stored["bytes"]),
        "filesystem_bytes": filesystem_bytes,
        "reservations": int(reserved["reservations"]),
        "reserved_bytes": int(reserved["bytes"]),
        "accounted_bytes": accounted_bytes,
        "available_bytes": max(0, config.max_media_spool_bytes - accounted_bytes),
        "media_root": readiness.as_dict(),
    }


def _stream(handle: Any) -> Iterator[bytes]:
    while True:
        chunk = handle.read(_COPY_CHUNK_BYTES)
        if not chunk:
            return
        yield chunk


def drain_media_spool(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    limit: int = 100,
    execute: bool = False,
) -> dict[str, Any]:
    if limit < 1 or limit > 10_000:
        raise ValueError("limit must be between 1 and 10000")
    readiness = media_root_readiness(config)
    rows = conn.execute(
        """
        SELECT id, byte_size, content_sha256, file_path, spool_locator
        FROM media_artifacts
        WHERE storage_tier = 'spool' AND capture_status = 'stored'
        ORDER BY created_at, id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    summary: dict[str, Any] = {
        "dry_run": not execute,
        "selected": len(rows),
        "selected_bytes": sum(int(row["byte_size"] or 0) for row in rows),
        "moved": 0,
        "moved_bytes": 0,
        "missing": 0,
        "invalid": 0,
        "source_cleanup_failed": 0,
        "errors": 0,
        "media_root": readiness.as_dict(),
    }
    if not execute or not rows:
        return summary
    if not readiness.ok:
        raise MediaStorageUnavailable(f"media root unavailable: {readiness.status}")
    if config.media_spool_root is None:
        raise MediaStorageUnavailable("media spool root is not configured")

    source_store = BlobStore(config.media_spool_root)
    target_store = BlobStore(config.media_root)
    for row in rows:
        locator = prefer_relative_locator(row["spool_locator"], row["file_path"])
        resolution = source_store.resolve(locator, require_file=True)
        if resolution.path is None:
            summary["missing"] += 1
            continue
        expected_size = int(row["byte_size"] or 0)
        expected_sha256 = str(row["content_sha256"] or "")
        try:
            with source_store.open(resolution.path) as handle:
                target = target_store.write(
                    str(row["spool_locator"] or Path(resolution.path).name),
                    _stream(handle),
                    expected_size=expected_size,
                    expected_sha256=expected_sha256 or None,
                )
            with conn:
                updated = conn.execute(
                    """
                    UPDATE media_artifacts
                    SET storage_tier = 'media-root', file_path = ?, blob_locator = ?,
                        spool_locator = NULL
                    WHERE id = ? AND storage_tier = 'spool'
                    """,
                    (str(target), target_store.relative_locator(target), row["id"]),
                )
                if updated.rowcount != 1:
                    raise BlobStoreError("media spool row changed before durable tier transition")
            delete_result = source_store.delete(resolution.path)
            if not delete_result.deleted:
                summary["source_cleanup_failed"] += 1
            summary["moved"] += 1
            summary["moved_bytes"] += expected_size
        except (BlobStoreError, OSError, ValueError):
            summary["errors"] += 1
    return summary
