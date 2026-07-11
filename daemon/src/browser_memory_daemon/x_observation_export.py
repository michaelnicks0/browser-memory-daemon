from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import __version__
from .config import APP_NAME
from .migration_steps import MIGRATIONS
from .migrations import schema_fingerprint

CONTRACT = "bmd.x-observations"
CONTRACT_VERSION = 1
MAX_LIMIT = 1_000
_CURSOR_KEYS = {"contract", "version", "ingest_sequence", "observation_id"}
_X_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/[A-Za-z0-9_./%-]+(?:\?[A-Za-z0-9_=&%.-]*)?",
    re.IGNORECASE,
)
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_STATUS_RE = re.compile(r"^/([A-Za-z0-9_]{1,15})/status/([0-9]+)(?:/|$)", re.IGNORECASE)
_PROFILE_RE = re.compile(r"^/([A-Za-z0-9_]{1,15})(?:/|$)", re.IGNORECASE)
_WRITE_ACTIONS = {
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_CREATE_INDEX,
    sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_INDEX,
    sqlite3.SQLITE_CREATE_TEMP_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
    sqlite3.SQLITE_CREATE_TEMP_VIEW,
    sqlite3.SQLITE_CREATE_TRIGGER,
    sqlite3.SQLITE_CREATE_VIEW,
    sqlite3.SQLITE_DROP_INDEX,
    sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_INDEX,
    sqlite3.SQLITE_DROP_TEMP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_TRIGGER,
    sqlite3.SQLITE_DROP_TEMP_VIEW,
    sqlite3.SQLITE_DROP_TRIGGER,
    sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_REINDEX,
    sqlite3.SQLITE_ANALYZE,
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_DETACH,
}


class XObservationExportError(RuntimeError):
    code = "x_observation_export_failed"


class XObservationCompatibilityError(XObservationExportError):
    code = "x_observation_contract_incompatible"


class XObservationCursorError(ValueError):
    code = "x_observation_cursor_invalid"


def default_database_path(runtime_root: str | Path | None = None) -> Path:
    selected: str | Path | None = runtime_root if runtime_root is not None else os.environ.get("BMD_RUNTIME_ROOT")
    if selected:
        return Path(str(selected)).expanduser() / "browser-memory.sqlite3"
    data_home_value = os.environ.get("XDG_DATA_HOME")
    data_home = Path(data_home_value).expanduser() if data_home_value else Path.home() / ".local" / "share"
    return data_home / str(APP_NAME) / "browser-memory.sqlite3"


def _deny_writes(action: int, _arg1: str | None, _arg2: str | None, _db: str | None, _source: str | None) -> int:
    return sqlite3.SQLITE_DENY if action in _WRITE_ACTIONS else sqlite3.SQLITE_OK


def _open_query_only(database: Path) -> sqlite3.Connection:
    path = Path(database).expanduser()
    if not path.is_file():
        raise XObservationCompatibilityError("BMD database does not exist")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA query_only = ON")
    if int(conn.execute("PRAGMA query_only").fetchone()[0]) != 1:
        conn.close()
        raise XObservationCompatibilityError("SQLite query-only mode could not be enabled")
    conn.set_authorizer(_deny_writes)
    return conn


def _validate_schema(conn: sqlite3.Connection) -> int:
    latest = MIGRATIONS[-1]
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if user_version != latest.version:
        relation = "older" if user_version < latest.version else "newer"
        raise XObservationCompatibilityError(
            f"BMD database schema is {relation} than export contract support"
        )
    tables = {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name IN "
            "('schema_migrations','capture_observations','observation_ingest_sequences','snapshots','document_url_claims','media_artifact_observations')"
        )
    }
    required = {
        "schema_migrations",
        "capture_observations",
        "observation_ingest_sequences",
        "snapshots",
        "document_url_claims",
        "media_artifact_observations",
    }
    if tables != required:
        raise XObservationCompatibilityError("BMD database is missing required export tables")
    ledger = conn.execute(
        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    if len(ledger) != latest.version:
        raise XObservationCompatibilityError("BMD migration ledger is incomplete")
    for expected, row in zip(MIGRATIONS, ledger, strict=True):
        if (
            int(row["version"]) != expected.version
            or str(row["name"]) != expected.name
            or str(row["checksum"]) != expected.checksum
        ):
            raise XObservationCompatibilityError("BMD migration ledger is incompatible")
    if schema_fingerprint(conn) != latest.schema_fingerprint:
        raise XObservationCompatibilityError("BMD schema fingerprint is incompatible")
    return user_version


def encode_cursor(ingest_sequence: int, observation_id: str) -> str:
    payload = {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "ingest_sequence": int(ingest_sequence),
        "observation_id": str(observation_id),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[int, str]:
    if cursor is None or cursor == "":
        return 0, ""
    value = str(cursor).strip()
    if not value or len(value) > 2_048 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise XObservationCursorError("invalid X observation cursor")
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise XObservationCursorError("invalid X observation cursor") from exc
    if not isinstance(payload, dict) or set(payload) != _CURSOR_KEYS:
        raise XObservationCursorError("invalid X observation cursor")
    if payload.get("contract") != CONTRACT or payload.get("version") != CONTRACT_VERSION:
        raise XObservationCursorError("unsupported X observation cursor")
    sequence = payload.get("ingest_sequence")
    observation_id = payload.get("observation_id")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise XObservationCursorError("invalid X observation cursor")
    if not isinstance(observation_id, str) or (sequence > 0 and not observation_id):
        raise XObservationCursorError("invalid X observation cursor")
    return sequence, observation_id


def _canonical_x_url(value: str) -> str | None:
    raw = str(value or "").strip().rstrip(".,;:!?)]}'\"")
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return None
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if not path.startswith("/"):
        path = "/" + path
    return f"https://x.com{path.rstrip('/') or '/'}"


def _classify_x_url(url: str) -> tuple[str, str | None, str | None]:
    path = urlparse(url).path
    status = _STATUS_RE.match(path)
    if status:
        return "status", status.group(2), status.group(1)
    lowered = path.lower().rstrip("/")
    if lowered == "/i/bookmarks":
        return "bookmarks", None, None
    if lowered in {"/home", "/explore", "/notifications"}:
        return "timeline", None, None
    profile = _PROFILE_RE.match(path)
    if profile:
        handle = profile.group(1)
        if lowered.endswith("/likes"):
            return "likes", None, handle
        if handle.lower() not in {"i", "home", "explore", "notifications", "messages", "search"}:
            return "profile", None, handle
    return "other_x", None, None


def _discovered_urls(row: sqlite3.Row, claims: list[sqlite3.Row]) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str, str]] = []
    for field in ("observed_url", "normalized_observed_url"):
        canonical = _canonical_x_url(str(row[field] or ""))
        if canonical:
            candidates.append((canonical, "observed_url", "observed"))
    for claim in claims:
        canonical = _canonical_x_url(str(claim["normalized_claimed_url"] or claim["claimed_url"] or ""))
        if canonical:
            candidates.append((canonical, "url_claim", str(claim["provenance_quality"] or "inferred")))
    for matched in _X_URL_RE.findall(str(row["cleaned_text"] or "")):
        canonical = _canonical_x_url(matched)
        if canonical:
            candidates.append((canonical, "body", "inferred"))
    by_url: dict[str, dict[str, Any]] = {}
    source_rank = {"observed_url": 3, "url_claim": 2, "body": 1}
    quality_rank = {"observed": 3, "inferred": 2, "ambiguous": 1}
    for url, source, quality in candidates:
        kind, status_id, handle = _classify_x_url(url)
        quality = quality if quality in quality_rank else "inferred"
        current = by_url.get(url)
        candidate = {
            "url": url,
            "kind": kind,
            "status_id": status_id,
            "handle_hint": handle,
            "discovery_source": source,
            "provenance_quality": quality,
        }
        if current is None or (
            source_rank[source], quality_rank[quality]
        ) > (
            source_rank[str(current["discovery_source"])],
            quality_rank[str(current["provenance_quality"])],
        ):
            by_url[url] = candidate
    return [by_url[url] for url in sorted(by_url)]


def _text_summary(row: sqlite3.Row) -> dict[str, Any]:
    text = row["cleaned_text"]
    source = str(row["cleaned_text_source"] or "absent")
    stored_hash = str(row["text_hash"] or "").lower()
    valid_stored_hash = stored_hash if re.fullmatch(r"[0-9a-f]{64}", stored_hash) else None
    if text is None:
        completeness = "absent" if row["snapshot_id"] is None else "unknown"
        char_count = 0
        text_hash = valid_stored_hash
    else:
        completeness = "complete" if source != "legacy-fallback" else "unknown"
        value = str(text)
        char_count = len(value)
        text_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
        if completeness == "complete" and valid_stored_hash and valid_stored_hash != text_hash:
            raise XObservationCompatibilityError("BMD snapshot text hash is incompatible")
    return {
        "sha256": text_hash,
        "char_count": char_count,
        "completeness": completeness,
        "authority_source": source if source in {"capture", "chunks-hash-verified", "sidecar-hash-verified", "legacy-fallback"} else "absent",
        "body_included": False,
        "body_owner": "browser_memory_daemon",
    }


def _title_summary(title: str | None) -> dict[str, Any]:
    value = str(title or "")
    return {
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None,
        "char_count": len(value),
        "body_included": False,
    }


def _iso_datetime(value: object) -> str:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise XObservationCompatibilityError("BMD observation timestamp is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _record(row: sqlite3.Row, discovered: list[dict[str, Any]]) -> dict[str, Any]:
    observed = _canonical_x_url(str(row["normalized_observed_url"] or ""))
    observed_surface = _classify_x_url(observed)[0] if observed else "non_x_container"
    hints: dict[tuple[str, str], dict[str, str]] = {}
    for item in discovered:
        handle = item["handle_hint"]
        if handle and _HANDLE_RE.fullmatch(str(handle)):
            key = (str(handle).lower(), str(item["url"]))
            hints[key] = {
                "kind": "handle",
                "value": str(handle),
                "quality": "alias_only",
                "source_url": str(item["url"]),
            }
    return {
        "observation_id": str(row["observation_id"]),
        "ingest_sequence": int(row["ingest_sequence"]),
        "navigation_id": row["navigation_id"],
        "visit_id": row["visit_id"],
        "document_id": str(row["document_id"]),
        "snapshot_id": row["snapshot_id"],
        "captured_at": _iso_datetime(row["captured_at"]),
        "observed_url": str(row["observed_url"]),
        "normalized_observed_url": str(row["normalized_observed_url"]),
        "observed_surface": observed_surface,
        "discovered_x_urls": discovered,
        "capture": {
            "reason": str(row["capture_reason"]),
            "method": str(row["capture_method"]),
            "extraction_version": str(row["extraction_version"]),
            "disposition": str(row["disposition"]),
            "provenance_quality": str(row["provenance_quality"]),
            "source_id": str(row["source_id"]),
            "media_relationship_count": int(row["media_relationship_count"]),
        },
        "text": _text_summary(row),
        "title": _title_summary(row["title"]),
        "collection_evidence": {
            "classification": "none",
            "kind": None,
            "proof_type": None,
            "source_surface": observed_surface if observed_surface != "non_x_container" else None,
        },
        "identity_hints": [hints[key] for key in sorted(hints)],
    }


_SELECT_ROWS = """
SELECT
  seq.sequence AS ingest_sequence,
  obs.id AS observation_id,
  obs.navigation_id,
  obs.visit_id,
  obs.document_id,
  obs.snapshot_id,
  obs.observed_url,
  obs.normalized_observed_url,
  obs.title,
  obs.captured_at,
  obs.capture_reason,
  obs.capture_method,
  obs.extraction_version,
  obs.disposition,
  obs.provenance_quality,
  src.id AS source_id,
  snap.text_hash,
  snap.cleaned_text,
  snap.cleaned_text_source,
  (
    SELECT COUNT(*) FROM media_artifact_observations mao
    WHERE mao.observation_id = obs.id
  ) AS media_relationship_count
FROM observation_ingest_sequences seq
JOIN capture_observations obs ON obs.id = seq.observation_id
LEFT JOIN visits visit ON visit.id = obs.visit_id
LEFT JOIN sources src ON src.id = COALESCE(visit.source_id, 'chrome-extension')
LEFT JOIN snapshots snap ON snap.id = obs.snapshot_id
WHERE (seq.sequence > ? OR (seq.sequence = ? AND obs.id > ?))
ORDER BY seq.sequence, obs.id
LIMIT ?
"""


def export_x_observations(
    database: str | Path,
    *,
    cursor: str | None = None,
    limit: int = 100,
    now: Callable[[], datetime] | None = None,
    build_revision: str | None = None,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    position_sequence, position_id = decode_cursor(cursor)
    records: list[dict[str, Any]] = []
    holds = {"legacy_without_observation_identity": 0, "without_discovered_x_url": 0}
    exhausted = False
    scanned_any = False
    conn = _open_query_only(Path(database))
    try:
        schema_version = _validate_schema(conn)
        missing_sequence = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM capture_observations obs
                LEFT JOIN observation_ingest_sequences seq ON seq.observation_id = obs.id
                WHERE seq.observation_id IS NULL
                """
            ).fetchone()[0]
        )
        if missing_sequence:
            raise XObservationCompatibilityError("BMD observations are missing stable ingest sequence")
        batch_size = min(MAX_LIMIT, max(100, limit * 2))
        while len(records) < limit:
            rows = conn.execute(
                _SELECT_ROWS,
                (position_sequence, position_sequence, position_id, batch_size),
            ).fetchall()
            if not rows:
                exhausted = True
                break
            for row in rows:
                scanned_any = True
                position_sequence = int(row["ingest_sequence"])
                position_id = str(row["observation_id"])
                claims = conn.execute(
                    """
                    SELECT claimed_url, normalized_claimed_url, provenance_quality
                    FROM document_url_claims
                    WHERE observation_id = ? OR (observation_id IS NULL AND document_id = ?)
                    ORDER BY normalized_claimed_url, id
                    """,
                    (position_id, str(row["document_id"])),
                ).fetchall()
                discovered = _discovered_urls(row, claims)
                if not discovered:
                    holds["without_discovered_x_url"] += 1
                    continue
                records.append(_record(row, discovered))
                if len(records) == limit:
                    break
            if len(records) == limit:
                exhausted = conn.execute(
                    """
                    SELECT NOT EXISTS(
                      SELECT 1 FROM observation_ingest_sequences seq
                      JOIN capture_observations obs ON obs.id = seq.observation_id
                      WHERE seq.sequence > ? OR (seq.sequence = ? AND obs.id > ?)
                    )
                    """,
                    (position_sequence, position_sequence, position_id),
                ).fetchone()[0] == 1
                break
            if len(rows) < batch_size:
                exhausted = True
                break
        generated = (now or (lambda: datetime.now(UTC)))().astimezone(UTC)
        next_cursor = encode_cursor(position_sequence, position_id) if scanned_any else cursor
        return {
            "contract": CONTRACT,
            "contract_version": CONTRACT_VERSION,
            "producer": {
                "name": "browser-memory-daemon",
                "version": __version__,
                "schema_version": schema_version,
                "build_revision": build_revision,
            },
            "generated_at": generated.isoformat().replace("+00:00", "Z"),
            "order": {
                "direction": "ascending",
                "fields": ["ingest_sequence", "observation_id"],
                "boundary": "exclusive",
            },
            "records": records,
            "next_cursor": next_cursor,
            "exhausted": bool(exhausted),
            "holds": holds,
        }
    finally:
        conn.close()
