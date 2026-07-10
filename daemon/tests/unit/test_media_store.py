from browser_memory_daemon import media, media_store


def test_media_facade_preserves_admission_api_identity():
    assert media.media_storage_allowed is media_store.media_storage_allowed


def test_media_store_owns_blob_admission_and_accounting_helpers():
    assert callable(media_store.media_storage_allowed)
    assert callable(media_store.stored_media_bytes)


def test_media_facade_preserves_artifact_store_api_identity():
    assert media.purge_media_cache is media_store.purge_media_cache
    assert media.media_artifact is media_store.media_artifact
    assert media.media_artifacts_for_snapshot is media_store.media_artifacts_for_snapshot
    assert media.media_artifacts_for_document is media_store.media_artifacts_for_document
