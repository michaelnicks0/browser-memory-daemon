from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from browser_memory_daemon.config import load_config
from browser_memory_daemon.db import connect, init_db
from browser_memory_daemon.ingest import ingest_capture
from browser_memory_daemon.media import media_artifacts_for_snapshot, purge_media_cache
from browser_memory_daemon.media_worker import normalize_hls_video_skips, normalize_legacy_blob_video_skips, normalize_snapshot_budget_skips, normalize_terminal_failed_artifacts, run_once
from browser_memory_daemon.models import CapturePayload


def test_media_worker_processes_data_url_task_and_marks_success(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/worker-media",
            "title": "Worker Media",
            "text": "Readable worker media body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
        assert summary["attempted"] == 1
        assert summary["stored"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "stored"
        task = conn.execute("SELECT status FROM media_fetch_tasks").fetchone()
        assert task["status"] == "succeeded"


def test_media_worker_tasks_are_seeded_when_existing_unresolved_refs_have_no_task(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/seed-task",
            "title": "Seed Task",
            "text": "Readable seed task body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        conn.execute("DELETE FROM media_fetch_tasks")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM media_fetch_tasks").fetchone()[0] == 0
    init_db(cfg)
    with connect(cfg.db_path) as conn:
        task = conn.execute("SELECT status FROM media_fetch_tasks").fetchone()
        assert task["status"] == "pending"


def test_media_worker_marks_pending_task_succeeded_when_artifact_already_stored(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/already-stored-task",
            "title": "Already Stored Task",
            "text": "Readable already stored task body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        ingest_capture(conn, cfg, payload)
        assert run_once(conn, cfg, worker_id="test-worker", limit=10)["stored"] == 1
        conn.execute(
            "UPDATE media_fetch_tasks SET status = 'pending', last_error = 'stale lease', lease_owner = 'old-worker', lease_until = '2099-01-01T00:00:00Z'"
        )
        conn.commit()
        summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
        task = conn.execute("SELECT status, last_error, lease_owner, lease_until FROM media_fetch_tasks").fetchone()
        assert summary["attempted"] == 0
        assert summary["already_stored"] == 1
        assert task["status"] == "succeeded"
        assert task["last_error"] is None
        assert task["lease_owner"] is None
        assert task["lease_until"] is None


def test_media_worker_rehydrates_purged_cache_when_source_still_fetchable(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/worker-rehydrate",
            "title": "Worker Rehydrate",
            "text": "Readable worker rehydrate body.",
            "media_artifacts": [{"media_type": "image", "source_url": "data:image/png;base64,iVBORw0KGgo=", "mime_type": "image/png"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        assert run_once(conn, cfg, worker_id="test-worker", limit=10)["stored"] == 1
        purged = purge_media_cache(conn, cfg, {"domain": "example.com", "dry_run": False, "rehydrate": True})
        assert purged["purged"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "purged"
        assert media["has_file"] is False
        summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
        assert summary["stored"] == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "stored"
        assert media["has_file"] is True


def test_media_worker_normalizes_terminal_failed_artifacts(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/normalize-failures",
            "title": "Normalize Failures",
            "text": "Readable worker failure classification body.",
            "media_artifacts": [
                {"media_type": "image", "source_url": "data:image/png;base64,bad", "mime_type": "image/png"},
                {"media_type": "image", "source_url": "https://example.com/missing.png", "mime_type": "image/png"},
                {"media_type": "image", "source_url": "https://example.com/rate.png", "mime_type": "image/png"},
            ],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        rows = media_artifacts_for_snapshot(conn, result["snapshot_id"])
        reasons = {
            "data:image/png;base64,bad": "invalid-data-url-payload",
            "https://example.com/missing.png": "fetch-status-404",
            "https://example.com/rate.png": "fetch-status-429",
        }
        for row in rows:
            conn.execute("UPDATE media_artifacts SET capture_status = 'failed', status_reason = ? WHERE id = ?", (reasons[row["source_url"]], row["id"]))
            conn.execute("UPDATE media_fetch_tasks SET status = 'failed', last_error = ? WHERE artifact_id = ?", (reasons[row["source_url"]], row["id"]))
        changed = normalize_terminal_failed_artifacts(conn)
        assert changed == 3
        status_by_url = {row["source_url"]: row["capture_status"] for row in media_artifacts_for_snapshot(conn, result["snapshot_id"])}
        assert status_by_url == {
            "data:image/png;base64,bad": "skipped",
            "https://example.com/missing.png": "expired",
            "https://example.com/rate.png": "retrying",
        }
        task_status_by_url = {
            row["source_url"]: row["status"]
            for row in conn.execute(
                """
                SELECT m.source_url, t.status
                FROM media_artifacts m
                JOIN media_fetch_tasks t ON t.artifact_id = m.id
                ORDER BY m.source_url
                """
            ).fetchall()
        }
        assert task_status_by_url["data:image/png;base64,bad"] == "skipped"
        assert task_status_by_url["https://example.com/missing.png"] == "skipped"
        assert task_status_by_url["https://example.com/rate.png"] == "retrying"


def test_media_worker_reclassifies_legacy_blob_video_skips_as_references(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    payload = CapturePayload.from_dict(
        {
            "url": "https://example.com/blob-video",
            "title": "Blob Video",
            "text": "Readable worker blob video classification body.",
            "media_artifacts": [{"media_type": "video", "source_url": "blob:https://example.com/abc", "mime_type": "video/mp4"}],
        },
        allow_any_url=True,
    )
    with connect(cfg.db_path) as conn:
        result = ingest_capture(conn, cfg, payload)
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        conn.execute(
            "UPDATE media_artifacts SET capture_status = 'skipped', status_reason = 'unsupported-media-url-scheme' WHERE id = ?",
            (media["id"],),
        )
        changed = normalize_legacy_blob_video_skips(conn)
        assert changed == 1
        media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
        assert media["capture_status"] == "referenced"
        assert media["status_reason"] is None


@contextmanager
def hls_fixture_server():
    init_bytes = b"\x00\x00\x00 ftypiso5"
    seg1 = b"video-segment-one"
    seg2 = b"video-segment-two"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            paths = {
                "/master.m3u8": (
                    "application/x-mpegURL",
                    b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=200,RESOLUTION=320x180\n/variant.m3u8\n",
                ),
                "/variant.m3u8": (
                    "application/vnd.apple.mpegurl",
                    b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXT-X-MAP:URI=\"/init.mp4\"\n#EXTINF:1.0,\n/seg1.m4s\n#EXTINF:1.0,\n/seg2.m4s\n#EXT-X-ENDLIST\n",
                ),
                "/audio.m3u8": (
                    "application/x-mpegURL",
                    b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:1.0,\n/audio.m4s\n#EXT-X-ENDLIST\n",
                ),
                "/mp4a/audio.m3u8": (
                    "application/x-mpegURL",
                    b"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:1.0,\n/audio.m4s\n#EXT-X-ENDLIST\n",
                ),
                "/init.mp4": ("video/mp4", init_bytes),
                "/seg1.m4s": ("video/iso.segment", seg1),
                "/seg2.m4s": ("video/iso.segment", seg2),
                "/audio.m4s": ("audio/mp4", b"audio-only"),
            }
            if self.path not in paths:
                self.send_response(404)
                self.end_headers()
                return
            content_type, body = paths[self.path]
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", init_bytes + seg1 + seg2
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_media_worker_stores_hls_master_playlist_as_video_mp4(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with hls_fixture_server() as (base_url, expected_bytes):
        payload = CapturePayload.from_dict(
            {
                "url": "https://example.com/hls-video",
                "title": "HLS Video",
                "text": "Readable worker HLS video body.",
                "media_artifacts": [{"media_type": "video", "source_url": f"{base_url}/master.m3u8"}],
            },
            allow_any_url=True,
        )
        with connect(cfg.db_path) as conn:
            result = ingest_capture(conn, cfg, payload)
            summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert summary["attempted"] == 1
            assert summary["stored"] == 1
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
            assert media["capture_status"] == "stored"
            assert media["mime_type"] == "video/mp4"
            assert media["byte_size"] == len(expected_bytes)
            assert media["has_file"] is True
            file_row = conn.execute("SELECT file_path FROM media_artifacts WHERE id = ?", (media["id"],)).fetchone()
            assert open(file_row["file_path"], "rb").read() == expected_bytes


def test_media_worker_requeues_legacy_hls_video_unsupported_skips(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with hls_fixture_server() as (base_url, _expected_bytes):
        payload = CapturePayload.from_dict(
            {
                "url": "https://example.com/hls-requeue",
                "title": "HLS Requeue",
                "text": "Readable worker HLS requeue body.",
                "media_artifacts": [{"media_type": "video", "source_url": f"{base_url}/master.m3u8", "metadata": {"cdp_recorder": True}}],
            },
            allow_any_url=True,
        )
        with connect(cfg.db_path) as conn:
            result = ingest_capture(conn, cfg, payload)
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
            conn.execute(
                "UPDATE media_artifacts SET capture_status = 'skipped', status_reason = 'unsupported-media-url-scheme' WHERE id = ?",
                (media["id"],),
            )
            conn.execute("UPDATE media_fetch_tasks SET status = 'skipped', last_error = 'unsupported-media-url-scheme' WHERE artifact_id = ?", (media["id"],))
            changed = normalize_hls_video_skips(conn)
            assert changed == 1
            summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert summary["stored"] == 1
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
            assert media["capture_status"] == "stored"
            stored_row = conn.execute("SELECT metadata_json FROM media_artifacts WHERE id = ?", (media["id"],)).fetchone()
            assert json.loads(stored_row["metadata_json"])["cdp_recorder"] is True


def test_media_worker_requeues_snapshot_budget_skips_after_cap_raise(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with hls_fixture_server() as (base_url, _expected_bytes):
        payload = CapturePayload.from_dict(
            {
                "url": "https://example.com/snapshot-budget-requeue",
                "title": "Snapshot Budget Requeue",
                "text": "Readable worker snapshot budget requeue body.",
                "media_artifacts": [{"media_type": "video", "source_url": f"{base_url}/master.m3u8"}],
            },
            allow_any_url=True,
        )
        with connect(cfg.db_path) as conn:
            result = ingest_capture(conn, cfg, payload)
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
            conn.execute(
                "UPDATE media_artifacts SET capture_status = 'skipped', status_reason = 'snapshot-media-budget' WHERE id = ?",
                (media["id"],),
            )
            conn.execute("UPDATE media_fetch_tasks SET status = 'skipped', last_error = 'snapshot-media-budget' WHERE artifact_id = ?", (media["id"],))
            changed = normalize_snapshot_budget_skips(conn)
            assert changed == 1
            task = conn.execute("SELECT status FROM media_fetch_tasks WHERE artifact_id = ?", (media["id"],)).fetchone()
            assert task["status"] == "pending"
            summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert summary["stored"] == 1
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
            assert media["capture_status"] == "stored"


def test_media_worker_keeps_hls_audio_rendition_referenced_not_skipped(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    init_db(cfg)
    with hls_fixture_server() as (base_url, _expected_bytes):
        payload = CapturePayload.from_dict(
            {
                "url": "https://example.com/hls-audio",
                "title": "HLS Audio",
                "text": "Readable worker HLS audio body.",
                "media_artifacts": [{"media_type": "video", "source_url": f"{base_url}/mp4a/audio.m3u8"}],
            },
            allow_any_url=True,
        )
        with connect(cfg.db_path) as conn:
            result = ingest_capture(conn, cfg, payload)
            summary = run_once(conn, cfg, worker_id="test-worker", limit=10)
            assert summary["stored"] == 0
            media = media_artifacts_for_snapshot(conn, result["snapshot_id"])[0]
            assert media["capture_status"] == "referenced"
            assert media["status_reason"] == "hls-audio-rendition"
            task = conn.execute("SELECT status FROM media_fetch_tasks WHERE artifact_id = ?", (media["id"],)).fetchone()
            assert task["status"] == "skipped"
