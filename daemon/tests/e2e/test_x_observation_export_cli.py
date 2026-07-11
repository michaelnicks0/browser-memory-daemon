from __future__ import annotations

import json

import browser_memory_daemon.cli as cli_module
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.models import CapturePayload


def test_cli_export_queries_existing_database_without_init_migration_or_token(tmp_path, monkeypatch, capsys):
    cfg = load_config(
        runtime_root=tmp_path / "runtime",
        blob_root=tmp_path / "blobs",
        test_mode=True,
        token="fixture-token",
        policy_mode="all",
    )
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        stored = ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "observation_id": "browser-cli-export",
                    "visit_id": "visit-cli-export",
                    "url": "https://x.com/fixture/status/123",
                    "title": "CLI fixture",
                    "text": "CLI fixture body",
                    "captured_at": "2026-07-11T00:00:00Z",
                },
                allow_any_url=True,
            ),
        )
        conn.commit()

    monkeypatch.delenv("BMD_API_TOKEN", raising=False)
    monkeypatch.setattr(cli_module, "init_db", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("init forbidden")))
    monkeypatch.setattr(
        cli_module,
        "migrate_database",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("migration forbidden")),
    )

    result = cli_module.main(
        [
            "--runtime-root",
            str(cfg.data_root),
            "export",
            "x-observations",
            "--limit",
            "10",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["contract"] == "bmd.x-observations"
    assert payload["producer"]["build_revision"] is None
    assert [row["observation_id"] for row in payload["records"]] == [stored["observation_id"]]
