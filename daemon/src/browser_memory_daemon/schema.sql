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

CREATE TABLE IF NOT EXISTS visit_events (
  id TEXT PRIMARY KEY,
  visit_id TEXT,
  document_id TEXT,
  source_id TEXT NOT NULL,
  url TEXT NOT NULL,
  normalized_url TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_started_at TEXT,
  event_ended_at TEXT NOT NULL,
  active_seconds INTEGER,
  max_scroll_percent INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE SET NULL,
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

CREATE TABLE IF NOT EXISTS media_artifacts (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  visit_id TEXT,
  media_type TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'content',
  source_url TEXT NOT NULL,
  normalized_source_url TEXT NOT NULL,
  page_url TEXT NOT NULL,
  alt_text TEXT,
  title TEXT,
  mime_type TEXT,
  width INTEGER,
  height INTEGER,
  duration_seconds REAL,
  byte_size INTEGER,
  content_sha256 TEXT,
  file_path TEXT,
  capture_status TEXT NOT NULL DEFAULT 'referenced',
  status_reason TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
  FOREIGN KEY(visit_id) REFERENCES visits(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS media_fetch_tasks (
  id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL,
  worker_kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  priority INTEGER NOT NULL DEFAULT 50,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_attempt_at TEXT,
  lease_owner TEXT,
  lease_until TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(artifact_id) REFERENCES media_artifacts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS privacy_rules (
  id TEXT PRIMARY KEY,
  rule_type TEXT NOT NULL,
  pattern TEXT NOT NULL,
  action TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DELETE FROM privacy_rules
WHERE rowid NOT IN (
  SELECT MIN(rowid)
  FROM privacy_rules
  GROUP BY rule_type, pattern, action
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
CREATE INDEX IF NOT EXISTS idx_visits_blocked_captured_created ON visits(blocked, captured_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visits_document_captured_created ON visits(document_id, captured_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visits_normalized_url ON visits(normalized_url);
CREATE INDEX IF NOT EXISTS idx_visit_events_visit_id ON visit_events(visit_id);
CREATE INDEX IF NOT EXISTS idx_visit_events_document_id ON visit_events(document_id);
CREATE INDEX IF NOT EXISTS idx_visit_events_visit_ended_created ON visit_events(visit_id, event_ended_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visit_events_document_ended_created ON visit_events(document_id, event_ended_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visit_events_normalized_url ON visit_events(normalized_url);
CREATE INDEX IF NOT EXISTS idx_visit_events_event_ended_at ON visit_events(event_ended_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_document_id ON snapshots(document_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_document_captured_created ON snapshots(document_id, captured_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_media_artifacts_document_id ON media_artifacts(document_id);
CREATE INDEX IF NOT EXISTS idx_media_artifacts_snapshot_id ON media_artifacts(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_media_artifacts_content_sha256 ON media_artifacts(content_sha256);
CREATE INDEX IF NOT EXISTS idx_media_artifacts_capture_status ON media_artifacts(capture_status);
CREATE INDEX IF NOT EXISTS idx_media_artifacts_status_created ON media_artifacts(capture_status, created_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_media_fetch_tasks_status_next ON media_fetch_tasks(status, next_attempt_at, priority);
CREATE INDEX IF NOT EXISTS idx_media_fetch_tasks_artifact ON media_fetch_tasks(artifact_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_privacy_rules_semantics ON privacy_rules(rule_type, pattern, action);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_snapshot_chunk_index ON chunks(document_id, snapshot_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_chunks_snapshot_chunk_index ON chunks(snapshot_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
