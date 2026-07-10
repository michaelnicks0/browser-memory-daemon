from __future__ import annotations

import base64
import ipaddress
import socket
import time
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import unquote_to_bytes, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import RuntimeConfig

SAFE_MEDIA_SUFFIX_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".m4s": "video/mp4",
    ".ts": "video/mp2t",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".mp3": "audio/mpeg",
}

EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/ogg": ".ogv",
    "video/quicktime": ".mov",
    "video/mp2t": ".ts",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".oga",
    "audio/webm": ".weba",
}

HLS_MIME_TYPES = {
    "application/x-mpegurl",
    "application/vnd.apple.mpegurl",
    "application/mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
}


class _FetchBudget(Protocol):
    deadline: float | None

    def claim_request(self) -> bool: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler)


def _open_public_no_redirect(request: Request, *, timeout: float) -> Any:
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


_PUBLIC_FETCH_OPENER = _open_public_no_redirect
_PUBLIC_FETCH_RESOLVER = socket.getaddrinfo


def _sanitize_mime(value: Any, *, media_type: str = "") -> str:
    mime = str(value or "").split(";", 1)[0].strip().lower()
    if not mime:
        return ""
    if media_type == "image" and not mime.startswith("image/"):
        return ""
    if media_type == "video" and not (mime.startswith("video/") or mime.startswith("audio/")):
        return ""
    if media_type == "audio" and not mime.startswith("audio/"):
        return ""
    return mime[:128]


def _infer_mime_from_url(source_url: str, media_type: str) -> str:
    suffix = Path(urlsplit(source_url or "").path).suffix.lower()
    if suffix in SAFE_MEDIA_SUFFIX_MIME:
        return _sanitize_mime(SAFE_MEDIA_SUFFIX_MIME[suffix], media_type=media_type)
    return ""


def _file_extension(mime_type: str, source_url: str) -> str:
    if mime_type in EXT_BY_MIME:
        return EXT_BY_MIME[mime_type]
    suffix = Path(urlsplit(source_url).path).suffix.lower()
    if suffix in SAFE_MEDIA_SUFFIX_MIME and _sanitize_mime(SAFE_MEDIA_SUFFIX_MIME[suffix], media_type=""):
        return suffix
    if mime_type.startswith("image/"):
        return ".img"
    if mime_type.startswith("video/"):
        return ".video"
    if mime_type.startswith("audio/"):
        return ".audio"
    return ".bin"


def _safe_response_mime(value: str, *, media_type: str) -> str:
    return _sanitize_mime(value, media_type=media_type)


def _data_url_to_media(data_url: str, *, media_type: str, max_bytes: int) -> tuple[bytes, str, str]:
    header, separator, payload = data_url.partition(",")
    if not separator:
        return b"", "", "invalid-data-url"
    header_lower = header.lower()
    mime = _safe_response_mime(header_lower.removeprefix("data:").split(";", 1)[0], media_type=media_type)
    try:
        content = base64.b64decode(payload, validate=True) if ";base64" in header_lower else unquote_to_bytes(payload)
    except Exception:
        return b"", mime, "invalid-data-url-payload"
    if len(content) > max_bytes:
        return b"", mime, "media-too-large"
    return content, mime, ""


def _request_for_url(source_url: str, page_url: str, *, accept: str) -> Request:
    del page_url
    return Request(
        source_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149 Safari/537.36 BrowserMemoryDaemon/0.1",
            "Accept": accept,
        },
    )


def _normalized_host(value: str) -> str:
    return str(value or "").strip().strip("[]").rstrip(".").lower()


def _private_host_allowed(config: RuntimeConfig, host: str) -> bool:
    normalized = _normalized_host(host)
    return normalized in {_normalized_host(item) for item in config.media_public_fetch_allow_private_hosts}


def _is_public_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return parsed.is_global


def _resolved_addresses(host: str, port: int) -> tuple[list[str], str]:
    try:
        infos = _PUBLIC_FETCH_RESOLVER(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return [], f"fetch-error-dns-{str(exc)[:120]}"
    except Exception as exc:
        return [], f"fetch-error-dns-{str(exc)[:120]}"
    addresses: list[str] = []
    for info in infos:
        try:
            sockaddr = info[4]
            address = str(sockaddr[0])
        except Exception:
            continue
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        return [], "fetch-error-dns-empty"
    return addresses, ""


def _validate_public_fetch_url(config: RuntimeConfig, source_url: str) -> str:
    parts = urlsplit(source_url)
    if parts.scheme not in {"http", "https"}:
        return "fetch-blocked-url-scheme"
    host = parts.hostname or ""
    if not host:
        return "fetch-blocked-private-host"
    if _private_host_allowed(config, host):
        return ""
    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        return "fetch-blocked-private-address"
    addresses, reason = _resolved_addresses(host, parts.port or (443 if parts.scheme == "https" else 80))
    if reason:
        return reason
    if any(not _is_public_address(address) for address in addresses):
        return "fetch-blocked-private-address"
    return ""


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None) or getattr(response, "code", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    try:
        return int(status or 200)
    except (TypeError, ValueError):
        return 200


def _response_header(headers: Any, name: str) -> str:
    if not headers:
        return ""
    return str(headers.get(name) or headers.get(name.lower()) or headers.get(name.title()) or "")


def _redirect_target(current_url: str, location: str) -> str:
    return urljoin(current_url, location.strip())


def _deadline_expired(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _remaining_timeout(timeout_seconds: float, deadline: float | None) -> float:
    if deadline is None:
        return timeout_seconds
    return max(0.001, min(timeout_seconds, deadline - time.monotonic()))


def _guarded_public_fetch(
    config: RuntimeConfig,
    source_url: str,
    page_url: str,
    *,
    accept: str,
    max_bytes: int,
    timeout_seconds: float,
    deadline: float | None = None,
    budget: _FetchBudget | None = None,
) -> tuple[bytes, str, str, str]:
    del page_url  # Public daemon fetch intentionally sends no Referer.
    current_url = source_url
    visited: set[str] = set()
    redirects = 0
    while True:
        if _deadline_expired(deadline):
            return b"", "", current_url, "hls-time-budget-exceeded"
        if current_url in visited:
            return b"", "", current_url, "fetch-redirect-loop"
        visited.add(current_url)
        reason = _validate_public_fetch_url(config, current_url)
        if reason:
            return b"", "", current_url, reason
        if budget is not None and not budget.claim_request():
            return b"", "", current_url, "hls-request-budget-exceeded"
        request = _request_for_url(current_url, "", accept=accept)
        try:
            with _PUBLIC_FETCH_OPENER(request, timeout=_remaining_timeout(timeout_seconds, deadline)) as response:
                status = _response_status(response)
                if 300 <= status < 400:
                    location = _response_header(response.headers, "location")
                    if not location:
                        return b"", "", current_url, "fetch-redirect-missing-location"
                    redirects += 1
                    if redirects > config.media_public_fetch_max_redirects:
                        return b"", "", current_url, "fetch-too-many-redirects"
                    current_url = _redirect_target(current_url, location)
                    continue
                if status >= 400:
                    return b"", "", current_url, f"fetch-status-{status}"
                content, read_reason = _read_http_response_limited(response, max_bytes=max_bytes)
                return content, str(response.headers.get("content-type", "")), current_url, read_reason
        except HTTPError as exc:
            if 300 <= int(exc.code) < 400:
                location = _response_header(exc.headers, "location")
                if not location:
                    return b"", "", current_url, "fetch-redirect-missing-location"
                redirects += 1
                if redirects > config.media_public_fetch_max_redirects:
                    return b"", "", current_url, "fetch-too-many-redirects"
                current_url = _redirect_target(current_url, location)
                continue
            return b"", "", current_url, f"fetch-status-{exc.code}"
        except TimeoutError:
            return b"", "", current_url, "fetch-timeout"
        except URLError as exc:
            url_reason = getattr(exc, "reason", exc)
            return b"", "", current_url, f"fetch-error-{str(url_reason)[:160]}"
        except Exception as exc:
            return b"", "", current_url, f"fetch-error-{str(exc)[:160]}"


def _content_type_mime(value: str) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _is_hls_candidate(source_url: str, content_type: str) -> bool:
    mime = _content_type_mime(content_type)
    path = urlsplit(source_url or "").path.lower()
    return mime in HLS_MIME_TYPES or path.endswith(".m3u8")


def _looks_like_hls_playlist(content: bytes) -> bool:
    return content.lstrip().startswith(b"#EXTM3U")


def _read_http_response_limited(response: Any, *, max_bytes: int) -> tuple[bytes, str]:
    try:
        content_length = int(response.headers.get("content-length") or "0")
    except ValueError:
        content_length = 0
    if content_length > max_bytes:
        return b"", "media-too-large"
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            return b"", "media-too-large"
        chunks.append(chunk)
    return b"".join(chunks), ""


def _fetch_media_bytes(
    source_url: str,
    page_url: str,
    *,
    media_type: str,
    max_bytes: int,
    timeout_seconds: float,
    config: RuntimeConfig,
) -> tuple[bytes, str, str]:
    parts = urlsplit(source_url)
    if parts.scheme == "data":
        return _data_url_to_media(source_url, media_type=media_type, max_bytes=max_bytes)
    if parts.scheme not in {"http", "https"}:
        return b"", "", "unsupported-media-url-scheme"
    deadline = time.monotonic() + max(0.001, timeout_seconds)
    initial_max_bytes = max_bytes
    if media_type == "video" and parts.path.lower().endswith(".m3u8"):
        initial_max_bytes = min(max_bytes, config.media_hls_playlist_max_bytes)
    content, raw_content_type, final_url, reason = _guarded_public_fetch(
        config,
        source_url,
        page_url,
        accept="image/avif,image/webp,image/apng,image/svg+xml,image/*,video/*,application/vnd.apple.mpegurl,application/x-mpegURL,*/*;q=0.8",
        max_bytes=initial_max_bytes,
        timeout_seconds=timeout_seconds,
        deadline=deadline,
    )
    response_mime = _safe_response_mime(raw_content_type, media_type=media_type)
    hls_candidate = media_type == "video" and _is_hls_candidate(final_url or source_url, raw_content_type)
    if reason:
        return b"", response_mime, reason
    if hls_candidate or (media_type == "video" and _looks_like_hls_playlist(content)):
        if len(content) > config.media_hls_playlist_max_bytes:
            return b"", "", "media-too-large"
    if raw_content_type and not response_mime and not hls_candidate:
        return b"", "", "non-media-content-type"
    if media_type == "video" and (hls_candidate or _looks_like_hls_playlist(content)):
        from .media_hls import (
            _fetch_hls_media_bytes,
            _HlsFetchBudget,
        )

        budget = _HlsFetchBudget(requests_remaining=max(0, config.media_hls_max_requests - 1), deadline=deadline)
        return _fetch_hls_media_bytes(
            final_url or source_url,
            page_url,
            content,
            max_bytes=max_bytes,
            timeout_seconds=_remaining_timeout(timeout_seconds, deadline),
            config=config,
            budget=budget,
            deadline=deadline,
        )
    return content, response_mime, ""
