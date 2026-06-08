import json
import threading

import pytest

from browser_memory_daemon.app import make_server
from browser_memory_daemon.cli import main
from browser_memory_daemon.config import load_config


@pytest.fixture()
def cli_server(tmp_path):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", host="127.0.0.1", port=0)
    srv = make_server(cfg)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()
        thread.join(timeout=5)


def _base_args(port):
    return ["--host", "127.0.0.1", "--port", str(port), "--token", "test-token"]


def _last_json(capsys):
    out = capsys.readouterr().out
    return json.loads(out)


def test_cli_admin_commands(cli_server, capsys):
    assert main(_base_args(cli_server) + [
        "capture-fixture",
        "--url",
        "https://cli.example/stirling",
        "--title",
        "CLI Stirling",
        "--text",
        "CLI admin command fixture text.",
    ]) == 0
    stored = _last_json(capsys)
    assert stored["stored"] is True

    assert main(_base_args(cli_server) + ["recent", "--limit", "1"]) == 0
    recent = _last_json(capsys)
    assert recent["results"][0]["title"] == "CLI Stirling"

    assert main(_base_args(cli_server) + ["document", stored["document_id"]]) == 0
    document = _last_json(capsys)
    assert document["document"]["title"] == "CLI Stirling"

    assert main(_base_args(cli_server) + ["snapshot", stored["snapshot_id"]]) == 0
    snapshot = _last_json(capsys)
    assert "CLI admin command fixture text" in snapshot["text"]

    assert main(_base_args(cli_server) + ["doctor"]) == 0
    doctor = _last_json(capsys)
    assert doctor["ok"] is True

    assert main(_base_args(cli_server) + ["policy-rules", "--block-domain", "cli-block.example"]) == 0
    rule = _last_json(capsys)
    assert rule["rule"]["pattern"] == "cli-block.example"
