import json
import threading
import urllib.parse
import urllib.request

from browser_memory_daemon.app import make_server
from browser_memory_daemon.config import load_config


def request(method, url, token="test-token", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, json.loads(response.read().decode() or "{}")


def test_http_capture_search_forget_round_trip(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0)
    server = make_server(cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, health = request("GET", f"{base}/health", token=None)
        assert status == 200
        assert health["ok"] is True

        try:
            request("POST", f"{base}/capture", token="wrong", body={"url": "https://example.com", "text": "x"})
            raise AssertionError("unauthorized request should fail")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401

        status, blocked = request("POST", f"{base}/capture", body={"url": "https://mail.google.com/mail", "text": "private"})
        assert status == 200
        assert blocked["stored"] is False

        status, stored = request("POST", f"{base}/capture", body={
            "url": "https://example.org/stirling",
            "title": "Synthetic Stirling Article",
            "text": "Low temperature differential Stirling engines are memorable.",
        })
        assert status == 201
        assert stored["stored"] is True

        q = urllib.parse.urlencode({"q": "Stirling", "limit": "3"})
        status, found = request("GET", f"{base}/search?{q}")
        assert status == 200
        assert found["results"][0]["title"] == "Synthetic Stirling Article"

        bad_q = urllib.parse.urlencode({"q": '"unterminated', "limit": "3"})
        status, malformed = request("GET", f"{base}/search?{bad_q}")
        assert status == 200
        assert "results" in malformed

        try:
            request("GET", f"{base}/search?q=x&limit=not-int")
            raise AssertionError("invalid limit should fail")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

        status, receipt = request("POST", f"{base}/forget", body={"domain": "example.org"})
        assert status == 200
        assert receipt["counts"]["documents"] == 1

        status, found_after = request("GET", f"{base}/search?{q}")
        assert found_after["results"] == []
    finally:
        server.shutdown()
        thread.join(timeout=5)
