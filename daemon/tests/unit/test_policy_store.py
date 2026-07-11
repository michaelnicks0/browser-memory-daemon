import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.migrations import MigrationCompatibilityError
from browser_memory_daemon.policy_store import create_policy_rule, evaluate_policy_rules, normalize_rule_pattern


def _conn(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
    init_db(cfg)
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_domain_rule_rejects_port_or_path_to_prevent_overbroad_localhost_blocks():
    with pytest.raises(ValueError, match="use url-prefix"):
        normalize_rule_pattern("domain", "127.0.0.1:32400")
    with pytest.raises(ValueError, match="use url-prefix"):
        normalize_rule_pattern("domain", "https://example.com/private")


def test_url_prefix_rule_scopes_to_port_and_path(tmp_path):
    conn = _conn(tmp_path)
    try:
        rule = create_policy_rule(
            conn,
            rule_type="url-prefix",
            pattern="http://127.0.0.1:32400/web/",
            action="block",
        )
        assert rule["pattern"] == "http://127.0.0.1:32400/web/"

        blocked = evaluate_policy_rules(conn, "http://127.0.0.1:32400/web/index.html")
        assert blocked.allowed is False
        assert blocked.reason == "policy-rule:block-url-prefix:http://127.0.0.1:32400/web/"

        assert evaluate_policy_rules(conn, "http://127.0.0.1:8765/ui").allowed is True
        assert evaluate_policy_rules(conn, "http://127.0.0.1:32400/other").allowed is True
        assert evaluate_policy_rules(conn, "http://localhost:32400/web/index.html").allowed is True
    finally:
        conn.close()


def test_policy_rule_creation_is_semantically_idempotent_under_concurrency(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
    init_db(cfg)

    def create_once(_idx: int) -> dict:
        with connect(cfg.db_path) as conn:
            return create_policy_rule(conn, rule_type="domain", pattern="Example.COM.", action="block")

    with ThreadPoolExecutor(max_workers=8) as executor:
        rules = list(executor.map(create_once, range(8)))

    assert {rule["id"] for rule in rules} == {rules[0]["id"]}
    assert all(rule["pattern"] == "example.com" for rule in rules)
    with connect(cfg.db_path) as conn:
        rows = conn.execute("SELECT id, rule_type, pattern, action FROM privacy_rules").fetchall()
        assert len(rows) == 1
        assert dict(rows[0]) == {"id": rules[0]["id"], "rule_type": "domain", "pattern": "example.com", "action": "block"}


def test_init_db_rejects_schema_drift_instead_of_replaying_policy_dedupe(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        conn.execute("DROP INDEX IF EXISTS idx_privacy_rules_semantics")
        conn.execute("INSERT INTO privacy_rules(id, rule_type, pattern, action) VALUES ('rule-a', 'domain', 'duplicate.example', 'block')")
        conn.execute("INSERT INTO privacy_rules(id, rule_type, pattern, action) VALUES ('rule-b', 'domain', 'duplicate.example', 'block')")
        conn.commit()

    with pytest.raises(MigrationCompatibilityError, match="schema fingerprint mismatch"):
        init_db(cfg)
    with connect(cfg.db_path) as conn:
        rows = conn.execute("SELECT id, rule_type, pattern, action FROM privacy_rules WHERE pattern = 'duplicate.example'").fetchall()
        assert [row["id"] for row in rows] == ["rule-a", "rule-b"]
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE type = 'index' AND name = 'idx_privacy_rules_semantics'"
        ).fetchone()[0] == 0
