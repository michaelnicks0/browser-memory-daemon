from __future__ import annotations

NAME = "add-observation-ingest-sequences"
SQL = """
CREATE TABLE observation_ingest_sequences (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  observation_id TEXT NOT NULL UNIQUE REFERENCES capture_observations(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
INSERT INTO observation_ingest_sequences(observation_id)
SELECT id
FROM capture_observations
ORDER BY created_at, id;
"""
DESTRUCTIVE = False
SCHEMA_FINGERPRINT = "86ed5e8fa754ad84d3249c9d207667be5f4940feaa756c974a075d2e3df28bec"
