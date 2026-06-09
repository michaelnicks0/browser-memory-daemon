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
    state_root: Path = Path.home() / ".local" / "state" / APP_NAME
    max_payload_bytes: int = 2_000_000
    max_media_payload_bytes: int = 40_000_000
    max_media_artifact_bytes: int = 25_000_000
    max_media_artifacts_per_capture: int = 50
    max_media_fetches_per_capture: int = 12
    max_media_fetches_per_call: int = 100
    media_fetch_timeout_seconds: float = 12.0
    media_fetch_on_capture: bool = True
    raw_html_enabled: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_root / "browser-memory.sqlite3"

    @property
    def clean_text_root(self) -> Path:
        return self.data_root / "blobs" / "clean-text"

    @property
    def raw_html_root(self) -> Path:
        return self.data_root / "blobs" / "raw-html"

    @property
    def media_root(self) -> Path:
        return self.data_root / "blobs" / "media"

    @property
    def audit_log_path(self) -> Path:
        return self.state_root / "audit.jsonl"

    def ensure_dirs(self) -> None:
        for path in [self.config_root, self.data_root, self.state_root, self.clean_text_root, self.media_root]:
            path.mkdir(parents=True, exist_ok=True)
        if self.raw_html_enabled:
            self.raw_html_root.mkdir(parents=True, exist_ok=True)


def load_config(
    *,
    host: str | None = None,
    port: int | None = None,
    token: str | None = None,
    policy_mode: str | None = None,
    runtime_root: str | Path | None = None,
    test_mode: bool = False,
) -> RuntimeConfig:
    env_root = os.environ.get("BMD_RUNTIME_ROOT")
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
    selected_port = port if port is not None else int(os.environ.get("BMD_PORT", DEFAULT_PORT))
    selected_policy_mode = normalize_policy_mode(policy_mode or os.environ.get("BMD_POLICY_MODE") or DEFAULT_POLICY_MODE)
    cfg = RuntimeConfig(
        host=host or os.environ.get("BMD_HOST", DEFAULT_HOST),
        port=int(selected_port),
        api_token=api_token,
        policy_mode=selected_policy_mode,
        config_root=config_root,
        data_root=data_root,
        state_root=state_root,
    )
    cfg.ensure_dirs()
    return cfg
