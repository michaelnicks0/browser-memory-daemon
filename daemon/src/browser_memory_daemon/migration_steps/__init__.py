from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from . import (
    v0001_baseline_schema,
    v0002_deduplicate_privacy_rules,
    v0003_seed_media_fetch_tasks,
)


@dataclass(frozen=True)
class MigrationStep:
    version: int
    name: str
    checksum: str
    sql: str = ""
    apply: Callable[[sqlite3.Connection], None] | None = None
    destructive: bool = False
    schema_fingerprint: str | None = None


def migration_checksum(version: int, name: str, payload: str) -> str:
    material = f"{version}:{name}\n{payload}".encode()
    return hashlib.sha256(material).hexdigest()


MIGRATIONS = (
    MigrationStep(
        version=1,
        name=v0001_baseline_schema.NAME,
        checksum=migration_checksum(1, v0001_baseline_schema.NAME, v0001_baseline_schema.SQL),
        sql=v0001_baseline_schema.SQL,
        schema_fingerprint=v0001_baseline_schema.SCHEMA_FINGERPRINT,
    ),
    MigrationStep(
        version=2,
        name=v0002_deduplicate_privacy_rules.NAME,
        checksum=migration_checksum(2, v0002_deduplicate_privacy_rules.NAME, v0002_deduplicate_privacy_rules.SQL),
        sql=v0002_deduplicate_privacy_rules.SQL,
    ),
    MigrationStep(
        version=3,
        name=v0003_seed_media_fetch_tasks.NAME,
        checksum=migration_checksum(3, v0003_seed_media_fetch_tasks.NAME, v0003_seed_media_fetch_tasks.CHECKSUM_PAYLOAD),
        apply=v0003_seed_media_fetch_tasks.apply,
    ),
)

__all__ = ["MIGRATIONS", "MigrationStep", "migration_checksum"]
