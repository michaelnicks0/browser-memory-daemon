import io

from browser_memory_daemon import media, media_hls
from browser_memory_daemon.config import load_config


def test_media_facade_preserves_hls_transport_api_identity():
    assert media._HlsFetchBudget is media_hls._HlsFetchBudget
    assert media._fetch_hls_media_bytes is media_hls._fetch_hls_media_bytes
    assert media._hls_playlist_to_media is media_hls._hls_playlist_to_media


def test_hls_assembly_streams_segments_without_joining_whole_artifact(tmp_path, monkeypatch):
    cfg = load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all")
    payloads = {
        "https://cdn.example/seg-1.ts": b"segment-one",
        "https://cdn.example/seg-2.ts": b"segment-two",
    }

    def fake_fetch(source_url, _page_url, *, output_stream=None, **_kwargs):
        content = payloads[source_url]
        if output_stream is not None:
            output_stream.write(content)
            return b"", ""
        return content, ""

    monkeypatch.setattr(media_hls, "_fetch_hls_asset", fake_fetch)
    output = io.BytesIO()
    content, mime_type, reason = media_hls._hls_playlist_to_media(
        "https://cdn.example/playlist.m3u8",
        "https://example.org/page",
        "#EXTM3U\nseg-1.ts\nseg-2.ts\n",
        max_bytes=100,
        timeout_seconds=1,
        config=cfg,
        budget=media_hls._HlsFetchBudget(requests_remaining=4, deadline=None),
        output_stream=output,
    )

    assert content == b""
    assert mime_type == "video/mp2t"
    assert reason == ""
    assert output.getvalue() == b"segment-onesegment-two"
