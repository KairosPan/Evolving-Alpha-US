# tests/refine/test_forge_propose.py
from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.forge import propose_skill_ops

def _skill(sid, status, stats=None):
    return Skill(skill_id=sid, name=sid, type="pattern", family="runner", phases=["trend"],
                 status=status, stats=stats or SkillStats())

def _h(*skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(list(skills)),
                        memory=MemoryStore.from_lessons([]))

def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s

_ep_counter = 0

def _ep(skill_id, outcome, adv, sym="RUN", exit_d=date(2026, 6, 3)):
    """Each call gets a unique episode_id (counter suffix) so INSERT OR IGNORE keeps all N rows."""
    global _ep_counter
    _ep_counter += 1
    return Episode(episode_id=f"{skill_id}:{sym}:{outcome}:{adv}:{exit_d}:{_ep_counter}", symbol=sym, skill_id=skill_id,
                   entry_date=date(2026, 6, 1), exit_date=exit_d, outcome=outcome, advantage=adv)

def test_incubating_strong_positive_proposes_promote():
    h = _h(_skill("s1", "incubating"))
    # n=5, win_rate=0.8, mean_adv>0 — use list-comp so _ep is called 5 distinct times
    eps = [_ep("s1", "continued", 2.0) for _ in range(4)] + [_ep("s1", "faded", 0.5)]
    ops = propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20))
    assert len(ops) == 1 and ops[0].tool == "promote_skill" and ops[0].args["skill_id"] == "s1"
    assert ops[0].rationale                                              # carries evidence

def test_active_strong_negative_proposes_soft_retire():
    h = _h(_skill("s2", "active"))
    # n=5, nuke_rate=0.6 — use list-comp so _ep is called 5 distinct times
    eps = [_ep("s2", "nuked", -2.0) for _ in range(3)] + [_ep("s2", "continued", 1.0) for _ in range(2)]
    ops = propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20))
    assert len(ops) == 1 and ops[0].tool == "retire_skill"
    assert ops[0].args["skill_id"] == "s2" and ops[0].args["permanent"] is False   # soft demote

def test_status_gates_the_direction():
    # an ACTIVE skill with great stats is NOT promoted; an INCUBATING skill with nukes is NOT retired
    h = _h(_skill("act", "active"), _skill("inc", "incubating"))
    eps = ([_ep("act", "continued", 2.0) for _ in range(5)] +
           [_ep("inc", "nuked", -2.0) for _ in range(5)])
    ops = propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20))
    assert ops == []

def test_below_sample_floor_no_op():
    h = _h(_skill("s5", "incubating"))
    eps = [_ep("s5", "continued", 2.0) for _ in range(2)]              # n=2 < 5
    assert propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20)) == []

def test_pit_excludes_future_episodes():
    h = _h(_skill("s1", "incubating"))
    # learned_asof=exit_date=2026-09-01 > asof=2026-06-20, so for_asof returns []
    eps = [_ep("s1", "continued", 2.0, exit_d=date(2026, 9, 1)) for _ in range(5)]
    assert propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20)) == []
