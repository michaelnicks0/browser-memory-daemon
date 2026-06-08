from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BLOCKED_SCHEMES = {"chrome", "chrome-extension", "edge", "about", "file", "data", "javascript"}
SENSITIVE_DOMAIN_KEYWORDS = {
    "admin",
    "auth",
    "account",
    "accounts",
    "bank",
    "banking",
    "billing",
    "card",
    "checkout",
    "chat",
    "claims",
    "discord",
    "doctor",
    "gmail",
    "health",
    "insurance",
    "irs",
    "legal",
    "login",
    "mail",
    "medical",
    "messages",
    "mychart",
    "oauth",
    "outlook",
    "patient",
    "paypal",
    "signin",
    "slack",
    "tax",
    "telegram",
}
SENSITIVE_PATH_KEYWORDS = {
    "account",
    "admin",
    "auth",
    "billing",
    "checkout",
    "login",
    "logout",
    "oauth",
    "password",
    "payment",
    "profile",
    "settings",
    "signin",
    "token",
}
BLOCKED_DOMAIN_SUFFIXES = {
    "accounts.google.com",
    "bankofamerica.com",
    "capitalone.com",
    "chase.com",
    "mail.google.com",
    "outlook.live.com",
    "outlook.office.com",
    "paypal.com",
    "wellsfargo.com",
}
SECRETISH_PATH_SEGMENT = re.compile(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9._~+=-]{16,}")

SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "auth",
    "code",
    "key",
    "magic",
    "password",
    "refresh_token",
    "session",
    "sessionid",
    "sid",
    "state",
    "token",
}

REDACTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b")),
    ("api_key", re.compile(r"\b(?:api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{16,}", re.I)),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
]


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = "allowed"
    privacy_class: str = "normal"


def _normalized_host(host: str) -> str:
    return (host or "").strip().strip("[]").rstrip(".").lower()


def _is_private_or_loopback_host(host: str) -> bool:
    host = _normalized_host(host)
    if host == "localhost" or host.endswith(".localhost") or host.startswith("127."):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _host_labels(host: str) -> set[str]:
    host = _normalized_host(host)
    labels = set(host.replace("-", ".").split("."))
    if host.endswith(".google.com") and "accounts" in labels:
        labels.add("account")
    return labels


def evaluate_capture(url: str, *, is_incognito: bool = False) -> PolicyDecision:
    if is_incognito:
        return PolicyDecision(False, "incognito-blocked", "blocked")
    parts = urlsplit(url or "")
    if not parts.scheme:
        return PolicyDecision(False, "missing-url-scheme", "blocked")
    if parts.scheme.lower() in BLOCKED_SCHEMES:
        return PolicyDecision(False, f"blocked-scheme:{parts.scheme.lower()}", "blocked")
    host = _normalized_host(parts.hostname or "")
    if not host:
        return PolicyDecision(False, "missing-host", "blocked")
    if _is_private_or_loopback_host(host):
        return PolicyDecision(False, "private-or-loopback-host", "blocked")
    for blocked_domain in BLOCKED_DOMAIN_SUFFIXES:
        if host == blocked_domain or host.endswith(f".{blocked_domain}"):
            return PolicyDecision(False, f"blocked-domain:{blocked_domain}", "blocked")
    labels = _host_labels(host)
    hits = labels & SENSITIVE_DOMAIN_KEYWORDS
    if hits:
        return PolicyDecision(False, f"sensitive-domain:{sorted(hits)[0]}", "blocked")
    path_labels = set(filter(None, re.split(r"[^a-zA-Z0-9]+", (parts.path or "").lower())))
    path_hits = path_labels & SENSITIVE_PATH_KEYWORDS
    if path_hits:
        return PolicyDecision(False, f"sensitive-path:{sorted(path_hits)[0]}", "blocked")
    query_keys = {k.lower() for k, _ in parse_qsl(parts.query, keep_blank_values=True)}
    query_hits = query_keys & SENSITIVE_QUERY_KEYS
    if query_hits:
        return PolicyDecision(False, f"sensitive-query:{sorted(query_hits)[0]}", "blocked")
    return PolicyDecision(True)


def redact_text(text: str) -> tuple[str, int, list[str]]:
    redacted = text or ""
    count = 0
    classes: list[str] = []
    for label, pattern in REDACTION_PATTERNS:
        redacted, n = pattern.subn(f"[REDACTED:{label}]", redacted)
        if n:
            count += n
            classes.append(label)
    return redacted, count, classes


def redact_url(url: str) -> tuple[str, int, list[str]]:
    if not url:
        return "", 0, []
    parts = urlsplit(url)
    count = 0
    classes: list[str] = []
    safe_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            safe_pairs.append((key, "[REDACTED:url_secret]"))
            count += 1
            if "url_secret" not in classes:
                classes.append("url_secret")
        else:
            safe_value, n, labels = redact_text(value)
            safe_pairs.append((key, safe_value))
            count += n
            classes.extend(label for label in labels if label not in classes)
    fragment = ""
    if parts.fragment:
        fragment = "[REDACTED:url_fragment]"
        count += 1
        classes.append("url_fragment")
    safe_segments = []
    for segment in parts.path.split("/"):
        if SECRETISH_PATH_SEGMENT.fullmatch(segment):
            safe_segments.append("[REDACTED:path_secret]")
            count += 1
            if "path_secret" not in classes:
                classes.append("path_secret")
        else:
            safe_segment, n, labels = redact_text(segment)
            safe_segments.append(safe_segment)
            count += n
            classes.extend(label for label in labels if label not in classes)
    safe_path = "/".join(safe_segments)
    safe_query = urlencode(safe_pairs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, safe_path, safe_query, fragment)), count, classes
