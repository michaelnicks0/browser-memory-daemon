ALTER TABLE snapshots ADD COLUMN cleaned_text TEXT;
ALTER TABLE snapshots ADD COLUMN cleaned_text_source TEXT NOT NULL DEFAULT 'legacy-fallback'
  CHECK (cleaned_text_source IN ('legacy-fallback', 'capture', 'chunks-hash-verified', 'sidecar-hash-verified'));