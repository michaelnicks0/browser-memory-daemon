"""Expand the authority model with capture observations and URL claims."""

from pathlib import Path

NAME = "add_capture_observations_and_url_claims"
SCHEMA_FINGERPRINT = "7af3e2b801c8b89882fe0d24c07d25ad5ecbaa392a488be4e88e03b1fc6a220f"
SQL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
