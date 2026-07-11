ALTER TABLE media_artifacts ADD COLUMN storage_tier TEXT NOT NULL DEFAULT 'media-root' CHECK (storage_tier IN ('media-root', 'spool'));
ALTER TABLE media_artifacts ADD COLUMN spool_locator TEXT;

CREATE TABLE media_spool_reservations (
  reservation_id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL,
  reserved_bytes INTEGER NOT NULL CHECK (reserved_bytes > 0),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
