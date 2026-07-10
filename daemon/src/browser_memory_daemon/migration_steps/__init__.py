from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from . import (
    v0001_baseline_schema,
    v0002_deduplicate_privacy_rules,
    v0003_seed_media_fetch_tasks,
    v0004_capture_observations_and_url_claims,
    v0005_backfill_historical_observations,
    v0006_link_media_artifacts_to_observations,
    v0007_add_claimed_visit_identity,
    v0008_add_relative_blob_locators,
    v0009_add_sqlite_snapshot_text_authority,
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
    MigrationStep(
        version=4,
        name=v0004_capture_observations_and_url_claims.NAME,
        checksum=migration_checksum(
            4,
            v0004_capture_observations_and_url_claims.NAME,
            v0004_capture_observations_and_url_claims.SQL,
        ),
        sql=v0004_capture_observations_and_url_claims.SQL,
        schema_fingerprint=v0004_capture_observations_and_url_claims.SCHEMA_FINGERPRINT,
    ),
    MigrationStep(
        version=5,
        name=v0005_backfill_historical_observations.NAME,
        checksum=migration_checksum(
            5,
            v0005_backfill_historical_observations.NAME,
            v0005_backfill_historical_observations.CHECKSUM_PAYLOAD,
        ),
        apply=v0005_backfill_historical_observations.apply,
    ),
    MigrationStep(
        version=6,
        name=v0006_link_media_artifacts_to_observations.NAME,
        checksum=migration_checksum(
            6,
            v0006_link_media_artifacts_to_observations.NAME,
            v0006_link_media_artifacts_to_observations.CHECKSUM_PAYLOAD,
        ),
        sql=v0006_link_media_artifacts_to_observations.SQL,
        apply=v0006_link_media_artifacts_to_observations.apply,
        schema_fingerprint=v0006_link_media_artifacts_to_observations.SCHEMA_FINGERPRINT,
    ),
    MigrationStep(
        version=7,
        name=v0007_add_claimed_visit_identity.NAME,
        checksum=migration_checksum(
            7,
            v0007_add_claimed_visit_identity.NAME,
            v0007_add_claimed_visit_identity.CHECKSUM_PAYLOAD,
        ),
        sql=v0007_add_claimed_visit_identity.SQL,
        schema_fingerprint=v0007_add_claimed_visit_identity.SCHEMA_FINGERPRINT,
    ),
    MigrationStep(
        version=8,
        name=v0008_add_relative_blob_locators.NAME,
        checksum=migration_checksum(
            8,
            v0008_add_relative_blob_locators.NAME,
            v0008_add_relative_blob_locators.CHECKSUM_PAYLOAD,
        ),
        sql=v0008_add_relative_blob_locators.SQL,
        schema_fingerprint=v0008_add_relative_blob_locators.SCHEMA_FINGERPRINT,
    ),
    MigrationStep(
        version=9,
        name=v0009_add_sqlite_snapshot_text_authority.NAME,
        checksum=migration_checksum(
            9,
            v0009_add_sqlite_snapshot_text_authority.NAME,
            v0009_add_sqlite_snapshot_text_authority.CHECKSUM_PAYLOAD,
        ),
        sql=v0009_add_sqlite_snapshot_text_authority.SQL,
        apply=v0009_add_sqlite_snapshot_text_authority.apply,
        schema_fingerprint=v0009_add_sqlite_snapshot_text_authority.SCHEMA_FINGERPRINT,
    ),
)

__all__ = ["MIGRATIONS", "MigrationStep", "migration_checksum"]
