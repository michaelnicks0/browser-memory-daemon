from browser_memory_daemon.normalize import domain_from_url, normalize_url


def test_normalize_url_removes_tracking_fragment_default_port_and_sorts_query():
    assert (
        normalize_url("HTTPS://Example.COM:443/article?utm_source=newsletter&b=2&a=1#section")
        == "https://example.com/article?a=1&b=2"
    )


def test_normalize_url_preserves_meaningful_duplicate_query_values():
    assert (
        normalize_url("https://example.com/search?tag=python&utm_medium=social&tag=sqlite")
        == "https://example.com/search?tag=python&tag=sqlite"
    )


def test_normalize_url_removes_empty_default_path_only_for_missing_path():
    assert normalize_url("https://example.com") == "https://example.com/"
    assert normalize_url("https://example.com/docs/") == "https://example.com/docs/"


def test_domain_from_url_lowercases_hostname():
    assert domain_from_url("https://WWW.Example.COM:443/docs") == "www.example.com"
