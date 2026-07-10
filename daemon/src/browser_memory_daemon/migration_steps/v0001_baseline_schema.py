"""Immutable version-1 baseline schema. Do not edit; add a new migration step."""

from pathlib import Path


NAME = "baseline_current_schema"
SCHEMA_FINGERPRINT = "be56235db5662fad16ee822e6c1fbda0445535041acb96dd971c8a20ad67d0b1"
SQL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
