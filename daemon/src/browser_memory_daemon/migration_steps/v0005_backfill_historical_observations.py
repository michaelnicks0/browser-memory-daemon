from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

NAME = "backfill_historical_capture_observations_and_url_claims"


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8", errors="replace")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _origin(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def apply(conn: sqlite3.Connection) -> None:
    snapshots = conn.execute(
        """
        SELECT
          s.id AS snapshot_id,
          s.visit_id,
          s.document_id,
          s.captured_at,
          d.canonical_url,
          d.normalized_url,
          d.title AS document_title,
          v.url AS visit_url,
          v.normalized_url AS visit_normalized_url,
          v.title AS visit_title
        FROM snapshots s
        JOIN documents d ON d.id = s.document_id
        LEFT JOIN visits v ON v.id = s.visit_id
        ORDER BY s.captured_at, s.id
        """
    ).fetchall()
    for row in snapshots:
        observed_url = row["visit_url"] or row["canonical_url"]
        normalized_observed_url = row["visit_normalized_url"] or row["normalized_url"]
        quality = "inferred" if row["visit_id"] else "ambiguous"
        disposition = "historical-inferred" if row["visit_id"] else "historical-ambiguous"
        observation_id = _stable_id("obs", "historical-snapshot", row["snapshot_id"])
        idempotency_key = f"historical-snapshot:{row['snapshot_id']}"
        conn.execute(
            """
            INSERT OR IGNORE INTO capture_observations(
              id, idempotency_key, navigation_id, visit_id, document_id, snapshot_id,
              observed_url, normalized_observed_url, title, captured_at,
              capture_reason, capture_method, extraction_version,
              disposition, provenance_quality, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'historical-backfill', 'legacy', 'legacy-v1', ?, ?, '{}')
            """,
            (
                observation_id,
                idempotency_key,
                row["visit_id"],
                row["visit_id"],
                row["document_id"],
                row["snapshot_id"],
                observed_url,
                normalized_observed_url,
                row["visit_title"] or row["document_title"] or "",
                row["captured_at"],
                disposition,
                quality,
            ),
        )

    documents = conn.execute(
        """
        SELECT id, canonical_url, normalized_url, first_seen_at, last_seen_at
        FROM documents
        ORDER BY id
        """
    ).fetchall()
    for row in documents:
        claim_id = _stable_id("claim", "legacy-canonical", row["id"], row["canonical_url"])
        conn.execute(
            """
            INSERT OR IGNORE INTO document_url_claims(
              id, document_id, observation_id, claim_type,
              claimed_url, normalized_claimed_url, claim_origin, same_origin,
              identity_effect, provenance_quality, first_observed_at, last_observed_at,
              metadata_json
            ) VALUES (?, ?, NULL, 'legacy-canonical', ?, ?, ?, NULL,
                      'historical-authority', 'ambiguous', ?, ?, '{}')
            """,
            (
                claim_id,
                row["id"],
                row["canonical_url"],
                row["normalized_url"],
                _origin(row["canonical_url"]),
                row["first_seen_at"],
                row["last_seen_at"],
            ),
        )


CHECKSUM_PAYLOAD = Path(__file__).read_text(encoding="utf-8")
