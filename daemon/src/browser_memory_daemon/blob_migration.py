from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .blob_store import BlobStore, BlobStoreError
from .config import RuntimeConfig


@dataclass(frozen=True)
class BlobMigrationPlan:
    table: str
    column: str
    row_id: str
    source_path: Path
    target_path: Path


def _safe_resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _relocate_path(raw_path: str, *, source_root: Path, target_root: Path) -> tuple[Path, Path] | None:
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
    if relative.parts and relative.parts[0] not in {"clean-text", "raw-html", "media"}:
        return None
    return source, target_store.path(*relative.parts)


def plan_blob_root_migration(conn: sqlite3.Connection, config: RuntimeConfig, *, source_root: str | Path | None = None) -> list[BlobMigrationPlan]:
    """Return DB blob paths that should move from source_root to config.blob_root."""
    selected_source = Path(source_root).expanduser() if source_root else config.data_root / "blobs"
    resolved_source_root = _safe_resolve(selected_source)
    resolved_target_root = _safe_resolve(config.blob_root)
    if resolved_source_root == resolved_target_root:
        return []

    plans: list[BlobMigrationPlan] = []
    snapshot_rows = conn.execute(
        "SELECT id, cleaned_text_path FROM snapshots WHERE COALESCE(cleaned_text_path, '') != '' ORDER BY id"
    ).fetchall()
    for row in snapshot_rows:
        relocated = _relocate_path(row["cleaned_text_path"], source_root=resolved_source_root, target_root=resolved_target_root)
        if relocated:
            source, target = relocated
            plans.append(BlobMigrationPlan("snapshots", "cleaned_text_path", row["id"], source, target))

    media_rows = conn.execute("SELECT id, file_path FROM media_artifacts WHERE COALESCE(file_path, '') != '' ORDER BY id").fetchall()
    for row in media_rows:
        relocated = _relocate_path(row["file_path"], source_root=resolved_source_root, target_root=resolved_target_root)
        if relocated:
            source, target = relocated
            plans.append(BlobMigrationPlan("media_artifacts", "file_path", row["id"], source, target))
    return plans


def migrate_blob_root(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    source_root: str | Path | None = None,
    execute: bool = False,
    remove_source: bool = False,
) -> dict[str, Any]:
    """Copy DB-referenced blob files to config.blob_root and rewrite DB paths.

    The default is dry-run. `remove_source` is intentionally separate from
    `execute` so deployments can switch to the NAS root without deleting the
    previous local copy until the operator has verified the new path.
    """
    plans = plan_blob_root_migration(conn, config, source_root=source_root)
    summary: dict[str, Any] = {
        "dry_run": not execute,
        "remove_source": bool(remove_source and execute),
        "source_root": str(_safe_resolve(Path(source_root).expanduser() if source_root else config.data_root / "blobs")),
        "target_root": str(_safe_resolve(config.blob_root)),
        "planned": len(plans),
        "copied": 0,
        "already_present": 0,
        "missing_source": 0,
        "updated": 0,
        "removed_source": 0,
        "errors": [],
    }
    if not plans:
        return summary

    source_store = BlobStore(Path(source_root).expanduser() if source_root else config.data_root / "blobs")
    target_store = BlobStore(config.blob_root)
    updates: list[BlobMigrationPlan] = []
    for plan in plans:
        source_exists = source_store.exists(plan.source_path)
        target_exists = target_store.exists(plan.target_path)
        if not source_exists and not target_exists:
            summary["missing_source"] += 1
            continue
        if execute and source_exists and not target_exists:
            try:
                expected_size = source_store.stat(plan.source_path).st_size
                with source_store.open(plan.source_path) as source_handle:
                    target_store.write(plan.target_path, source_handle, expected_size=expected_size)
                summary["copied"] += 1
                target_exists = True
            except (OSError, BlobStoreError) as exc:
                summary["errors"].append({"id": plan.row_id, "source": str(plan.source_path), "target": str(plan.target_path), "error": str(exc)})
                continue
        elif target_exists:
            summary["already_present"] += 1
        updates.append(plan)

    if execute and updates:
        with conn:
            for plan in updates:
                if plan.table == "snapshots":
                    conn.execute("UPDATE snapshots SET cleaned_text_path = ? WHERE id = ?", (str(plan.target_path), plan.row_id))
                elif plan.table == "media_artifacts":
                    conn.execute("UPDATE media_artifacts SET file_path = ? WHERE id = ?", (str(plan.target_path), plan.row_id))
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
