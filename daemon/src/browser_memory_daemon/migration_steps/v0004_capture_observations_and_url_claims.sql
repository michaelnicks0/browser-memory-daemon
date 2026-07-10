CREATE TABLE IF NOT EXISTS capture_observations (
  id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  navigation_id TEXT,
  visit_id TEXT REFERENCES visits(id) ON DELETE SET NULL,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  snapshot_id TEXT REFERENCES snapshots(id) ON DELETE SET NULL,
  source_id TEXT NOT NULL DEFAULT 'chrome-extension' REFERENCES sources(id),
  observed_url TEXT NOT NULL,
  normalized_observed_url TEXT NOT NULL,
  title TEXT,
  captured_at TEXT NOT NULL,
  capture_reason TEXT NOT NULL DEFAULT 'unspecified',
  capture_method TEXT NOT NULL DEFAULT 'unknown',
  extraction_version TEXT NOT NULL DEFAULT 'unknown',
  disposition TEXT NOT NULL DEFAULT 'accepted'
    CHECK (disposition IN ('accepted', 'duplicate', 'rejected', 'historical-inferred', 'historical-ambiguous')),
  provenance_quality TEXT NOT NULL DEFAULT 'observed'
    CHECK (provenance_quality IN ('observed', 'inferred', 'ambiguous')),
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (length(idempotency_key) > 0)
);

CREATE INDEX IF NOT EXISTS idx_capture_observations_visit_captured
  ON capture_observations(visit_id, captured_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_capture_observations_document_captured
  ON capture_observations(document_id, captured_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_capture_observations_snapshot
  ON capture_observations(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_capture_observations_normalized_url
  ON capture_observations(normalized_observed_url, captured_at DESC);

CREATE TABLE IF NOT EXISTS document_url_claims (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  observation_id TEXT REFERENCES capture_observations(id) ON DELETE SET NULL,
  claim_type TEXT NOT NULL
    CHECK (claim_type IN ('canonical', 'alternate', 'og-url', 'legacy-canonical')),
  claimed_url TEXT NOT NULL,
  normalized_claimed_url TEXT NOT NULL,
  claim_origin TEXT,
  same_origin INTEGER CHECK (same_origin IS NULL OR same_origin IN (0, 1)),
  identity_effect TEXT NOT NULL DEFAULT 'none'
    CHECK (identity_effect IN ('none', 'same-origin-alias', 'historical-authority')),
  provenance_quality TEXT NOT NULL DEFAULT 'observed'
    CHECK (provenance_quality IN ('observed', 'inferred', 'ambiguous')),
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(document_id, claim_type, normalized_claimed_url)
);

CREATE INDEX IF NOT EXISTS idx_document_url_claims_document
  ON document_url_claims(document_id, last_observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_url_claims_normalized
  ON document_url_claims(normalized_claimed_url, claim_type);
CREATE INDEX IF NOT EXISTS idx_document_url_claims_observation
  ON document_url_claims(observation_id);
