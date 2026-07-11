from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .config import RuntimeConfig
from .media_fetch import _PUBLIC_FETCH_OPENER as _PUBLIC_FETCH_OPENER
from .media_fetch import _PUBLIC_FETCH_RESOLVER as _PUBLIC_FETCH_RESOLVER
from .media_fetch import _file_extension as _file_extension
from .media_fetch import _guarded_public_fetch as _guarded_public_fetch
from .media_fetch import _infer_mime_from_url as _infer_mime_from_url
from .media_fetch import _safe_response_mime as _safe_response_mime
from .media_fetch import _sanitize_mime as _sanitize_mime
from .media_hls import _fetch_hls_asset as _fetch_hls_asset
from .media_hls import _fetch_hls_media_bytes as _fetch_hls_media_bytes
from .media_hls import _hls_playlist_to_media as _hls_playlist_to_media
from .media_hls import _HlsFetchBudget as _HlsFetchBudget
from .media_models import (
    MEDIA_CAPTURE_STATUSES as MEDIA_CAPTURE_STATUSES,
)
from .media_models import (
    MEDIA_ROLES,
    MEDIA_TYPES,
    media_capture_status_for_fetch_reason,
    normalize_capture_status,
)
from .media_models import (
    MEDIA_TASK_STATUSES as MEDIA_TASK_STATUSES,
)
from .media_models import (
    normalize_task_status as normalize_task_status,
)
from .media_resources import media_resource_budget
from .media_storage import media_blob_store_and_locator
from .media_store import MediaArtifactWrite
from .media_store import media_artifact as media_artifact
from .media_store import media_artifacts_for_document as media_artifacts_for_document
from .media_store import media_artifacts_for_snapshot as media_artifacts_for_snapshot
from .media_store import media_fetch_supported as _media_fetch_supported
from .media_store import media_storage_allowed as media_storage_allowed
from .media_store import persist_media_artifact as _persist_media_artifact
from .media_store import purge_media_cache as purge_media_cache
from .media_store import stored_media_bytes as _stored_media_bytes
from .media_tasks import (
    _pending_media_artifact_filters,
    claim_media_fetch_tasks,
    ensure_media_fetch_task,
)
from .media_tasks import (
    media_fetch_task_id as media_fetch_task_id,
)
from .media_tasks import (
    process_media_fetch_task_rows as _process_media_fetch_task_rows,
)
from .media_transport import _fetch_media_bytes as _fetch_media_bytes
from .media_transport import _fetch_media_stream as _fetch_media_stream
from .normalize import normalize_url
from .policy import POLICY_MODE_ALL, redact_text, redact_url
from .storage_paths import validate_media_artifact_id

MAX_HTTP_MEDIA_SOURCE_URL_CHARS = 65_536
MAX_DATA_MEDIA_SOURCE_URL_CHARS = 1_100_000
def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"







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
    def from_dict(cls, data: dict[str, Any]) -> MediaRef:
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


def _seed_media_fetch_tasks_for_pending_artifacts(
    conn: sqlite3.Connection,
    *,
    worker_kind: str = "daemon-public",
    snapshot_id: str | None = None,
    document_id: str | None = None,
    domain: str | None = None,
    limit: int = 25,
) -> int:
    where, params = _pending_media_artifact_filters(snapshot_id=snapshot_id, document_id=document_id, domain=domain)
    rows = conn.execute(
        f"""
        SELECT m.id, m.source_url, m.metadata_json
        FROM media_artifacts m
        LEFT JOIN documents d ON d.id = m.document_id
        WHERE {' AND '.join(where)}
        ORDER BY m.created_at DESC, m.id
        LIMIT ?
        """,
        [*params, max(1, int(limit))],
    ).fetchall()
    seeded = 0
    for row in rows:
        if not _media_fetch_supported(row["source_url"] or ""):
            continue
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        ensure_media_fetch_task(conn, row["id"], worker_kind=worker_kind, priority=_metadata_priority(metadata))
        seeded += 1
    return seeded


def process_media_fetch_task_rows(conn: sqlite3.Connection, config: RuntimeConfig, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return _process_media_fetch_task_rows(
        conn,
        config,
        rows,
        fetch_artifact=fetch_and_store_media_artifact,
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
    resources = media_resource_budget(config).snapshot()
    return {
        "artifacts": {row["capture_status"]: row["n"] for row in artifact_rows},
        "tasks": {row["status"]: row["n"] for row in task_rows},
        "bytes": {"stored": stored_bytes},
        "gates": {
            "max_media_artifact_bytes": config.max_media_artifact_bytes,
            "max_media_inflight_bytes": config.max_media_inflight_bytes,
            "max_media_concurrent_requests": config.max_media_concurrent_requests,
            "max_media_bytes_per_snapshot": config.max_media_bytes_per_snapshot,
            "max_media_bytes_per_domain": config.max_media_bytes_per_domain,
            "max_media_cache_bytes": config.max_media_cache_bytes,
            "media_min_priority_to_store": config.media_min_priority_to_store,
            "media_mime_allowlist": list(config.media_mime_allowlist),
            "cache_pressure": stored_bytes / config.max_media_cache_bytes if config.max_media_cache_bytes else 0,
        },
        "resources": resources,
        "recent_nonstored": [dict(row) for row in recent],
    }




























def _payload_from_media_row(
    row: sqlite3.Row | dict[str, Any],
    *,
    capture_status: str,
    status_reason: str = "",
    mime_type: str = "",
) -> dict[str, Any]:
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
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        raw_metadata = value.get("metadata_json")
        if raw_metadata:
            try:
                parsed = json.loads(raw_metadata)
                metadata = parsed if isinstance(parsed, dict) else {}
            except Exception:
                metadata = {}
        else:
            metadata = {}
    if metadata:
        payload["metadata"] = metadata
    return payload


def fetch_and_store_media_artifact(conn: sqlite3.Connection, config: RuntimeConfig, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    store, locator, _tier_status = media_blob_store_and_locator(config, value)
    if value.get("capture_status") == "stored" and store is not None and locator and store.exists(locator):
        return {
            "stored": True,
            "artifact_id": value["id"],
            "capture_status": "stored",
            "byte_size": int(value.get("byte_size") or 0),
            "skipped": True,
            "reason": "already-stored",
        }
    with _fetch_media_stream(
        value.get("source_url") or "",
        value.get("page_url") or "",
        media_type=value.get("media_type") or "",
        max_bytes=config.max_media_artifact_bytes,
        timeout_seconds=config.media_fetch_timeout_seconds,
        config=config,
    ) as fetched:
        if fetched.reason:
            return store_media_artifact(
                conn,
                config,
                _payload_from_media_row(
                    value,
                    capture_status=media_capture_status_for_fetch_reason(
                        fetched.reason,
                        source_url=value.get("source_url") or "",
                        media_type=value.get("media_type") or "",
                    ),
                    status_reason=fetched.reason,
                    mime_type=fetched.mime_type,
                ),
            )
        if fetched.stream is None or fetched.byte_size <= 0:
            empty_reason = "empty-media-response"
            return store_media_artifact(
                conn,
                config,
                _payload_from_media_row(
                    value,
                    capture_status=media_capture_status_for_fetch_reason(
                        empty_reason,
                        source_url=value.get("source_url") or "",
                        media_type=value.get("media_type") or "",
                    ),
                    status_reason=empty_reason,
                    mime_type=fetched.mime_type,
                ),
            )
        payload = _payload_from_media_row(value, capture_status="stored", mime_type=fetched.mime_type)
        return _persist_media_artifact(
            conn,
            config,
            _build_media_artifact_write(
                config,
                payload,
                content_stream=fetched.stream,
                content_size=fetched.byte_size,
            ),
        )


def fetch_pending_media_artifacts(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    snapshot_id: str | None = None,
    document_id: str | None = None,
    domain: str | None = None,
    limit: int | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    selected_limit = max(1, min(int(limit or config.max_media_fetches_per_call), config.max_media_fetches_per_call))
    worker_id = worker_id or f"media-fetch-pending-{uuid.uuid4()}"
    with conn:
        seeded = _seed_media_fetch_tasks_for_pending_artifacts(
            conn,
            snapshot_id=snapshot_id,
            document_id=document_id,
            domain=domain,
            limit=selected_limit,
        )
    results: list[dict[str, Any]] = []
    claimed = 0
    for _ in range(selected_limit):
        with conn:
            rows = claim_media_fetch_tasks(
                conn,
                worker_id=worker_id,
                limit=1,
                snapshot_id=snapshot_id,
                document_id=document_id,
                domain=domain,
            )
        if not rows:
            break
        claimed += 1
        results.extend(process_media_fetch_task_rows(conn, config, rows))
    return {
        "attempted": len(results),
        "claimed": claimed,
        "seeded_tasks": seeded,
        "stored": sum(1 for item in results if item.get("stored")),
        "failed": sum(1 for item in results if item.get("capture_status") == "failed"),
        "skipped": sum(1 for item in results if item.get("capture_status") == "skipped"),
        "remaining": _count_pending_media_artifacts(conn, snapshot_id=snapshot_id, document_id=document_id, domain=domain),
        "results": results,
    }


def _count_pending_media_artifacts(conn: sqlite3.Connection, *, snapshot_id: str | None = None, document_id: str | None = None, domain: str | None = None) -> int:
    where, params = _pending_media_artifact_filters(snapshot_id=snapshot_id, document_id=document_id, domain=domain)
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
        initial_status_reason = (
            "opaque-browser-blob"
            if ref.media_type == "video" and ref.source_url.lower().startswith("blob:")
            else None
        )
        row = conn.execute("SELECT id FROM media_artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE media_artifacts
                SET visit_id = COALESCE(visit_id, ?), alt_text = ?, title = ?, width = COALESCE(width, ?),
                    height = COALESCE(height, ?), duration_seconds = COALESCE(duration_seconds, ?),
                    metadata_json = ?,
                    status_reason = CASE
                      WHEN capture_status = 'referenced' THEN COALESCE(status_reason, ?)
                      ELSE status_reason
                    END
                WHERE id = ?
                """,
                (
                    visit_id,
                    alt_text,
                    title,
                    ref.width,
                    ref.height,
                    ref.duration_seconds,
                    json.dumps(metadata, sort_keys=True),
                    initial_status_reason,
                    artifact_id,
                ),
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'referenced', ?, ?)
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
                initial_status_reason,
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

def _artifact_priority(data: dict[str, Any], ref: MediaRef) -> int:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else ref.metadata
    explicit = data.get("priority")
    if explicit is not None and explicit != "":
        try:
            return max(0, min(100, int(float(explicit))))
        except (TypeError, ValueError):
            pass
    return _metadata_priority({**(metadata or {}), "width": ref.width, "height": ref.height})


def _build_media_artifact_write(
    config: RuntimeConfig,
    data: dict[str, Any],
    *,
    content_stream: Any | None = None,
    content_size: int | None = None,
) -> MediaArtifactWrite:
    snapshot_id = _bounded_text(data.get("snapshot_id") or data.get("snapshotId"), max_chars=128)
    document_id = _bounded_text(data.get("document_id") or data.get("documentId"), max_chars=128)
    visit_id = _bounded_text(data.get("visit_id") or data.get("visitId"), max_chars=128) or None
    page_url = _bounded_text(data.get("page_url") or data.get("pageUrl") or data.get("url"), max_chars=8192)
    if not snapshot_id or not document_id:
        raise ValueError("snapshot_id and document_id are required")

    ref = _row_to_ref(data)
    generated_artifact_id = media_artifact_id(snapshot_id, ref)
    provided_artifact_id = _bounded_text(data.get("artifact_id") or data.get("artifactId"), max_chars=128)
    source_url, normalized_source_url, url_redactions = _storage_url(config, ref.source_url)
    alt_text, alt_redactions = _storage_text(config, ref.alt_text)
    title, title_redactions = _storage_text(config, ref.title)
    metadata = dict(ref.metadata or {})
    priority = _artifact_priority(data, ref)
    metadata.setdefault("priority", priority)
    metadata["metadata_redaction_count"] = url_redactions + alt_redactions + title_redactions

    artifact_id = validate_media_artifact_id(provided_artifact_id) if provided_artifact_id else generated_artifact_id
    content_base64 = data.get("content_base64") or data.get("contentBase64") or ""
    status = normalize_capture_status(
        data.get("capture_status") or data.get("captureStatus"),
        default="metadata-only",
    )
    reason = _bounded_text(data.get("status_reason") or data.get("statusReason"), max_chars=512)
    content = b"" if content_stream is not None else (_decode_base64(str(content_base64)) if content_base64 else b"")
    selected_content_size = max(0, int(content_size or 0)) if content_stream is not None else len(content)
    mime_type = _sanitize_mime(
        data.get("mime_type") or data.get("mimeType") or ref.mime_type,
        media_type=ref.media_type,
    )
    return MediaArtifactWrite(
        artifact_id=artifact_id,
        generated_artifact_id=generated_artifact_id,
        artifact_id_provided=bool(provided_artifact_id),
        document_id=document_id,
        snapshot_id=snapshot_id,
        visit_id=visit_id,
        media_type=ref.media_type,
        role=ref.role,
        source_url=source_url,
        normalized_source_url=normalized_source_url,
        page_url=page_url,
        alt_text=alt_text,
        title=title,
        mime_type=mime_type,
        width=ref.width,
        height=ref.height,
        duration_seconds=ref.duration_seconds,
        capture_status=status,
        status_reason=reason,
        metadata_json=json.dumps(metadata, sort_keys=True),
        priority=priority,
        content=content,
        content_stream=content_stream,
        content_size=selected_content_size,
        file_extension=_file_extension(mime_type, ref.source_url),
        fetch_supported=_media_fetch_supported(source_url),
    )


def store_media_artifact(conn: sqlite3.Connection, config: RuntimeConfig, data: dict[str, Any]) -> dict[str, Any]:
    return _persist_media_artifact(conn, config, _build_media_artifact_write(config, data))


def _spool_limited_stream(stream: Any, spool: Any, max_bytes: int, expected_bytes: int | None = None) -> int:
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
        spool.write(chunk)
        if remaining is not None:
            remaining -= len(chunk)
    if expected_bytes is not None and remaining and remaining > 0:
        raise ValueError("incomplete media upload")
    spool.seek(0)
    return total


class _ExpectedLengthStream:
    def __init__(self, stream: Any, expected_bytes: int, *, max_chunk_bytes: int = 64 * 1024) -> None:
        if expected_bytes < 0:
            raise ValueError("expected_bytes must be nonnegative")
        self._stream = stream
        self._remaining = expected_bytes
        self._max_chunk_bytes = max_chunk_bytes

    def read(self, size: int = -1) -> bytes:
        if self._remaining == 0:
            return b""
        requested = self._remaining if size < 0 else min(size, self._remaining)
        requested = min(requested, self._max_chunk_bytes)
        chunk = self._stream.read(requested)
        if not chunk:
            raise ValueError("incomplete media upload")
        if not isinstance(chunk, (bytes, bytearray, memoryview)) or len(chunk) > requested:
            raise ValueError("invalid media upload stream")
        self._remaining -= len(chunk)
        return bytes(chunk)


def store_media_blob_stream(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    artifact_id: str,
    stream: Any,
    *,
    headers: dict[str, str] | None = None,
    content_length: int | None = None,
) -> dict[str, Any]:
    artifact_id = validate_media_artifact_id(artifact_id)
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
    raw_content_type = headers.get("content-type", "")
    if raw_content_type.split(";", 1)[0].strip().lower() == "application/octet-stream":
        raw_content_type = ""
    media_type = artifact.get("media_type") or ""
    mime_type = _safe_response_mime(raw_content_type or artifact.get("mime_type") or _infer_mime_from_url(artifact.get("source_url") or "", media_type), media_type=media_type)
    if raw_content_type and not mime_type:
        capture_status = "referenced" if media_type == "video" else "skipped"
        return store_media_artifact(conn, config, _payload_from_media_row(artifact, capture_status=capture_status, status_reason="non-media-content-type"))
    if content_length is not None:
        payload = _payload_from_media_row(artifact, capture_status="stored", mime_type=mime_type)
        return _persist_media_artifact(
            conn,
            config,
            _build_media_artifact_write(
                config,
                payload,
                content_stream=_ExpectedLengthStream(stream, content_length),
                content_size=content_length,
            ),
        )
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as content_stream:
        content_size = _spool_limited_stream(
            stream,
            content_stream,
            config.max_media_artifact_bytes,
            expected_bytes=content_length,
        )
        payload = _payload_from_media_row(artifact, capture_status="stored", mime_type=mime_type)
        return _persist_media_artifact(
            conn,
            config,
            _build_media_artifact_write(
                config,
                payload,
                content_stream=content_stream,
                content_size=content_size,
            ),
        )
