from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3


NAME = "seed_daemon_public_media_fetch_tasks"
SELECT_SQL = """
SELECT id, source_url, metadata_json
FROM media_artifacts
WHERE capture_status IN ('referenced', 'metadata-only', 'queued', 'retrying', 'failed', 'purged')
  AND COALESCE(file_path, '') = ''
  AND COALESCE(source_url, '') != ''
"""
INSERT_SQL = """
INSERT OR IGNORE INTO media_fetch_tasks(
  id, artifact_id, worker_kind, status, priority, attempts, max_attempts,
  next_attempt_at, lease_owner, lease_until, last_error
) VALUES (?, ?, 'daemon-public', 'pending', ?, 0, 5, NULL, NULL, NULL, NULL)
"""


def _stable_task_id(artifact_id: str) -> str:
    value = f"daemon-public:{artifact_id}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"mtask_{digest}"


def _supported(source_url: str) -> bool:
    return (source_url or "").lower().strip().startswith(("http://", "https://", "data:"))


def apply(conn: sqlite3.Connection) -> None:
    for row in conn.execute(SELECT_SQL).fetchall():
        source_url = row["source_url"]
        if not _supported(source_url):
            continue
        priority = 50
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
            priority = int(float(metadata.get("priority", priority)))
        except (TypeError, ValueError, json.JSONDecodeError):
            priority = 50
        artifact_id = row["id"]
        conn.execute(
            INSERT_SQL,
            (_stable_task_id(artifact_id), artifact_id, max(0, min(100, priority))),
        )


# Freeze the complete callback implementation into the ledger checksum.
CHECKSUM_PAYLOAD = Path(__file__).read_text(encoding="utf-8")
