from __future__ import annotations

import hashlib
import sqlite3
from urllib.parse import urlsplit

from .config import RuntimeConfig
from .db import audit
from .lifecycle import recompute_visit_dwell
from .media import media_artifact_id, parse_media_refs, record_media_references
from .models import CapturePayload
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


def _url_origin(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def _observation_identity(
    payload: CapturePayload,
    *,
    safe_url: str,
    document_id: str,
    snapshot_id: str,
) -> tuple[str, str, str]:
    if payload.observation_id:
        idempotency_key = f"browser:{payload.observation_id}"
        quality = "observed"
    else:
        idempotency_key = "derived:" + text_hash(
            "\n".join([payload.visit_id, payload.captured_at, safe_url, document_id, snapshot_id])
        )
        quality = "inferred"
    return stable_id("obs", idempotency_key), idempotency_key, quality


def _observation_exists_and_matches(
    conn: sqlite3.Connection,
    *,
    observation_id: str,
    idempotency_key: str,
    navigation_id: str,
    document_id: str,
    snapshot_id: str,
    visit_id: str,
    safe_url: str,
    normalized_url: str,
    title: str,
    captured_at: str,
    capture_reason: str,
    capture_method: str,
    extraction_version: str,
    provenance_quality: str,
) -> bool:
    row = conn.execute(
        """
        SELECT idempotency_key, navigation_id, document_id, snapshot_id, visit_id,
               observed_url, normalized_observed_url, title, captured_at,
               capture_reason, capture_method, extraction_version, provenance_quality
        FROM capture_observations
        WHERE id = ?
        """,
        (observation_id,),
    ).fetchone()
    if row is None:
        return False
    expected = {
        "idempotency_key": idempotency_key,
        "navigation_id": navigation_id,
        "document_id": document_id,
        "snapshot_id": snapshot_id,
        "visit_id": visit_id,
        "observed_url": safe_url,
        "normalized_observed_url": normalized_url,
        "title": title,
        "captured_at": captured_at,
        "capture_reason": capture_reason,
        "capture_method": capture_method,
        "extraction_version": extraction_version,
        "provenance_quality": provenance_quality,
    }
    if any(row[field] != value for field, value in expected.items()):
        raise ValueError("observation_id conflicts with an existing capture")
    return True


def _assert_visit_identity(
    conn: sqlite3.Connection,
    *,
    visit_id: str,
    document_id: str,
    normalized_url: str,
) -> None:
    row = conn.execute(
        "SELECT document_id, normalized_url FROM visits WHERE id = ?",
        (visit_id,),
    ).fetchone()
    if row is not None and (row["document_id"], row["normalized_url"]) != (document_id, normalized_url):
        raise ValueError("visit_id conflicts with an existing navigation")


def ingest_capture(conn: sqlite3.Connection, config: RuntimeConfig, payload: CapturePayload) -> dict:
    safe_url, safe_canonical, safe_title, stored_text, redaction_count, redaction_classes = _prepare_storage_values(config, payload)

    normalized = normalize_url(safe_url)
    canonical_normalized = normalize_url(safe_canonical) if safe_canonical else normalized
    domain = domain_from_url(normalized)
    document_id = stable_id("doc", normalized)
    digest = text_hash(stored_text)
    snapshot_id = stable_id("snap", f"{document_id}:{digest}")
    observation_id, idempotency_key, observation_quality = _observation_identity(
        payload,
        safe_url=safe_url,
        document_id=document_id,
        snapshot_id=snapshot_id,
    )
    _observation_exists_and_matches(
        conn,
        observation_id=observation_id,
        idempotency_key=idempotency_key,
        navigation_id=payload.navigation_id or payload.visit_id,
        document_id=document_id,
        snapshot_id=snapshot_id,
        visit_id=payload.visit_id,
        safe_url=safe_url,
        normalized_url=normalized,
        title=safe_title,
        captured_at=payload.captured_at,
        capture_reason=payload.capture_reason,
        capture_method=payload.extraction_method,
        extraction_version=payload.extraction_version,
        provenance_quality=observation_quality,
    )
    _assert_visit_identity(
        conn,
        visit_id=payload.visit_id,
        document_id=document_id,
        normalized_url=normalized,
    )
    chunks = chunk_text(stored_text)
    media_refs = parse_media_refs(payload.media_artifacts, max_refs=config.max_media_artifacts_per_capture)

    with conn:
        conn.execute(
            """
            INSERT INTO documents(id, canonical_url, normalized_url, domain, title, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=CASE
                WHEN documents.last_seen_at IS NULL OR excluded.last_seen_at >= documents.last_seen_at
                THEN excluded.title ELSE documents.title END,
              first_seen_at=MIN(documents.first_seen_at, excluded.first_seen_at),
              last_seen_at=MAX(documents.last_seen_at, excluded.last_seen_at)
            """,
            (document_id, normalized, normalized, domain, safe_title, payload.captured_at, payload.captured_at),
        )
        conn.execute(
            """
            INSERT INTO visits(
              id, document_id, source_id, url, normalized_url, title, source_device, browser_profile,
              visit_started_at, captured_at, dwell_seconds, is_incognito, blocked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET
              title=CASE
                WHEN visits.captured_at IS NULL OR excluded.captured_at >= visits.captured_at
                THEN excluded.title ELSE visits.title END,
              captured_at=CASE
                WHEN visits.captured_at IS NULL OR excluded.captured_at > visits.captured_at
                THEN excluded.captured_at ELSE visits.captured_at END,
              visit_started_at=CASE
                WHEN visits.visit_started_at IS NULL THEN excluded.visit_started_at
                WHEN excluded.visit_started_at IS NULL THEN visits.visit_started_at
                ELSE MIN(visits.visit_started_at, excluded.visit_started_at) END,
              dwell_seconds=MAX(COALESCE(visits.dwell_seconds, 0), COALESCE(excluded.dwell_seconds, 0)),
              is_incognito=MAX(visits.is_incognito, excluded.is_incognito)
            """,
            (
                payload.visit_id,
                document_id,
                "chrome-extension",
                safe_url,
                normalized,
                safe_title,
                payload.source_device,
                payload.browser_profile,
                payload.visit_started_at,
                payload.captured_at,
                payload.dwell_seconds,
                int(payload.is_incognito),
            ),
        )
        delayed_event_count = conn.execute(
            """
            UPDATE visit_events
            SET visit_id = ?, document_id = ?, attachment_method = 'visit-id-delayed'
            WHERE visit_id IS NULL
              AND claimed_visit_id = ?
              AND normalized_url = ?
            """,
            (payload.visit_id, document_id, payload.visit_id, normalized),
        ).rowcount
        if delayed_event_count:
            recompute_visit_dwell(conn, payload.visit_id)
        snapshot_cursor = conn.execute(
            """
            INSERT OR IGNORE INTO snapshots(
              id, document_id, visit_id, captured_at, content_type, extraction_method,
              text_hash, cleaned_text_path, privacy_class, redaction_count, cleaned_text_locator,
              cleaned_text, cleaned_text_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?, 'capture')
            """,
            (
                snapshot_id,
                document_id,
                payload.visit_id,
                payload.captured_at,
                payload.content_type,
                payload.extraction_method,
                digest,
                config.policy_mode,
                redaction_count,
                stored_text,
            ),
        )
        snapshot_created = bool(snapshot_cursor.rowcount)
        if not snapshot_created:
            conn.execute(
                """
                UPDATE snapshots
                SET cleaned_text_source = CASE
                      WHEN cleaned_text IS NULL THEN 'capture'
                      ELSE cleaned_text_source
                    END,
                    cleaned_text = COALESCE(cleaned_text, ?)
                WHERE id = ?
                """,
                (stored_text, snapshot_id),
            )
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
        observation_cursor = conn.execute(
            """
            INSERT OR IGNORE INTO capture_observations(
              id, idempotency_key, navigation_id, visit_id, document_id, snapshot_id,
              observed_url, normalized_observed_url, title, captured_at,
              capture_reason, capture_method, extraction_version,
              disposition, provenance_quality, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            (
                observation_id,
                idempotency_key,
                payload.navigation_id or payload.visit_id,
                payload.visit_id,
                document_id,
                snapshot_id,
                safe_url,
                normalized,
                safe_title,
                payload.captured_at,
                payload.capture_reason,
                payload.extraction_method,
                payload.extraction_version,
                "accepted" if snapshot_created else "duplicate",
                observation_quality,
            ),
        )
        observation_created = bool(observation_cursor.rowcount)
        if not observation_created:
            _observation_exists_and_matches(
                conn,
                observation_id=observation_id,
                idempotency_key=idempotency_key,
                navigation_id=payload.navigation_id or payload.visit_id,
                document_id=document_id,
                snapshot_id=snapshot_id,
                visit_id=payload.visit_id,
                safe_url=safe_url,
                normalized_url=normalized,
                title=safe_title,
                captured_at=payload.captured_at,
                capture_reason=payload.capture_reason,
                capture_method=payload.extraction_method,
                extraction_version=payload.extraction_version,
                provenance_quality=observation_quality,
            )

        conn.execute(
            """
            INSERT INTO observation_ingest_sequences(observation_id)
            SELECT ?
            WHERE NOT EXISTS (
              SELECT 1 FROM observation_ingest_sequences WHERE observation_id = ?
            )
            """,
            (observation_id, observation_id),
        )

        claim_ids: list[str] = []
        if safe_canonical and canonical_normalized != normalized:
            claim_id = stable_id("claim", f"canonical:{document_id}:{canonical_normalized}")
            observed_origin = _url_origin(normalized)
            claim_origin = _url_origin(canonical_normalized)
            same_origin = int(
                observed_origin is not None
                and claim_origin is not None
                and observed_origin == claim_origin
            )
            conn.execute(
                """
                INSERT INTO document_url_claims(
                  id, document_id, observation_id, claim_type,
                  claimed_url, normalized_claimed_url, claim_origin, same_origin,
                  identity_effect, provenance_quality, first_observed_at, last_observed_at,
                  metadata_json
                ) VALUES (?, ?, ?, 'canonical', ?, ?, ?, ?, 'none', 'observed', ?, ?, '{}')
                ON CONFLICT(document_id, claim_type, normalized_claimed_url) DO UPDATE SET
                  observation_id=CASE
                    WHEN excluded.last_observed_at >= document_url_claims.last_observed_at
                    THEN excluded.observation_id ELSE document_url_claims.observation_id END,
                  claimed_url=CASE
                    WHEN excluded.last_observed_at >= document_url_claims.last_observed_at
                    THEN excluded.claimed_url ELSE document_url_claims.claimed_url END,
                  claim_origin=CASE
                    WHEN excluded.last_observed_at >= document_url_claims.last_observed_at
                    THEN excluded.claim_origin ELSE document_url_claims.claim_origin END,
                  same_origin=CASE
                    WHEN excluded.last_observed_at >= document_url_claims.last_observed_at
                    THEN excluded.same_origin ELSE document_url_claims.same_origin END,
                  first_observed_at=MIN(document_url_claims.first_observed_at, excluded.first_observed_at),
                  last_observed_at=MAX(document_url_claims.last_observed_at, excluded.last_observed_at)
                """,
                (
                    claim_id,
                    document_id,
                    observation_id,
                    safe_canonical,
                    canonical_normalized,
                    claim_origin,
                    same_origin,
                    payload.captured_at,
                    payload.captured_at,
                ),
            )
            claim_ids.append(claim_id)

        record_media_references(
            conn,
            config,
            document_id=document_id,
            snapshot_id=snapshot_id,
            visit_id=payload.visit_id,
            page_url=safe_url,
            refs=media_refs,
        )
        for ref in media_refs:
            conn.execute(
                """
                INSERT OR IGNORE INTO media_artifact_observations(
                  artifact_id, observation_id, provenance_quality, observed_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    media_artifact_id(snapshot_id, ref),
                    observation_id,
                    observation_quality,
                    payload.captured_at,
                ),
            )
        media_ref_count = len(media_refs)
        audit(
            conn,
            "capture.stored",
            {
                "document_id": document_id,
                "snapshot_id": snapshot_id,
                "visit_id": payload.visit_id,
                "observation_id": observation_id,
                "observation_created": observation_created,
                "url_claim_count": len(claim_ids),
                "snapshot_created": snapshot_created,
                "chunk_count": len(chunks) if snapshot_created else 0,
                "media_ref_count": media_ref_count,
                "redaction_count": redaction_count,
                "redaction_classes": redaction_classes,
                "domain": domain,
                "policy_mode": config.policy_mode,
                "text_authority": "sqlite",
                "clean_text_sidecar_status": "not-created",
            },
        )
    return {
        "stored": True,
        "document_id": document_id,
        "snapshot_id": snapshot_id,
        "visit_id": payload.visit_id,
        "observation_id": observation_id,
        "observation_created": observation_created,
        "url_claim_ids": claim_ids,
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
        "text_authority": "sqlite",
        "clean_text_sidecar_status": "not-created",
    }
