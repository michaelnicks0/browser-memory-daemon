import ast
from pathlib import Path

from browser_memory_daemon import media, media_fetch, media_transport


def test_media_facade_preserves_guarded_fetch_api_identity():
    assert media._fetch_media_bytes is media_transport._fetch_media_bytes
    assert media._fetch_media_stream is media_transport._fetch_media_stream
    assert media._guarded_public_fetch is media_fetch._guarded_public_fetch
    assert media._safe_response_mime is media_fetch._safe_response_mime


def test_guarded_fetch_layer_does_not_depend_on_hls_or_coordinator():
    module = ast.parse(Path(media_fetch.__file__).read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "media_hls" not in imported_modules
    assert "media_transport" not in imported_modules
