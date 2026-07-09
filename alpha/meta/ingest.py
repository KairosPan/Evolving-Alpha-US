from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# Only fetch over http(s). Blocks file:// / ftp:// / gopher:// / data: — closing the Local File
# Disclosure / SSRF-by-scheme vector that urllib.urlopen otherwise honors. (Private-IP-range SSRF
# blocking is a separate hardening still gated on non-localhost serving — see the spec roadmap.)
_ALLOWED_SCHEMES = ("http", "https")

from alpha.meta.models import Attachment, LessonSource


class IngestError(Exception):
    """A URL could not be fetched/parsed; the route turns this into 'paste the text instead'."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def from_text(text: str, title: str = "") -> LessonSource:
    return LessonSource(kind="text", title=title, text=text, fetched_at=_now())


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "head", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()
        elif self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def _urllib_fetcher(url: str) -> str:
    req = Request(url, headers={"User-Agent": "sonia-kairos-cockpit/1.0"})
    with urlopen(req, timeout=15) as resp:           # noqa: S310 (operator-supplied URL, localhost tool)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def fetch_url(url: str, *, fetcher: Callable[[str], str] | None = None) -> LessonSource:
    scheme = urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise IngestError(f"only http(s) URLs are allowed (got {scheme or 'no'} scheme) — "
                          "paste the text instead")
    fetch = fetcher or _urllib_fetcher
    try:
        raw = fetch(url)
    except Exception as e:                            # network/decode/etc -> friendly route message
        raise IngestError(f"could not fetch {url}: {type(e).__name__}: {e}") from e
    parser = _TextExtractor()
    parser.feed(raw)
    return LessonSource(kind="url", url=url, title=parser.title, text=parser.text(), fetched_at=_now())


# ---------------------------------------------------------------------------
# ingest_attachments — file/URL ingestion for the chat cockpit composer
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_TEXT_EXT = {".txt", ".md", ".csv"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_TEXT = 50_000


def _ext(name: str) -> str:
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


def _cap(text: str) -> str:
    return text if len(text) <= _MAX_TEXT else text[:_MAX_TEXT] + "\n\n[... truncated ...]"


def _pdf_text(data: bytes) -> str:
    try:
        import pypdf
    except ImportError as e:
        raise IngestError("PDF support needs pypdf (pip install -e '.[web]')") from e
    try:
        reader = pypdf.PdfReader(BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except IngestError:
        raise
    except Exception as e:
        raise IngestError(f"could not read PDF: {type(e).__name__}") from e


def ingest_attachments(text: str, files=None, *, fetcher=None) -> tuple[str, list[Attachment]]:
    """(clean_text, attachments) from composer text + uploaded (filename, bytes) files. txt/md/csv
    decoded, pdf via pypdf, images rejected (no vision), unknown rejected; http(s) URLs in `text`
    fetched via the scheme-allowlisted fetch_url. Never raises — bad inputs become note attachments."""
    out: list[Attachment] = []
    for name, data in (files or []):
        ext = _ext(name)
        if ext in _IMAGE_EXT:
            out.append(Attachment(kind="file", name=name, mime="image",
                                  text=f"[image '{name}' attached — Sonia can't read images; describe it in text]"))
            continue
        try:
            if ext == ".pdf":
                body = _pdf_text(data)
            elif ext in _TEXT_EXT:
                body = data.decode("utf-8", errors="replace")
            else:
                out.append(Attachment(kind="file", name=name,
                                      text=f"[unsupported file '{name}' — paste the text instead]"))
                continue
        except IngestError as e:
            out.append(Attachment(kind="file", name=name, text=f"[{e}]"))
            continue
        out.append(Attachment(kind="file", name=name, text=_cap(body)))
    for url in _URL_RE.findall(text or ""):
        try:
            src = fetch_url(url, fetcher=fetcher)
            out.append(Attachment(kind="url", name=url, text=_cap(src.text)))
        except IngestError as e:
            out.append(Attachment(kind="url", name=url, text=f"[{e}]"))
    return (text or "").strip(), out
