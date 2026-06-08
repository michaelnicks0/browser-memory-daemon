from __future__ import annotations

from .config import RuntimeConfig
from .db import init_db


def migrate(config: RuntimeConfig) -> None:
    """Apply idempotent SQLite migrations for the current development phase."""
    init_db(config)
