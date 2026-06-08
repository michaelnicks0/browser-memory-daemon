from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from urllib.parse import urlsplit


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_iso_datetime(value: str | None, field_name: str) -> str | None:
    if value in {None, ""}:
        return None
    text = str(value)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601 datetime") from exc
    return text


@dataclass(frozen=True)
class CapturePayload:
    url: str
    text: str
    title: str = ""
    canonical_url: str = ""
    source: str = "chrome-extension"
    source_device: str = "workstation1-windows-chrome"
    browser_profile: str = "Default"
    visit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    captured_at: str = field(default_factory=utc_now_iso)
    visit_started_at: str | None = None
    dwell_seconds: int | None = None
    extraction_method: str = "dom-visible-text-v1"
    content_type: str = "text/html"
    is_incognito: bool = False

    @classmethod
    def from_dict(cls, data: dict, *, max_text_chars: int = 1_000_000) -> "CapturePayload":
        url = str(data.get("url") or "").strip()
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("url must be an absolute http(s) URL")
        text = str(data.get("text") or "")
        if not text.strip():
            raise ValueError("text is required")
        if len(text) > max_text_chars:
            raise ValueError("text payload too large")
        captured_at = validate_iso_datetime(data.get("captured_at") or data.get("capturedAt") or utc_now_iso(), "captured_at")
        visit_started_at = validate_iso_datetime(data.get("visit_started_at") or data.get("visitStartedAt"), "visit_started_at")
        dwell = data.get("dwell_seconds") if "dwell_seconds" in data else data.get("dwellSeconds")
        if dwell is not None:
            dwell = int(dwell)
            if dwell < 0:
                raise ValueError("dwell_seconds must be non-negative")
        return cls(
            url=url,
            text=text,
            title=str(data.get("title") or ""),
            canonical_url=str(data.get("canonical_url") or data.get("canonicalUrl") or ""),
            source=str(data.get("source") or "chrome-extension"),
            source_device=str(data.get("source_device") or data.get("sourceDevice") or "workstation1-windows-chrome"),
            browser_profile=str(data.get("browser_profile") or data.get("browserProfile") or "Default"),
            visit_id=str(data.get("visit_id") or data.get("visitId") or uuid.uuid4()),
            captured_at=captured_at or utc_now_iso(),
            visit_started_at=visit_started_at,
            dwell_seconds=dwell,
            extraction_method=str(data.get("extraction_method") or data.get("extractionMethod") or "dom-visible-text-v1"),
            content_type=str(data.get("content_type") or data.get("contentType") or "text/html"),
            is_incognito=bool(data.get("is_incognito") or data.get("incognito") or False),
        )
