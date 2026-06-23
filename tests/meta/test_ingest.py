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
