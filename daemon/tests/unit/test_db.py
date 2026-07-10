from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import SQLITE_BUSY_TIMEOUT_MS, connect, init_db


def test_connect_uses_extended_busy_timeout(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == SQLITE_BUSY_TIMEOUT_MS


def test_init_db_enforces_wal_and_connection_pragmas(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
    init_db(cfg)

    with connect(cfg.db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
