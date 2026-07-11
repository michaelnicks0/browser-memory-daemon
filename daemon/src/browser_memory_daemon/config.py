from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .policy import DEFAULT_POLICY_MODE, normalize_policy_mode

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
APP_NAME = "browser-memory-daemon"


@dataclass(frozen=True)
class RuntimeConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    api_token: str = ""
    policy_mode: str = DEFAULT_POLICY_MODE
    config_root: Path = Path.home() / ".config" / APP_NAME
    data_root: Path = Path.home() / ".local" / "share" / APP_NAME
    blob_root: Path = Path.home() / ".local" / "share" / APP_NAME / "blobs"
    derivative_root: Path | None = None
    media_root_path: Path | None = None
    media_spool_root: Path | None = None
    state_root: Path = Path.home() / ".local" / "state" / APP_NAME
    max_payload_bytes: int = 2_000_000
    max_media_payload_bytes: int = 40_000_000
    max_media_artifact_bytes: int = 250_000_000
    max_media_inflight_bytes: int = 500_000_000
    max_media_concurrent_requests: int = 4
    max_media_bytes_per_snapshot: int = 1_000_000_000
    max_media_bytes_per_domain: int = 10_000_000_000
    max_media_cache_bytes: int = 100_000_000_000
    media_mime_allowlist: tuple[str, ...] = ("image/", "video/mp4", "video/webm", "video/ogg", "video/quicktime", "video/mp2t", "audio/mp4", "audio/aac", "audio/mpeg", "audio/ogg", "audio/webm")
    media_min_priority_to_store: int = 0
    max_media_artifacts_per_capture: int = 50
    max_media_fetches_per_capture: int = 12
    max_media_fetches_per_call: int = 100
    media_fetch_timeout_seconds: float = 12.0
    media_public_fetch_allow_private_hosts: tuple[str, ...] = ()
    media_public_fetch_max_redirects: int = 5
    media_hls_max_requests: int = 64
    media_hls_max_depth: int = 3
    media_hls_playlist_max_bytes: int = 1_000_000
    media_fetch_on_capture: bool = False
    raw_html_enabled: bool = False
    require_blob_root_mount: bool = False
    require_media_root_mount: bool = False
    media_root_identity: str = ""
    max_media_spool_bytes: int = 0

    @property
    def db_path(self) -> Path:
        return self.data_root / "browser-memory.sqlite3"

    @property
    def clean_text_root(self) -> Path:
        return (self.derivative_root or self.blob_root) / "clean-text"

    @property
    def raw_html_root(self) -> Path:
        return (self.derivative_root or self.blob_root) / "raw-html"

    @property
    def media_root(self) -> Path:
        return self.media_root_path or self.blob_root / "media"

    @property
    def media_spool_enabled(self) -> bool:
        return self.media_spool_root is not None and self.max_media_spool_bytes > 0

    @property
    def audit_log_path(self) -> Path:
        return self.state_root / "audit.jsonl"

    def ensure_dirs(self) -> None:
        for path in [self.config_root, self.data_root, self.state_root]:
            path.mkdir(parents=True, exist_ok=True)
        if self.media_root_identity and not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", self.media_root_identity):
            raise ValueError("BMD_MEDIA_ROOT_IDENTITY must match [A-Za-z0-9._-]{1,128}")
        if self.max_media_spool_bytes < 0:
            raise RuntimeError("BMD_MAX_MEDIA_SPOOL_BYTES must be non-negative")
        if self.max_media_inflight_bytes <= 0:
            raise ValueError("BMD_MAX_MEDIA_INFLIGHT_BYTES must be positive")
        if self.max_media_concurrent_requests <= 0:
            raise ValueError("BMD_MAX_MEDIA_CONCURRENT_REQUESTS must be positive")
        if self.max_media_artifact_bytes > self.max_media_inflight_bytes:
            raise ValueError("BMD_MAX_MEDIA_INFLIGHT_BYTES must allow at least one maximum-size media artifact")
        if (self.media_spool_root is None) != (self.max_media_spool_bytes == 0):
            raise ValueError("BMD_MEDIA_SPOOL_ROOT and positive BMD_MAX_MEDIA_SPOOL_BYTES must be configured together")
        if self.media_spool_root is not None:
            spool = self.media_spool_root.expanduser().resolve(strict=False)
            data = self.data_root.expanduser().resolve(strict=False)
            media = self.media_root.expanduser().resolve(strict=False)
            if not spool.is_relative_to(data):
                raise ValueError("BMD_MEDIA_SPOOL_ROOT must be contained under the local BMD runtime data root")
            if spool == media or spool.is_relative_to(media) or media.is_relative_to(spool):
                raise ValueError("BMD_MEDIA_SPOOL_ROOT must not overlap BMD_MEDIA_ROOT")
        # Blob roots are external/cache boundaries and are created by the
        # operation that actually writes them, never as a prerequisite for
        # local SQLite startup or text capture.


def has_non_root_mount_ancestor(path: Path) -> bool:
    resolved = Path(path).expanduser().resolve(strict=False)
    for candidate in (resolved, *resolved.parents):
        if candidate.parent == candidate:
            continue
        try:
            if candidate.exists() and candidate.is_mount():
                return True
        except OSError:
            continue
    return False


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


def load_config(
    *,
    host: str | None = None,
    port: int | None = None,
    token: str | None = None,
    policy_mode: str | None = None,
    runtime_root: str | Path | None = None,
    blob_root: str | Path | None = None,
    derivative_root: str | Path | None = None,
    media_root: str | Path | None = None,
    media_spool_root: str | Path | None = None,
    test_mode: bool = False,
) -> RuntimeConfig:
    env_root = os.environ.get("BMD_RUNTIME_ROOT")
    env_blob_root = os.environ.get("BMD_BLOB_ROOT")
    env_derivative_root = os.environ.get("BMD_DERIVATIVE_ROOT")
    env_media_root = os.environ.get("BMD_MEDIA_ROOT")
    env_media_spool_root = os.environ.get("BMD_MEDIA_SPOOL_ROOT")
    selected_root = Path(runtime_root or env_root).expanduser() if (runtime_root or env_root) else None
    api_token = token if token is not None else os.environ.get("BMD_API_TOKEN", "")
    if test_mode and not api_token:
        api_token = "test-token"
    if not api_token:
        raise ValueError("BMD_API_TOKEN is required unless test_mode=True")
    if selected_root:
        data_root = selected_root
        config_root = selected_root / "config"
        state_root = selected_root / "state"
    else:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")).expanduser()
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()
        state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")).expanduser()
        data_root = data_home / APP_NAME
        config_root = config_home / APP_NAME
        state_root = state_home / APP_NAME
    blob_root_value = blob_root if blob_root is not None else env_blob_root
    selected_blob_root = Path(blob_root_value).expanduser() if blob_root_value else data_root / "blobs"
    derivative_root_value = derivative_root if derivative_root is not None else env_derivative_root
    selected_derivative_root = Path(derivative_root_value).expanduser() if derivative_root_value else selected_blob_root
    media_root_value = media_root if media_root is not None else env_media_root
    selected_media_root = Path(media_root_value).expanduser() if media_root_value else None
    media_spool_root_value = media_spool_root if media_spool_root is not None else env_media_spool_root
    selected_media_spool_root = Path(media_spool_root_value).expanduser() if media_spool_root_value else None
    selected_port = port if port is not None else int(os.environ.get("BMD_PORT", DEFAULT_PORT))
    selected_policy_mode = normalize_policy_mode(policy_mode or os.environ.get("BMD_POLICY_MODE") or DEFAULT_POLICY_MODE)
    cfg = RuntimeConfig(
        host=host or os.environ.get("BMD_HOST", DEFAULT_HOST),
        port=int(selected_port),
        api_token=api_token,
        policy_mode=selected_policy_mode,
        config_root=config_root,
        data_root=data_root,
        blob_root=selected_blob_root,
        derivative_root=selected_derivative_root,
        media_root_path=selected_media_root,
        media_spool_root=selected_media_spool_root,
        state_root=state_root,
        max_payload_bytes=_env_int("BMD_MAX_PAYLOAD_BYTES", RuntimeConfig.max_payload_bytes),
        max_media_payload_bytes=_env_int("BMD_MAX_MEDIA_PAYLOAD_BYTES", RuntimeConfig.max_media_payload_bytes),
        max_media_artifact_bytes=_env_int("BMD_MAX_MEDIA_ARTIFACT_BYTES", RuntimeConfig.max_media_artifact_bytes),
        max_media_inflight_bytes=_env_int("BMD_MAX_MEDIA_INFLIGHT_BYTES", RuntimeConfig.max_media_inflight_bytes),
        max_media_concurrent_requests=_env_int(
            "BMD_MAX_MEDIA_CONCURRENT_REQUESTS", RuntimeConfig.max_media_concurrent_requests
        ),
        max_media_bytes_per_snapshot=_env_int("BMD_MAX_MEDIA_BYTES_PER_SNAPSHOT", RuntimeConfig.max_media_bytes_per_snapshot),
        max_media_bytes_per_domain=_env_int("BMD_MAX_MEDIA_BYTES_PER_DOMAIN", RuntimeConfig.max_media_bytes_per_domain),
        max_media_cache_bytes=_env_int("BMD_MAX_MEDIA_CACHE_BYTES", RuntimeConfig.max_media_cache_bytes),
        media_mime_allowlist=_env_tuple("BMD_MEDIA_MIME_ALLOWLIST", RuntimeConfig.media_mime_allowlist),
        media_min_priority_to_store=_env_int("BMD_MEDIA_MIN_PRIORITY_TO_STORE", RuntimeConfig.media_min_priority_to_store),
        max_media_artifacts_per_capture=_env_int("BMD_MAX_MEDIA_ARTIFACTS_PER_CAPTURE", RuntimeConfig.max_media_artifacts_per_capture),
        max_media_fetches_per_capture=_env_int("BMD_MAX_MEDIA_FETCHES_PER_CAPTURE", RuntimeConfig.max_media_fetches_per_capture),
        max_media_fetches_per_call=_env_int("BMD_MAX_MEDIA_FETCHES_PER_CALL", RuntimeConfig.max_media_fetches_per_call),
        media_fetch_timeout_seconds=_env_float("BMD_MEDIA_FETCH_TIMEOUT_SECONDS", RuntimeConfig.media_fetch_timeout_seconds),
        media_public_fetch_allow_private_hosts=_env_tuple("BMD_MEDIA_PUBLIC_FETCH_ALLOW_PRIVATE_HOSTS", RuntimeConfig.media_public_fetch_allow_private_hosts),
        media_public_fetch_max_redirects=_env_int("BMD_MEDIA_PUBLIC_FETCH_MAX_REDIRECTS", RuntimeConfig.media_public_fetch_max_redirects),
        media_hls_max_requests=_env_int("BMD_MEDIA_HLS_MAX_REQUESTS", RuntimeConfig.media_hls_max_requests),
        media_hls_max_depth=_env_int("BMD_MEDIA_HLS_MAX_DEPTH", RuntimeConfig.media_hls_max_depth),
        media_hls_playlist_max_bytes=_env_int("BMD_MEDIA_HLS_PLAYLIST_MAX_BYTES", RuntimeConfig.media_hls_playlist_max_bytes),
        media_fetch_on_capture=_env_bool("BMD_MEDIA_FETCH_ON_CAPTURE", RuntimeConfig.media_fetch_on_capture),
        require_blob_root_mount=_env_bool("BMD_REQUIRE_BLOB_ROOT_MOUNT", RuntimeConfig.require_blob_root_mount),
        require_media_root_mount=_env_bool("BMD_REQUIRE_MEDIA_ROOT_MOUNT", RuntimeConfig.require_media_root_mount),
        media_root_identity=str(os.environ.get("BMD_MEDIA_ROOT_IDENTITY", "")).strip(),
        max_media_spool_bytes=_env_int("BMD_MAX_MEDIA_SPOOL_BYTES", RuntimeConfig.max_media_spool_bytes),
    )
    cfg.ensure_dirs()
    return cfg
