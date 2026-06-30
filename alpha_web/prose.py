"""Render model-authored markdown into safe HTML for a chat bubble.

Sonia / the agent reply in markdown. Printing that raw gives literal `**` markers and a wall of
collapsed lines (see `partials/message_assistant.html`). We render it server-side instead.

Safety (the text is model-authored, so it must not be able to inject markup) rests on two
independent markdown-it layers, both on by default here:
  1. `html=False` makes markdown-it escape any raw HTML in the source — `<script>`, `<img onerror>`,
     event-handler attributes etc. all become inert text, never live elements.
  2. Link/image URLs are gated by `validateLink` (rejects contiguous `javascript:`/`vbscript:`/`file:`/
     non-image `data:` schemes → they fall back to literal text) AND, as the load-bearing backstop,
     `normalizeLink` percent-encodes any smuggled whitespace/control chars in a scheme (the one
     `validateLink` regex gap, e.g. `java\tscript:`), so the browser parses the result as a benign
     relative URL on the operator's own origin, not as `javascript:`.
So the rendered string is safe to emit unescaped. `breaks=True` turns a single newline into <br>,
matching how chat text is typed. Keep `normalize` on (do not pass `normalize_url=...` that defeats
layer 2) — the whitespace-scheme regression in tests/web/test_prose.py pins this.
"""
from __future__ import annotations

from markdown_it import MarkdownIt
from markupsafe import Markup

# One stateless renderer, reused across requests (.render holds no per-call state on the instance).
_MD = MarkdownIt("commonmark", {"breaks": True, "html": False})


def render_markdown(text: str | None) -> Markup:
    """Markdown string → safe HTML, wrapped in Markup so Jinja does not re-escape it."""
    return Markup(_MD.render(text or ""))
