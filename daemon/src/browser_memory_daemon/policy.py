from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

POLICY_MODE_ALL = "all"
POLICY_MODE_RECALL = "recall"
POLICY_MODE_BALANCED = "balanced"
POLICY_MODE_STRICT = "strict"
POLICY_MODES = {POLICY_MODE_ALL, POLICY_MODE_RECALL, POLICY_MODE_BALANCED, POLICY_MODE_STRICT}
DEFAULT_POLICY_MODE = POLICY_MODE_ALL

BLOCKED_SCHEMES = {"chrome", "chrome-extension", "edge", "about", "data", "javascript"}
FILE_SCHEME = "file"
WEB_SCHEMES = {"http", "https"}

# Strict mode preserves the original broad keyword guardrails.
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

STRICT_BLOCK_QUERY_KEYS = {
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
BALANCED_BLOCK_QUERY_KEYS = {
    "access_token",
    "api_key",
    "password",
    "refresh_token",
    "session",
    "sessionid",
    "sid",
    "token",
}

# Non-all modes redact these URL values when storage is allowed. All mode bypasses redaction.
SENSITIVE_QUERY_KEYS = STRICT_BLOCK_QUERY_KEYS
REDACT_QUERY_KEYS = STRICT_BLOCK_QUERY_KEYS | {
    "callbackurl",
    "callback_url",
    "continue",
    "id_token",
    "redirect_uri",
    "returnto",
    "return_to",
    "user_code",
}

OPAQUE_PATH_SEGMENT = re.compile(
    r"(?:"
    r"[A-Fa-f0-9]{24,}"  # long hex IDs
    r"|[A-Za-z0-9_-]{32,}"  # long opaque base64/base58-ish IDs
    r"|[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"  # JWT-ish
    r")"
)

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


def normalize_policy_mode(policy_mode: str | None) -> str:
    mode = str(policy_mode or DEFAULT_POLICY_MODE).strip().lower()
    if mode not in POLICY_MODES:
        raise ValueError(f"policy_mode must be one of: {', '.join(sorted(POLICY_MODES))}")
    return mode


def redaction_enabled(policy_mode: str | None) -> bool:
    return normalize_policy_mode(policy_mode) != POLICY_MODE_ALL


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


def _base_web_decision(url: str, *, is_incognito: bool, policy_mode: str) -> tuple[PolicyDecision | None, SplitResult, str]:
    parts = urlsplit(url or "")
    if is_incognito and policy_mode != POLICY_MODE_ALL:
        return PolicyDecision(False, "incognito-blocked", "blocked"), parts, ""
    if not parts.scheme:
        return PolicyDecision(False, "missing-url-scheme", "blocked"), parts, ""
    scheme = parts.scheme.lower()
    if policy_mode == POLICY_MODE_ALL:
        return None, parts, _normalized_host(parts.hostname or "")
    if scheme in BLOCKED_SCHEMES or scheme == FILE_SCHEME:
        return PolicyDecision(False, f"blocked-scheme:{scheme}", "blocked"), parts, ""
    if scheme not in WEB_SCHEMES:
        return PolicyDecision(False, f"blocked-scheme:{scheme}", "blocked"), parts, ""
    host = _normalized_host(parts.hostname or "")
    if not host:
        return PolicyDecision(False, "missing-host", "blocked"), parts, host
    if policy_mode in {POLICY_MODE_STRICT, POLICY_MODE_BALANCED} and _is_private_or_loopback_host(host):
        return PolicyDecision(False, "private-or-loopback-host", "blocked"), parts, host
    return None, parts, host


def evaluate_capture(url: str, *, is_incognito: bool = False, policy_mode: str | None = None) -> PolicyDecision:
    """Return the capture decision for a URL under the selected policy mode.

    Modes:
    - all: no URL/incognito filtering; caller/platform constraints only.
    - recall: capture nearly all http(s); block browser/file/non-web schemes and incognito only.
    - balanced: block private/local hosts, known high-risk domains, and high-risk query keys.
    - strict: original broad domain/path/query keyword filtering.
    """
    mode = normalize_policy_mode(policy_mode)
    if mode == POLICY_MODE_ALL:
        return PolicyDecision(True, "allowed:all", "all")

    base_decision, parts, host = _base_web_decision(url, is_incognito=is_incognito, policy_mode=mode)
    if base_decision is not None:
        return base_decision
    if mode == POLICY_MODE_RECALL:
        return PolicyDecision(True, "allowed:recall", "normal")

    for blocked_domain in BLOCKED_DOMAIN_SUFFIXES:
        if host == blocked_domain or host.endswith(f".{blocked_domain}"):
            return PolicyDecision(False, f"blocked-domain:{blocked_domain}", "blocked")

    query_keys = {k.lower() for k, _ in parse_qsl(parts.query, keep_blank_values=True)}
    block_query_keys = STRICT_BLOCK_QUERY_KEYS if mode == POLICY_MODE_STRICT else BALANCED_BLOCK_QUERY_KEYS
    query_hits = query_keys & block_query_keys
    if query_hits:
        return PolicyDecision(False, f"sensitive-query:{sorted(query_hits)[0]}", "blocked")

    if mode == POLICY_MODE_BALANCED:
        return PolicyDecision(True, "allowed:balanced", "normal")

    labels = _host_labels(host)
    hits = labels & SENSITIVE_DOMAIN_KEYWORDS
    if hits:
        return PolicyDecision(False, f"sensitive-domain:{sorted(hits)[0]}", "blocked")
    path_labels = set(filter(None, re.split(r"[^a-zA-Z0-9]+", (parts.path or "").lower())))
    path_hits = path_labels & SENSITIVE_PATH_KEYWORDS
    if path_hits:
        return PolicyDecision(False, f"sensitive-path:{sorted(path_hits)[0]}", "blocked")
    return PolicyDecision(True, "allowed:strict", "normal")


def _netloc_without_userinfo(parts) -> str:
    host = parts.hostname or ""
    if not host:
        return parts.netloc
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port:
        return f"{host}:{port}"
    return host


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
    safe_netloc = parts.netloc
    if parts.username is not None or parts.password is not None:
        safe_netloc = _netloc_without_userinfo(parts)
        count += 1
        classes.append("url_userinfo")
    safe_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in REDACT_QUERY_KEYS:
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
        if OPAQUE_PATH_SEGMENT.fullmatch(segment):
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
    return urlunsplit((parts.scheme, safe_netloc, safe_path, safe_query, fragment)), count, classes
