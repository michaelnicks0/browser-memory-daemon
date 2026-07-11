from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, BinaryIO, cast

from . import __version__
from .api_errors import NotFoundError, ResourceUnavailableError
from .config import RuntimeConfig
from .db import audit, connect, init_db
from .forget import forget
from .ingest import ingest_capture
from .lifecycle import record_visit_event
from .media import (
    fetch_pending_media_artifacts,
    media_artifact,
    media_queue_status,
    purge_media_cache,
    store_media_artifact,
    store_media_blob_stream,
)
from .media_resources import MediaResourceUnavailable, media_resource_budget
from .media_storage import media_blob_store_and_locator, media_root_readiness
from .models import CapturePayload
from .ops import doctor, document_detail, recent_captures, snapshot_detail, timeline
from .policy import POLICY_MODE_ALL, evaluate_capture
from .policy_store import create_policy_rule, delete_policy_rule, evaluate_policy_rules, list_policy_rules
from .search import search_memory


@dataclass(frozen=True)
class MediaDownload:
    stream: BinaryIO
    content_length: int
    content_type: str
    filename: str


class MemoryApplication:
    """Request-independent Browser Memory use cases and transaction boundaries."""

    def __init__(self, config: RuntimeConfig, *, database_ready: bool = False) -> None:
        self.config = config
        self._database_ready = database_ready
        self._database_lock = threading.Lock()

    def ensure_database(self) -> None:
        if self._database_ready and self.config.db_path.exists():
            return
        with self._database_lock:
            if self._database_ready and self.config.db_path.exists():
                return
            init_db(self.config)
            self._database_ready = True

    def health(self) -> dict[str, object]:
        readiness = media_root_readiness(self.config)
        return {
            "ok": True,
            "version": __version__,
            "storage_root": str(self.config.data_root),
            "blob_root": str(self.config.blob_root),
            "derivative_root": str(self.config.clean_text_root.parent),
            "media_root": str(self.config.media_root),
            "media_spool_enabled": self.config.media_spool_enabled,
            "media_root_status": readiness.status,
            "capture_enabled": True,
            "policy_mode": self.config.policy_mode,
        }

    def ready(self) -> dict[str, object]:
        self.ensure_database()
        return {"ready": True, "db_path": str(self.config.db_path)}

    def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            results = cast(list[dict[str, Any]], search_memory(conn, query, limit=limit))
            audit(conn, "search", {"query_len": len(query), "result_count": len(results)})
            conn.commit()
        return results

    def recent(self, *, limit: int | str | None = "25") -> list[dict[str, Any]]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            results = cast(list[dict[str, Any]], recent_captures(conn, limit=limit))
            audit(conn, "recent", {"result_count": len(results)})
            conn.commit()
        return results

    def timeline(
        self,
        *,
        day: str | None,
        after: str | None,
        before: str | None,
        limit: int | str | None = "100",
    ) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], timeline(conn, day=day, after=after, before=before, limit=limit))
            audit(conn, "timeline", {"result_count": result["count"]})
            conn.commit()
        return result

    def document_detail(self, document_id: str) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], document_detail(conn, self.config, document_id))
            audit(conn, "document.detail", {"document_id": document_id})
            conn.commit()
        return result

    def snapshot_detail(self, snapshot_id: str) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], snapshot_detail(conn, self.config, snapshot_id))
            audit(conn, "snapshot.detail", {"snapshot_id": snapshot_id})
            conn.commit()
        return result

    def media_queue_status(self, *, limit: int) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], media_queue_status(conn, self.config, limit=limit))
            audit(conn, "media.queue_status", {})
            conn.commit()
        return result

    @contextmanager
    def media_download(self, artifact_id: str) -> Iterator[MediaDownload]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            artifact = cast(dict[str, Any], media_artifact(conn, self.config, artifact_id))
            audit(conn, "media.detail", {"artifact_id": artifact_id})
            conn.commit()
        artifact.pop("resolved_file_path", None)
        store, locator, tier_status = media_blob_store_and_locator(self.config, artifact)
        resolution = store.resolve(locator, require_file=True) if store is not None else None
        if not artifact.get("has_file") or resolution is None or resolution.path is None:
            raise NotFoundError(
                "media artifact file not stored",
                extra={
                    "storage_status": tier_status,
                    "artifact": {
                        key: value
                        for key, value in artifact.items()
                        if key not in {"file_path", "blob_locator", "spool_locator"}
                    },
                },
            )
        assert store is not None
        assert locator is not None
        content_length = resolution.path.stat().st_size
        try:
            with media_resource_budget(self.config).acquire(
                byte_count=content_length,
                request_count=1,
                timeout=0,
            ):
                with store.open(locator) as stream:
                    yield MediaDownload(
                        stream=stream,
                        content_length=content_length,
                        content_type=artifact.get("mime_type") or "application/octet-stream",
                        filename=resolution.path.name,
                    )
        except MediaResourceUnavailable as exc:
            raise ResourceUnavailableError(str(exc)) from exc

    def doctor(self, *, storage_census: bool) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], doctor(self.config, conn, storage_census=storage_census))
            audit(conn, "doctor", {"ok": result["ok"]})
            conn.commit()
        return result

    def list_policy_rules(self) -> list[dict[str, Any]]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            return cast(list[dict[str, Any]], list_policy_rules(conn))

    def evaluate_policy(self, url: str) -> dict[str, object]:
        static_decision = evaluate_capture(url, policy_mode=self.config.policy_mode)
        decision = static_decision
        if static_decision.allowed:
            self.ensure_database()
            with connect(self.config.db_path) as conn:
                rules_decision = evaluate_policy_rules(conn, url)
            if not rules_decision.allowed:
                decision = rules_decision
        return {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "privacy_class": decision.privacy_class,
            "policy_mode": self.config.policy_mode,
            "static_reason": static_decision.reason,
        }

    def store_media_blob(
        self,
        artifact_id: str,
        stream: Any,
        *,
        headers: Mapping[str, str],
        content_length: int,
    ) -> dict[str, Any]:
        self.ensure_database()
        try:
            with media_resource_budget(self.config).acquire(
                byte_count=content_length,
                request_count=1,
                timeout=0,
            ):
                with connect(self.config.db_path) as conn:
                    result = cast(dict[str, Any], store_media_blob_stream(
                        conn,
                        self.config,
                        artifact_id,
                        stream,
                        headers=dict(headers),
                        content_length=content_length,
                    ))
                    audit(
                        conn,
                        "media.blob_put",
                        {
                            "artifact_id": artifact_id,
                            "stored": result["stored"],
                            "capture_status": result["capture_status"],
                            "byte_size": result["byte_size"],
                        },
                    )
                    conn.commit()
            return result
        except MediaResourceUnavailable as exc:
            raise ResourceUnavailableError(str(exc)) from exc

    def purge_media_cache(self, data: Mapping[str, Any]) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], purge_media_cache(conn, self.config, dict(data)))
            audit(
                conn,
                "media.cache_purge",
                {
                    "dry_run": result["dry_run"],
                    "rehydrate": result["rehydrate"],
                    "selected": result["selected"],
                    "purged": result["purged"],
                    "bytes": result["bytes"],
                },
            )
            conn.commit()
        return result

    def fetch_pending_media(self, data: Mapping[str, Any]) -> dict[str, Any]:
        snapshot_id = data.get("snapshot_id") or data.get("snapshotId")
        document_id = data.get("document_id") or data.get("documentId")
        domain = data.get("domain")
        limit = _coerce_limit(
            data.get("limit"),
            self.config.max_media_fetches_per_call,
            self.config.max_media_fetches_per_call,
        )
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], fetch_pending_media_artifacts(
                conn,
                self.config,
                snapshot_id=snapshot_id,
                document_id=document_id,
                domain=domain,
                limit=limit,
            ))
            audit(
                conn,
                "media.fetch_pending",
                {
                    "snapshot_id": snapshot_id,
                    "document_id": document_id,
                    "domain": domain,
                    "attempted": result["attempted"],
                    "stored": result["stored"],
                    "failed": result["failed"],
                    "skipped": result["skipped"],
                    "remaining": result["remaining"],
                    "background": False,
                },
            )
            conn.commit()
        return result

    def store_media_artifact(self, data: Mapping[str, Any]) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], store_media_artifact(conn, self.config, dict(data)))
            audit(
                conn,
                "media.stored" if result["stored"] else "media.metadata",
                {
                    "artifact_id": result["artifact_id"],
                    "document_id": result["document_id"],
                    "snapshot_id": result["snapshot_id"],
                    "media_type": result["media_type"],
                    "capture_status": result["capture_status"],
                    "byte_size": result["byte_size"],
                },
            )
            conn.commit()
        return result

    def record_visit_event(self, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(data)
        url = str(payload.get("url") or "")
        decision = evaluate_capture(
            url,
            is_incognito=bool(payload.get("is_incognito") or payload.get("incognito") or False),
            policy_mode=self.config.policy_mode,
        )
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            if decision.allowed:
                rules_decision = evaluate_policy_rules(conn, url)
                if not rules_decision.allowed:
                    decision = rules_decision
            if not decision.allowed:
                audit(conn, "visit_event.blocked", {"reason": decision.reason})
                conn.commit()
                return {"stored": False, "blocked": True, "reason": decision.reason}
            return cast(dict[str, Any], record_visit_event(conn, payload, policy_mode=self.config.policy_mode))

    def capture(self, data: Mapping[str, Any]) -> dict[str, Any]:
        payload_data = dict(data)
        url = str(payload_data.get("url") or "")
        decision = evaluate_capture(
            url,
            is_incognito=bool(payload_data.get("is_incognito") or payload_data.get("incognito") or False),
            policy_mode=self.config.policy_mode,
        )
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            if decision.allowed:
                rules_decision = evaluate_policy_rules(conn, url)
                if not rules_decision.allowed:
                    decision = rules_decision
            if not decision.allowed:
                audit(conn, "capture.blocked", {"reason": decision.reason})
                conn.commit()
                return {"stored": False, "blocked": True, "reason": decision.reason}
            payload = CapturePayload.from_dict(
                payload_data,
                allow_any_url=self.config.policy_mode == POLICY_MODE_ALL,
            )
            result = cast(dict[str, Any], ingest_capture(conn, self.config, payload))
        self._start_background_fetch(
            snapshot_id=result.get("snapshot_id", ""),
            media_ref_count=int(result.get("media_ref_count") or 0),
        )
        return result

    def forget(self, data: Mapping[str, Any]) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            result = cast(dict[str, Any], forget(conn, self.config, domain=data.get("domain"), url=data.get("url")))
            audit(
                conn,
                "forget",
                {
                    "receipt_id": result["receipt_id"],
                    "scope_keys": sorted(result["scope"].keys()),
                },
            )
            conn.commit()
        return result

    def create_policy_rule(self, *, rule_type: str, pattern: str, action: str) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            return cast(dict[str, Any], create_policy_rule(
                conn,
                rule_type=rule_type,
                pattern=pattern,
                action=action,
            ))

    def delete_policy_rule(self, rule_id: str) -> dict[str, Any]:
        self.ensure_database()
        with connect(self.config.db_path) as conn:
            return cast(dict[str, Any], delete_policy_rule(conn, rule_id))

    def _start_background_fetch(self, *, snapshot_id: str, media_ref_count: int) -> None:
        if not self.config.media_fetch_on_capture or not snapshot_id or media_ref_count <= 0:
            return
        limit = min(self.config.max_media_fetches_per_capture, media_ref_count)
        thread = threading.Thread(
            target=self._background_fetch,
            kwargs={"snapshot_id": snapshot_id, "limit": limit},
            daemon=True,
        )
        thread.start()

    def _background_fetch(self, *, snapshot_id: str, limit: int) -> None:
        try:
            self.ensure_database()
            with connect(self.config.db_path) as conn:
                result = fetch_pending_media_artifacts(
                    conn,
                    self.config,
                    snapshot_id=snapshot_id,
                    limit=limit,
                )
                audit(
                    conn,
                    "media.fetch_pending",
                    {
                        "snapshot_id": snapshot_id,
                        "attempted": result["attempted"],
                        "stored": result["stored"],
                        "failed": result["failed"],
                        "skipped": result["skipped"],
                        "remaining": result["remaining"],
                        "background": True,
                    },
                )
                conn.commit()
        except Exception:
            return


def _coerce_limit(value: int | str | None, default: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))
