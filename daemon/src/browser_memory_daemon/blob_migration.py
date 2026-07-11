from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .blob_lifecycle import register_committed_blob
from .blob_store import BlobStore, BlobStoreError
from .config import RuntimeConfig
from .media_storage import media_root_readiness


@dataclass(frozen=True)
class BlobMigrationPlan:
    table: str
    column: str
    row_id: str
    source_path: Path
    target_path: Path
    target_root: Path
    expected_size: int | None
    expected_sha256: str | None


def _safe_resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _sha256(store: BlobStore, path: Path) -> str:
    digest = hashlib.sha256()
    with store.open(path) as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _target_verified(store: BlobStore, plan: BlobMigrationPlan) -> bool:
    try:
        stat = store.stat(plan.target_path)
        if plan.expected_size is not None and stat.st_size != plan.expected_size:
            return False
        return plan.expected_sha256 is None or _sha256(store, plan.target_path) == plan.expected_sha256
    except (OSError, BlobStoreError):
        return False


def _relocate_path(
    raw_path: str,
    *,
    source_root: Path,
    target_root: Path,
    expected_prefix: str,
) -> tuple[Path, Path] | None:
    if not raw_path:
        return None
    source_store = BlobStore(source_root)
    target_store = BlobStore(target_root)
    resolution = source_store.resolve(raw_path, require_file=False)
    source = resolution.path
    if resolution.status in {"outside-root", "invalid", "empty"} or source is None:
        return None
    try:
        relative = source.relative_to(source_store.root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    target_parts = relative.parts
    if relative.parts[0] in {"clean-text", "raw-html", "media"}:
        if relative.parts[0] != expected_prefix or len(relative.parts) < 2:
            return None
        target_parts = relative.parts[1:]
    return source, target_store.path(*target_parts)


def plan_blob_root_migration(conn: sqlite3.Connection, config: RuntimeConfig, *, source_root: str | Path | None = None) -> list[BlobMigrationPlan]:
    """Return DB blob paths that should move into configured derivative/media roots."""
    selected_source = Path(source_root).expanduser() if source_root else config.data_root / "blobs"
    resolved_source_root = _safe_resolve(selected_source)

    plans: list[BlobMigrationPlan] = []
    snapshot_rows = conn.execute(
        "SELECT id, cleaned_text_path, text_hash FROM snapshots WHERE COALESCE(cleaned_text_path, '') != '' ORDER BY id"
    ).fetchall()
    for row in snapshot_rows:
        relocated = _relocate_path(
            row["cleaned_text_path"],
            source_root=resolved_source_root,
            target_root=config.clean_text_root,
            expected_prefix="clean-text",
        )
        if relocated:
            source, target = relocated
            if source != target:
                plans.append(
                    BlobMigrationPlan(
                        "snapshots",
                        "cleaned_text_path",
                        row["id"],
                        source,
                        target,
                        _safe_resolve(config.clean_text_root),
                        None,
                        str(row["text_hash"] or "") or None,
                    )
                )

    media_rows = conn.execute(
        """
        SELECT id, file_path, byte_size, content_sha256
        FROM media_artifacts
        WHERE storage_tier = 'media-root' AND COALESCE(file_path, '') != ''
        ORDER BY id
        """
    ).fetchall()
    for row in media_rows:
        relocated = _relocate_path(
            row["file_path"],
            source_root=resolved_source_root,
            target_root=config.media_root,
            expected_prefix="media",
        )
        if relocated:
            source, target = relocated
            if source != target:
                plans.append(
                    BlobMigrationPlan(
                        "media_artifacts",
                        "file_path",
                        row["id"],
                        source,
                        target,
                        _safe_resolve(config.media_root),
                        int(row["byte_size"] or 0) or None,
                        str(row["content_sha256"] or "") or None,
                    )
                )
    return plans


def migrate_blob_root(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    source_root: str | Path | None = None,
    execute: bool = False,
    remove_source: bool = False,
) -> dict[str, Any]:
    """Copy DB-referenced blobs to configured derivative/media roots and rewrite DB paths.

    The default is dry-run. `remove_source` is intentionally separate from
    `execute` so deployments can switch to the NAS root without deleting the
    previous local copy until the operator has verified the new path.
    """
    plans = plan_blob_root_migration(conn, config, source_root=source_root)
    media_readiness = media_root_readiness(config)
    summary: dict[str, Any] = {
        "dry_run": not execute,
        "remove_source": bool(remove_source and execute),
        "source_root": str(_safe_resolve(Path(source_root).expanduser() if source_root else config.data_root / "blobs")),
        "target_roots": {
            "clean_text": str(_safe_resolve(config.clean_text_root)),
            "media": str(_safe_resolve(config.media_root)),
        },
        "planned": len(plans),
        "media_root": media_readiness.as_dict(),
        "copied": 0,
        "already_present": 0,
        "missing_source": 0,
        "updated": 0,
        "removed_source": 0,
        "errors": [],
    }
    if not plans:
        return summary
    if execute and any(plan.table == "media_artifacts" for plan in plans) and not media_readiness.ok:
        summary["errors"].append(f"media root unavailable: {media_readiness.status}")
        return summary

    source_store = BlobStore(Path(source_root).expanduser() if source_root else config.data_root / "blobs")
    updates: list[BlobMigrationPlan] = []
    for plan in plans:
        target_store = BlobStore(plan.target_root)
        source_exists = source_store.exists(plan.source_path)
        target_exists = target_store.exists(plan.target_path)
        if not source_exists and not target_exists:
            summary["missing_source"] += 1
            continue
        if execute and source_exists and not target_exists:
            try:
                expected_size = plan.expected_size or source_store.stat(plan.source_path).st_size
                with source_store.open(plan.source_path) as source_handle:
                    target_store.write(
                        plan.target_path,
                        source_handle,
                        expected_size=expected_size,
                        expected_sha256=plan.expected_sha256,
                    )
                summary["copied"] += 1
                target_exists = True
            except (OSError, BlobStoreError) as exc:
                summary["errors"].append({"id": plan.row_id, "source": str(plan.source_path), "target": str(plan.target_path), "error": str(exc)})
                continue
        elif target_exists:
            if not _target_verified(target_store, plan):
                summary["errors"].append(
                    {"id": plan.row_id, "target": str(plan.target_path), "error": "target-integrity-mismatch"}
                )
                continue
            summary["already_present"] += 1
        updates.append(plan)

    if execute and updates:
        with conn:
            for plan in updates:
                if plan.table == "snapshots":
                    locator = BlobStore(config.clean_text_root).relative_locator(plan.target_path)
                    conn.execute(
                        "UPDATE snapshots SET cleaned_text_path = ?, cleaned_text_locator = ? WHERE id = ?",
                        (str(plan.target_path), locator, plan.row_id),
                    )
                    register_committed_blob(
                        conn,
                        owner_kind="snapshot-derivative",
                        owner_id=plan.row_id,
                        storage_tier="derivative",
                        locator=locator,
                        byte_size=plan.expected_size,
                        content_sha256=plan.expected_sha256,
                    )
                elif plan.table == "media_artifacts":
                    locator = BlobStore(config.media_root).relative_locator(plan.target_path)
                    conn.execute(
                        """
                        UPDATE media_artifacts
                        SET file_path = ?, blob_locator = ?, storage_tier = 'media-root', spool_locator = NULL
                        WHERE id = ?
                        """,
                        (str(plan.target_path), locator, plan.row_id),
                    )
                    register_committed_blob(
                        conn,
                        owner_kind="media-artifact",
                        owner_id=plan.row_id,
                        storage_tier="media-root",
                        locator=locator,
                        byte_size=plan.expected_size,
                        content_sha256=plan.expected_sha256,
                    )
                summary["updated"] += 1
        if remove_source:
            for plan in updates:
                if plan.source_path == plan.target_path or not source_store.exists(plan.source_path):
                    continue
                result = source_store.delete(plan.source_path)
                if result.deleted:
                    summary["removed_source"] += 1
                else:
                    summary["errors"].append({"id": plan.row_id, "source": str(plan.source_path), "error": result.status})
    return summary
