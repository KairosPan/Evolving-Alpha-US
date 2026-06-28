"""PIT-gated recall in the conversational system prompt — regression + behavioural tests."""
from datetime import date
from alpha.converse.agent import build_system_prompt
from alpha.converse.registry import ToolRegistry
from alpha.harness.loader import load_seeds
from alpha.harness.memory import Lesson

_MARKER = "FUTURE_LESSON_MARKER"


def _harness_with_lesson(learned):
    h = load_seeds("seeds")
    h.memory.add(Lesson(lesson_id="L_future", lesson=_MARKER, outcome="principle", learned_asof=learned))
    return h


def test_recalled_lesson_appears_when_unmasked():
    """Lesson learned 2026-01-10 is visible when asof=2026-02-01 (learned_asof <= asof)."""
    h = _harness_with_lesson(date(2026, 1, 10))
    out = build_system_prompt(h, ToolRegistry(), asof=date(2026, 2, 1))
    assert _MARKER in out


def test_future_lesson_masked_for_past_asof():
    """Lesson learned 2026-03-01 is absent when asof=2026-01-01 (PIT firewall regression)."""
    h = _harness_with_lesson(date(2026, 3, 1))
    out = build_system_prompt(h, ToolRegistry(), asof=date(2026, 1, 1))
    assert _MARKER not in out


def test_default_asof_none_keeps_existing_shape():
    """Default asof=None preserves TOOLS: and DOCTRINE: in the prompt."""
    h = load_seeds("seeds")
    out = build_system_prompt(h, ToolRegistry())
    assert "TOOLS:" in out
    assert "DOCTRINE:" in out
