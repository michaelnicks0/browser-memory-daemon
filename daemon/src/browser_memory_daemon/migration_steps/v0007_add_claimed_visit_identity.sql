ALTER TABLE visit_events ADD COLUMN claimed_visit_id TEXT;
ALTER TABLE visit_events ADD COLUMN attachment_method TEXT NOT NULL DEFAULT 'historical' CHECK (attachment_method IN ('historical', 'visit-id', 'visit-id-delayed', 'legacy-url-fallback', 'unmatched'));
UPDATE visit_events
SET claimed_visit_id = visit_id
WHERE visit_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_visit_events_claimed_visit
  ON visit_events(claimed_visit_id, normalized_url, event_started_at);
