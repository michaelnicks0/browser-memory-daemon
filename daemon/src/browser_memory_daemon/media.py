from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote_to_bytes, urlsplit
from urllib.request import Request, urlopen

from .config import RuntimeConfig
from .normalize import normalize_url
from .policy import POLICY_MODE_ALL, redact_text, redact_url


MEDIA_TYPES = {"image", "video"}
MEDIA_ROLES = {"content", "poster", "source"}
MEDIA_CAPTURE_STATUSES = {
    "referenced",
    "metadata-only",
    "queued",
    "fetching",
    "fetched",
    "uploading",
    "stored",
    "retrying",
    "failed",
    "skipped",
    "expired",
    "purged",
}
MEDIA_TASK_STATUSES = {"pending", "leased", "retrying", "succeeded", "failed", "skipped"}
MAX_HTTP_MEDIA_SOURCE_URL_CHARS = 65_536
MAX_DATA_MEDIA_SOURCE_URL_CHARS = 1_100_000
PERMANENT_SKIP_REASONS = {
    "unsupported-media-url-scheme",
    "invalid-data-url",
    "invalid-data-url-payload",
    "media-too-large",
    "non-media-content-type",
    "disallowed-mime",
    "snapshot-media-budget",
    "domain-media-budget",
    "media-cache-budget",
    "priority-below-threshold",
}


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


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
}


def _bounded_text(value: Any, *, max_chars: int = 2048) -> str:
    text = str(value or "").strip()
    return text[:max_chars]


def _bounded_source_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower().startswith("data:"):
        if len(text) > MAX_DATA_MEDIA_SOURCE_URL_CHARS:
            raise ValueError("media data URL is too large")
        return text
    return text[:MAX_HTTP_MEDIA_SOURCE_URL_CHARS]


def _safe_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _sanitize_mime(value: Any, *, media_type: str = "") -> str:
    mime = str(value or "").split(";", 1)[0].strip().lower()
    if not mime:
        return ""
    if media_type == "image" and not mime.startswith("image/"):
        return ""
    if media_type == "video" and not mime.startswith("video/"):
        return ""
    return mime[:128]


def _infer_mime_from_url(source_url: str, media_type: str) -> str:
    suffix = Path(urlsplit(source_url or "").path).suffix.lower()
    by_suffix = {
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
    }
    if suffix in by_suffix:
        return _sanitize_mime(by_suffix[suffix], media_type=media_type)
    return ""


def _file_extension(mime_type: str, source_url: str) -> str:
    if mime_type in EXT_BY_MIME:
        return EXT_BY_MIME[mime_type]
    suffix = Path(urlsplit(source_url).path).suffix.lower()
    if suffix and re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    if mime_type.startswith("image/"):
        return ".img"
    if mime_type.startswith("video/"):
        return ".video"
    return ".bin"


def _normalize_media_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.scheme in {"http", "https", "file"}:
        try:
            return normalize_url(url)
        except Exception:
            return url
    if parts.scheme == "data":
        return f"data:{hashlib.sha256(url.encode('utf-8')).hexdigest()}"
    if parts.scheme == "blob":
        return url.split("?", 1)[0].split("#", 1)[0]
    return url


def _storage_url(config: RuntimeConfig, url: str) -> tuple[str, str, int]:
    if config.policy_mode == POLICY_MODE_ALL:
        safe_url = url
        return safe_url, _normalize_media_url(safe_url), 0
    safe_url, redactions, _ = redact_url(url)
    return safe_url, _normalize_media_url(safe_url), redactions


def _storage_text(config: RuntimeConfig, value: str) -> tuple[str, int]:
    if config.policy_mode == POLICY_MODE_ALL:
        return value, 0
    safe, redactions, _ = redact_text(value)
    return safe, redactions


@dataclass(frozen=True)
class MediaRef:
    media_type: str
    source_url: str
    role: str = "content"
    alt_text: str = ""
    title: str = ""
    mime_type: str = ""
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaRef":
        media_type = str(data.get("media_type") or data.get("mediaType") or data.get("type") or "").lower().strip()
        if media_type not in MEDIA_TYPES:
            raise ValueError("media_type must be image or video")
        role = str(data.get("role") or "content").lower().strip()
        if role not in MEDIA_ROLES:
            role = "content"
        source_url = _bounded_source_url(data.get("source_url") or data.get("sourceUrl") or data.get("src") or data.get("current_src") or data.get("currentSrc"))
        if not source_url:
            raise ValueError("media source_url is required")
        return cls(
            media_type=media_type,
            role=role,
            source_url=source_url,
            alt_text=_bounded_text(data.get("alt_text") or data.get("altText") or data.get("alt")),
            title=_bounded_text(data.get("title")),
            mime_type=_sanitize_mime(data.get("mime_type") or data.get("mimeType") or data.get("type_attr") or data.get("typeAttr"), media_type=media_type),
            width=_safe_int(data.get("width") or data.get("naturalWidth") or data.get("videoWidth")),
            height=_safe_int(data.get("height") or data.get("naturalHeight") or data.get("videoHeight")),
            duration_seconds=_safe_float(data.get("duration_seconds") or data.get("durationSeconds") or data.get("duration")),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )

    def stable_key(self) -> str:
        return "|".join([self.media_type, self.role, self.source_url])


def parse_media_refs(raw: Any, *, max_refs: int) -> list[MediaRef]:
    if not isinstance(raw, list):
        return []
    refs: list[MediaRef] = []
    seen: set[str] = set()
    for item in raw[:max_refs]:
        if not isinstance(item, dict):
            continue
        try:
            ref = MediaRef.from_dict(item)
        except ValueError:
            continue
        key = ref.stable_key()
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def media_artifact_id(snapshot_id: str, ref: MediaRef) -> str:
    return stable_id("media", f"{snapshot_id}:{ref.stable_key()}")


def media_artifact_id_from_parts(snapshot_id: str, media_type: str, role: str, source_url: str) -> str:
    return stable_id("media", f"{snapshot_id}:{media_type}|{role}|{source_url}")


def media_fetch_task_id(artifact_id: str, worker_kind: str) -> str:
    return stable_id("mtask", f"{worker_kind}:{artifact_id}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_capture_status(value: Any, *, default: str = "metadata-only") -> str:
    status = str(value or "").lower().strip().replace("_", "-")
    return status if status in MEDIA_CAPTURE_STATUSES else default


def normalize_task_status(value: Any, *, default: str = "pending") -> str:
    status = str(value or "").lower().strip().replace("_", "-")
    return status if status in MEDIA_TASK_STATUSES else default


def _media_fetch_supported(source_url: str) -> bool:
    try:
        return urlsplit(source_url).scheme in {"http", "https", "data"}
    except Exception:
        return False


def media_capture_status_for_fetch_reason(reason: str, *, source_url: str = "") -> str:
    normalized = str(reason or "").strip()
    lower = normalized.lower()
    source_scheme = urlsplit(source_url or "").scheme.lower()
    if normalized in PERMANENT_SKIP_REASONS:
        return "skipped"
    if source_scheme == "data" and lower in {"failed to fetch", "invalid-data-url", "invalid-data-url-payload"}:
        return "skipped"
    if lower.startswith(("fetch-status-401", "fetch-status-403", "fetch-status-404", "fetch-status-410")):
        return "expired"
    if lower.startswith(("fetch-status-429", "fetch-timeout", "fetch-error-")):
        return "retrying"
    if lower in {"empty-media-response", "failed to fetch"}:
        return "retrying"
    return "failed"


def _metadata_priority(metadata: dict[str, Any] | None) -> int:
    if not isinstance(metadata, dict):
        return 50
    for key in ("priority", "media_priority", "score"):
        raw = metadata.get(key)
        if raw is None or raw == "":
            continue
        try:
            return max(0, min(100, int(float(raw))))
        except (TypeError, ValueError):
            continue
    try:
        width = int(float(metadata.get("width") or 0))
        height = int(float(metadata.get("height") or 0))
        if width and height:
            return max(1, min(100, (width * height) // 10_000))
    except (TypeError, ValueError):
        pass
    return 50


def _mime_allowed(config: RuntimeConfig, mime_type: str, media_type: str) -> bool:
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if not mime:
        return True
    if media_type == "image" and not mime.startswith("image/"):
        return False
    if media_type == "video" and not mime.startswith("video/"):
        return False
    allowlist = tuple(item.lower().strip() for item in config.media_mime_allowlist if item.strip())
    if not allowlist:
        return True
    return any(mime.startswith(item) if item.endswith("/") else mime == item for item in allowlist)


def _stored_media_bytes(conn: sqlite3.Connection, where_sql: str = "", params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(
        f"SELECT COALESCE(SUM(byte_size), 0) AS n FROM media_artifacts WHERE capture_status = 'stored' AND COALESCE(file_path, '') != '' {where_sql}",
        params,
    ).fetchone()
    return int(row["n"] if row else 0)


def media_storage_allowed(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    document_id: str,
    snapshot_id: str,
    media_type: str,
    mime_type: str,
    candidate_bytes: int,
    priority: int = 50,
) -> tuple[bool, str]:
    if candidate_bytes > config.max_media_artifact_bytes:
        return False, "media-too-large"
    if priority < config.media_min_priority_to_store:
        return False, "priority-below-threshold"
    if not _mime_allowed(config, mime_type, media_type):
        return False, "disallowed-mime"
    if config.max_media_bytes_per_snapshot > 0:
        current = _stored_media_bytes(conn, "AND snapshot_id = ?", (snapshot_id,))
        if current + candidate_bytes > config.max_media_bytes_per_snapshot:
            return False, "snapshot-media-budget"
    if config.max_media_bytes_per_domain > 0:
        doc = conn.execute("SELECT domain FROM documents WHERE id = ?", (document_id,)).fetchone()
        if doc and doc["domain"]:
            current = conn.execute(
                """
                SELECT COALESCE(SUM(m.byte_size), 0) AS n
                FROM media_artifacts m
                JOIN documents d ON d.id = m.document_id
                WHERE m.capture_status = 'stored'
                  AND COALESCE(m.file_path, '') != ''
                  AND d.domain = ?
                """,
                (doc["domain"],),
            ).fetchone()["n"]
            if int(current or 0) + candidate_bytes > config.max_media_bytes_per_domain:
                return False, "domain-media-budget"
    if config.max_media_cache_bytes > 0:
        current = _stored_media_bytes(conn)
        if current + candidate_bytes > config.max_media_cache_bytes:
            return False, "media-cache-budget"
    return True, ""


def ensure_media_fetch_task(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    worker_kind: str = "daemon-public",
    priority: int = 50,
    status: str = "pending",
    last_error: str = "",
    force_reset: bool = False,
) -> str:
    task_id = media_fetch_task_id(artifact_id, worker_kind)
    normalized_status = normalize_task_status(status)
    now = _utc_now()
    force = bool(force_reset)
    conn.execute(
        """
        INSERT INTO media_fetch_tasks(
          id, artifact_id, worker_kind, status, priority, attempts, max_attempts,
          next_attempt_at, lease_owner, lease_until, last_error, updated_at
        ) VALUES (?, ?, ?, ?, ?, 0, 5, NULL, NULL, NULL, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          priority=MAX(media_fetch_tasks.priority, excluded.priority),
          status=CASE
            WHEN ? THEN excluded.status
            WHEN media_fetch_tasks.status IN ('succeeded', 'skipped') THEN media_fetch_tasks.status
            ELSE excluded.status
          END,
          attempts=CASE WHEN ? THEN 0 ELSE media_fetch_tasks.attempts END,
          next_attempt_at=CASE WHEN ? THEN NULL ELSE media_fetch_tasks.next_attempt_at END,
          lease_owner=CASE WHEN ? THEN NULL ELSE media_fetch_tasks.lease_owner END,
          lease_until=CASE WHEN ? THEN NULL ELSE media_fetch_tasks.lease_until END,
          last_error=CASE WHEN ? THEN NULL ELSE COALESCE(NULLIF(excluded.last_error, ''), media_fetch_tasks.last_error) END,
          updated_at=excluded.updated_at
        """,
        (task_id, artifact_id, worker_kind, normalized_status, int(priority), None if force else (last_error or None), now, force, force, force, force, force, force),
    )
    return task_id


def mark_media_fetch_task(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    worker_kind: str = "daemon-public",
    status: str,
    error: str = "",
) -> None:
    conn.execute(
        """
        UPDATE media_fetch_tasks
        SET status = ?, last_error = NULLIF(?, ''), lease_owner = NULL, lease_until = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (normalize_task_status(status), error[:512], _utc_now(), media_fetch_task_id(artifact_id, worker_kind)),
    )


def media_queue_status(conn: sqlite3.Connection, config: RuntimeConfig, *, limit: int = 50) -> dict[str, Any]:
    artifact_rows = conn.execute("SELECT capture_status, COUNT(*) AS n FROM media_artifacts GROUP BY capture_status").fetchall()
    task_rows = conn.execute("SELECT status, COUNT(*) AS n FROM media_fetch_tasks GROUP BY status").fetchall()
    stored_bytes = _stored_media_bytes(conn)
    recent = conn.execute(
        """
        SELECT m.id, m.document_id, m.snapshot_id, d.domain, m.media_type, m.capture_status,
               m.status_reason, m.byte_size, m.created_at
        FROM media_artifacts m
        LEFT JOIN documents d ON d.id = m.document_id
        WHERE m.capture_status IN ('referenced','queued','retrying','failed','skipped','expired','purged')
        ORDER BY m.created_at DESC, m.id
        LIMIT ?
        """,
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    return {
        "artifacts": {row["capture_status"]: row["n"] for row in artifact_rows},
        "tasks": {row["status"]: row["n"] for row in task_rows},
        "bytes": {"stored": stored_bytes},
        "gates": {
            "max_media_artifact_bytes": config.max_media_artifact_bytes,
            "max_media_bytes_per_snapshot": config.max_media_bytes_per_snapshot,
            "max_media_bytes_per_domain": config.max_media_bytes_per_domain,
            "max_media_cache_bytes": config.max_media_cache_bytes,
            "media_min_priority_to_store": config.media_min_priority_to_store,
            "media_mime_allowlist": list(config.media_mime_allowlist),
            "cache_pressure": stored_bytes / config.max_media_cache_bytes if config.max_media_cache_bytes else 0,
        },
        "recent_nonstored": [dict(row) for row in recent],
    }


def _safe_response_mime(value: str, *, media_type: str) -> str:
    mime = _sanitize_mime(value, media_type=media_type)
    if mime:
        return mime
    return ""


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


def _fetch_media_bytes(source_url: str, page_url: str, *, media_type: str, max_bytes: int, timeout_seconds: float) -> tuple[bytes, str, str]:
    parts = urlsplit(source_url)
    if parts.scheme == "data":
        return _data_url_to_media(source_url, media_type=media_type, max_bytes=max_bytes)
    if parts.scheme not in {"http", "https"}:
        return b"", "", "unsupported-media-url-scheme"
    request = Request(
        source_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149 Safari/537.36 BrowserMemoryDaemon/0.1",
            "Referer": page_url or f"{parts.scheme}://{parts.netloc}/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,video/*,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_mime = _safe_response_mime(response.headers.get("content-type", ""), media_type=media_type)
            if response.headers.get("content-type") and not response_mime:
                return b"", "", "non-media-content-type"
            try:
                content_length = int(response.headers.get("content-length") or "0")
            except ValueError:
                content_length = 0
            if content_length > max_bytes:
                return b"", response_mime, "media-too-large"
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    return b"", response_mime, "media-too-large"
                chunks.append(chunk)
            return b"".join(chunks), response_mime, ""
    except HTTPError as exc:
        return b"", "", f"fetch-status-{exc.code}"
    except TimeoutError:
        return b"", "", "fetch-timeout"
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        return b"", "", f"fetch-error-{str(reason)[:160]}"
    except Exception as exc:
        return b"", "", f"fetch-error-{str(exc)[:160]}"


def _payload_from_media_row(row: sqlite3.Row | dict[str, Any], *, capture_status: str, status_reason: str = "", content: bytes = b"", mime_type: str = "") -> dict[str, Any]:
    value = dict(row)
    payload: dict[str, Any] = {
        "artifact_id": value["id"],
        "document_id": value["document_id"],
        "snapshot_id": value["snapshot_id"],
        "visit_id": value.get("visit_id") or None,
        "page_url": value.get("page_url") or "",
        "media_type": value.get("media_type") or "",
        "role": value.get("role") or "content",
        "source_url": value.get("source_url") or "",
        "alt_text": value.get("alt_text") or "",
        "title": value.get("title") or "",
        "mime_type": mime_type or value.get("mime_type") or "",
        "width": value.get("width"),
        "height": value.get("height"),
        "duration_seconds": value.get("duration_seconds"),
        "capture_status": capture_status,
        "status_reason": status_reason,
    }
    if content:
        payload["content_base64"] = base64.b64encode(content).decode("ascii")
    return payload


def fetch_and_store_media_artifact(conn: sqlite3.Connection, config: RuntimeConfig, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    file_path = value.get("file_path") or ""
    if value.get("capture_status") == "stored" and file_path and Path(file_path).exists():
        return {
            "stored": True,
            "artifact_id": value["id"],
            "capture_status": "stored",
            "byte_size": int(value.get("byte_size") or 0),
            "skipped": True,
            "reason": "already-stored",
        }
    content, response_mime, reason = _fetch_media_bytes(
        value.get("source_url") or "",
        value.get("page_url") or "",
        media_type=value.get("media_type") or "",
        max_bytes=config.max_media_artifact_bytes,
        timeout_seconds=config.media_fetch_timeout_seconds,
    )
    if reason:
        return store_media_artifact(
            conn,
            config,
            _payload_from_media_row(
                value,
                capture_status=media_capture_status_for_fetch_reason(reason, source_url=value.get("source_url") or ""),
                status_reason=reason,
                mime_type=response_mime,
            ),
        )
    if not content:
        empty_reason = "empty-media-response"
        return store_media_artifact(
            conn,
            config,
            _payload_from_media_row(
                value,
                capture_status=media_capture_status_for_fetch_reason(empty_reason, source_url=value.get("source_url") or ""),
                status_reason=empty_reason,
                mime_type=response_mime,
            ),
        )
    return store_media_artifact(conn, config, _payload_from_media_row(value, capture_status="stored", content=content, mime_type=response_mime))


def fetch_pending_media_artifacts(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    snapshot_id: str | None = None,
    document_id: str | None = None,
    domain: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    selected_limit = max(1, min(int(limit or config.max_media_fetches_per_call), config.max_media_fetches_per_call))
    where = ["m.capture_status IN ('referenced', 'metadata-only', 'queued', 'retrying', 'failed', 'purged')", "COALESCE(m.file_path, '') = ''"]
    params: list[Any] = []
    if snapshot_id:
        where.append("m.snapshot_id = ?")
        params.append(snapshot_id)
    if document_id:
        where.append("m.document_id = ?")
        params.append(document_id)
    if domain:
        normalized_domain = domain.lower().strip()
        where.append("(lower(d.domain) = ? OR lower(m.page_url) LIKE ? OR lower(m.source_url) LIKE ?)")
        params.extend([normalized_domain, f"%://{normalized_domain}/%", f"%{normalized_domain}%"])
    params.append(selected_limit)
    rows = conn.execute(
        f"""
        SELECT m.*
        FROM media_artifacts m
        LEFT JOIN documents d ON d.id = m.document_id
        WHERE {' AND '.join(where)}
        ORDER BY m.created_at DESC, m.id
        LIMIT ?
        """,
        params,
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            result = fetch_and_store_media_artifact(conn, config, row)
        except Exception as exc:
            result = {"stored": False, "artifact_id": row["id"], "capture_status": "failed", "error": str(exc)}
        results.append(result)
    return {
        "attempted": len(results),
        "stored": sum(1 for item in results if item.get("stored")),
        "failed": sum(1 for item in results if item.get("capture_status") == "failed"),
        "skipped": sum(1 for item in results if item.get("capture_status") == "skipped"),
        "remaining": _count_pending_media_artifacts(conn, snapshot_id=snapshot_id, document_id=document_id, domain=domain),
        "results": results,
    }


def _count_pending_media_artifacts(conn: sqlite3.Connection, *, snapshot_id: str | None = None, document_id: str | None = None, domain: str | None = None) -> int:
    where = ["m.capture_status IN ('referenced', 'metadata-only', 'queued', 'retrying', 'failed', 'purged')", "COALESCE(m.file_path, '') = ''"]
    params: list[Any] = []
    if snapshot_id:
        where.append("m.snapshot_id = ?")
        params.append(snapshot_id)
    if document_id:
        where.append("m.document_id = ?")
        params.append(document_id)
    if domain:
        normalized_domain = domain.lower().strip()
        where.append("(lower(d.domain) = ? OR lower(m.page_url) LIKE ? OR lower(m.source_url) LIKE ?)")
        params.extend([normalized_domain, f"%://{normalized_domain}/%", f"%{normalized_domain}%"])
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM media_artifacts m
        LEFT JOIN documents d ON d.id = m.document_id
        WHERE {' AND '.join(where)}
        """,
        params,
    ).fetchone()
    return int(row[0]) if row else 0


def record_media_references(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    document_id: str,
    snapshot_id: str,
    visit_id: str | None,
    page_url: str,
    refs: list[MediaRef],
) -> int:
    inserted = 0
    for ref in refs[: config.max_media_artifacts_per_capture]:
        artifact_id = media_artifact_id(snapshot_id, ref)
        source_url, normalized_source_url, url_redactions = _storage_url(config, ref.source_url)
        alt_text, alt_redactions = _storage_text(config, ref.alt_text)
        title, title_redactions = _storage_text(config, ref.title)
        metadata = dict(ref.metadata or {})
        priority = _metadata_priority({**metadata, "width": ref.width, "height": ref.height})
        metadata.setdefault("priority", priority)
        metadata["metadata_redaction_count"] = url_redactions + alt_redactions + title_redactions
        row = conn.execute("SELECT id FROM media_artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE media_artifacts
                SET visit_id = COALESCE(visit_id, ?), alt_text = ?, title = ?, width = COALESCE(width, ?),
                    height = COALESCE(height, ?), duration_seconds = COALESCE(duration_seconds, ?),
                    metadata_json = ?
                WHERE id = ?
                """,
                (visit_id, alt_text, title, ref.width, ref.height, ref.duration_seconds, json.dumps(metadata, sort_keys=True), artifact_id),
            )
            if _media_fetch_supported(source_url):
                ensure_media_fetch_task(conn, artifact_id, worker_kind="daemon-public", priority=priority)
            continue
        conn.execute(
            """
            INSERT INTO media_artifacts(
              id, document_id, snapshot_id, visit_id, media_type, role, source_url,
              normalized_source_url, page_url, alt_text, title, mime_type, width, height,
              duration_seconds, capture_status, status_reason, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'referenced', NULL, ?)
            """,
            (
                artifact_id,
                document_id,
                snapshot_id,
                visit_id,
                ref.media_type,
                ref.role,
                source_url,
                normalized_source_url,
                page_url,
                alt_text,
                title,
                ref.mime_type,
                ref.width,
                ref.height,
                ref.duration_seconds,
                json.dumps(metadata, sort_keys=True),
            ),
        )
        if _media_fetch_supported(source_url):
            ensure_media_fetch_task(conn, artifact_id, worker_kind="daemon-public", priority=priority)
        inserted += 1
    return inserted


def _decode_base64(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise ValueError("content_base64 is not valid base64") from exc


def _row_to_ref(data: dict[str, Any]) -> MediaRef:
    return MediaRef.from_dict(data)


def _write_media_blob(config: RuntimeConfig, artifact_id: str, mime_type: str, source_url: str, content: bytes) -> str:
    extension = _file_extension(mime_type, source_url)
    target = config.media_root / f"{artifact_id}{extension}"
    tmp_root = config.media_root / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_root / f"{artifact_id}{extension}.tmp"
    tmp.write_bytes(content)
    tmp.replace(target)
    return str(target)


def _artifact_priority(data: dict[str, Any], ref: MediaRef) -> int:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else ref.metadata
    explicit = data.get("priority")
    if explicit is not None and explicit != "":
        try:
            return max(0, min(100, int(float(explicit))))
        except (TypeError, ValueError):
            pass
    return _metadata_priority({**(metadata or {}), "width": ref.width, "height": ref.height})


def store_media_artifact(conn: sqlite3.Connection, config: RuntimeConfig, data: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = _bounded_text(data.get("snapshot_id") or data.get("snapshotId"), max_chars=128)
    document_id = _bounded_text(data.get("document_id") or data.get("documentId"), max_chars=128)
    visit_id = _bounded_text(data.get("visit_id") or data.get("visitId"), max_chars=128) or None
    page_url = _bounded_text(data.get("page_url") or data.get("pageUrl") or data.get("url"), max_chars=8192)
    if not snapshot_id or not document_id:
        raise ValueError("snapshot_id and document_id are required")
    snap = conn.execute("SELECT id, document_id FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    if not snap:
        raise KeyError("snapshot not found")
    if snap["document_id"] != document_id:
        raise ValueError("document_id does not match snapshot")

    ref = _row_to_ref(data)
    artifact_id = _bounded_text(data.get("artifact_id") or data.get("artifactId"), max_chars=128) or media_artifact_id(snapshot_id, ref)
    source_url, normalized_source_url, url_redactions = _storage_url(config, ref.source_url)
    alt_text, alt_redactions = _storage_text(config, ref.alt_text)
    title, title_redactions = _storage_text(config, ref.title)
    metadata = dict(ref.metadata or {})
    priority = _artifact_priority(data, ref)
    metadata.setdefault("priority", priority)
    metadata["metadata_redaction_count"] = url_redactions + alt_redactions + title_redactions

    content_base64 = data.get("content_base64") or data.get("contentBase64") or ""
    status = normalize_capture_status(data.get("capture_status") or data.get("captureStatus"), default="metadata-only")
    reason = _bounded_text(data.get("status_reason") or data.get("statusReason"), max_chars=512)
    content = b""
    mime_type = _sanitize_mime(data.get("mime_type") or data.get("mimeType") or ref.mime_type, media_type=ref.media_type)
    if content_base64:
        content = _decode_base64(str(content_base64))
        allowed, gate_reason = media_storage_allowed(
            conn,
            config,
            document_id=document_id,
            snapshot_id=snapshot_id,
            media_type=ref.media_type,
            mime_type=mime_type,
            candidate_bytes=len(content),
            priority=priority,
        )
        if not allowed:
            content = b""
            status = "skipped"
            reason = gate_reason
        else:
            status = "stored"
    elif status == "stored":
        status = "metadata-only"

    content_sha256 = hashlib.sha256(content).hexdigest() if content else ""
    file_path = ""
    byte_size = len(content) if content else None
    if content:
        file_path = _write_media_blob(config, artifact_id, mime_type, ref.source_url, content)

    with conn:
        conn.execute(
            """
            INSERT INTO media_artifacts(
              id, document_id, snapshot_id, visit_id, media_type, role, source_url,
              normalized_source_url, page_url, alt_text, title, mime_type, width, height,
              duration_seconds, byte_size, content_sha256, file_path, capture_status,
              status_reason, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              visit_id=COALESCE(excluded.visit_id, media_artifacts.visit_id),
              alt_text=excluded.alt_text,
              title=excluded.title,
              mime_type=COALESCE(NULLIF(excluded.mime_type, ''), media_artifacts.mime_type),
              width=COALESCE(excluded.width, media_artifacts.width),
              height=COALESCE(excluded.height, media_artifacts.height),
              duration_seconds=COALESCE(excluded.duration_seconds, media_artifacts.duration_seconds),
              byte_size=COALESCE(excluded.byte_size, media_artifacts.byte_size),
              content_sha256=COALESCE(NULLIF(excluded.content_sha256, ''), media_artifacts.content_sha256),
              file_path=COALESCE(NULLIF(excluded.file_path, ''), media_artifacts.file_path),
              capture_status=CASE
                WHEN media_artifacts.capture_status = 'stored' AND excluded.capture_status != 'stored' THEN media_artifacts.capture_status
                ELSE excluded.capture_status
              END,
              status_reason=CASE
                WHEN media_artifacts.capture_status = 'stored' AND excluded.capture_status != 'stored' THEN media_artifacts.status_reason
                ELSE excluded.status_reason
              END,
              metadata_json=excluded.metadata_json
            """,
            (
                artifact_id,
                document_id,
                snapshot_id,
                visit_id,
                ref.media_type,
                ref.role,
                source_url,
                normalized_source_url,
                page_url,
                alt_text,
                title,
                mime_type,
                ref.width,
                ref.height,
                ref.duration_seconds,
                byte_size,
                content_sha256,
                file_path,
                status,
                reason or None,
                json.dumps(metadata, sort_keys=True),
            ),
        )
        if status == "stored":
            mark_media_fetch_task(conn, artifact_id, worker_kind="daemon-public", status="succeeded")
            mark_media_fetch_task(conn, artifact_id, worker_kind="browser", status="succeeded")
        elif status in {"skipped", "expired"}:
            mark_media_fetch_task(conn, artifact_id, worker_kind="daemon-public", status="skipped", error=reason)
    return {
        "stored": status == "stored",
        "artifact_id": artifact_id,
        "snapshot_id": snapshot_id,
        "document_id": document_id,
        "media_type": ref.media_type,
        "role": ref.role,
        "capture_status": status,
        "byte_size": byte_size or 0,
    }


def _read_limited_stream(stream: Any, max_bytes: int, expected_bytes: int | None = None) -> bytes:
    chunks: list[bytes] = []
    total = 0
    remaining = expected_bytes
    while remaining is None or remaining > 0:
        read_size = 64 * 1024 if remaining is None else min(64 * 1024, remaining)
        chunk = stream.read(read_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("media artifact too large")
        chunks.append(chunk)
        if remaining is not None:
            remaining -= len(chunk)
    if expected_bytes is not None and remaining and remaining > 0:
        raise ValueError("incomplete media upload")
    return b"".join(chunks)


def store_media_blob_stream(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    artifact_id: str,
    stream: Any,
    *,
    headers: dict[str, str] | None = None,
    content_length: int | None = None,
) -> dict[str, Any]:
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    row = conn.execute("SELECT * FROM media_artifacts WHERE id = ?", (artifact_id,)).fetchone()
    if not row:
        raise KeyError("media artifact not found")
    artifact = dict(row)
    if headers.get("x-bmd-document-id") and headers["x-bmd-document-id"] != artifact["document_id"]:
        raise ValueError("document_id does not match artifact")
    if headers.get("x-bmd-snapshot-id") and headers["x-bmd-snapshot-id"] != artifact["snapshot_id"]:
        raise ValueError("snapshot_id does not match artifact")
    if content_length is not None and content_length > config.max_media_artifact_bytes:
        return store_media_artifact(conn, config, _payload_from_media_row(artifact, capture_status="skipped", status_reason="media-too-large"))
    content = _read_limited_stream(stream, config.max_media_artifact_bytes, expected_bytes=content_length)
    raw_content_type = headers.get("content-type", "")
    if raw_content_type.split(";", 1)[0].strip().lower() == "application/octet-stream":
        raw_content_type = ""
    media_type = artifact.get("media_type") or ""
    mime_type = _safe_response_mime(raw_content_type or artifact.get("mime_type") or _infer_mime_from_url(artifact.get("source_url") or "", media_type), media_type=media_type)
    if raw_content_type and not mime_type:
        return store_media_artifact(conn, config, _payload_from_media_row(artifact, capture_status="skipped", status_reason="non-media-content-type"))
    priority = _metadata_priority(json.loads(artifact.get("metadata_json") or "{}"))
    allowed, reason = media_storage_allowed(
        conn,
        config,
        document_id=artifact["document_id"],
        snapshot_id=artifact["snapshot_id"],
        media_type=artifact["media_type"],
        mime_type=mime_type,
        candidate_bytes=len(content),
        priority=priority,
    )
    if not allowed:
        return store_media_artifact(conn, config, _payload_from_media_row(artifact, capture_status="skipped", status_reason=reason, mime_type=mime_type))
    return store_media_artifact(conn, config, _payload_from_media_row(artifact, capture_status="stored", content=content, mime_type=mime_type))


def _purge_scope_sql(scope: dict[str, Any]) -> tuple[list[str], list[Any], str]:
    rehydrate_only = bool(scope.get("rehydrate_only") or scope.get("rehydrateOnly"))
    where = ["m.capture_status = 'purged'", "COALESCE(m.file_path, '') = ''"] if rehydrate_only else ["COALESCE(m.file_path, '') != ''"]
    params: list[Any] = []
    labels: list[str] = []
    domain = str(scope.get("domain") or "").lower().strip().lstrip(".")
    if domain:
        where.append("(lower(d.domain) = ? OR lower(d.domain) LIKE ?)")
        params.extend([domain, f"%.{domain}"])
        labels.append(f"domain:{domain}")
    document_id = str(scope.get("document_id") or scope.get("documentId") or "").strip()
    if document_id:
        where.append("m.document_id = ?")
        params.append(document_id)
        labels.append(f"document:{document_id}")
    snapshot_id = str(scope.get("snapshot_id") or scope.get("snapshotId") or "").strip()
    if snapshot_id:
        where.append("m.snapshot_id = ?")
        params.append(snapshot_id)
        labels.append(f"snapshot:{snapshot_id}")
    older_than = str(scope.get("older_than") or scope.get("olderThan") or "").strip()
    if older_than:
        where.append("m.created_at < ?")
        params.append(older_than)
        labels.append(f"older-than:{older_than}")
    if not labels:
        labels.append("all")
    return where, params, ";".join(labels)


def purge_media_cache(conn: sqlite3.Connection, config: RuntimeConfig, scope: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool(scope.get("dry_run") if "dry_run" in scope else scope.get("dryRun", True))
    rehydrate = bool(scope.get("rehydrate") or False)
    rehydrate_only = bool(scope.get("rehydrate_only") or scope.get("rehydrateOnly"))
    max_bytes_to_purge = _safe_int(scope.get("max_bytes_to_purge") or scope.get("maxBytesToPurge"))
    where, params, label = _purge_scope_sql(scope)
    rows = conn.execute(
        f"""
        SELECT m.id, m.file_path, m.byte_size, m.source_url, m.capture_status
        FROM media_artifacts m
        LEFT JOIN documents d ON d.id = m.document_id
        WHERE {' AND '.join(where)}
        ORDER BY m.created_at ASC, m.id
        """,
        params,
    ).fetchall()
    selected = []
    selected_bytes = 0
    media_root = config.media_root.resolve()
    for row in rows:
        file_path = Path(row["file_path"] or "")
        if rehydrate_only:
            selected.append((row, file_path, 0))
            continue
        try:
            resolved = file_path.resolve()
            if not resolved.is_relative_to(media_root):
                continue
        except Exception:
            continue
        size = int(row["byte_size"] or (resolved.stat().st_size if resolved.exists() else 0))
        if max_bytes_to_purge is not None and selected_bytes + size > max_bytes_to_purge:
            break
        selected.append((row, resolved, size))
        selected_bytes += size
    purged = 0
    missing = 0
    if not dry_run:
        with conn:
            for row, resolved, _size in selected:
                if rehydrate_only:
                    if _media_fetch_supported(row["source_url"] or ""):
                        ensure_media_fetch_task(conn, row["id"], worker_kind="daemon-public", status="pending", force_reset=True)
                    continue
                if resolved.exists():
                    resolved.unlink()
                    purged += 1
                else:
                    missing += 1
                conn.execute(
                    """
                    UPDATE media_artifacts
                    SET file_path = '', capture_status = 'purged', status_reason = ?
                    WHERE id = ?
                    """,
                    (f"cache-purged:{label}", row["id"]),
                )
                if rehydrate and _media_fetch_supported(row["source_url"] or ""):
                    ensure_media_fetch_task(conn, row["id"], worker_kind="daemon-public", status="pending", force_reset=True)
    return {
        "dry_run": dry_run,
        "rehydrate": rehydrate,
        "rehydrate_only": rehydrate_only,
        "scope": scope,
        "selected": len(selected),
        "purged": purged,
        "missing_files": missing,
        "bytes": selected_bytes,
        "sample_artifact_ids": [row["id"] for row, _path, _size in selected[:20]],
    }


def media_artifact(conn: sqlite3.Connection, artifact_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM media_artifacts WHERE id = ?", (artifact_id,)).fetchone()
    if not row:
        raise KeyError("media artifact not found")
    value = dict(row)
    path = value.get("file_path")
    value["has_file"] = bool(path and Path(path).exists())
    return value


def media_artifacts_for_snapshot(conn: sqlite3.Connection, snapshot_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, media_type, role, source_url, normalized_source_url, alt_text, title, mime_type,
               width, height, duration_seconds, byte_size, capture_status, status_reason, file_path,
               created_at
        FROM media_artifacts
        WHERE snapshot_id = ?
        ORDER BY media_type, role, created_at, id
        """,
        (snapshot_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        path = item.pop("file_path", None)
        item["has_file"] = bool(path and Path(path).exists())
        if item["has_file"]:
            item["content_url"] = f"/media-artifacts/{item['id']}"
        result.append(item)
    return result


def media_artifacts_for_document(conn: sqlite3.Connection, document_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, snapshot_id, media_type, role, source_url, normalized_source_url, alt_text, title,
               mime_type, width, height, duration_seconds, byte_size, capture_status, status_reason,
               file_path, created_at
        FROM media_artifacts
        WHERE document_id = ?
        ORDER BY created_at DESC, id
        LIMIT ?
        """,
        (document_id, limit),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        path = item.pop("file_path", None)
        item["has_file"] = bool(path and Path(path).exists())
        if item["has_file"]:
            item["content_url"] = f"/media-artifacts/{item['id']}"
        result.append(item)
    return result
