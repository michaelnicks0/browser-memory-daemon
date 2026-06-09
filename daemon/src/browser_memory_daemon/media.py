from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from .config import RuntimeConfig
from .normalize import normalize_url
from .policy import POLICY_MODE_ALL, redact_text, redact_url


MEDIA_TYPES = {"image", "video"}
MEDIA_ROLES = {"content", "poster", "source"}


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
        source_url = _bounded_text(data.get("source_url") or data.get("sourceUrl") or data.get("src") or data.get("current_src") or data.get("currentSrc"), max_chars=8192)
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
        inserted += 1
    return inserted


def _decode_base64(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise ValueError("content_base64 is not valid base64") from exc


def _row_to_ref(data: dict[str, Any]) -> MediaRef:
    return MediaRef.from_dict(data)


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
    metadata["metadata_redaction_count"] = url_redactions + alt_redactions + title_redactions

    content_base64 = data.get("content_base64") or data.get("contentBase64") or ""
    status = str(data.get("capture_status") or data.get("captureStatus") or "metadata-only").lower().strip()
    reason = _bounded_text(data.get("status_reason") or data.get("statusReason"), max_chars=512)
    content = b""
    if content_base64:
        content = _decode_base64(str(content_base64))
        if len(content) > config.max_media_artifact_bytes:
            raise ValueError("media artifact too large")
        status = "stored"
    elif status not in {"referenced", "metadata-only", "skipped", "failed"}:
        status = "metadata-only"

    mime_type = _sanitize_mime(data.get("mime_type") or data.get("mimeType") or ref.mime_type, media_type=ref.media_type)
    content_sha256 = hashlib.sha256(content).hexdigest() if content else ""
    file_path = ""
    byte_size = len(content) if content else None
    if content:
        extension = _file_extension(mime_type, ref.source_url)
        target = config.media_root / f"{artifact_id}{extension}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        file_path = str(target)

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
              capture_status=excluded.capture_status,
              status_reason=excluded.status_reason,
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
