from __future__ import annotations

NAME = "add-media-cache-reservations"
SQL = """
CREATE TABLE media_cache_reservations (
  reservation_id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT '',
  reserved_bytes INTEGER NOT NULL CHECK (reserved_bytes > 0),
  owner_pid INTEGER NOT NULL CHECK (owner_pid > 0),
  owner_start_token TEXT NOT NULL CHECK (owner_start_token <> ''),
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);
CREATE INDEX idx_media_cache_reservations_expiry ON media_cache_reservations(expires_at);
CREATE INDEX idx_media_cache_reservations_snapshot ON media_cache_reservations(snapshot_id);
CREATE INDEX idx_media_cache_reservations_domain ON media_cache_reservations(domain);
"""
DESTRUCTIVE = False
SCHEMA_FINGERPRINT = "2cb98df1869434601a6483387e8442ab142d125c353385d47794c16dbc7988c3"
