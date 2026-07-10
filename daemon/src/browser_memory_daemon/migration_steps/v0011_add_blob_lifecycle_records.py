from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

NAME = "add-blob-lifecycle-records"
SQL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
DESTRUCTIVE = False
SCHEMA_FINGERPRINT = "ab5053b91c27082493d59f15391c2245c1e0d2719c06837fc7866b20e88b7139"


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO blob_storage_records(
          id, owner_kind, owner_id, storage_tier, locator,
          byte_size, content_sha256, state
        )
        SELECT 'blob-' || lower(hex(randomblob(16))),
               'media-artifact', id, storage_tier,
               COALESCE(
                 NULLIF(CASE WHEN storage_tier = 'spool' THEN spool_locator ELSE blob_locator END, ''),
                 file_path
               ),
               byte_size, NULLIF(content_sha256, ''), 'committed'
        FROM media_artifacts
        WHERE capture_status = 'stored'
          AND COALESCE(
                NULLIF(CASE WHEN storage_tier = 'spool' THEN spool_locator ELSE blob_locator END, ''),
                NULLIF(file_path, '')
              ) IS NOT NULL
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO blob_storage_records(
          id, owner_kind, owner_id, storage_tier, locator,
          content_sha256, state
        )
        SELECT 'blob-' || lower(hex(randomblob(16))),
               'snapshot-derivative', id, 'derivative',
               COALESCE(NULLIF(cleaned_text_locator, ''), cleaned_text_path),
               NULLIF(text_hash, ''), 'committed'
        FROM snapshots
        WHERE COALESCE(NULLIF(cleaned_text_locator, ''), NULLIF(cleaned_text_path, '')) IS NOT NULL
        """
    )


CHECKSUM_PAYLOAD = SQL + "\n" + inspect.getsource(apply)
