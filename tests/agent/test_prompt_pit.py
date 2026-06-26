from datetime import date, datetime
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.memory import Lesson
from alpha.harness.state import HarnessState
from alpha.agent.prompt import build_system_prompt


def _h():
    lessons = [
        Lesson(lesson_id="seed", outcome="principle", lesson="SEED_RULE_TEXT"),
        Lesson(lesson_id="future", outcome="loss", lesson="FUTURE_LESSON_TEXT",
               learned_asof=date(2026, 6, 12)),
    ]
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons(lessons))


def test_full_mode_masks_future_lesson():
    before = build_system_prompt(_h(), injection="full", asof=datetime(2026, 6, 11, 16, 0))
    on = build_system_prompt(_h(), injection="full", asof=datetime(2026, 6, 12, 16, 0))
    assert "FUTURE_LESSON_TEXT" not in before and "SEED_RULE_TEXT" in before
    assert "FUTURE_LESSON_TEXT" in on


def test_retrieval_mode_masks_future_lesson():
    before = build_system_prompt(_h(), injection="retrieval", asof=datetime(2026, 6, 11, 16, 0))
    on = build_system_prompt(_h(), injection="retrieval", asof=datetime(2026, 6, 12, 16, 0))
    assert "FUTURE_LESSON_TEXT" not in before and "SEED_RULE_TEXT" in before
    assert "FUTURE_LESSON_TEXT" in on


def test_no_asof_renders_all_lessons():
    out = build_system_prompt(_h(), injection="full")     # asof omitted -> no gate
    assert "FUTURE_LESSON_TEXT" in out and "SEED_RULE_TEXT" in out
