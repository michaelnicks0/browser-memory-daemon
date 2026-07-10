CREATE TABLE blob_storage_records (
  id TEXT PRIMARY KEY,
  operation_id TEXT,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('media-artifact', 'snapshot-derivative', 'orphan')),
  owner_id TEXT NOT NULL,
  storage_tier TEXT NOT NULL CHECK (storage_tier IN ('derivative', 'media-root', 'spool')),
  locator TEXT NOT NULL,
  byte_size INTEGER,
  content_sha256 TEXT,
  state TEXT NOT NULL CHECK (state IN ('staged', 'committed', 'tombstoned', 'missing', 'deleted', 'blocked', 'failed')),
  reason TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  completed_at TEXT,
  UNIQUE(owner_kind, owner_id, storage_tier, locator)
);

CREATE INDEX idx_blob_storage_records_state_updated
  ON blob_storage_records(state, updated_at, id);
CREATE INDEX idx_blob_storage_records_operation
  ON blob_storage_records(operation_id, state, id);
