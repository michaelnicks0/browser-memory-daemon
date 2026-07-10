from __future__ import annotations

import json
import sqlite3
import uuid
from urllib.parse import urlsplit

from .blob_lifecycle import process_blob_tombstones, tombstone_blob
from .blob_store import prefer_relative_locator
from .config import RuntimeConfig
from .normalize import domain_from_url, normalize_url
from .policy import POLICY_MODE_ALL, redact_url


def _normalize_forget_domain(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("forget domain is required")
    if "://" in text:
        raise ValueError("forget domain must be a hostname, not a URL")
    if any(char in text for char in "/?#@%*_\\") or any(char.isspace() for char in text):
        raise ValueError("forget domain must be a literal hostname without path, query, wildcard, or userinfo")
    parts = urlsplit(f"https://{text}")
    try:
        if parts.port is not None:
            raise ValueError("forget domain must not include a port; use URL forget for scoped deletion")
    except ValueError as exc:
        raise ValueError("forget domain must be a literal hostname without a port") from exc
    host = (parts.hostname or text).strip().strip("[]").rstrip(".").lower()
    if not host:
        raise ValueError("forget domain must be a literal hostname")
    return host.lstrip(".")


def _storage_url_selector(config: RuntimeConfig, url: str) -> tuple[str, str, str, str]:
    raw_url = str(url or "").strip()
    if not raw_url:
        raise ValueError("forget url is required")
    parts = urlsplit(raw_url)
    if not parts.scheme:
        raise ValueError("forget url must be absolute")
    if config.policy_mode == POLICY_MODE_ALL:
        storage_url = raw_url
        selector_policy = "literal"
    else:
        storage_url, _, _ = redact_url(raw_url)
        selector_policy = "redacted"
    receipt_url, _, _ = redact_url(raw_url)
    return storage_url, normalize_url(storage_url), normalize_url(receipt_url), selector_policy


def _document_ids_for_url(conn: sqlite3.Connection, config: RuntimeConfig, url: str) -> tuple[list[str], dict[str, str]]:
    storage_url, normalized, receipt_url, selector_policy = _storage_url_selector(config, url)
    rows = conn.execute(
        """
        SELECT id FROM documents WHERE normalized_url = ? OR canonical_url = ?
        UNION
        SELECT document_id AS id FROM visits WHERE normalized_url = ? OR url = ?
        """,
        (normalized, normalized, normalized, storage_url),
    ).fetchall()
    return [row["id"] for row in rows if row["id"]], {"url": receipt_url, "selector_policy": selector_policy}


def forget(conn: sqlite3.Connection, config: RuntimeConfig, *, domain: str | None = None, url: str | None = None) -> dict:
    has_domain = domain is not None and str(domain).strip() != ""
    has_url = url is not None and str(url).strip() != ""
    if has_domain == has_url:
        raise ValueError("forget requires exactly one selector: domain or url")
    normalized_domain = None
    if has_domain:
        normalized_domain = _normalize_forget_domain(str(domain))
        doc_rows = conn.execute(
            "SELECT id FROM documents WHERE domain = ? OR domain LIKE ?",
            (normalized_domain, f"%.{normalized_domain}"),
        ).fetchall()
        document_ids = [row["id"] for row in doc_rows]
        scope = {"domain": normalized_domain, "selector_policy": "domain-suffix"}
    else:
        document_ids, scope = _document_ids_for_url(conn, config, str(url))
    counts = {
        "documents": 0,
        "visits": 0,
        "visit_events": 0,
        "snapshots": 0,
        "chunks": 0,
        "blobs": 0,
        "media_artifacts": 0,
        "media_blobs": 0,
        "media_blobs_out_of_root": 0,
        "media_blobs_failed": 0,
        "fts": 0,
        "embeddings": 0,
        "redactions": 0,
        "feedback_events": 0,
        "blobs_out_of_root": 0,
        "blobs_failed": 0,
    }
    receipt_id = str(uuid.uuid4())
    counts["media_blobs_tombstoned"] = 0
    counts["blobs_tombstoned"] = 0
    counts["blob_deletions_pending"] = 0
    with conn:
        for document_id in document_ids:
            snapshot_rows = conn.execute(
                "SELECT id, cleaned_text_path, cleaned_text_locator, text_hash FROM snapshots WHERE document_id = ?",
                (document_id,),
            ).fetchall()
            media_rows = conn.execute(
                """
                SELECT id, file_path, blob_locator, storage_tier, spool_locator,
                       byte_size, content_sha256
                FROM media_artifacts WHERE document_id = ?
                """,
                (document_id,),
            ).fetchall()
            for media in media_rows:
                tier = str(media["storage_tier"] or "media-root")
                locator = (
                    prefer_relative_locator(media["spool_locator"], media["file_path"])
                    if tier == "spool"
                    else prefer_relative_locator(media["blob_locator"], media["file_path"])
                )
                if locator:
                    tombstone_blob(
                        conn,
                        operation_id=receipt_id,
                        owner_kind="media-artifact",
                        owner_id=str(media["id"]),
                        storage_tier=tier,
                        locator=str(locator),
                        reason="forget",
                        byte_size=int(media["byte_size"]) if media["byte_size"] is not None else None,
                        content_sha256=str(media["content_sha256"] or "") or None,
                    )
                    counts["media_blobs_tombstoned"] += 1
            counts["media_artifacts"] += conn.execute("DELETE FROM media_artifacts WHERE document_id = ?", (document_id,)).rowcount
            chunk_rows = conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,)).fetchall()
            for chunk in chunk_rows:
                counts["embeddings"] += conn.execute("DELETE FROM embeddings WHERE chunk_id = ?", (chunk["id"],)).rowcount
                counts["feedback_events"] += conn.execute("DELETE FROM feedback_events WHERE chunk_id = ?", (chunk["id"],)).rowcount
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk["id"],))
                counts["fts"] += 1
            for snap in snapshot_rows:
                counts["redactions"] += conn.execute("DELETE FROM redactions WHERE snapshot_id = ?", (snap["id"],)).rowcount
                locator = prefer_relative_locator(snap["cleaned_text_locator"], snap["cleaned_text_path"])
                if locator:
                    tombstone_blob(
                        conn,
                        operation_id=receipt_id,
                        owner_kind="snapshot-derivative",
                        owner_id=str(snap["id"]),
                        storage_tier="derivative",
                        locator=str(locator),
                        reason="forget",
                        content_sha256=str(snap["text_hash"] or "") or None,
                    )
                    counts["blobs_tombstoned"] += 1
            counts["chunks"] += conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,)).rowcount
            counts["snapshots"] += conn.execute("DELETE FROM snapshots WHERE document_id = ?", (document_id,)).rowcount
            counts["visit_events"] += conn.execute(
                "DELETE FROM visit_events WHERE document_id = ? OR visit_id IN (SELECT id FROM visits WHERE document_id = ?)",
                (document_id, document_id),
            ).rowcount
            counts["visits"] += conn.execute("DELETE FROM visits WHERE document_id = ?", (document_id,)).rowcount
            counts["feedback_events"] += conn.execute("DELETE FROM feedback_events WHERE document_id = ?", (document_id,)).rowcount
            counts["documents"] += conn.execute("DELETE FROM documents WHERE id = ?", (document_id,)).rowcount
        if domain:
            event_rows = conn.execute("SELECT id, normalized_url FROM visit_events WHERE document_id IS NULL").fetchall()
            for event in event_rows:
                event_domain = domain_from_url(event["normalized_url"])
                if event_domain == normalized_domain or event_domain.endswith(f".{normalized_domain}"):
                    counts["visit_events"] += conn.execute("DELETE FROM visit_events WHERE id = ?", (event["id"],)).rowcount
        else:
            counts["visit_events"] += conn.execute("DELETE FROM visit_events WHERE normalized_url = ?", (scope["url"],)).rowcount
        conn.execute(
            "INSERT INTO deletion_receipts(id, scope_json, counts_json) VALUES (?, ?, ?)",
            (receipt_id, json.dumps(scope, sort_keys=True), json.dumps(counts, sort_keys=True)),
        )
    deletion = process_blob_tombstones(conn, config, operation_id=receipt_id)
    state_rows = conn.execute(
        """
        SELECT owner_kind, state, COUNT(*) AS n FROM blob_storage_records
        WHERE operation_id = ? GROUP BY owner_kind, state
        """,
        (receipt_id,),
    ).fetchall()
    for row in state_rows:
        count = int(row["n"])
        if row["owner_kind"] == "media-artifact":
            if row["state"] == "deleted":
                counts["media_blobs"] += count
            elif row["state"] == "blocked":
                counts["media_blobs_out_of_root"] += count
            elif row["state"] == "failed":
                counts["media_blobs_failed"] += count
        if row["owner_kind"] == "snapshot-derivative":
            if row["state"] == "deleted":
                counts["blobs"] += count
            elif row["state"] == "blocked":
                counts["blobs_out_of_root"] += count
            elif row["state"] == "failed":
                counts["blobs_failed"] += count
    counts["blob_deletions_deleted"] = deletion["deleted"]
    counts["blob_deletions_missing"] = deletion["missing"]
    counts["blob_deletions_blocked"] = deletion["blocked"]
    counts["blob_deletions_failed"] = deletion["failed"]
    counts["blob_deletions_pending"] = deletion["pending"]
    with conn:
        conn.execute(
            "UPDATE deletion_receipts SET counts_json = ? WHERE id = ?",
            (json.dumps(counts, sort_keys=True), receipt_id),
        )
    complete = deletion["pending"] == 0
    return {
        "forgotten": complete,
        "database_forgotten": True,
        "receipt_id": receipt_id,
        "scope": scope,
        "counts": counts,
        "deletion": deletion,
    }
