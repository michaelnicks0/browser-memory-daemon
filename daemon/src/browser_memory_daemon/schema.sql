PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  canonical_url TEXT UNIQUE,
  normalized_url TEXT NOT NULL,
  domain TEXT NOT NULL,
  title TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visits (
  id TEXT PRIMARY KEY,
  document_id TEXT,
  source_id TEXT NOT NULL,
  url TEXT NOT NULL,
  normalized_url TEXT NOT NULL,
  title TEXT,
  source_device TEXT,
  browser_profile TEXT,
  visit_started_at TEXT,
  captured_at TEXT NOT NULL,
  dwell_seconds INTEGER,
  is_incognito INTEGER NOT NULL DEFAULT 0,
  blocked INTEGER NOT NULL DEFAULT 0,
  block_reason TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY(source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS snapshots (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  visit_id TEXT,
  captured_at TEXT NOT NULL,
  content_type TEXT,
  extraction_method TEXT NOT NULL,
  text_hash TEXT NOT NULL,
  cleaned_text_path TEXT,
  privacy_class TEXT NOT NULL DEFAULT 'normal',
  redaction_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  title TEXT,
  url TEXT NOT NULL,
  heading_path TEXT,
  FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  document_id UNINDEXED,
  snapshot_id UNINDEXED,
  title,
  url,
  text
);

CREATE TABLE IF NOT EXISTS privacy_rules (
  id TEXT PRIMARY KEY,
  rule_type TEXT NOT NULL,
  pattern TEXT NOT NULL,
  action TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS redactions (
  id TEXT PRIMARY KEY,
  snapshot_id TEXT,
  redaction_class TEXT NOT NULL,
  redaction_count INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS embeddings (
  id TEXT PRIMARY KEY,
  chunk_id TEXT NOT NULL,
  model_name TEXT NOT NULL,
  vector_ref TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback_events (
  id TEXT PRIMARY KEY,
  document_id TEXT,
  chunk_id TEXT,
  feedback_type TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deletion_receipts (
  id TEXT PRIMARY KEY,
  scope_json TEXT NOT NULL,
  counts_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
CREATE INDEX IF NOT EXISTS idx_visits_captured_at ON visits(captured_at);
CREATE INDEX IF NOT EXISTS idx_visits_normalized_url ON visits(normalized_url);
CREATE INDEX IF NOT EXISTS idx_snapshots_document_id ON snapshots(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
