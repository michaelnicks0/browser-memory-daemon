from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .config import RuntimeConfig

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(config: RuntimeConfig) -> None:
    config.ensure_dirs()
    with connect(config.db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute(
            "INSERT OR IGNORE INTO sources(id, source_type, source_name) VALUES (?, ?, ?)",
            ("chrome-extension", "browser", "chrome-extension"),
        )


def audit(conn: sqlite3.Connection, event_type: str, metadata: dict[str, Any]) -> str:
    event_id = str(uuid.uuid4())
    safe_metadata = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    conn.execute(
        "INSERT INTO audit_events(id, event_type, metadata_json) VALUES (?, ?, ?)",
        (event_id, event_type, safe_metadata),
    )
    return event_id
