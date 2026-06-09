from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from .db import audit
from .models import utc_now_iso, validate_iso_datetime
from .normalize import normalize_url
from .policy import redact_url, redaction_enabled

_ALLOWED_EVENT_TYPES = {
    "active-segment",
    "tab-activated",
    "tab-deactivated",
    "tab-closed",
    "navigation-away",
    "window-blurred",
}


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _optional_int(value: Any, field_name: str, *, minimum: int = 0, maximum: int | None = None) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if parsed < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{field_name} must be <= {maximum}")
    return parsed


def _find_visit(conn: sqlite3.Connection, *, visit_id: str | None, normalized_url: str) -> sqlite3.Row | None:
    if visit_id:
        row = conn.execute(
            "SELECT id, document_id, dwell_seconds FROM visits WHERE id = ?",
            (visit_id,),
        ).fetchone()
        if row:
            return row
    return conn.execute(
        """
        SELECT id, document_id, dwell_seconds
        FROM visits
        WHERE normalized_url = ?
        ORDER BY captured_at DESC, created_at DESC
        LIMIT 1
        """,
        (normalized_url,),
    ).fetchone()


def _find_document_id(conn: sqlite3.Connection, normalized_url: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM documents WHERE normalized_url = ? OR canonical_url = ? LIMIT 1",
        (normalized_url, normalized_url),
    ).fetchone()
    return row["id"] if row else None


def record_visit_event(conn: sqlite3.Connection, data: dict[str, Any], *, policy_mode: str | None = None) -> dict[str, Any]:
    """Store a metadata-only browser lifecycle event and update visit dwell time.

    The event payload intentionally contains URL/time/scroll metadata only. Page body
    text continues to flow exclusively through /capture.
    """
    raw_url = str(data.get("url") or "").strip()
    if not raw_url:
        raise ValueError("url is required")
    safe_url = raw_url
    if redaction_enabled(policy_mode):
        safe_url, _, _ = redact_url(raw_url)
    normalized_url = normalize_url(safe_url)

    event_type = str(data.get("event_type") or data.get("eventType") or "").strip()
    if event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError(f"event_type must be one of {sorted(_ALLOWED_EVENT_TYPES)}")

    visit_id = str(data.get("visit_id") or data.get("visitId") or "").strip() or None
    event_started_at = validate_iso_datetime(data.get("event_started_at") or data.get("eventStartedAt"), "event_started_at")
    event_ended_at = validate_iso_datetime(data.get("event_ended_at") or data.get("eventEndedAt") or utc_now_iso(), "event_ended_at")
    active_seconds = _optional_int(data.get("active_seconds") if "active_seconds" in data else data.get("activeSeconds"), "active_seconds", maximum=86_400)
    max_scroll_percent = _optional_int(
        data.get("max_scroll_percent") if "max_scroll_percent" in data else data.get("maxScrollPercent"),
        "max_scroll_percent",
        maximum=100,
    )
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    event_id = str(data.get("id") or data.get("event_id") or data.get("eventId") or "").strip()
    if not event_id:
        event_id = _stable_id("vevt", f"{visit_id or ''}:{event_type}:{safe_url}:{event_started_at or ''}:{event_ended_at or ''}:{active_seconds or 0}")

    with conn:
        visit = _find_visit(conn, visit_id=visit_id, normalized_url=normalized_url)
        document_id = visit["document_id"] if visit else _find_document_id(conn, normalized_url)
        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO visit_events(
              id, visit_id, document_id, source_id, url, normalized_url, event_type,
              event_started_at, event_ended_at, active_seconds, max_scroll_percent, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                visit["id"] if visit else None,
                document_id,
                "chrome-extension",
                safe_url,
                normalized_url,
                event_type,
                event_started_at,
                event_ended_at,
                active_seconds,
                max_scroll_percent,
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
            ),
        ).rowcount
        dwell_updated = False
        if inserted and visit and active_seconds is not None and active_seconds > 0:
            overlapping_segment = conn.execute(
                """
                SELECT 1
                FROM visit_events
                WHERE id != ?
                  AND visit_id = ?
                  AND event_started_at = ?
                  AND active_seconds > 0
                LIMIT 1
                """,
                (event_id, visit["id"], event_started_at),
            ).fetchone()
            if not overlapping_segment:
                conn.execute(
                    "UPDATE visits SET dwell_seconds = COALESCE(dwell_seconds, 0) + ? WHERE id = ?",
                    (active_seconds, visit["id"]),
                )
                dwell_updated = True
        audit(
            conn,
            "visit_event.stored" if inserted else "visit_event.duplicate",
            {
                "event_id": event_id,
                "visit_id": visit["id"] if visit else visit_id,
                "document_id": document_id,
                "event_type": event_type,
                "active_seconds": active_seconds,
                "dwell_updated": dwell_updated,
            },
        )
    return {
        "stored": bool(inserted),
        "event_id": event_id,
        "visit_id": visit["id"] if visit else visit_id,
        "document_id": document_id,
        "event_type": event_type,
        "active_seconds": active_seconds,
        "max_scroll_percent": max_scroll_percent,
        "dwell_updated": dwell_updated,
    }
