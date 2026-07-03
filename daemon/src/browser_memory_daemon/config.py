from __future__ import annotations

from dataclasses import dataclass
import os
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
    state_root: Path = Path.home() / ".local" / "state" / APP_NAME
    max_payload_bytes: int = 2_000_000
    max_media_payload_bytes: int = 40_000_000
    max_media_artifact_bytes: int = 250_000_000
    max_media_bytes_per_snapshot: int = 1_000_000_000
    max_media_bytes_per_domain: int = 10_000_000_000
    max_media_cache_bytes: int = 100_000_000_000
    media_mime_allowlist: tuple[str, ...] = ("image/", "video/mp4", "video/webm", "video/ogg", "video/quicktime", "video/mp2t", "audio/mp4", "audio/aac", "audio/mpeg", "audio/ogg", "audio/webm")
    media_min_priority_to_store: int = 0
    max_media_artifacts_per_capture: int = 50
    max_media_fetches_per_capture: int = 12
    max_media_fetches_per_call: int = 100
    media_fetch_timeout_seconds: float = 12.0
    media_fetch_on_capture: bool = False
    raw_html_enabled: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_root / "browser-memory.sqlite3"

    @property
    def clean_text_root(self) -> Path:
        return self.blob_root / "clean-text"

    @property
    def raw_html_root(self) -> Path:
        return self.blob_root / "raw-html"

    @property
    def media_root(self) -> Path:
        return self.blob_root / "media"

    @property
    def audit_log_path(self) -> Path:
        return self.state_root / "audit.jsonl"

    def ensure_dirs(self) -> None:
        for path in [self.config_root, self.data_root, self.blob_root, self.state_root, self.clean_text_root, self.media_root]:
            path.mkdir(parents=True, exist_ok=True)
        if self.raw_html_enabled:
            self.raw_html_root.mkdir(parents=True, exist_ok=True)


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
    test_mode: bool = False,
) -> RuntimeConfig:
    env_root = os.environ.get("BMD_RUNTIME_ROOT")
    env_blob_root = os.environ.get("BMD_BLOB_ROOT")
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
        data_root = Path.home() / ".local" / "share" / APP_NAME
        config_root = Path.home() / ".config" / APP_NAME
        state_root = Path.home() / ".local" / "state" / APP_NAME
    blob_root_value = blob_root if blob_root is not None else env_blob_root
    selected_blob_root = Path(blob_root_value).expanduser() if blob_root_value else data_root / "blobs"
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
        state_root=state_root,
        max_payload_bytes=_env_int("BMD_MAX_PAYLOAD_BYTES", RuntimeConfig.max_payload_bytes),
        max_media_payload_bytes=_env_int("BMD_MAX_MEDIA_PAYLOAD_BYTES", RuntimeConfig.max_media_payload_bytes),
        max_media_artifact_bytes=_env_int("BMD_MAX_MEDIA_ARTIFACT_BYTES", RuntimeConfig.max_media_artifact_bytes),
        max_media_bytes_per_snapshot=_env_int("BMD_MAX_MEDIA_BYTES_PER_SNAPSHOT", RuntimeConfig.max_media_bytes_per_snapshot),
        max_media_bytes_per_domain=_env_int("BMD_MAX_MEDIA_BYTES_PER_DOMAIN", RuntimeConfig.max_media_bytes_per_domain),
        max_media_cache_bytes=_env_int("BMD_MAX_MEDIA_CACHE_BYTES", RuntimeConfig.max_media_cache_bytes),
        media_mime_allowlist=_env_tuple("BMD_MEDIA_MIME_ALLOWLIST", RuntimeConfig.media_mime_allowlist),
        media_min_priority_to_store=_env_int("BMD_MEDIA_MIN_PRIORITY_TO_STORE", RuntimeConfig.media_min_priority_to_store),
        max_media_artifacts_per_capture=_env_int("BMD_MAX_MEDIA_ARTIFACTS_PER_CAPTURE", RuntimeConfig.max_media_artifacts_per_capture),
        max_media_fetches_per_capture=_env_int("BMD_MAX_MEDIA_FETCHES_PER_CAPTURE", RuntimeConfig.max_media_fetches_per_capture),
        max_media_fetches_per_call=_env_int("BMD_MAX_MEDIA_FETCHES_PER_CALL", RuntimeConfig.max_media_fetches_per_call),
        media_fetch_timeout_seconds=_env_float("BMD_MEDIA_FETCH_TIMEOUT_SECONDS", RuntimeConfig.media_fetch_timeout_seconds),
        media_fetch_on_capture=_env_bool("BMD_MEDIA_FETCH_ON_CAPTURE", RuntimeConfig.media_fetch_on_capture),
    )
    cfg.ensure_dirs()
    return cfg
