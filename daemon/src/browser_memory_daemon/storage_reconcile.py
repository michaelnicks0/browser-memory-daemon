from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .blob_lifecycle import (
    blob_lifecycle_status,
    process_blob_tombstones,
    register_committed_blob,
    tombstone_blob,
)
from .blob_store import BlobStore, BlobStoreError, prefer_relative_locator
from .config import RuntimeConfig
from .media_storage import MEDIA_ROOT_MARKER, media_blob_store_and_locator, media_root_readiness


def _sample(values: list[str], limit: int = 20) -> list[str]:
    return values[:limit]


def _matches_expected_blob(store: BlobStore, locator: str, row: sqlite3.Row) -> bool:
    try:
        stat = store.stat(locator)
        expected_size = row["byte_size"]
        if expected_size is not None and stat.st_size != int(expected_size):
            return False
        expected_sha256 = str(row["content_sha256"] or "").lower()
        if not expected_sha256:
            return True
        digest = hashlib.sha256()
        with store.open(locator) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected_sha256
    except (BlobStoreError, OSError):
        return False


def _relative_reference(store: BlobStore, locator: str) -> str | None:
    resolution = store.resolve(locator, require_file=False)
    if resolution.path is None or resolution.status in {"outside-root", "invalid", "empty"}:
        return None
    try:
        return store.relative_locator(resolution.path)
    except RuntimeError:
        return None


def _stores(config: RuntimeConfig) -> dict[str, BlobStore]:
    stores = {"derivative": BlobStore(config.clean_text_root)}
    if media_root_readiness(config).ok:
        stores["media-root"] = BlobStore(config.media_root)
    if config.media_spool_root is not None:
        stores["spool"] = BlobStore(config.media_spool_root)
    return stores


def _referenced_locators(conn: sqlite3.Connection, stores: dict[str, BlobStore]) -> dict[str, set[str]]:
    referenced: dict[str, set[str]] = {tier: set() for tier in stores}
    rows = conn.execute(
        """
        SELECT storage_tier, locator FROM blob_storage_records
        WHERE state IN ('staged', 'committed', 'tombstoned', 'failed', 'blocked')
        """
    ).fetchall()
    for row in rows:
        tier = str(row["storage_tier"])
        store = stores.get(tier)
        if store is None:
            continue
        relative = _relative_reference(store, str(row["locator"]))
        if relative:
            referenced[tier].add(relative)
    media_rows = conn.execute(
        """
        SELECT file_path, blob_locator, storage_tier, spool_locator
        FROM media_artifacts
        WHERE COALESCE(blob_locator, '') != ''
           OR COALESCE(spool_locator, '') != ''
           OR COALESCE(file_path, '') != ''
        """
    ).fetchall()
    for row in media_rows:
        tier = str(row["storage_tier"] or "media-root")
        store = stores.get(tier)
        if store is None:
            continue
        locator = (
            prefer_relative_locator(row["spool_locator"], row["file_path"])
            if tier == "spool"
            else prefer_relative_locator(row["blob_locator"], row["file_path"])
        )
        relative = _relative_reference(store, str(locator or ""))
        if relative:
            referenced[tier].add(relative)
    derivative_rows = conn.execute(
        """
        SELECT cleaned_text_path, cleaned_text_locator FROM snapshots
        WHERE COALESCE(cleaned_text_locator, '') != '' OR COALESCE(cleaned_text_path, '') != ''
        """
    ).fetchall()
    derivative_store = stores["derivative"]
    for row in derivative_rows:
        locator = prefer_relative_locator(row["cleaned_text_locator"], row["cleaned_text_path"])
        relative = _relative_reference(derivative_store, str(locator or ""))
        if relative:
            referenced["derivative"].add(relative)
    return referenced


def _filesystem_candidates(store: BlobStore) -> list[Path]:
    if not store.root.is_dir():
        return []
    files: list[Path] = []
    for path in store.root.rglob("*"):
        try:
            relative = path.relative_to(store.root)
            if ".staging" in relative.parts or path.is_symlink() or not path.is_file():
                continue
            if path.name == MEDIA_ROOT_MARKER or path.name.startswith(".bmd-"):
                continue
            files.append(path)
        except (OSError, ValueError):
            continue
    return files


def reconcile_storage(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    execute: bool = False,
    stale_stage_seconds: int = 3600,
    limit: int = 1000,
) -> dict[str, Any]:
    limit = max(1, int(limit))
    lifecycle_before = blob_lifecycle_status(conn)
    if execute:
        tombstones = process_blob_tombstones(conn, config, limit=limit)
    else:
        tombstones = {
            "selected": min(limit, lifecycle_before["pending"]),
            "deleted": 0,
            "missing": 0,
            "failed": lifecycle_before["failed"],
            "blocked": lifecycle_before["blocked"],
            "pending": lifecycle_before["pending"],
        }

    missing: list[tuple[sqlite3.Row, str, str]] = []
    recovered: list[tuple[sqlite3.Row, str]] = []
    corrupt: list[str] = []
    wrong_root: list[str] = []
    unavailable: list[str] = []
    rows = conn.execute(
        """
        SELECT id, file_path, blob_locator, storage_tier, spool_locator,
               byte_size, content_sha256, capture_status
        FROM media_artifacts
        WHERE capture_status IN ('stored', 'purging', 'missing')
          AND (COALESCE(blob_locator, '') != ''
               OR COALESCE(spool_locator, '') != ''
               OR COALESCE(file_path, '') != '')
        ORDER BY id
        """
    ).fetchall()
    for row in rows:
        store, locator, tier_status = media_blob_store_and_locator(config, dict(row))
        if store is None:
            unavailable.append(str(row["id"]))
            continue
        resolution = store.resolve(locator, require_file=False)
        if resolution.status in {"outside-root", "invalid", "empty", "not-file"} or resolution.path is None:
            wrong_root.append(str(row["id"]))
        elif store.exists(locator):
            if not _matches_expected_blob(store, str(locator), row):
                missing.append((row, str(locator), "storage-reconcile:corrupt"))
                corrupt.append(str(row["id"]))
            elif row["capture_status"] == "missing":
                recovered.append((row, str(locator)))
        elif row["capture_status"] != "missing":
            missing.append((row, str(locator), "storage-reconcile:missing"))
    marked_missing = 0
    marked_recovered = 0
    if execute:
        with conn:
            for row, locator, missing_reason in missing[:limit]:
                register_committed_blob(
                    conn,
                    owner_kind="media-artifact",
                    owner_id=str(row["id"]),
                    storage_tier=str(row["storage_tier"]),
                    locator=locator,
                    byte_size=int(row["byte_size"]) if row["byte_size"] is not None else None,
                    content_sha256=str(row["content_sha256"] or "") or None,
                )
                conn.execute(
                    """
                    UPDATE blob_storage_records
                    SET state = 'missing', reason = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                        completed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                    WHERE owner_kind = 'media-artifact' AND owner_id = ?
                      AND storage_tier = ? AND locator = ?
                    """,
                    (missing_reason, row["id"], row["storage_tier"], locator),
                )
                conn.execute(
                    """
                    UPDATE media_artifacts
                    SET capture_status = 'missing', status_reason = ?
                    WHERE id = ? AND capture_status IN ('stored', 'missing')
                    """,
                    (missing_reason, row["id"]),
                )
                marked_missing += 1
            for row, locator in recovered[:limit]:
                register_committed_blob(
                    conn,
                    owner_kind="media-artifact",
                    owner_id=str(row["id"]),
                    storage_tier=str(row["storage_tier"]),
                    locator=locator,
                    byte_size=int(row["byte_size"]) if row["byte_size"] is not None else None,
                    content_sha256=str(row["content_sha256"] or "") or None,
                )
                conn.execute(
                    """
                    UPDATE media_artifacts
                    SET capture_status = 'stored', status_reason = NULL
                    WHERE id = ? AND capture_status = 'missing'
                    """,
                    (row["id"],),
                )
                marked_recovered += 1

    stores = _stores(config)
    referenced = _referenced_locators(conn, stores)
    now = time.time()
    stale_stages: list[tuple[str, BlobStore, Path]] = []
    orphan_files: list[tuple[str, BlobStore, str]] = []
    for tier, store in stores.items():
        for stage in store.staged_paths():
            try:
                if now - stage.stat().st_mtime >= max(0, int(stale_stage_seconds)):
                    stale_stages.append((tier, store, stage))
            except OSError:
                continue
        for path in _filesystem_candidates(store):
            try:
                locator = store.relative_locator(path)
            except RuntimeError:
                continue
            if locator not in referenced[tier]:
                orphan_files.append((tier, store, locator))

    stale_deleted = 0
    orphan_deleted = 0
    if execute:
        for _tier, store, stage in stale_stages[:limit]:
            if store.delete(stage).deleted:
                stale_deleted += 1
        operation_id = f"reconcile-{uuid.uuid4().hex}"
        with conn:
            for tier, _store, locator in orphan_files[:limit]:
                owner_id = hashlib.sha256(f"{tier}:{locator}".encode()).hexdigest()
                tombstone_blob(
                    conn,
                    operation_id=operation_id,
                    owner_kind="orphan",
                    owner_id=owner_id,
                    storage_tier=tier,
                    locator=locator,
                    reason="storage-reconcile:orphan",
                )
        if orphan_files:
            orphan_outcome = process_blob_tombstones(
                conn,
                config,
                operation_id=operation_id,
                limit=limit,
            )
            orphan_deleted = orphan_outcome["deleted"] + orphan_outcome["missing"]

    return {
        "dry_run": not execute,
        "tombstones": tombstones,
        "missing": {
            "count": len(missing),
            "marked": marked_missing,
            "sample_artifact_ids": _sample(
                [str(row["id"]) for row, _locator, _reason in missing]
            ),
        },
        "corrupt": {"count": len(corrupt), "sample_artifact_ids": _sample(corrupt)},
        "recovered": {
            "count": len(recovered),
            "marked": marked_recovered,
            "sample_artifact_ids": _sample([str(row["id"]) for row, _locator in recovered]),
        },
        "wrong_root": {"count": len(wrong_root), "sample_artifact_ids": _sample(wrong_root)},
        "unavailable": {"count": len(unavailable), "sample_artifact_ids": _sample(unavailable)},
        "orphans": {
            "count": len(orphan_files),
            "deleted": orphan_deleted,
            "sample_locators": _sample([f"{tier}:{locator}" for tier, _store, locator in orphan_files]),
        },
        "stale_stages": {
            "count": len(stale_stages),
            "deleted": stale_deleted,
            "sample_locators": _sample(
                [f"{tier}:{store.relative_locator(path)}" for tier, store, path in stale_stages]
            ),
        },
        "lifecycle": blob_lifecycle_status(conn),
    }
