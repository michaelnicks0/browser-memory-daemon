from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

MEDIA_TYPES = frozenset({"image", "video"})
MEDIA_ROLES = frozenset({"content", "poster", "source"})

# Statuses accepted from capture/upload callers. Internal storage recovery adds
# `purging` and `missing`; those states are never caller-selectable.
MEDIA_CAPTURE_STATUSES = frozenset(
    {
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
)
MEDIA_ARTIFACT_STATUSES = MEDIA_CAPTURE_STATUSES | frozenset({"purging", "missing"})
MEDIA_TASK_STATUSES = frozenset({"pending", "leased", "retrying", "succeeded", "failed", "skipped"})

PERMANENT_SKIP_REASONS = frozenset(
    {
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
        "fetch-blocked-private-address",
        "fetch-blocked-private-host",
        "fetch-blocked-reserved-address",
        "fetch-blocked-url-scheme",
        "fetch-redirect-loop",
        "fetch-redirect-missing-location",
        "fetch-too-many-redirects",
    }
)

# The matrix documents legal steady-state movement. Historical normalization and
# explicit operator requeue may use force-reset paths that are intentionally
# modeled separately from ordinary worker progression.
MEDIA_TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"pending", "leased", "retrying", "succeeded", "failed", "skipped"}),
    "leased": frozenset({"pending", "leased", "retrying", "succeeded", "failed", "skipped"}),
    "retrying": frozenset({"pending", "leased", "retrying", "succeeded", "failed", "skipped"}),
    "failed": frozenset({"pending", "retrying", "failed", "skipped"}),
    "succeeded": frozenset({"succeeded"}),
    "skipped": frozenset({"skipped"}),
}

MEDIA_ARTIFACT_TRANSITIONS: dict[str, frozenset[str]] = {
    "referenced": frozenset({"referenced", "metadata-only", "queued", "fetching", "uploading", "stored", "retrying", "failed", "skipped", "expired", "purged"}),
    "metadata-only": frozenset({"metadata-only", "queued", "fetching", "uploading", "stored", "retrying", "failed", "skipped", "expired", "purged"}),
    "queued": frozenset({"queued", "fetching", "uploading", "stored", "retrying", "failed", "skipped", "expired"}),
    "fetching": frozenset({"fetching", "fetched", "stored", "retrying", "failed", "skipped", "expired", "referenced"}),
    "fetched": frozenset({"fetched", "stored", "retrying", "failed", "skipped"}),
    "uploading": frozenset({"uploading", "stored", "retrying", "failed", "skipped", "referenced"}),
    "stored": frozenset({"stored", "purging", "missing"}),
    "retrying": frozenset({"retrying", "queued", "fetching", "uploading", "stored", "failed", "skipped", "expired", "referenced"}),
    "failed": frozenset({"failed", "retrying", "referenced", "skipped", "expired"}),
    "skipped": frozenset({"skipped", "referenced", "queued", "fetching", "stored"}),
    "expired": frozenset({"expired", "referenced", "retrying"}),
    "purging": frozenset({"purging", "purged"}),
    "purged": frozenset({"purged", "referenced", "queued", "fetching", "uploading", "stored"}),
    "missing": frozenset({"missing", "stored", "purging", "purged"}),
}


def normalize_capture_status(value: Any, *, default: str = "metadata-only") -> str:
    status = str(value or "").lower().strip().replace("_", "-")
    return status if status in MEDIA_CAPTURE_STATUSES else default


def normalize_task_status(value: Any, *, default: str = "pending") -> str:
    status = str(value or "").lower().strip().replace("_", "-")
    return status if status in MEDIA_TASK_STATUSES else default


def media_task_transition_allowed(current: str, target: str, *, force_reset: bool = False) -> bool:
    current_status = str(current or "").strip().lower()
    target_status = str(target or "").strip().lower()
    if current_status not in MEDIA_TASK_STATUSES or target_status not in MEDIA_TASK_STATUSES:
        return False
    if force_reset and target_status == "pending":
        return True
    return target_status in MEDIA_TASK_TRANSITIONS[current_status]


def media_artifact_transition_allowed(current: str, target: str) -> bool:
    current_status = str(current or "").strip().lower()
    target_status = str(target or "").strip().lower()
    if current_status not in MEDIA_ARTIFACT_STATUSES or target_status not in MEDIA_ARTIFACT_STATUSES:
        return False
    return target_status in MEDIA_ARTIFACT_TRANSITIONS[current_status]


def media_capture_status_for_fetch_reason(reason: str, *, source_url: str = "", media_type: str = "") -> str:
    normalized = str(reason or "").strip()
    lower = normalized.lower()
    source_scheme = urlsplit(source_url or "").scheme.lower()
    if normalized in PERMANENT_SKIP_REASONS:
        if lower == "non-media-content-type" and str(media_type or "").lower() == "video":
            return "referenced"
        return "skipped"
    if source_scheme == "data" and lower in {"failed to fetch", "invalid-data-url", "invalid-data-url-payload"}:
        return "skipped"
    if lower.startswith(("fetch-status-401", "fetch-status-403", "fetch-status-404", "fetch-status-410")):
        return "expired"
    if lower.startswith(("fetch-status-429", "fetch-timeout", "fetch-error-")):
        return "retrying"
    if lower.startswith("hls-"):
        return "referenced"
    if lower in {"empty-media-response", "failed to fetch"}:
        return "retrying"
    return "failed"
