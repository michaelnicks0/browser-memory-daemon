"""Link media artifacts to the capture observations that supplied their references."""

from __future__ import annotations

import sqlite3
from pathlib import Path

NAME = "link_media_artifacts_to_capture_observations"
SCHEMA_FINGERPRINT = "074f15fb74c515cac72b645aee2b3d88407481f10c97d34d19fc4e30803f0dd3"
SQL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
CHECKSUM_PAYLOAD = SQL + "\n-- apply implementation --\n" + Path(__file__).read_text(encoding="utf-8")


def apply(conn: sqlite3.Connection) -> None:
    artifacts = conn.execute(
        "SELECT id, snapshot_id, visit_id FROM media_artifacts ORDER BY id"
    ).fetchall()
    for artifact in artifacts:
        exact = []
        if artifact["visit_id"]:
            exact = conn.execute(
                """
                SELECT id, captured_at
                FROM capture_observations
                WHERE snapshot_id = ? AND visit_id = ?
                ORDER BY captured_at, id
                """,
                (artifact["snapshot_id"], artifact["visit_id"]),
            ).fetchall()
        quality = "inferred"
        candidates = exact
        if len(exact) != 1:
            candidates = conn.execute(
                """
                SELECT id, captured_at
                FROM capture_observations
                WHERE snapshot_id = ?
                ORDER BY captured_at, id
                """,
                (artifact["snapshot_id"],),
            ).fetchall()
            quality = "ambiguous"
        if len(candidates) != 1:
            continue
        observation = candidates[0]
        conn.execute(
            """
            INSERT OR IGNORE INTO media_artifact_observations(
              artifact_id, observation_id, provenance_quality, observed_at
            ) VALUES (?, ?, ?, ?)
            """,
            (artifact["id"], observation["id"], quality, observation["captured_at"]),
        )
