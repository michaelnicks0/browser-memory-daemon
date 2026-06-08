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
