from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}

DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = _normalize_netloc(parts)
    query_pairs = [
        (idx, k, v)
        for idx, (k, v) in enumerate(parse_qsl(parts.query, keep_blank_values=True))
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode([(k, v) for _, k, v in sorted(query_pairs, key=lambda item: (item[1].lower(), item[1], item[0]))], doseq=True)
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def domain_from_url(url: str) -> str:
    return urlsplit(url).hostname.lower() if urlsplit(url).hostname else ""


def _normalize_netloc(parts) -> str:
    host = (parts.hostname or "").strip().strip("[]").rstrip(".").lower()
    if not host:
        return parts.netloc.lower()
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port and port != DEFAULT_PORTS.get(parts.scheme.lower()):
        return f"{host}:{port}"
    return host
