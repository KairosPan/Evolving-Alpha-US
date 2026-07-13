import pytest
from alpha.meta.ingest import from_text, fetch_url, IngestError


def test_from_text_builds_source():
    s = from_text("hello body", title="note")
    assert s.kind == "text" and s.text == "hello body" and s.title == "note" and s.fetched_at


def test_fetch_url_strips_html_via_injected_fetcher():
    html = "<html><head><title>Squeeze 101</title></head><body><p>High SI.</p><script>x=1</script></body></html>"
    s = fetch_url("http://example.com/a", fetcher=lambda u: html)
    assert s.kind == "url" and s.url == "http://example.com/a"
    assert "High SI." in s.text and "x=1" not in s.text and s.title == "Squeeze 101"


def test_fetch_url_failure_raises_ingesterror():
    def boom(u):
        raise OSError("no network")
    with pytest.raises(IngestError):
        fetch_url("http://example.com/a", fetcher=boom)


def test_fetch_url_rejects_non_http_schemes_no_file_disclosure():
    """Security: file:// / ftp:// must be rejected (no Local File Disclosure via urlopen)."""
    import pytest as _pytest
    from alpha.meta.ingest import fetch_url, IngestError
    for bad in ("file:///etc/passwd", "ftp://example.com/x", "gopher://x", "data:text/plain,hi"):
        with _pytest.raises(IngestError):
            fetch_url(bad)            # no fetcher injected -> must be blocked BEFORE any real fetch


def test_default_fetcher_blocks_private_and_metadata_ssrf():
    """The default (non-injected) fetcher routes through netguard: a private/metadata destination is
    blocked as an IngestError before any body is returned — the A9 SSRF precondition, offline."""
    for bad in ("http://127.0.0.1:6379/", "http://169.254.169.254/latest/meta-data/",
                "http://10.0.0.5/", "http://[::1]/"):
        with pytest.raises(IngestError):
            fetch_url(bad)            # no fetcher injected -> netguard rejects the IP literal, no socket
