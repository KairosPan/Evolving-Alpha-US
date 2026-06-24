from alpha.meta.ingest import ingest_attachments


def test_text_file_decoded_and_text_preserved():
    clean, atts = ingest_attachments("plain prose", files=[("notes.md", b"# Heading\nbody")])
    assert clean == "plain prose"
    assert atts[0].kind == "file" and atts[0].name == "notes.md" and "Heading" in atts[0].text


def test_image_is_rejected_with_a_friendly_note():
    _, atts = ingest_attachments("", files=[("chart.png", b"\x89PNG\r\n")])
    assert len(atts) == 1 and "can't read images" in atts[0].text.lower()


def test_unknown_type_rejected():
    _, atts = ingest_attachments("", files=[("a.bin", b"\x00\x01")])
    assert "unsupported" in atts[0].text.lower()


def test_url_detected_and_fetched_via_injected_fetcher():
    html = "<html><head><title>Squeeze</title></head><body>short interest spikes</body></html>"
    _, atts = ingest_attachments("see https://example.com/post", fetcher=lambda _u: html)
    url_atts = [a for a in atts if a.kind == "url"]
    assert url_atts and "short interest spikes" in url_atts[0].text


def test_dead_url_becomes_a_note_not_a_crash():
    def boom(_u): raise RuntimeError("no net")
    _, atts = ingest_attachments("https://example.com", fetcher=boom)
    assert atts and "could not fetch" in atts[0].text


def test_pdf_text_extraction_when_pypdf_present():
    import pytest
    pypdf = pytest.importorskip("pypdf")
    import io
    w = pypdf.PdfWriter()
    w.add_blank_page(width=72, height=72)
    buf = io.BytesIO(); w.write(buf)
    _, atts = ingest_attachments("", files=[("doc.pdf", buf.getvalue())])
    assert atts[0].kind == "file" and atts[0].name == "doc.pdf"   # parses without raising


def test_corrupt_pdf_becomes_friendly_note_not_a_crash():
    """A corrupt/invalid PDF must never raise — it must become a note attachment."""
    import pytest
    pytest.importorskip("pypdf")
    # Bytes that begin with %PDF- but are otherwise pure garbage, reliably making
    # pypdf raise PdfStreamError / PdfReadError during parse.
    corrupt = b"%PDF-1.4\n" + b"\x00\xff\xfe\xfd" * 64
    _, atts = ingest_attachments("", files=[("bad.pdf", corrupt)])
    assert len(atts) == 1
    assert atts[0].kind == "file" and atts[0].name == "bad.pdf"
    assert "could not read PDF" in atts[0].text
