NAME = "normalize_baseline_reference_data"
SQL = """
INSERT OR IGNORE INTO sources(id, source_type, source_name)
VALUES ('chrome-extension', 'browser', 'chrome-extension');

DELETE FROM privacy_rules
WHERE rowid NOT IN (
  SELECT MIN(rowid)
  FROM privacy_rules
  GROUP BY rule_type, pattern, action
);
"""
