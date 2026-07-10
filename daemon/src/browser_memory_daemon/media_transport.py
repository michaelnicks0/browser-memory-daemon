from __future__ import annotations

import tempfile
import time
from typing import BinaryIO, cast
from urllib.parse import urlsplit

from .config import RuntimeConfig
from .media_fetch import (
    FetchedMediaStream,
    _content_type_mime,
    _data_url_to_media,
    _guarded_public_fetch,
    _is_hls_candidate,
    _looks_like_hls_playlist,
    _safe_response_mime,
)
from .media_hls import _fetch_hls_media_bytes, _HlsFetchBudget
from .media_resources import MediaResourceUnavailable, media_resource_budget


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
        hls_budget = (
            _HlsFetchBudget(requests_remaining=config.media_hls_max_requests, deadline=deadline)
            if media_type == "video"
            else None
        )
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
            budget=hls_budget,
            output_stream=spool,
            hls_playlist_max_bytes=(config.media_hls_playlist_max_bytes if media_type == "video" else None),
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
            assert hls_budget is not None
            spool.seek(0)
            spool.truncate()
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
