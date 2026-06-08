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


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    query = urlencode(query_pairs, doseq=True)
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def domain_from_url(url: str) -> str:
    return urlsplit(url).hostname.lower() if urlsplit(url).hostname else ""
