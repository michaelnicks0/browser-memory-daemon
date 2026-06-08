from __future__ import annotations

import sqlite3
from urllib.parse import urlsplit
import uuid

from .db import audit
from .policy import PolicyDecision

VALID_RULE_TYPES = {"domain", "url-prefix"}
VALID_ACTIONS = {"block"}


def normalize_rule_pattern(rule_type: str, pattern: str) -> str:
    text = str(pattern or "").strip()
    if not text:
        raise ValueError("policy rule pattern is required")
    if rule_type == "domain":
        parts = urlsplit(text if "://" in text else f"https://{text}")
        host = (parts.hostname or text).strip().strip("[]").rstrip(".").lower()
        if not host or "/" in host or " " in host:
            raise ValueError("domain policy rule pattern must be a hostname")
        return host.lstrip(".")
    if rule_type == "url-prefix":
        parts = urlsplit(text)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("url-prefix policy rule pattern must be an absolute http(s) URL prefix")
        return text
    raise ValueError(f"unsupported policy rule type: {rule_type}")


def list_policy_rules(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, rule_type, pattern, action, created_at FROM privacy_rules ORDER BY created_at DESC, pattern ASC"
    ).fetchall()
    return [dict(row) for row in rows]


def create_policy_rule(conn: sqlite3.Connection, *, rule_type: str, pattern: str, action: str = "block") -> dict:
    selected_type = str(rule_type or "").strip().lower()
    selected_action = str(action or "block").strip().lower()
    if selected_type not in VALID_RULE_TYPES:
        raise ValueError(f"policy rule type must be one of: {', '.join(sorted(VALID_RULE_TYPES))}")
    if selected_action not in VALID_ACTIONS:
        raise ValueError("only block policy rules are supported in this phase")
    normalized_pattern = normalize_rule_pattern(selected_type, pattern)
    existing = conn.execute(
        "SELECT id, rule_type, pattern, action, created_at FROM privacy_rules WHERE rule_type = ? AND pattern = ? AND action = ?",
        (selected_type, normalized_pattern, selected_action),
    ).fetchone()
    if existing:
        return dict(existing)
    rule_id = str(uuid.uuid4())
    with conn:
        conn.execute(
            "INSERT INTO privacy_rules(id, rule_type, pattern, action) VALUES (?, ?, ?, ?)",
            (rule_id, selected_type, normalized_pattern, selected_action),
        )
        audit(conn, "policy.rule.created", {"rule_id": rule_id, "rule_type": selected_type, "action": selected_action})
    return {"id": rule_id, "rule_type": selected_type, "pattern": normalized_pattern, "action": selected_action}


def delete_policy_rule(conn: sqlite3.Connection, rule_id: str) -> dict:
    if not rule_id:
        raise ValueError("policy rule id is required")
    with conn:
        count = conn.execute("DELETE FROM privacy_rules WHERE id = ?", (rule_id,)).rowcount
        audit(conn, "policy.rule.deleted", {"rule_id": rule_id, "deleted": bool(count)})
    return {"deleted": bool(count), "id": rule_id}


def evaluate_policy_rules(conn: sqlite3.Connection, url: str) -> PolicyDecision:
    parts = urlsplit(url or "")
    host = (parts.hostname or "").strip().strip("[]").rstrip(".").lower()
    rows = conn.execute("SELECT rule_type, pattern, action FROM privacy_rules WHERE action = 'block'").fetchall()
    for row in rows:
        pattern = row["pattern"]
        if row["rule_type"] == "domain" and _domain_matches(host, pattern):
            return PolicyDecision(False, f"policy-rule:block-domain:{pattern}", "blocked")
        if row["rule_type"] == "url-prefix" and (url or "").startswith(pattern):
            return PolicyDecision(False, "policy-rule:block-url-prefix", "blocked")
    return PolicyDecision(True)


def _domain_matches(host: str, pattern: str) -> bool:
    return bool(host) and (host == pattern or host.endswith(f".{pattern}"))
