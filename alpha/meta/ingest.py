from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Callable
from urllib.request import Request, urlopen

from alpha.meta.models import LessonSource


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
    req = Request(url, headers={"User-Agent": "evolving-alpha-cockpit/1.0"})
    with urlopen(req, timeout=15) as resp:           # noqa: S310 (operator-supplied URL, localhost tool)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def fetch_url(url: str, *, fetcher: Callable[[str], str] | None = None) -> LessonSource:
    fetch = fetcher or _urllib_fetcher
    try:
        raw = fetch(url)
    except Exception as e:                            # network/decode/etc -> friendly route message
        raise IngestError(f"could not fetch {url}: {type(e).__name__}: {e}") from e
    parser = _TextExtractor()
    parser.feed(raw)
    return LessonSource(kind="url", url=url, title=parser.title, text=parser.text(), fetched_at=_now())
