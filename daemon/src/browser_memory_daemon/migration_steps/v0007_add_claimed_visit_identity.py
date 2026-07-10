"""Preserve claimed visit identity for delayed lifecycle attachment."""

from pathlib import Path

NAME = "add_claimed_visit_identity"
SQL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
SCHEMA_FINGERPRINT = "64b8fee023a0a0e3983925ec0b51246edaa0a3ef54b4aa3dd5ef3d2c7832a288"
CHECKSUM_PAYLOAD = SQL
