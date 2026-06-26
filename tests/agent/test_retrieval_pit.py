from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.memory import Lesson
from alpha.harness.state import HarnessState
from alpha.agent.retrieval import select_for_prompt


def _h_with_lessons():
    lessons = [
        Lesson(lesson_id="seed", outcome="principle", lesson="seed rule"),                  # learned_asof None
        Lesson(lesson_id="future", outcome="loss", lesson="learned on D",
               learned_asof=date(2026, 6, 12)),
    ]
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons(lessons))


def test_future_lesson_masked_before_its_asof():
    sel = select_for_prompt(_h_with_lessons(), phase_prior=None, asof=date(2026, 6, 11))
    ids = {l.lesson_id for l in sel.lessons}
    assert ids == {"seed"}                       # the future lesson is hidden at D-1; the seed stays


def test_future_lesson_visible_on_its_asof():
    sel = select_for_prompt(_h_with_lessons(), phase_prior=None, asof=date(2026, 6, 12))
    assert {l.lesson_id for l in sel.lessons} == {"seed", "future"}


def test_no_asof_means_no_gate():
    sel = select_for_prompt(_h_with_lessons(), phase_prior=None)   # asof omitted
    assert {l.lesson_id for l in sel.lessons} == {"seed", "future"}


def test_accepts_datetime_asof_directly():
    """Passing a datetime directly must not raise and must mask the future lesson."""
    from datetime import datetime
    sel = select_for_prompt(_h_with_lessons(), phase_prior=None,
                            asof=datetime(2026, 6, 11, 16, 0))
    ids = {l.lesson_id for l in sel.lessons}
    # datetime(2026,6,11,...) normalises to date(2026,6,11) → same as the existing mask test
    assert ids == {"seed"}


def test_plain_date_asof_unchanged():
    """A plain date still works after the normalisation guard is in place."""
    sel = select_for_prompt(_h_with_lessons(), phase_prior=None,
                            asof=date(2026, 6, 12))
    assert {l.lesson_id for l in sel.lessons} == {"seed", "future"}
