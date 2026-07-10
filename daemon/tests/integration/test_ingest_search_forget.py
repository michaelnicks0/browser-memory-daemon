import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import io
from pathlib import Path

import pytest

from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.forget import forget
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.blob_migration import migrate_blob_root
from browser_memory_daemon.media import fetch_pending_media_artifacts, media_artifacts_for_snapshot, media_capture_status_for_fetch_reason, store_media_artifact, store_media_blob_stream
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.ops import snapshot_detail
from browser_memory_daemon.search import search_memory


def stored_media_path(conn, artifact_id: str) -> Path:
    row = conn.execute("SELECT file_path FROM media_artifacts WHERE id = ?", (artifact_id,)).fetchone()
    return Path(row["file_path"])


def test_ingest_search_redact_and_forget(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)
    fake_secret = "SECRETSECRETSECRET12345"
    payload = CapturePayload.from_dict({
        "url": "https://example.com/article?utm_source=x",
        "canonical_url": "https://example.com/article",
        "title": "Stirling Test",
        "text": f"A Stirling engine uses cyclic compression. api_key = {fake_secret}",
    })
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert result["stored"] is True
        assert result["redaction_count"] == 1
        rows = search_memory(conn, "Stirling", limit=5)
        assert len(rows) == 1
        assert rows[0]["title"] == "Stirling Test"
        stored_text = cfg.clean_text_root.joinpath(f'{result["snapshot_id"]}.txt').read_text()
        assert "SECRETSECRET" not in stored_text
        receipt = forget(conn, cfg, domain="example.com")
        assert receipt["counts"]["documents"] == 1
        assert search_memory(conn, "Stirling", limit=5) == []
        assert not cfg.clean_text_root.joinpath(f'{result["snapshot_id"]}.txt').exists()


def test_metadata_redacted_before_fts_and_forget_by_original_url(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)
    title_secret = "TITLESECRET000000000000"
    url_secret = "URLSECRET000000000000"
    original_url = f"https://example.org/read?id=123&token={url_secret}"
    payload = CapturePayload.from_dict({
        "url": original_url,
        "canonical_url": "https://example.org/read",
        "title": f"Readable title token = {title_secret}",
        "text": "A public article about turbines.",
    })
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        rows = search_memory(conn, "Readable", limit=5)
        assert rows
        assert title_secret not in rows[0]["title"]
        assert url_secret not in rows[0]["url"]
        receipt = forget(conn, cfg, url=original_url)
        assert receipt["counts"]["documents"] == 1
        assert receipt["scope"]["selector_policy"] == "redacted"
        assert url_secret not in receipt["scope"]["url"]
        assert search_memory(conn, "turbines", limit=5) == []


def test_url_path_secret_redacted_and_not_searchable(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)
    path_secret = "SECRETSECRETSECRET1234567890OPAQUEID"
    payload = CapturePayload.from_dict({
        "url": f"https://example.net/share/{path_secret}",
        "title": "Shared public article",
        "text": "A public article about alternators.",
    })
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        assert search_memory(conn, path_secret, limit=5) == []
        rows = search_memory(conn, "alternators", limit=5)
        assert rows
        assert path_secret not in rows[0]["url"]


def test_url_userinfo_redacted_before_storage_and_fts(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)
    userinfo_secret = "USERINFOSECRET000000000000"
    payload = CapturePayload.from_dict({
        "url": f"https://reader:{userinfo_secret}@example.org/public-article",
        "title": "Userinfo URL Article",
        "text": "A public article about safe URL metadata storage.",
    })
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert result["redaction_count"] == 1
        assert search_memory(conn, userinfo_secret, limit=5) == []
        rows = search_memory(conn, "metadata", limit=5)
        assert rows
        assert userinfo_secret not in rows[0]["url"]
        assert "reader:" not in rows[0]["url"]
        visit = conn.execute("SELECT url FROM visits").fetchone()
        assert visit["url"] == "https://example.org/public-article"


def test_all_mode_stores_without_redaction_and_accepts_file_urls(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    fake_secret = "ALLMODESECRETSECRET12345"
    payload = CapturePayload.from_dict(
        {
            "url": f"file:///tmp/local-note.html?token={fake_secret}#fragment",
            "title": f"All mode title token = {fake_secret}",
            "text": f"All mode body preserves api_key = {fake_secret} and exact text.",
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert result["redaction_count"] == 0
        assert result["policy_mode"] == "all"
        rows = search_memory(conn, fake_secret, limit=10)
        assert rows
        assert any(fake_secret in row["title"] or fake_secret in row["url"] or fake_secret in row["snippet"] for row in rows)
        visit = conn.execute("SELECT url, is_incognito FROM visits").fetchone()
        assert fake_secret in visit["url"]


def test_all_mode_forget_url_uses_literal_selector_but_redacts_receipt_scope(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    url_secret = "ALLMODEURLSECRET1234567890"
    original_url = f"file:///tmp/local-note.html?token={url_secret}#frag"
    payload = CapturePayload.from_dict(
        {
            "url": original_url,
            "title": "All Mode Forget URL",
            "text": f"All mode forget should delete literal URL memory {url_secret}.",
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        assert search_memory(conn, url_secret, limit=5)

        receipt = forget(conn, cfg, url=original_url)
        receipt_row = conn.execute("SELECT scope_json FROM deletion_receipts WHERE id = ?", (receipt["receipt_id"],)).fetchone()

        assert receipt["counts"]["documents"] == 1
        assert receipt["scope"]["selector_policy"] == "literal"
        assert url_secret not in receipt["scope"]["url"]
        assert url_secret not in receipt_row["scope_json"]
        assert search_memory(conn, url_secret, limit=5) == []


def test_forget_requires_one_literal_selector(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        with pytest.raises(ValueError, match="exactly one selector"):
            forget(conn, cfg)
        with pytest.raises(ValueError, match="exactly one selector"):
            forget(conn, cfg, domain="example.com", url="https://example.com/page")
        with pytest.raises(ValueError, match="hostname, not a URL"):
            forget(conn, cfg, domain="https://example.com/page")
        with pytest.raises(ValueError, match="literal hostname"):
            forget(conn, cfg, domain="*.example.com")
        with pytest.raises(ValueError, match="absolute"):
            forget(conn, cfg, url="example.com/page")


def test_media_artifacts_are_related_to_snapshot_not_fts_and_deleted_by_forget(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/media-page",
            "title": "Media Page",
            "text": "Readable article body without media alt needles.",
            "media_artifacts": [
                {
                    "media_type": "image",
                    "role": "content",
                    "source_url": "https://example.com/assets/hero.png",
                    "alt_text": "MEDIA_ALT_NEEDLE should not be full-text indexed",
                    "mime_type": "image/png",
                    "width": 640,
                    "height": 360,
                }
            ],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert result["media_ref_count"] == 1
        assert search_memory(conn, "MEDIA_ALT_NEEDLE", limit=5) == []
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])
        assert len(media) == 1
        assert media[0]["capture_status"] == "referenced"
        assert media[0]["file_path_status"] == "config-required"
        task = conn.execute("SELECT artifact_id, worker_kind, status FROM media_fetch_tasks").fetchone()
        assert task["artifact_id"] == media[0]["id"]
        assert task["worker_kind"] == "daemon-public"
        assert task["status"] == "pending"
        stored = store_media_artifact(
            conn,
            cfg,
            {
                "document_id": result["document_id"],
                "snapshot_id": result["snapshot_id"],
                "visit_id": result["visit_id"],
                "page_url": "https://example.com/media-page",
                "media_type": "image",
                "role": "content",
                "source_url": "https://example.com/assets/hero.png",
                "mime_type": "image/png",
                "content_base64": "iVBORw0KGgo=",
            },
        )
        assert stored["stored"] is True
        file_rows = conn.execute("SELECT file_path, byte_size FROM media_artifacts").fetchall()
        assert len(file_rows) == 1
        assert file_rows[0]["byte_size"] == 8
        media_path = stored_media_path(conn, stored["artifact_id"])
        assert media_path.parent == cfg.media_root
        assert media_path.exists()
        receipt = forget(conn, cfg, domain="example.com")
        assert receipt["counts"]["media_artifacts"] == 1
        assert receipt["counts"]["media_blobs"] == 1
        assert not media_path.exists()


def test_ingest_and_media_write_to_configured_blob_root(tmp_path):
    runtime_root = tmp_path / "runtime"
    blob_root = tmp_path / "nas-blobs"
    cfg = load_config(runtime_root=runtime_root, blob_root=blob_root, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/nas-blob-root",
            "title": "NAS Blob Root",
            "text": "Readable body for relocated blob root.",
            "media_artifacts": [{"media_type": "image", "source_url": "https://example.com/nas.png", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        clean_path = cfg.clean_text_root / f"{result['snapshot_id']}.txt"
        assert cfg.db_path == runtime_root / "browser-memory.sqlite3"
        assert clean_path.exists()
        assert not (runtime_root / "blobs").exists()

        stored = store_media_artifact(
            conn,
            cfg,
            {
                "document_id": result["document_id"],
                "snapshot_id": result["snapshot_id"],
                "visit_id": result["visit_id"],
                "page_url": "https://example.com/nas-blob-root",
                "media_type": "image",
                "source_url": "https://example.com/nas.png",
                "mime_type": "image/png",
                "content_base64": base64.b64encode(b"nasbytes").decode("ascii"),
            },
        )
        row = conn.execute(
            "SELECT cleaned_text_path, cleaned_text_locator FROM snapshots WHERE id = ?",
            (result["snapshot_id"],),
        ).fetchone()
        media_row = conn.execute(
            "SELECT file_path, blob_locator FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()

    assert row["cleaned_text_path"] == str(clean_path)
    assert row["cleaned_text_locator"] == clean_path.name
    media_path = Path(media_row["file_path"])
    assert media_row["blob_locator"] == media_path.name
    assert media_path.parent == cfg.media_root
    assert media_path.name != f"{stored['artifact_id']}.png"
    assert media_path.exists()


def test_blob_path_consumers_reject_db_paths_outside_configured_roots(tmp_path):
    cfg = load_config(runtime_root=tmp_path / "runtime", test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    outside_clean = outside_root / "clean.txt"
    outside_media = outside_root / "media.png"
    outside_clean.write_text("OUTSIDE_CLEAN_SECRET", encoding="utf-8")
    outside_media.write_bytes(b"OUTSIDE_MEDIA_SECRET")
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/out-of-root-paths",
            "title": "Out Of Root Paths",
            "text": "Readable in-database fallback text.",
            "media_artifacts": [{"media_type": "image", "source_url": "https://example.com/outside.png", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        stored = store_media_artifact(
            conn,
            cfg,
            {
                "document_id": result["document_id"],
                "snapshot_id": result["snapshot_id"],
                "visit_id": result["visit_id"],
                "page_url": "https://example.com/out-of-root-paths",
                "media_type": "image",
                "source_url": "https://example.com/outside.png",
                "mime_type": "image/png",
                "content_base64": base64.b64encode(b"inside").decode("ascii"),
            },
        )
        conn.execute(
            "UPDATE snapshots SET cleaned_text_path = ? WHERE id = ?",
            (str(outside_clean), result["snapshot_id"]),
        )
        conn.execute(
            "UPDATE media_artifacts SET file_path = ? WHERE id = ?",
            (str(outside_media), stored["artifact_id"]),
        )

        relative_detail = snapshot_detail(conn, cfg, result["snapshot_id"])
        assert "Readable in-database fallback text." in relative_detail["text"]
        assert relative_detail["snapshot"]["clean_text_locator_kind"] == "relative"
        relative_media = media_artifacts_for_snapshot(conn, result["snapshot_id"], cfg)[0]
        assert relative_media["has_file"] is True
        assert relative_media["file_locator_kind"] == "relative"

        conn.execute(
            "UPDATE snapshots SET cleaned_text_locator = ? WHERE id = ?",
            (str(outside_clean), result["snapshot_id"]),
        )
        conn.execute(
            "UPDATE media_artifacts SET blob_locator = ?, byte_size = ? WHERE id = ?",
            (str(outside_media), outside_media.stat().st_size, stored["artifact_id"]),
        )

        detail = snapshot_detail(conn, cfg, result["snapshot_id"])
        assert "OUTSIDE_CLEAN_SECRET" not in detail["text"]
        assert detail["snapshot"]["clean_text_path_status"] == "outside-root"
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"], cfg)[0]
        assert media["has_file"] is False
        assert media["file_path_status"] == "outside-root"
        assert "content_url" not in media

        receipt = forget(conn, cfg, domain="example.com")

    assert receipt["counts"]["blobs"] == 0
    assert receipt["counts"]["blobs_out_of_root"] == 1
    assert receipt["counts"]["media_blobs"] == 0
    assert receipt["counts"]["media_blobs_out_of_root"] == 1
    assert outside_clean.exists()
    assert outside_media.exists()


def test_blob_root_migration_copies_files_and_rewrites_db_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("BMD_BLOB_ROOT", raising=False)
    runtime_root = tmp_path / "runtime"
    nas_root = tmp_path / "nas-blobs"
    old_cfg = load_config(runtime_root=runtime_root, test_mode=True, token="test-token", policy_mode="all")
    init_db(old_cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/blob-migration",
            "title": "Blob Migration",
            "text": "Readable body before blob migration.",
            "media_artifacts": [{"media_type": "image", "source_url": "https://example.com/migrate.png", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(old_cfg.db_path) as conn:
        result = ingest_capture(conn, old_cfg, payload)
        stored = store_media_artifact(
            conn,
            old_cfg,
            {
                "document_id": result["document_id"],
                "snapshot_id": result["snapshot_id"],
                "visit_id": result["visit_id"],
                "page_url": "https://example.com/blob-migration",
                "media_type": "image",
                "source_url": "https://example.com/migrate.png",
                "mime_type": "image/png",
                "content_base64": base64.b64encode(b"movebytes").decode("ascii"),
            },
        )

    old_clean_path = old_cfg.clean_text_root / f"{result['snapshot_id']}.txt"
    with connect(old_cfg.db_path) as conn:
        old_media_path = stored_media_path(conn, stored["artifact_id"])
    old_media_relative = old_media_path.relative_to(old_cfg.media_root)
    new_cfg = load_config(runtime_root=runtime_root, blob_root=nas_root, test_mode=True, token="test-token", policy_mode="all")
    with connect(new_cfg.db_path) as conn:
        dry_run = migrate_blob_root(conn, new_cfg)
        assert dry_run["dry_run"] is True
        assert dry_run["planned"] == 2
        executed = migrate_blob_root(conn, new_cfg, execute=True)
        row = conn.execute(
            "SELECT cleaned_text_path, cleaned_text_locator FROM snapshots WHERE id = ?",
            (result["snapshot_id"],),
        ).fetchone()
        media_row = conn.execute(
            "SELECT file_path, blob_locator FROM media_artifacts WHERE id = ?",
            (stored["artifact_id"],),
        ).fetchone()

    assert executed["copied"] == 2
    assert executed["updated"] == 2
    assert old_clean_path.exists()
    assert old_media_path.exists()
    assert row["cleaned_text_path"] == str(new_cfg.clean_text_root / f"{result['snapshot_id']}.txt")
    assert row["cleaned_text_locator"] == f"{result['snapshot_id']}.txt"
    assert media_row["file_path"] == str(new_cfg.media_root / old_media_relative)
    assert media_row["blob_locator"] == old_media_relative.as_posix()
    assert (new_cfg.clean_text_root / f"{result['snapshot_id']}.txt").read_text() == "Readable body before blob migration."
    assert (new_cfg.media_root / old_media_relative).read_bytes() == b"movebytes"


def test_media_artifact_size_gate_skips_oversized_blob(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, max_media_artifact_bytes=4)
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/oversized-media-page",
            "title": "Oversized Media Page",
            "text": "Readable body for oversized media gate.",
            "media_artifacts": [{"media_type": "image", "source_url": "https://example.com/too-big.png", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        stored = store_media_artifact(
            conn,
            cfg,
            {
                "document_id": result["document_id"],
                "snapshot_id": result["snapshot_id"],
                "visit_id": result["visit_id"],
                "page_url": "https://example.com/oversized-media-page",
                "media_type": "image",
                "source_url": "https://example.com/too-big.png",
                "mime_type": "image/png",
                "content_base64": "iVBORw0KGgo=",
            },
        )
        assert stored["stored"] is False
        assert stored["capture_status"] == "skipped"
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["status_reason"] == "media-too-large"
        assert media["has_file"] is False


def test_media_global_cache_rolls_oldest_blob_when_limit_would_be_exceeded(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, max_media_artifact_bytes=20, max_media_bytes_per_domain=0, max_media_cache_bytes=12)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        old_result = ingest_capture(conn, cfg, CapturePayload.from_dict({"url": "https://old.example/media", "title": "Old", "text": "Readable old media body.", "media_artifacts": [{"media_type": "image", "source_url": "https://old.example/old.png", "mime_type": "image/png"}]}, allow_any_url=True))
        old = store_media_artifact(conn, cfg, {"document_id": old_result["document_id"], "snapshot_id": old_result["snapshot_id"], "visit_id": old_result["visit_id"], "page_url": "https://old.example/media", "media_type": "image", "source_url": "https://old.example/old.png", "mime_type": "image/png", "content_base64": base64.b64encode(b"oldbytes").decode("ascii")})
        old_path = stored_media_path(conn, old["artifact_id"])
        assert old_path.exists()
        conn.execute("UPDATE media_artifacts SET created_at = '2026-01-01 00:00:00' WHERE id = ?", (old["artifact_id"],))

        new_result = ingest_capture(conn, cfg, CapturePayload.from_dict({"url": "https://new.example/media", "title": "New", "text": "Readable new media body.", "media_artifacts": [{"media_type": "image", "source_url": "https://new.example/new.png", "mime_type": "image/png"}]}, allow_any_url=True))
        new = store_media_artifact(conn, cfg, {"document_id": new_result["document_id"], "snapshot_id": new_result["snapshot_id"], "visit_id": new_result["visit_id"], "page_url": "https://new.example/media", "media_type": "image", "source_url": "https://new.example/new.png", "mime_type": "image/png", "content_base64": base64.b64encode(b"newbytes").decode("ascii")})

        assert new["stored"] is True
        assert not old_path.exists()
        rows = {
            row["id"]: dict(row)
            for row in conn.execute("SELECT id, capture_status, status_reason, file_path, blob_locator FROM media_artifacts")
        }
        assert rows[old["artifact_id"]]["capture_status"] == "purged"
        assert rows[old["artifact_id"]]["status_reason"] == "cache-evicted:global-oldest"
        assert rows[old["artifact_id"]]["file_path"] == ""
        assert rows[old["artifact_id"]]["blob_locator"] == ""
        assert rows[new["artifact_id"]]["capture_status"] == "stored"


def test_media_domain_cache_rolls_oldest_blob_when_domain_limit_would_be_exceeded(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    cfg = replace(cfg, max_media_artifact_bytes=20, max_media_bytes_per_domain=12, max_media_cache_bytes=0)
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        old_result = ingest_capture(conn, cfg, CapturePayload.from_dict({"url": "https://x.example/old", "title": "Old", "text": "Readable old domain media body.", "media_artifacts": [{"media_type": "image", "source_url": "https://x.example/old.png", "mime_type": "image/png"}]}, allow_any_url=True))
        old = store_media_artifact(conn, cfg, {"document_id": old_result["document_id"], "snapshot_id": old_result["snapshot_id"], "visit_id": old_result["visit_id"], "page_url": "https://x.example/old", "media_type": "image", "source_url": "https://x.example/old.png", "mime_type": "image/png", "content_base64": base64.b64encode(b"oldbytes").decode("ascii")})
        old_path = stored_media_path(conn, old["artifact_id"])
        conn.execute("UPDATE media_artifacts SET created_at = '2026-01-01 00:00:00' WHERE id = ?", (old["artifact_id"],))

        new_result = ingest_capture(conn, cfg, CapturePayload.from_dict({"url": "https://x.example/new", "title": "New", "text": "Readable new domain media body.", "media_artifacts": [{"media_type": "image", "source_url": "https://x.example/new.png", "mime_type": "image/png"}]}, allow_any_url=True))
        new = store_media_artifact(conn, cfg, {"document_id": new_result["document_id"], "snapshot_id": new_result["snapshot_id"], "visit_id": new_result["visit_id"], "page_url": "https://x.example/new", "media_type": "image", "source_url": "https://x.example/new.png", "mime_type": "image/png", "content_base64": base64.b64encode(b"newbytes").decode("ascii")})

        assert new["stored"] is True
        assert not old_path.exists()
        rows = {row["id"]: dict(row) for row in conn.execute("SELECT id, capture_status, status_reason FROM media_artifacts")}
        assert rows[old["artifact_id"]]["capture_status"] == "purged"
        assert rows[old["artifact_id"]]["status_reason"] == "cache-evicted:domain-oldest"
        assert rows[new["artifact_id"]]["capture_status"] == "stored"


def test_raw_blob_upload_rejects_truncated_body_and_infers_mime_from_url(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/raw-media-page",
            "title": "Raw Media Page",
            "text": "Readable body for raw media upload.",
            "media_artifacts": [{"media_type": "image", "source_url": "https://example.com/raw.png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        artifact = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        with pytest.raises(ValueError, match="incomplete media upload"):
            store_media_blob_stream(
                conn,
                cfg,
                artifact["id"],
                io.BytesIO(b"1234"),
                headers={"Content-Type": "application/octet-stream"},
                content_length=8,
            )
        stored = store_media_blob_stream(
            conn,
            cfg,
            artifact["id"],
            io.BytesIO(b"12345678"),
            headers={"Content-Type": "application/octet-stream"},
            content_length=8,
        )
        assert stored["stored"] is True
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["mime_type"] == "image/png"
        assert media["byte_size"] == 8


def test_posted_cdp_metadata_enqueues_daemon_fetch_task(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://x.com/home",
            "title": "X Home",
            "text": "Readable X body for CDP metadata.",
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        posted = store_media_artifact(
            conn,
            cfg,
            {
                "document_id": result["document_id"],
                "snapshot_id": result["snapshot_id"],
                "visit_id": result["visit_id"],
                "page_url": "https://x.com/home",
                "media_type": "video",
                "role": "cdp-segment",
                "source_url": "https://video.twimg.com/amplify_video/1/vid/avc1/0/3000/1920x1080/seg.m4s",
                "mime_type": "video/mp4",
                "capture_status": "referenced",
                "metadata": {"cdp_recorder": True},
            },
        )
        assert posted["stored"] is False
        task = conn.execute(
            "SELECT artifact_id, worker_kind, status FROM media_fetch_tasks WHERE artifact_id = ?",
            (posted["artifact_id"],),
        ).fetchone()
        assert task["worker_kind"] == "daemon-public"
        assert task["status"] == "pending"


def test_fetch_pending_media_artifacts_stores_data_url_without_indexing_media_metadata(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    data_url = "data:image/png;base64,iVBORw0KGgo="
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/data-media-page",
            "title": "Data Media Page",
            "text": "Readable body for daemon-side media fetch fallback.",
            "media_artifacts": [
                {
                    "media_type": "image",
                    "role": "content",
                    "source_url": data_url,
                    "alt_text": "DATA_URL_MEDIA_ALT_NEEDLE",
                    "mime_type": "image/png",
                }
            ],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert search_memory(conn, "DATA_URL_MEDIA_ALT_NEEDLE", limit=5) == []
        fetched = fetch_pending_media_artifacts(conn, cfg, snapshot_id=result["snapshot_id"], limit=10)
        assert fetched["attempted"] == 1
        assert fetched["stored"] == 1
        assert fetched["remaining"] == 0
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"], cfg)
        assert media[0]["capture_status"] == "stored"
        assert media[0]["byte_size"] == 8
        assert media[0]["has_file"] is True


def test_fetch_pending_media_artifacts_keeps_large_data_url_ref_intact(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    content = b"x" * 9000
    data_url = "data:image/png;base64," + base64.b64encode(content).decode("ascii")
    assert len(data_url) > 8192
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/large-data-media-page",
            "title": "Large Data Media Page",
            "text": "Readable body for a large inline data URL media ref.",
            "media_artifacts": [{"media_type": "image", "role": "content", "source_url": data_url, "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["source_url"] == data_url
        fetched = fetch_pending_media_artifacts(conn, cfg, snapshot_id=result["snapshot_id"], limit=10)
        assert fetched["stored"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "stored"
        assert media["byte_size"] == len(content)


def test_media_fetch_reason_classification_keeps_remote_errors_out_of_failed_bucket():
    assert media_capture_status_for_fetch_reason("invalid-data-url-payload", source_url="data:image/png;base64,bad") == "skipped"
    assert media_capture_status_for_fetch_reason("fetch-status-404", source_url="https://example.com/missing.png") == "expired"
    assert media_capture_status_for_fetch_reason("fetch-status-429", source_url="https://example.com/rate.png") == "retrying"
    assert media_capture_status_for_fetch_reason("Failed to fetch", source_url="https://example.com/flaky.png") == "retrying"


def test_forget_domain_includes_subdomains(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)
    payload = CapturePayload.from_dict({
        "url": "https://www.example.com/page",
        "title": "Subdomain Article",
        "text": "A public article about subdomain deletion.",
    })
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        assert search_memory(conn, "subdomain", limit=5)
        receipt = forget(conn, cfg, domain="example.com")
        assert receipt["counts"]["documents"] == 1
        assert search_memory(conn, "subdomain", limit=5) == []


def test_repeat_capture_dedupes_snapshot_but_adds_visit(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)
    first = CapturePayload.from_dict({
        "url": "https://Example.COM:443/article?utm_source=feed&b=2&a=1",
        "title": "Dedupe Article",
        "text": "Stable body text about low-noise browser memory dedupe.",
        "captured_at": "2026-06-08T12:00:00Z",
    })
    second = CapturePayload.from_dict({
        "url": "https://example.com/article?a=1&b=2&utm_medium=social",
        "title": "Dedupe Article Updated Title",
        "text": "Stable body text about low-noise browser memory dedupe.",
        "captured_at": "2026-06-08T12:05:00Z",
    })
    with connect(cfg.db_path) as conn:
        first_result = ingest_capture(conn, cfg, first)
        second_result = ingest_capture(conn, cfg, second)
        assert first_result["document_id"] == second_result["document_id"]
        assert first_result["snapshot_id"] == second_result["snapshot_id"]
        assert first_result["snapshot_created"] is True
        assert second_result["snapshot_created"] is False
        assert second_result["chunk_count"] == 0
        counts = dict(conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM documents) AS documents,
              (SELECT COUNT(*) FROM visits) AS visits,
              (SELECT COUNT(*) FROM capture_observations) AS observations,
              (SELECT COUNT(*) FROM snapshots) AS snapshots,
              (SELECT COUNT(*) FROM chunks) AS chunks,
              (SELECT COUNT(*) FROM chunks_fts) AS chunks_fts
            """
        ).fetchone())
        assert counts == {"documents": 1, "visits": 2, "observations": 2, "snapshots": 1, "chunks": 1, "chunks_fts": 1}
        document = conn.execute("SELECT normalized_url, title, first_seen_at, last_seen_at FROM documents").fetchone()
        assert document["normalized_url"] == "https://example.com/article?a=1&b=2"
        assert document["title"] == "Dedupe Article Updated Title"
        assert document["first_seen_at"] == "2026-06-08T12:00:00Z"
        assert document["last_seen_at"] == "2026-06-08T12:05:00Z"
        rows = search_memory(conn, "low-noise", limit=5)
        assert len(rows) == 1
        assert rows[0]["document_id"] == first_result["document_id"]


def test_concurrent_duplicate_capture_is_idempotent_for_snapshot_chunks_and_fts(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)

    def capture(idx: int) -> dict:
        payload = CapturePayload.from_dict(
            {
                "visit_id": f"concurrent-duplicate-{idx}",
                "url": "https://example.com/concurrent-duplicate?utm_source=worker",
                "title": f"Concurrent Duplicate {idx}",
                "text": "Concurrent duplicate body text with IDEMPOTENT_CAPTURE_NEEDLE.",
                "captured_at": f"2026-06-08T12:00:{idx:02d}Z",
            }
        )
        with connect(cfg.db_path) as conn:
            return ingest_capture(conn, cfg, payload)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(capture, range(8)))

    assert {item["document_id"] for item in results} == {results[0]["document_id"]}
    assert {item["snapshot_id"] for item in results} == {results[0]["snapshot_id"]}
    assert sum(1 for item in results if item["snapshot_created"]) == 1
    assert sum(item["chunk_count"] for item in results) == 1
    with connect(cfg.db_path) as conn:
        counts = dict(
            conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM documents) AS documents,
                  (SELECT COUNT(*) FROM visits) AS visits,
                  (SELECT COUNT(*) FROM capture_observations) AS observations,
                  (SELECT COUNT(*) FROM snapshots) AS snapshots,
                  (SELECT COUNT(*) FROM chunks) AS chunks,
                  (SELECT COUNT(*) FROM chunks_fts) AS chunks_fts
                """
            ).fetchone()
        )
        assert counts == {"documents": 1, "visits": 8, "observations": 8, "snapshots": 1, "chunks": 1, "chunks_fts": 1}
        assert len(search_memory(conn, "IDEMPOTENT_CAPTURE_NEEDLE", limit=10)) == 1
    clean_files = list(cfg.clean_text_root.glob(f"{results[0]['snapshot_id']}*.txt"))
    assert clean_files == [cfg.clean_text_root / f"{results[0]['snapshot_id']}.txt"]


def test_changed_content_creates_new_snapshot_under_same_document(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)
    first = CapturePayload.from_dict({
        "url": "https://example.net/versioned",
        "title": "Versioned Article",
        "text": "Original version text includes ALPHA_VERSION_NEEDLE.",
        "captured_at": "2026-06-08T12:00:00Z",
    })
    second = CapturePayload.from_dict({
        "url": "https://example.net/versioned?utm_campaign=ignored",
        "title": "Versioned Article",
        "text": "Updated version text includes BETA_VERSION_NEEDLE.",
        "captured_at": "2026-06-08T12:10:00Z",
    })
    with connect(cfg.db_path) as conn:
        first_result = ingest_capture(conn, cfg, first)
        second_result = ingest_capture(conn, cfg, second)
        assert first_result["document_id"] == second_result["document_id"]
        assert first_result["snapshot_id"] != second_result["snapshot_id"]
        assert first_result["snapshot_created"] is True
        assert second_result["snapshot_created"] is True
        counts = dict(conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM documents) AS documents,
              (SELECT COUNT(*) FROM visits) AS visits,
              (SELECT COUNT(*) FROM capture_observations) AS observations,
              (SELECT COUNT(*) FROM snapshots) AS snapshots,
              (SELECT COUNT(*) FROM chunks) AS chunks,
              (SELECT COUNT(*) FROM chunks_fts) AS chunks_fts
            """
        ).fetchone())
        assert counts == {"documents": 1, "visits": 2, "observations": 2, "snapshots": 2, "chunks": 2, "chunks_fts": 2}
        alpha_rows = search_memory(conn, "ALPHA_VERSION_NEEDLE", limit=5)
        beta_rows = search_memory(conn, "BETA_VERSION_NEEDLE", limit=5)
        assert len(alpha_rows) == 1
        assert len(beta_rows) == 1
        assert alpha_rows[0]["document_id"] == beta_rows[0]["document_id"] == first_result["document_id"]
        assert alpha_rows[0]["snapshot_id"] == first_result["snapshot_id"]
        assert beta_rows[0]["snapshot_id"] == second_result["snapshot_id"]


def test_schema_has_planned_core_tables(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="strict")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')")}
    for expected in {
        "jobs",
        "embeddings",
        "redactions",
        "feedback_events",
        "deletion_receipts",
        "visit_events",
        "media_artifacts",
        "media_fetch_tasks",
        "capture_observations",
        "document_url_claims",
        "media_artifact_observations",
        "schema_migrations",
    }:
        assert expected in tables


def test_capture_payload_rejects_bad_timestamp():
    try:
        CapturePayload.from_dict({"url": "https://example.com", "text": "hello", "captured_at": "not-a-date"})
        raise AssertionError("expected timestamp validation failure")
    except ValueError as exc:
        assert "captured_at" in str(exc)
