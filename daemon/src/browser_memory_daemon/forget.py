from __future__ import annotations

import ipaddress
import json
import re
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .blob_lifecycle import process_blob_tombstones, tombstone_blob
from .blob_store import prefer_relative_locator
from .config import RuntimeConfig
from .normalize import domain_from_url, normalize_url
from .policy import POLICY_MODE_ALL, redact_url

DEFAULT_MAX_FORGET_RECORDS = 10_000
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


@dataclass(frozen=True)
class ForgetSelection:
    document_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    scope: dict[str, str]


def _normalize_forget_domain(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("forget domain is required")
    if "://" in text:
        raise ValueError("forget domain must be a hostname, not a URL")
    if any(char in text for char in "/?#@%*_\\") or any(char.isspace() for char in text):
        raise ValueError("forget domain must be a literal hostname without path, query, wildcard, or userinfo")
    candidate = text.rstrip(".")
    address_candidate = candidate[1:-1] if candidate.startswith("[") and candidate.endswith("]") else candidate
    try:
        return ipaddress.ip_address(address_candidate).compressed.lower()
    except ValueError:
        pass
    if re.fullmatch(r"[0-9.]+", candidate):
        raise ValueError("forget domain must be a valid hostname or IP literal")
    if ":" in candidate:
        raise ValueError("forget domain must be a literal hostname without a port")
    normalized_host = unicodedata.normalize("NFC", candidate).lower()
    try:
        ascii_host = normalized_host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("forget domain must be a valid hostname or IP literal") from exc
    labels = ascii_host.split(".")
    if len(ascii_host) > 253 or any(not label or not _HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError("forget domain must be a valid hostname or IP literal")
    try:
        ascii_host.encode("ascii").decode("idna")
    except UnicodeError as exc:
        raise ValueError("forget domain must be a valid hostname or IP literal") from exc
    return ascii_host


def _domain_storage_variants(normalized_domain: str) -> tuple[str, ...]:
    try:
        unicode_domain = normalized_domain.encode("ascii").decode("idna").lower()
    except UnicodeError:
        unicode_domain = normalized_domain
    return tuple(dict.fromkeys((normalized_domain, unicode_domain)))


def _matches_domain_scope(candidate: str, normalized_domain: str) -> bool:
    try:
        normalized_candidate = _normalize_forget_domain(candidate)
    except ValueError:
        return False
    return normalized_candidate == normalized_domain or normalized_candidate.endswith(f".{normalized_domain}")


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


def _document_ids_for_url(conn: sqlite3.Connection, config: RuntimeConfig, url: str) -> tuple[list[str], dict[str, str], str]:
    storage_url, normalized, receipt_url, selector_policy = _storage_url_selector(config, url)
    rows = conn.execute(
        """
        SELECT id FROM documents WHERE normalized_url = ?
        UNION
        SELECT document_id AS id FROM visits WHERE normalized_url = ? OR url = ?
        UNION
        SELECT document_id AS id FROM document_url_claims WHERE normalized_claimed_url = ?
        """,
        (normalized, normalized, storage_url, normalized),
    ).fetchall()
    return [row["id"] for row in rows if row["id"]], {"url": receipt_url, "selector_policy": selector_policy}, normalized


def _empty_counts() -> dict[str, int]:
    return {
        "documents": 0,
        "visits": 0,
        "visit_events": 0,
        "capture_observations": 0,
        "url_claims": 0,
        "snapshots": 0,
        "chunks": 0,
        "blobs": 0,
        "media_artifacts": 0,
        "media_observations": 0,
        "media_tasks": 0,
        "media_cache_reservations": 0,
        "media_blobs": 0,
        "media_blobs_out_of_root": 0,
        "media_blobs_failed": 0,
        "fts": 0,
        "embeddings": 0,
        "redactions": 0,
        "feedback_events": 0,
        "blobs_out_of_root": 0,
        "blobs_failed": 0,
        "media_blobs_tombstoned": 0,
        "blobs_tombstoned": 0,
        "blob_deletions_pending": 0,
    }


def _count(conn: sqlite3.Connection, sql: str, parameters: tuple[Any, ...]) -> int:
    return int(conn.execute(sql, parameters).fetchone()[0])


def _select_forget(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    domain: str | None,
    url: str | None,
) -> ForgetSelection:
    has_domain = domain is not None and str(domain).strip() != ""
    has_url = url is not None and str(url).strip() != ""
    if has_domain == has_url:
        raise ValueError("forget requires exactly one selector: domain or url")
    if has_domain:
        normalized_domain = _normalize_forget_domain(str(domain))
        domain_variants = _domain_storage_variants(normalized_domain)
        document_rows = []
        for variant in domain_variants:
            document_rows.extend(
                conn.execute(
                    """
                    SELECT id FROM documents
                    WHERE domain = ? OR substr(domain, -(length(?) + 1)) = '.' || ?
                    """,
                    (variant, variant, variant),
                ).fetchall()
            )
        selected_document_ids = tuple(str(row["id"]) for row in document_rows if row["id"])
        event_rows = conn.execute("SELECT id, normalized_url FROM visit_events WHERE document_id IS NULL").fetchall()
        event_ids = tuple(
            str(row["id"])
            for row in event_rows
            if (event_domain := domain_from_url(row["normalized_url"]))
            and _matches_domain_scope(event_domain, normalized_domain)
        )
        scope = {"domain": normalized_domain, "selector_policy": "domain-suffix"}
    else:
        document_ids, scope, event_selector = _document_ids_for_url(conn, config, str(url))
        selected_document_ids = tuple(document_ids)
        event_ids = tuple(
            str(row["id"])
            for row in conn.execute(
                "SELECT id FROM visit_events WHERE document_id IS NULL AND normalized_url = ?",
                (event_selector,),
            ).fetchall()
        )
    return ForgetSelection(
        document_ids=selected_document_ids,
        event_ids=event_ids,
        scope=scope,
    )


def _selection_counts(conn: sqlite3.Connection, selection: ForgetSelection) -> dict[str, int]:
    counts = _empty_counts()
    counts["documents"] = len(selection.document_ids)
    counts["visit_events"] = len(selection.event_ids)
    for document_id in selection.document_ids:
        counts["visits"] += _count(conn, "SELECT COUNT(*) FROM visits WHERE document_id = ?", (document_id,))
        counts["visit_events"] += _count(
            conn,
            "SELECT COUNT(*) FROM visit_events WHERE document_id = ? OR visit_id IN (SELECT id FROM visits WHERE document_id = ?)",
            (document_id, document_id),
        )
        counts["capture_observations"] += _count(
            conn,
            "SELECT COUNT(*) FROM capture_observations WHERE document_id = ?",
            (document_id,),
        )
        counts["url_claims"] += _count(
            conn,
            "SELECT COUNT(*) FROM document_url_claims WHERE document_id = ?",
            (document_id,),
        )
        counts["snapshots"] += _count(conn, "SELECT COUNT(*) FROM snapshots WHERE document_id = ?", (document_id,))
        counts["chunks"] += _count(conn, "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (document_id,))
        counts["fts"] += _count(
            conn,
            "SELECT COUNT(*) FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)",
            (document_id,),
        )
        counts["embeddings"] += _count(
            conn,
            "SELECT COUNT(*) FROM embeddings WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)",
            (document_id,),
        )
        counts["redactions"] += _count(
            conn,
            "SELECT COUNT(*) FROM redactions WHERE snapshot_id IN (SELECT id FROM snapshots WHERE document_id = ?)",
            (document_id,),
        )
        counts["feedback_events"] += _count(
            conn,
            "SELECT COUNT(*) FROM feedback_events WHERE document_id = ? OR chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)",
            (document_id, document_id),
        )
        counts["media_artifacts"] += _count(conn, "SELECT COUNT(*) FROM media_artifacts WHERE document_id = ?", (document_id,))
        counts["media_observations"] += _count(
            conn,
            """
            SELECT COUNT(*) FROM media_artifact_observations
            WHERE artifact_id IN (SELECT id FROM media_artifacts WHERE document_id = ?)
            """,
            (document_id,),
        )
        counts["media_tasks"] += _count(
            conn,
            """
            SELECT COUNT(*) FROM media_fetch_tasks
            WHERE artifact_id IN (SELECT id FROM media_artifacts WHERE document_id = ?)
            """,
            (document_id,),
        )
        counts["media_cache_reservations"] += _count(
            conn,
            "SELECT COUNT(*) FROM media_cache_reservations WHERE document_id = ?",
            (document_id,),
        )
        counts["media_blobs_tombstoned"] += _count(
            conn,
            """
            SELECT COUNT(*) FROM media_artifacts
            WHERE document_id = ? AND CASE
              WHEN storage_tier = 'spool'
              THEN COALESCE(NULLIF(spool_locator, ''), NULLIF(file_path, ''))
              ELSE COALESCE(NULLIF(blob_locator, ''), NULLIF(file_path, ''))
            END IS NOT NULL
            """,
            (document_id,),
        )
        counts["blobs_tombstoned"] += _count(
            conn,
            """
            SELECT COUNT(*) FROM snapshots
            WHERE document_id = ?
              AND COALESCE(NULLIF(cleaned_text_locator, ''), NULLIF(cleaned_text_path, '')) IS NOT NULL
            """,
            (document_id,),
        )
    return counts


def _selected_record_count(counts: dict[str, int]) -> int:
    return sum(
        counts[key]
        for key in (
            "documents",
            "visits",
            "visit_events",
            "capture_observations",
            "url_claims",
            "snapshots",
            "chunks",
            "fts",
            "embeddings",
            "redactions",
            "feedback_events",
            "media_artifacts",
            "media_observations",
            "media_tasks",
            "media_cache_reservations",
        )
    )


def forget(
    conn: sqlite3.Connection,
    config: RuntimeConfig,
    *,
    domain: str | None = None,
    url: str | None = None,
    dry_run: bool = False,
    max_records: int = DEFAULT_MAX_FORGET_RECORDS,
) -> dict[str, Any]:
    if not isinstance(dry_run, bool):
        raise ValueError("forget dry_run must be a boolean")
    if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records < 1:
        raise ValueError("forget max_records must be a positive integer")
    owns_transaction = not conn.in_transaction
    if owns_transaction:
        conn.execute("BEGIN" if dry_run else "BEGIN IMMEDIATE")
    try:
        selection = _select_forget(conn, config, domain=domain, url=url)
        preview_counts = _selection_counts(conn, selection)
        selected_records = _selected_record_count(preview_counts)
        guard = {
            "selected_records": selected_records,
            "max_records": max_records,
            "within_limit": selected_records <= max_records,
        }
        if dry_run:
            result = {
                "dry_run": True,
                "forgotten": False,
                "database_forgotten": False,
                "receipt_id": None,
                "scope": selection.scope,
                "counts": preview_counts,
                "guard": guard,
            }
            if owns_transaction:
                conn.rollback()
            return result
        if selected_records > max_records:
            raise ValueError(
                f"forget selection exceeds max_records guard: selected {selected_records}, allowed {max_records}; preview and raise the explicit limit"
            )
    except BaseException:
        if owns_transaction and conn.in_transaction:
            conn.rollback()
        raise
    document_ids = selection.document_ids
    scope = selection.scope
    counts = _empty_counts()
    for cascade_key in (
        "capture_observations",
        "url_claims",
        "media_observations",
        "media_tasks",
        "media_cache_reservations",
    ):
        counts[cascade_key] = preview_counts[cascade_key]
    receipt_id = str(uuid.uuid4())
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
                counts["fts"] += conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk["id"],)).rowcount
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
        for event_id in selection.event_ids:
            counts["visit_events"] += conn.execute("DELETE FROM visit_events WHERE id = ?", (event_id,)).rowcount
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
        "dry_run": False,
        "forgotten": complete,
        "database_forgotten": True,
        "receipt_id": receipt_id,
        "scope": scope,
        "counts": counts,
        "deletion": deletion,
        "guard": guard,
    }
