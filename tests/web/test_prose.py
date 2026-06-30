"""The assistant-bubble markdown renderer: structure in, safe HTML out.

Sonia/agent replies are markdown (bold, numbered/bulleted lists, headings, code). The cockpit
used to print that text raw, so `**bold**` showed literal asterisks and every newline collapsed
into one wall of text. `render_markdown` turns it into real HTML — and, because the text is
model-authored, the renderer must NOT let raw HTML or javascript: links through.
"""
from markupsafe import Markup

from alpha_web.prose import render_markdown


def test_bold_and_lists_become_real_html():
    out = render_markdown("intro line\n\n1. **First** pick\n2. **Second** pick\n\n- a\n- b")
    assert isinstance(out, Markup)              # Markup → Jinja won't re-escape it
    assert "<strong>First</strong>" in out
    assert "<ol>" in out and "<ul>" in out
    assert "<li>" in out
    assert "**" not in out                      # the asterisk markers are consumed, not printed


def test_headings_and_inline_code_render():
    out = render_markdown("# Title\n\nuse `base_breakout` here")
    assert "<h1>" in out
    assert "<code>base_breakout</code>" in out


def test_raw_html_in_model_text_is_escaped_not_injected():
    out = render_markdown("hi <script>alert(1)</script> <img src=x onerror=alert(2)>")
    # The whole tag is escaped to inert text — no live element survives (the `onerror=` substring
    # lives on, but harmlessly, inside `&lt;img …&gt;`).
    assert "<script" not in out
    assert "<img" not in out
    assert "&lt;script&gt;" in out              # shown as text, harmless


def test_dangerous_link_scheme_is_neutralised():
    out = render_markdown("[click](javascript:alert(1))")
    assert 'href="javascript:' not in out.lower()


def test_whitespace_smuggled_scheme_is_percent_encoded_not_executable():
    # validateLink's regex only catches a *contiguous* bad scheme, so `java<tab>script:` slips the
    # gate — but normalizeLink percent-encodes the tab (→ %09), so the browser sees a benign relative
    # URL, never `javascript:`. Pin both layers: no contiguous js href, and the control char is encoded.
    out = render_markdown("[a](<java\tscript:alert(1)>)")
    lo = out.lower()
    assert 'href="javascript:' not in lo          # no executable scheme reaches the DOM
    assert "\t" not in out                         # the smuggled control char was percent-encoded
    assert "%09" in out                            # ← normalizeLink, the load-bearing backstop


def test_empty_or_none_is_safe():
    assert render_markdown("") == ""
    assert render_markdown(None) == ""
