from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re


class StoragePathError(ValueError):
    """Raised when a configured or DB-supplied storage path escapes its root."""


MEDIA_ARTIFACT_ID_RE = re.compile(r"media_[A-Za-z0-9._-]{1,128}\Z")
SNAPSHOT_ID_RE = re.compile(r"snap_[0-9a-f]{32}\Z")
_SAFE_CHILD_RE = re.compile(r"[A-Za-z0-9._-]+\Z")


@dataclass(frozen=True)
class StoragePathResolution:
    path: Path | None
    status: str


_VALIDATION_ERROR = "invalid storage path"


def validate_media_artifact_id(value: str) -> str:
    artifact_id = str(value or "").strip()
    if not MEDIA_ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise ValueError("invalid media artifact id")
    return artifact_id


def validate_snapshot_id(value: str) -> str:
    snapshot_id = str(value or "").strip()
    if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise ValueError("invalid snapshot id")
    return snapshot_id


def storage_stem(namespace: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:32]
    return f"{namespace}_{digest}"


def _resolved_root(root: Path) -> Path:
    return root.expanduser().resolve(strict=False)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _check_child_part(part: str) -> str:
    text = str(part)
    if not text or text in {".", ".."}:
        raise StoragePathError(_VALIDATION_ERROR)
    if "/" in text or "\\" in text or "\x00" in text:
        raise StoragePathError(_VALIDATION_ERROR)
    if not _SAFE_CHILD_RE.fullmatch(text):
        raise StoragePathError(_VALIDATION_ERROR)
    return text


def contained_child_path(root: Path, *parts: str, create_root: bool = False) -> Path:
    if create_root:
        root.mkdir(parents=True, exist_ok=True)
    root_resolved = _resolved_root(root)
    child_parts = [_check_child_part(part) for part in parts]
    candidate = root_resolved.joinpath(*child_parts)
    resolved = candidate.resolve(strict=False)
    if not _is_relative_to(resolved, root_resolved):
        raise StoragePathError("storage path escapes configured root")
    return resolved


def resolve_db_path_under(root: Path, raw_path: str | Path | None, *, require_file: bool = False) -> StoragePathResolution:
    if raw_path is None or str(raw_path).strip() == "":
        return StoragePathResolution(None, "empty")
    raw = str(raw_path)
    if "\x00" in raw:
        return StoragePathResolution(None, "invalid")
    root_resolved = _resolved_root(root)
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root_resolved / candidate
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return StoragePathResolution(None, "invalid")
    if not _is_relative_to(resolved, root_resolved):
        return StoragePathResolution(None, "outside-root")
    if require_file:
        try:
            if not resolved.is_file():
                return StoragePathResolution(resolved, "missing")
        except OSError:
            return StoragePathResolution(None, "invalid")
    return StoragePathResolution(resolved, "ok")


def contained_existing_file(root: Path, raw_path: str | Path | None) -> StoragePathResolution:
    return resolve_db_path_under(root, raw_path, require_file=True)
