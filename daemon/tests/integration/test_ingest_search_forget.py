from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.forget import forget
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.models import CapturePayload
from browser_memory_daemon.search import search_memory


def test_ingest_search_redact_and_forget(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
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
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
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
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
    init_db(cfg)
    path_secret = "SECRETSECRETSECRET12345"
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
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
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


def test_forget_domain_includes_subdomains(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
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
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
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
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
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
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token")
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')")}
    for expected in {"jobs", "embeddings", "redactions", "feedback_events", "deletion_receipts"}:
        assert expected in tables


def test_capture_payload_rejects_bad_timestamp():
    try:
        CapturePayload.from_dict({"url": "https://example.com", "text": "hello", "captured_at": "not-a-date"})
        raise AssertionError("expected timestamp validation failure")
    except ValueError as exc:
        assert "captured_at" in str(exc)
