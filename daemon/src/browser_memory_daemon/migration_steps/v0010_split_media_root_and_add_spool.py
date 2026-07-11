"""Split media-root metadata and add bounded spool reservations."""

from pathlib import Path

NAME = "split_media_root_and_add_spool"
SQL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
SCHEMA_FINGERPRINT = "4d6194c80f10d501f6b3f440295237eab2b1c2a9bf28fa5e28e6d9e1199e6cc0"
DESTRUCTIVE = False
