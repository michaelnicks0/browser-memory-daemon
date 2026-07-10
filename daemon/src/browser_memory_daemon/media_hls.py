from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from .config import RuntimeConfig
from .media_fetch import _guarded_public_fetch


@dataclass
class _HlsFetchBudget:
    requests_remaining: int
    deadline: float | None

    def claim_request(self) -> bool:
        if self.requests_remaining <= 0:
            return False
        self.requests_remaining -= 1
        return True


def _parse_hls_attribute_list(value: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    current: list[str] = []
    in_quotes = False
    parts: list[str] = []
    for char in value:
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
        elif char == "," and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    for part in parts:
        key, sep, raw = part.partition("=")
        if not sep:
            continue
        attrs[key.strip().upper()] = raw.strip().strip('"')
    return attrs


def _hls_variant_candidates(playlist_text: str, playlist_url: str) -> list[tuple[int, str]]:
    lines = [line.strip() for line in playlist_text.splitlines()]
    variants: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        attrs = _parse_hls_attribute_list(line.split(":", 1)[1])
        score = int(attrs.get("AVERAGE-BANDWIDTH") or attrs.get("BANDWIDTH") or "0")
        for candidate in lines[index + 1 :]:
            if not candidate or candidate.startswith("#"):
                continue
            variants.append((score, urljoin(playlist_url, candidate)))
            break
    return sorted(variants, key=lambda item: item[0] or 10**12)


def _hls_map_uri(line: str) -> str:
    attrs = _parse_hls_attribute_list(line.split(":", 1)[1] if ":" in line else "")
    return attrs.get("URI", "")


def _fetch_hls_asset(
    source_url: str,
    page_url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    config: RuntimeConfig,
    budget: _HlsFetchBudget,
) -> tuple[bytes, str]:
    content, _content_type, _final_url, reason = _guarded_public_fetch(
        config,
        source_url,
        page_url,
        accept="video/*,application/octet-stream,*/*;q=0.8",
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
        deadline=budget.deadline,
        budget=budget,
    )
    return content, reason


def _fetch_hls_playlist(
    source_url: str,
    page_url: str,
    *,
    timeout_seconds: float,
    config: RuntimeConfig,
    budget: _HlsFetchBudget,
) -> tuple[str, str]:
    content, _content_type, _final_url, reason = _guarded_public_fetch(
        config,
        source_url,
        page_url,
        accept="application/vnd.apple.mpegurl,application/x-mpegURL,*/*;q=0.8",
        max_bytes=config.media_hls_playlist_max_bytes,
        timeout_seconds=timeout_seconds,
        deadline=budget.deadline,
        budget=budget,
    )
    if reason:
        return "", reason
    return content.decode("utf-8", "replace"), ""


def _hls_playlist_to_media(
    playlist_url: str,
    page_url: str,
    playlist_text: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    config: RuntimeConfig,
    budget: _HlsFetchBudget,
    deadline: float | None = None,
    depth: int = 0,
) -> tuple[bytes, str, str]:
    if _hls_deadline_expired(budget.deadline if budget.deadline is not None else deadline):
        return b"", "", "hls-time-budget-exceeded"
    if depth > config.media_hls_max_depth:
        return b"", "", "hls-depth-exceeded"
    if not playlist_text.lstrip().startswith("#EXTM3U"):
        return b"", "", "hls-invalid-playlist"
    variants = _hls_variant_candidates(playlist_text, playlist_url)
    if variants:
        last_reason = "hls-no-video-variant"
        for _, variant_url in variants:
            if _hls_deadline_expired(budget.deadline):
                return b"", "", "hls-time-budget-exceeded"
            variant_text, reason = _fetch_hls_playlist(
                variant_url,
                page_url,
                timeout_seconds=_remaining_hls_timeout(timeout_seconds, budget.deadline),
                config=config,
                budget=budget,
            )
            if reason:
                last_reason = reason
                continue
            content, mime, reason = _hls_playlist_to_media(
                variant_url,
                page_url,
                variant_text,
                max_bytes=max_bytes,
                timeout_seconds=_remaining_hls_timeout(timeout_seconds, budget.deadline),
                config=config,
                budget=budget,
                deadline=budget.deadline,
                depth=depth + 1,
            )
            if not reason:
                return content, mime, ""
            last_reason = reason
        return b"", "", last_reason

    path = urlsplit(playlist_url).path.lower()
    is_audio_rendition = "/mp4a/" in path or "/audio" in path

    init_url = ""
    segment_urls: list[str] = []
    for line in (line.strip() for line in playlist_text.splitlines()):
        if not line:
            continue
        if line.startswith("#EXT-X-MAP:"):
            init_uri = _hls_map_uri(line)
            if init_uri:
                init_url = urljoin(playlist_url, init_uri)
            continue
        if line.startswith("#"):
            continue
        segment_urls.append(urljoin(playlist_url, line))

    if not segment_urls:
        return b"", "", "hls-empty-playlist"

    content_parts: list[bytes] = []
    total = 0
    if init_url:
        if _hls_deadline_expired(budget.deadline):
            return b"", "", "hls-time-budget-exceeded"
        init_content, reason = _fetch_hls_asset(
            init_url,
            page_url,
            max_bytes=max_bytes,
            timeout_seconds=_remaining_hls_timeout(timeout_seconds, budget.deadline),
            config=config,
            budget=budget,
        )
        if reason:
            return b"", "", reason
        content_parts.append(init_content)
        total += len(init_content)

    for segment_url in segment_urls:
        if _hls_deadline_expired(budget.deadline):
            return b"", "", "hls-time-budget-exceeded"
        segment, reason = _fetch_hls_asset(
            segment_url,
            page_url,
            max_bytes=max_bytes - total,
            timeout_seconds=_remaining_hls_timeout(timeout_seconds, budget.deadline),
            config=config,
            budget=budget,
        )
        if reason:
            return b"", "", reason
        total += len(segment)
        if total > max_bytes:
            return b"", "", "media-too-large"
        content_parts.append(segment)

    joined = b"".join(content_parts)
    segment_paths = [urlsplit(url).path.lower() for url in segment_urls]
    if is_audio_rendition:
        if any(path.endswith(".aac") for path in segment_paths):
            return joined, "audio/aac", ""
        if any(path.endswith(".mp3") for path in segment_paths):
            return joined, "audio/mpeg", ""
        return joined, "audio/mp4", ""
    if init_url or any(path.endswith((".m4s", ".mp4")) for path in segment_paths):
        return joined, "video/mp4", ""
    return joined, "video/mp2t", ""


def _hls_deadline_expired(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _remaining_hls_timeout(timeout_seconds: float, deadline: float | None) -> float:
    if deadline is None:
        return timeout_seconds
    return max(0.001, min(timeout_seconds, deadline - time.monotonic()))


def _fetch_hls_media_bytes(
    source_url: str,
    page_url: str,
    playlist_content: bytes,
    *,
    max_bytes: int,
    timeout_seconds: float,
    config: RuntimeConfig,
    budget: _HlsFetchBudget,
    deadline: float | None = None,
) -> tuple[bytes, str, str]:
    playlist_text = playlist_content.decode("utf-8", "replace")
    return _hls_playlist_to_media(
        source_url,
        page_url,
        playlist_text,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
        config=config,
        budget=budget,
        deadline=deadline,
    )
