from __future__ import annotations

import hashlib
import sqlite3
import uuid

from .config import RuntimeConfig
from .db import audit
from .models import CapturePayload
from .media import media_artifact_id, parse_media_refs, record_media_references
from .normalize import domain_from_url, normalize_url
from .policy import POLICY_MODE_ALL, redact_text, redact_url


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, *, max_chars: int = 1800) -> list[str]:
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs or [text.strip()]:
        if current and current_len + len(paragraph) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        if len(paragraph) > max_chars:
            for i in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[i : i + max_chars])
            continue
        current.append(paragraph)
        current_len += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _write_clean_text_atomic(clean_path, text: str) -> None:
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = clean_path.with_name(f".{clean_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(clean_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _prepare_storage_values(config: RuntimeConfig, payload: CapturePayload) -> tuple[str, str, str, str, int, list[str]]:
    if config.policy_mode == POLICY_MODE_ALL:
        safe_url = payload.url
        safe_canonical = payload.canonical_url if payload.canonical_url else payload.url
        safe_title = payload.title
        stored_text = payload.text
        return safe_url, safe_canonical, safe_title, stored_text, 0, []

    safe_url, url_redactions, url_classes = redact_url(payload.url)
    if payload.canonical_url and payload.canonical_url != payload.url:
        safe_canonical, canonical_redactions, canonical_classes = redact_url(payload.canonical_url)
    else:
        safe_canonical, canonical_redactions, canonical_classes = safe_url, 0, []
    safe_title, title_redactions, title_classes = redact_text(payload.title)
    stored_text, text_redactions, text_classes = redact_text(payload.text)
    redaction_count = url_redactions + canonical_redactions + title_redactions + text_redactions
    redaction_classes = []
    for label in [*url_classes, *canonical_classes, *title_classes, *text_classes]:
        if label not in redaction_classes:
            redaction_classes.append(label)
    return safe_url, safe_canonical, safe_title, stored_text, redaction_count, redaction_classes


def ingest_capture(conn: sqlite3.Connection, config: RuntimeConfig, payload: CapturePayload) -> dict:
    safe_url, safe_canonical, safe_title, stored_text, redaction_count, redaction_classes = _prepare_storage_values(config, payload)

    normalized = normalize_url(safe_canonical or safe_url)
    original_normalized = normalize_url(safe_url)
    domain = domain_from_url(normalized)
    document_id = stable_id("doc", normalized)
    digest = text_hash(stored_text)
    snapshot_id = stable_id("snap", f"{document_id}:{digest}")
    clean_path = config.clean_text_root / f"{snapshot_id}.txt"
    chunks = chunk_text(stored_text)
    media_refs = parse_media_refs(payload.media_artifacts, max_refs=config.max_media_artifacts_per_capture)

    snapshot_exists_before = conn.execute("SELECT 1 FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone() is not None
    if not snapshot_exists_before:
        _write_clean_text_atomic(clean_path, stored_text)

    with conn:
        conn.execute(
            """
            INSERT INTO documents(id, canonical_url, normalized_url, domain, title, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,
              last_seen_at=excluded.last_seen_at
            """,
            (document_id, normalized, normalized, domain, safe_title, payload.captured_at, payload.captured_at),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO visits(
              id, document_id, source_id, url, normalized_url, title, source_device, browser_profile,
              visit_started_at, captured_at, dwell_seconds, is_incognito, blocked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                payload.visit_id,
                document_id,
                "chrome-extension",
                safe_url,
                original_normalized,
                safe_title,
                payload.source_device,
                payload.browser_profile,
                payload.visit_started_at,
                payload.captured_at,
                payload.dwell_seconds,
                int(payload.is_incognito),
            ),
        )
        snapshot_cursor = conn.execute(
            """
            INSERT OR IGNORE INTO snapshots(
              id, document_id, visit_id, captured_at, content_type, extraction_method,
              text_hash, cleaned_text_path, privacy_class, redaction_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                document_id,
                payload.visit_id,
                payload.captured_at,
                payload.content_type,
                payload.extraction_method,
                digest,
                str(clean_path),
                config.policy_mode,
                redaction_count,
            ),
        )
        snapshot_created = bool(snapshot_cursor.rowcount)
        if snapshot_created:
            for label in redaction_classes:
                conn.execute(
                    "INSERT OR IGNORE INTO redactions(id, snapshot_id, redaction_class, redaction_count) VALUES (?, ?, ?, ?)",
                    (stable_id("red", f"{snapshot_id}:{label}"), snapshot_id, label, redaction_count),
                )
            for idx, chunk in enumerate(chunks):
                chunk_id = stable_id("chunk", f"{snapshot_id}:{idx}:{chunk[:64]}")
                chunk_cursor = conn.execute(
                    "INSERT OR IGNORE INTO chunks(id, snapshot_id, document_id, chunk_index, text, title, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (chunk_id, snapshot_id, document_id, idx, chunk, safe_title, safe_url),
                )
                if chunk_cursor.rowcount:
                    conn.execute(
                        "INSERT INTO chunks_fts(chunk_id, document_id, snapshot_id, title, url, text) VALUES (?, ?, ?, ?, ?, ?)",
                        (chunk_id, document_id, snapshot_id, safe_title, safe_url, chunk),
                    )
        media_ref_count = record_media_references(
            conn,
            config,
            document_id=document_id,
            snapshot_id=snapshot_id,
            visit_id=payload.visit_id,
            page_url=safe_url,
            refs=media_refs,
        )
        audit(
            conn,
            "capture.stored",
            {
                "document_id": document_id,
                "snapshot_id": snapshot_id,
                "visit_id": payload.visit_id,
                "snapshot_created": snapshot_created,
                "chunk_count": len(chunks) if snapshot_created else 0,
                "media_ref_count": media_ref_count,
                "redaction_count": redaction_count,
                "redaction_classes": redaction_classes,
                "domain": domain,
                "policy_mode": config.policy_mode,
            },
        )
    return {
        "stored": True,
        "document_id": document_id,
        "snapshot_id": snapshot_id,
        "visit_id": payload.visit_id,
        "snapshot_created": snapshot_created,
        "chunk_count": len(chunks) if snapshot_created else 0,
        "media_ref_count": media_ref_count,
        "media_artifacts": [
            {
                "artifact_id": media_artifact_id(snapshot_id, ref),
                "document_id": document_id,
                "snapshot_id": snapshot_id,
                "visit_id": payload.visit_id,
                "page_url": safe_url,
                "media_type": ref.media_type,
                "role": ref.role,
                "source_url": ref.source_url,
                "mime_type": ref.mime_type,
                "width": ref.width,
                "height": ref.height,
                "duration_seconds": ref.duration_seconds,
                "metadata": ref.metadata or {},
            }
            for ref in media_refs
        ],
        "redaction_count": redaction_count,
        "policy_mode": config.policy_mode,
    }
