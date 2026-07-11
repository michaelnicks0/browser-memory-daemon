from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .config import RuntimeConfig

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SQLITE_BUSY_TIMEOUT_MS = 30_000
SQLITE_SYNCHRONOUS = "NORMAL"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA synchronous = {SQLITE_SYNCHRONOUS}")
    return conn


def init_db(config: RuntimeConfig) -> None:
    from .migrations import migrate_database

    migrate_database(config, execute=True)


def audit(conn: sqlite3.Connection, event_type: str, metadata: dict[str, Any]) -> str:
    event_id = str(uuid.uuid4())
    safe_metadata = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    conn.execute(
        "INSERT INTO audit_events(id, event_type, metadata_json) VALUES (?, ?, ?)",
        (event_id, event_type, safe_metadata),
    )
    return event_id
