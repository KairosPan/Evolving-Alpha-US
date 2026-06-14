from alpha.harness.skill import Skill, SkillStats
from alpha.harness.memory import Lesson, Importance
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.agent.retrieval import select_for_prompt


def _skill(sid, status="active", phases=("trend",), n=0, family="runner"):
    return Skill(skill_id=sid, name=sid, type="pattern", family=family, phases=list(phases),
                 status=status, stats=SkillStats(n=n))


def _h():
    skills = SkillRegistry.from_skills([
        _skill("hit", phases=["trend"], n=1), _skill("miss", phases=["washout"], n=9),
        _skill("inc", status="incubating"),
    ])
    memory = MemoryStore.from_lessons([
        Lesson(lesson_id="strong", phases=["trend"], outcome="principle", lesson="x",
               importance=Importance(base=1.0)),
        Lesson(lesson_id="weak", phases=["trend"], outcome="loss", lesson="y",
               importance=Importance(base=0.05)),     # below MIN_MEMORY_WEIGHT -> dropped
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=memory)


def test_phase_hit_ranked_first():
    sel = select_for_prompt(_h(), phase_prior="trend", skill_budget=5)
    assert [s.skill_id for s in sel.skills] == ["hit", "miss"]   # 'hit' matches phase, ranked first
    assert [s.skill_id for s in sel.trials] == ["inc"]           # incubating -> trial slot
    assert [l.lesson_id for l in sel.lessons] == ["strong"]      # weak lesson dropped (low weight)


def test_budget_truncates():
    sel = select_for_prompt(_h(), phase_prior="trend", skill_budget=1)
    assert len(sel.skills) == 1 and sel.skills[0].skill_id == "hit"


def test_no_phase_prior_falls_back_to_stats():
    sel = select_for_prompt(_h(), phase_prior=None, skill_budget=5)
    # no phase hit dimension -> order by stats.n desc: 'miss' (n=9) before 'hit' (n=1)
    assert [s.skill_id for s in sel.skills] == ["miss", "hit"]
