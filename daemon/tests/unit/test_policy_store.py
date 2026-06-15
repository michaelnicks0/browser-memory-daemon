import sqlite3

import pytest

from browser_memory_daemon.db import init_db
from browser_memory_daemon.policy_store import create_policy_rule, evaluate_policy_rules, normalize_rule_pattern
from browser_memory_daemon.config import load_config


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
