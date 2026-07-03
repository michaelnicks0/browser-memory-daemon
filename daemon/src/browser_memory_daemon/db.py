from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .config import RuntimeConfig

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SQLITE_BUSY_TIMEOUT_MS = 30_000


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(config: RuntimeConfig, *, seed_media_tasks: bool = True) -> None:
    config.ensure_dirs()
    with connect(config.db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute(
            "INSERT OR IGNORE INTO sources(id, source_type, source_name) VALUES (?, ?, ?)",
            ("chrome-extension", "browser", "chrome-extension"),
        )
        if seed_media_tasks:
            _seed_media_fetch_tasks(conn)


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _media_fetch_supported(source_url: str) -> bool:
    lower = (source_url or "").lower().strip()
    return lower.startswith(("http://", "https://", "data:"))


def _seed_media_fetch_tasks(conn: sqlite3.Connection) -> None:
    """Backfill daemon-public tasks for unresolved media refs on existing DBs."""
    try:
        rows = conn.execute(
            """
            SELECT id, source_url, metadata_json
            FROM media_artifacts
            WHERE capture_status IN ('referenced', 'metadata-only', 'queued', 'retrying', 'failed', 'purged')
              AND COALESCE(file_path, '') = ''
              AND COALESCE(source_url, '') != ''
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return
    for row in rows:
        source_url = row["source_url"]
        if not _media_fetch_supported(source_url):
            continue
        priority = 50
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
            priority = int(float(metadata.get("priority", priority)))
        except Exception:
            priority = 50
        artifact_id = row["id"]
        conn.execute(
            """
            INSERT OR IGNORE INTO media_fetch_tasks(
              id, artifact_id, worker_kind, status, priority, attempts, max_attempts,
              next_attempt_at, lease_owner, lease_until, last_error
            ) VALUES (?, ?, 'daemon-public', 'pending', ?, 0, 5, NULL, NULL, NULL, NULL)
            """,
            (_stable_id("mtask", f"daemon-public:{artifact_id}"), artifact_id, max(0, min(100, priority))),
        )


def audit(conn: sqlite3.Connection, event_type: str, metadata: dict[str, Any]) -> str:
    event_id = str(uuid.uuid4())
    safe_metadata = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    conn.execute(
        "INSERT INTO audit_events(id, event_type, metadata_json) VALUES (?, ?, ?)",
        (event_id, event_type, safe_metadata),
    )
    return event_id
