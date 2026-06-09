from dataclasses import replace
import io

import pytest

from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.forget import forget
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.media import fetch_pending_media_artifacts, media_artifacts_for_snapshot, store_media_artifact, store_media_blob_stream
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.search import search_memory


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
        receipt = forget(conn, domain="example.com")
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
        receipt = forget(conn, url=original_url)
        assert receipt["counts"]["documents"] == 1
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
        media_path = cfg.media_root / f"{stored['artifact_id']}.png"
        assert media_path.exists()
        receipt = forget(conn, domain="example.com")
        assert receipt["counts"]["media_artifacts"] == 1
        assert receipt["counts"]["media_blobs"] == 1
        assert not media_path.exists()


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
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])
        assert media[0]["capture_status"] == "stored"
        assert media[0]["byte_size"] == 8
        assert media[0]["has_file"] is True


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
        receipt = forget(conn, domain="example.com")
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
              (SELECT COUNT(*) FROM snapshots) AS snapshots,
              (SELECT COUNT(*) FROM chunks) AS chunks,
              (SELECT COUNT(*) FROM chunks_fts) AS chunks_fts
            """
        ).fetchone())
        assert counts == {"documents": 1, "visits": 2, "snapshots": 1, "chunks": 1, "chunks_fts": 1}
        document = conn.execute("SELECT normalized_url, title, first_seen_at, last_seen_at FROM documents").fetchone()
        assert document["normalized_url"] == "https://example.com/article?a=1&b=2"
        assert document["title"] == "Dedupe Article Updated Title"
        assert document["first_seen_at"] == "2026-06-08T12:00:00Z"
        assert document["last_seen_at"] == "2026-06-08T12:05:00Z"
        rows = search_memory(conn, "low-noise", limit=5)
        assert len(rows) == 1
        assert rows[0]["document_id"] == first_result["document_id"]


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
              (SELECT COUNT(*) FROM snapshots) AS snapshots,
              (SELECT COUNT(*) FROM chunks) AS chunks,
              (SELECT COUNT(*) FROM chunks_fts) AS chunks_fts
            """
        ).fetchone())
        assert counts == {"documents": 1, "visits": 2, "snapshots": 2, "chunks": 2, "chunks_fts": 2}
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
    for expected in {"jobs", "embeddings", "redactions", "feedback_events", "deletion_receipts", "visit_events", "media_artifacts", "media_fetch_tasks"}:
        assert expected in tables


def test_capture_payload_rejects_bad_timestamp():
    try:
        CapturePayload.from_dict({"url": "https://example.com", "text": "hello", "captured_at": "not-a-date"})
        raise AssertionError("expected timestamp validation failure")
    except ValueError as exc:
        assert "captured_at" in str(exc)
