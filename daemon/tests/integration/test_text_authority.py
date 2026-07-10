from pathlib import Path

from browser_memory_daemon.blob_store import BlobStore
from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.ops import doctor, snapshot_detail
from browser_memory_daemon.text_authority import reconcile_snapshot_text_authority


def test_new_capture_commits_complete_sqlite_text_without_creating_blob_root(tmp_path):
    blob_root = tmp_path / "offline-nas" / "blobs"
    cfg = load_config(
        runtime_root=tmp_path / "runtime",
        blob_root=blob_root,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )
    init_db(cfg)
    assert not blob_root.exists()

    original = "  Complete local SQLite text keeps exact leading whitespace.\nSecond line."
    with connect(cfg.db_path) as conn:
        stored = ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "visit_id": "sqlite-authority-visit",
                    "url": "https://example.com/sqlite-authority",
                    "title": "SQLite authority",
                    "text": original,
                    "media_artifacts": [
                        {
                            "media_type": "image",
                            "source_url": "https://example.com/deferred-image.png",
                            "mime_type": "image/png",
                        }
                    ],
                },
                allow_any_url=True,
            ),
        )
        row = conn.execute(
            """
            SELECT cleaned_text, cleaned_text_source, cleaned_text_path, cleaned_text_locator
            FROM snapshots WHERE id = ?
            """,
            (stored["snapshot_id"],),
        ).fetchone()
        detail = snapshot_detail(conn, cfg, stored["snapshot_id"])
        health = doctor(cfg, conn)
        media_count = conn.execute(
            "SELECT COUNT(*) FROM media_artifacts WHERE snapshot_id = ?", (stored["snapshot_id"],)
        ).fetchone()[0]

    assert dict(row) == {
        "cleaned_text": original,
        "cleaned_text_source": "capture",
        "cleaned_text_path": None,
        "cleaned_text_locator": None,
    }
    assert stored["text_authority"] == "sqlite"
    assert stored["clean_text_sidecar_status"] == "not-created"
    assert detail["text"] == original
    assert detail["text_source"] == "capture"
    assert detail["snapshot"]["has_clean_text"] is True
    assert detail["snapshot"]["clean_text_locator_kind"] == "none"
    assert detail["snapshot"]["clean_text_path_status"] == "empty"
    assert health["ok"] is True
    assert health["database"]["snapshots_missing_authoritative_text"] == 0
    assert health["storage"]["sqlite_text_bytes"] == len(original)
    assert media_count == 1
    assert not blob_root.exists()


def test_reconcile_promotes_only_hash_verified_contained_legacy_sidecar(tmp_path):
    cfg = load_config(
        runtime_root=tmp_path / "runtime",
        blob_root=tmp_path / "blobs",
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )
    init_db(cfg)
    original = "  Leading whitespace makes chunk reconstruction differ from the capture hash."
    with connect(cfg.db_path) as conn:
        stored = ingest_capture(
            conn,
            cfg,
            CapturePayload.from_dict(
                {
                    "visit_id": "legacy-sidecar-visit",
                    "url": "https://example.com/legacy-sidecar",
                    "title": "Legacy sidecar",
                    "text": original,
                },
                allow_any_url=True,
            ),
        )
        locator = f"{stored['snapshot_id']}.txt"
        sidecar_path = BlobStore(cfg.clean_text_root).write_text(locator, original)
        conn.execute(
            """
            UPDATE snapshots
            SET cleaned_text = NULL,
                cleaned_text_source = 'legacy-fallback',
                cleaned_text_path = ?,
                cleaned_text_locator = ?
            WHERE id = ?
            """,
            (str(sidecar_path), locator, stored["snapshot_id"]),
        )
        conn.commit()

        preview = reconcile_snapshot_text_authority(conn, cfg, execute=False)
        assert preview == {
            "dry_run": True,
            "scanned": 1,
            "resolved": 1,
            "applied": 0,
            "from_chunks": 0,
            "from_sidecars": 1,
            "unresolved": [],
            "remaining": 1,
        }
        applied = reconcile_snapshot_text_authority(conn, cfg, execute=True)
        row = conn.execute(
            "SELECT cleaned_text, cleaned_text_source FROM snapshots WHERE id = ?",
            (stored["snapshot_id"],),
        ).fetchone()
        detail = snapshot_detail(conn, cfg, stored["snapshot_id"])

    assert applied["dry_run"] is False
    assert applied["applied"] == 1
    assert applied["remaining"] == 0
    assert dict(row) == {
        "cleaned_text": original,
        "cleaned_text_source": "sidecar-hash-verified",
    }
    assert detail["text"] == original
    assert detail["text_source"] == "sidecar-hash-verified"
    assert Path(sidecar_path).read_text(encoding="utf-8") == original
