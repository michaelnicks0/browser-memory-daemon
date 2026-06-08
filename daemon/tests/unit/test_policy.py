from browser_memory_daemon.policy import evaluate_capture, redact_text, redact_url


def test_blocks_incognito_and_sensitive_urls():
    blocked = [
        "https://example.com/account/settings",
        "https://admin.example.com/",
        "https://accounts.google.com/",
        "https://chase.com/",
        "https://www.chase.com/",
        "https://secure.chase.com/dashboard",
        "https://bankofamerica.com/",
        "https://www.bankofamerica.com/",
        "https://paypal.com/billing",
        "https://legal.example.com/",
        "chrome://settings",
        "file:///tmp/test.html",
        "http://127.0.0.1:3000/admin",
        "http://127.1/private",
        "http://localhost.:3000/private",
        "https://mail.google.com/mail/u/0/",
        "https://mychart.example.org/visit",
    ]
    for url in blocked:
        assert not evaluate_capture(url).allowed, url
    assert not evaluate_capture("https://example.com", is_incognito=True).allowed


def test_allows_public_docs_url():
    decision = evaluate_capture("https://developer.chrome.com/docs/extensions/")
    assert decision.allowed
    assert decision.reason == "allowed"


def test_redacts_before_storage_classes():
    fake_api_secret = "abcdefghijklmnopqrstuvwxyz123"
    fake_bearer = "abcdefghijklmnopqrstuvwxyz1234567890"
    text = f"token = {fake_api_secret} Bearer {fake_bearer} 123-45-6789"
    redacted, count, classes = redact_text(text)
    assert count >= 3
    assert "abcdefghijklmnopqrstuvwxyz123" not in redacted
    assert "123-45-6789" not in redacted
    assert {"api_key", "bearer_token", "ssn"}.issubset(set(classes))


def test_redacts_url_query_and_fragment():
    url = "https://example.com/read?token=abc123&ok=1#secret-fragment"
    safe_url, count, classes = redact_url(url)
    assert count == 2
    assert "abc123" not in safe_url
    assert "secret-fragment" not in safe_url
    assert "url_secret" in classes
