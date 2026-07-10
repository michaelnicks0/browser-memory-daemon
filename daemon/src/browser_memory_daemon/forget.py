from __future__ import annotations

import json
import sqlite3
import uuid
from urllib.parse import urlsplit

from .blob_store import BlobStore, prefer_relative_locator
from .config import RuntimeConfig
from .media_storage import media_blob_store_and_locator
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


def _unlink_contained(paths: list[str], *, store: BlobStore) -> tuple[int, int, int]:
    unlinked = 0
    skipped_out_of_root = 0
    failed = 0
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if not key or key in seen:
            continue
        seen.add(key)
        result = store.delete(path)
        if result.status in {"outside-root", "invalid", "empty", "not-file"}:
            skipped_out_of_root += 1
            continue
        if result.deleted:
            unlinked += 1
        elif result.status == "error":
            failed += 1
    return unlinked, skipped_out_of_root, failed


def _unlink_media_targets(targets: list[tuple[BlobStore | None, str | None]]) -> tuple[int, int, int]:
    unlinked = 0
    skipped = 0
    failed = 0
    seen: set[tuple[str, str]] = set()
    for store, locator in targets:
        if store is None or not locator:
            skipped += 1
            continue
        key = (str(store.root), str(locator))
        if key in seen:
            continue
        seen.add(key)
        result = store.delete(locator)
        if result.status in {"outside-root", "invalid", "empty", "not-file"}:
            skipped += 1
        elif result.deleted:
            unlinked += 1
        elif result.status == "error":
            failed += 1
    return unlinked, skipped, failed


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
    media_targets: list[tuple[BlobStore | None, str | None]] = []
    clean_text_paths: list[str] = []
    with conn:
        for document_id in document_ids:
            snapshot_rows = conn.execute(
                "SELECT id, cleaned_text_path, cleaned_text_locator FROM snapshots WHERE document_id = ?",
                (document_id,),
            ).fetchall()
            media_rows = conn.execute(
                """
                SELECT id, file_path, blob_locator, storage_tier, spool_locator
                FROM media_artifacts WHERE document_id = ?
                """,
                (document_id,),
            ).fetchall()
            for media in media_rows:
                store, locator, _tier_status = media_blob_store_and_locator(config, dict(media))
                media_targets.append((store, locator))
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
                    clean_text_paths.append(locator)
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
    counts["media_blobs"], counts["media_blobs_out_of_root"], counts["media_blobs_failed"] = _unlink_media_targets(media_targets)
    counts["blobs"], counts["blobs_out_of_root"], counts["blobs_failed"] = _unlink_contained(clean_text_paths, store=BlobStore(config.clean_text_root))
    receipt_id = str(uuid.uuid4())
    with conn:
        conn.execute(
            "INSERT INTO deletion_receipts(id, scope_json, counts_json) VALUES (?, ?, ?)",
            (receipt_id, json.dumps(scope, sort_keys=True), json.dumps(counts, sort_keys=True)),
        )
    return {"forgotten": True, "receipt_id": receipt_id, "scope": scope, "counts": counts}
