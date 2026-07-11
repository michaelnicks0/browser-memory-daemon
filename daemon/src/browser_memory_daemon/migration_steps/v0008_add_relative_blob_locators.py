"""Add root-relative blob locators alongside legacy absolute paths."""

from pathlib import Path

NAME = "add_relative_blob_locators"
SQL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
SCHEMA_FINGERPRINT = "189c1acd13e12ebfa30b1e4243be2580796d01dd6ba87dfae0840691da4dc597"
CHECKSUM_PAYLOAD = SQL
