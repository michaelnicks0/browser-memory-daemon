import io
import json

from browser_memory_daemon.http_server import (
    begin_request,
    send_response_headers,
    set_request_route,
    stream_response_body,
    write_response_bytes,
)


class _Handler:
    command = "GET"

    def __init__(self, writer) -> None:
        self.wfile = writer
        self.close_connection = False


class _BrokenWriter:
    def write(self, _content: bytes) -> int:
        raise BrokenPipeError("client went away")


class _HeaderHandler(_Handler):
    def send_response(self, _status: int) -> None:
        return None

    def send_header(self, _name: str, _value: str) -> None:
        return None

    def end_headers(self) -> None:
        self.wfile.write(b"headers")


class _FailingStream:
    def read(self, _size: int) -> bytes:
        raise OSError("private disk path must not be logged")


def _event(capsys) -> dict:
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_response_write_disconnect_is_swallowed_and_recorded_without_second_response(capsys):
    handler = _Handler(_BrokenWriter())
    begin_request(handler)
    set_request_route(handler, "media-artifact-get")

    assert write_response_bytes(handler, b"payload", status=200) is False
    assert handler.close_connection is True
    event = _event(capsys)
    event["request_id"] = "ignored"
    event["latency_ms"] = 0
    assert event == {
        "event": "http.request",
        "request_id": "ignored",
        "method": "GET",
        "route": "media-artifact-get",
        "status": 499,
        "latency_ms": 0,
        "error_code": "client_disconnected",
    }


def test_header_disconnect_is_swallowed_before_a_response_body_is_attempted(capsys):
    handler = _HeaderHandler(_BrokenWriter())
    begin_request(handler)
    set_request_route(handler, "media-blob-put")

    assert send_response_headers(handler, 400, [("Content-Length", "2")]) is False
    assert handler.close_connection is True
    event = _event(capsys)
    assert event["status"] == 499
    assert event["error_code"] == "client_disconnected"


def test_stream_response_bounds_reads_and_classifies_source_failure(capsys):
    successful_handler = _Handler(io.BytesIO())
    begin_request(successful_handler)
    set_request_route(successful_handler, "media-artifact-get")
    stream = io.BytesIO(b"a" * (64 * 1024 + 7))

    assert stream_response_body(successful_handler, stream, status=200) is True
    assert successful_handler.wfile.getvalue() == b"a" * (64 * 1024 + 7)
    success = _event(capsys)
    assert success["status"] == 200
    assert success["error_code"] is None

    incomplete_handler = _Handler(io.BytesIO())
    begin_request(incomplete_handler)
    set_request_route(incomplete_handler, "media-artifact-get")
    assert stream_response_body(incomplete_handler, io.BytesIO(b"short"), status=200, expected_bytes=10) is False
    incomplete = _event(capsys)
    assert incomplete["status"] == 500
    assert incomplete["error_code"] == "response_stream_incomplete"

    failing_handler = _Handler(io.BytesIO())
    begin_request(failing_handler)
    set_request_route(failing_handler, "media-artifact-get")
    assert stream_response_body(failing_handler, _FailingStream(), status=200) is False
    assert failing_handler.close_connection is True
    failure = _event(capsys)
    assert failure["status"] == 500
    assert failure["error_code"] == "response_stream_failed"
    assert "private disk path" not in json.dumps(failure)
