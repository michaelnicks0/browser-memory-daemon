from browser_memory_daemon import media, media_fetch


def test_media_facade_preserves_guarded_fetch_api_identity():
    assert media._fetch_media_bytes is media_fetch._fetch_media_bytes
    assert media._guarded_public_fetch is media_fetch._guarded_public_fetch
    assert media._safe_response_mime is media_fetch._safe_response_mime
