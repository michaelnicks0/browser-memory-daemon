from browser_memory_daemon import media, media_hls


def test_media_facade_preserves_hls_transport_api_identity():
    assert media._HlsFetchBudget is media_hls._HlsFetchBudget
    assert media._fetch_hls_media_bytes is media_hls._fetch_hls_media_bytes
    assert media._hls_playlist_to_media is media_hls._hls_playlist_to_media
