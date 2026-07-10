CREATE TABLE IF NOT EXISTS media_artifact_observations (
  artifact_id TEXT NOT NULL REFERENCES media_artifacts(id) ON DELETE CASCADE,
  observation_id TEXT NOT NULL REFERENCES capture_observations(id) ON DELETE CASCADE,
  provenance_quality TEXT NOT NULL CHECK (provenance_quality IN ('observed', 'inferred', 'ambiguous')),
  observed_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (artifact_id, observation_id)
);

CREATE INDEX IF NOT EXISTS idx_media_artifact_observations_observation
  ON media_artifact_observations(observation_id, observed_at DESC);
