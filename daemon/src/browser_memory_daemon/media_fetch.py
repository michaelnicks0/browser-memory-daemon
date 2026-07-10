from __future__ import annotations

import base64
import ipaddress
import socket
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import unquote_to_bytes, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import RuntimeConfig
from .media_resources import MediaResourceLease, MediaResourceUnavailable, media_resource_budget


@dataclass
class FetchedMediaStream:
    stream: BinaryIO | None
    byte_size: int
    mime_type: str
    reason: str
    _resource_lease: MediaResourceLease | None = None

    def close(self) -> None:
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        if self._resource_lease is not None:
            self._resource_lease.release()
            self._resource_lease = None

    def __enter__(self) -> FetchedMediaStream:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

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
    output_stream: BinaryIO | None = None,
) -> tuple[bytes, str, str, str]:
    del page_url  # Public daemon fetch intentionally sends no Referer.
    current_url = source_url
    visited: set[str] = set()
    redirects = 0
    process_budget = media_resource_budget(config)
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
            resource_lease = process_budget.acquire(
                byte_count=0,
                request_count=1,
                timeout=_remaining_timeout(timeout_seconds, deadline),
            )
        except MediaResourceUnavailable:
            return b"", "", current_url, "media-resource-budget"
        try:
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
                    if output_stream is not None:
                        _size, read_reason = _read_http_response_to_stream(
                            response,
                            output_stream,
                            max_bytes=max_bytes,
                        )
                        return b"", str(response.headers.get("content-type", "")), current_url, read_reason
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
        finally:
            resource_lease.release()


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


def _read_http_response_to_stream(response: Any, stream: BinaryIO, *, max_bytes: int) -> tuple[int, str]:
    try:
        content_length = int(response.headers.get("content-length") or "0")
    except ValueError:
        content_length = 0
    if content_length > max_bytes:
        return 0, "media-too-large"
    total = 0
    while True:
        chunk = response.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            return 0, "media-too-large"
        stream.write(chunk)
    return total, ""




def _stream_size(stream: BinaryIO) -> int:
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return size


def _fetch_media_stream(
    source_url: str,
    page_url: str,
    *,
    media_type: str,
    max_bytes: int,
    timeout_seconds: float,
    config: RuntimeConfig,
) -> FetchedMediaStream:
    try:
        resource_lease = media_resource_budget(config).acquire(
            byte_count=max_bytes,
            request_count=0,
            timeout=timeout_seconds,
        )
    except MediaResourceUnavailable:
        return FetchedMediaStream(None, 0, "", "media-resource-budget")
    spool = cast(BinaryIO, tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b"))
    try:
        parts = urlsplit(source_url)
        if parts.scheme == "data":
            content, mime_type, reason = _data_url_to_media(source_url, media_type=media_type, max_bytes=max_bytes)
            if reason:
                spool.close()
                resource_lease.release()
                return FetchedMediaStream(None, 0, mime_type, reason)
            spool.write(content)
            spool.seek(0)
            return FetchedMediaStream(spool, len(content), mime_type, "", resource_lease)
        if parts.scheme not in {"http", "https"}:
            spool.close()
            resource_lease.release()
            return FetchedMediaStream(None, 0, "", "unsupported-media-url-scheme")
        deadline = time.monotonic() + max(0.001, timeout_seconds)
        initial_max_bytes = max_bytes
        if media_type == "video" and parts.path.lower().endswith(".m3u8"):
            initial_max_bytes = min(max_bytes, config.media_hls_playlist_max_bytes)
        _content, raw_content_type, final_url, reason = _guarded_public_fetch(
            config,
            source_url,
            page_url,
            accept="image/*,video/*,audio/*,application/vnd.apple.mpegurl,application/x-mpegURL,application/octet-stream,*/*;q=0.8",
            max_bytes=initial_max_bytes,
            timeout_seconds=timeout_seconds,
            deadline=deadline,
            output_stream=spool,
        )
        if reason:
            spool.close()
            resource_lease.release()
            return FetchedMediaStream(None, 0, "", reason)
        raw_mime = _content_type_mime(raw_content_type)
        response_mime = _safe_response_mime(raw_content_type, media_type=media_type)
        hls_candidate = media_type == "video" and _is_hls_candidate(final_url or source_url, raw_content_type)
        spool.seek(0)
        playlist_probe = spool.read(config.media_hls_playlist_max_bytes + 1) if media_type == "video" else b""
        looks_hls = media_type == "video" and _looks_like_hls_playlist(playlist_probe)
        if raw_mime and not response_mime and not hls_candidate and not looks_hls:
            spool.close()
            resource_lease.release()
            return FetchedMediaStream(None, 0, "", "non-media-content-type")
        if hls_candidate or looks_hls:
            if len(playlist_probe) > config.media_hls_playlist_max_bytes:
                spool.close()
                resource_lease.release()
                return FetchedMediaStream(None, 0, "", "media-too-large")
            from .media_hls import _fetch_hls_media_bytes, _HlsFetchBudget

            spool.seek(0)
            spool.truncate()
            hls_budget = _HlsFetchBudget(
                requests_remaining=max(0, config.media_hls_max_requests - 1),
                deadline=deadline,
            )
            _assembled, hls_mime, hls_reason = _fetch_hls_media_bytes(
                final_url or source_url,
                page_url,
                playlist_probe,
                max_bytes=max_bytes,
                timeout_seconds=timeout_seconds,
                config=config,
                budget=hls_budget,
                deadline=deadline,
                output_stream=spool,
            )
            if hls_reason:
                spool.close()
                resource_lease.release()
                return FetchedMediaStream(None, 0, hls_mime, hls_reason)
            response_mime = hls_mime
        byte_size = _stream_size(spool)
        if byte_size <= 0:
            spool.close()
            resource_lease.release()
            return FetchedMediaStream(None, 0, response_mime, "empty-media-response")
        spool.seek(0)
        return FetchedMediaStream(spool, byte_size, response_mime, "", resource_lease)
    except BaseException:
        spool.close()
        resource_lease.release()
        raise


def _fetch_media_bytes(
    source_url: str,
    page_url: str,
    *,
    media_type: str,
    max_bytes: int,
    timeout_seconds: float,
    config: RuntimeConfig,
) -> tuple[bytes, str, str]:
    with _fetch_media_stream(
        source_url,
        page_url,
        config=config,
        media_type=media_type,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
    ) as fetched:
        if fetched.reason or fetched.stream is None:
            return b"", fetched.mime_type, fetched.reason
        return fetched.stream.read(), fetched.mime_type, ""
