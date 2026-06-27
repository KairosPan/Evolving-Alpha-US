# tests/refine/test_forge_apply.py
from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.forge import forge_skills

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

def _wins(skill_id, n=5):
    return [Episode(episode_id=f"{skill_id}:{i}", symbol="RUN", skill_id=skill_id,
                    entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3), outcome="continued", advantage=2.0)
            for i in range(n)]

def _nukes(skill_id, n=5):
    return [Episode(episode_id=f"{skill_id}:{i}", symbol="RUN", skill_id=skill_id,
                    entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3), outcome="nuked", advantage=-2.0)
            for i in range(n)]

def test_applies_when_both_floors_agree():
    # incubating, episode evidence promotes AND skill.stats clears the gate (n>=3, expectancy>0)
    h = _h(_skill("s1", "incubating", SkillStats(n=5, expectancy=1.0)))
    log = EditLog()
    rep = forge_skills(h, _store(*_wins("s1")), MetaTools(h, log), asof=date(2026, 6, 20))
    assert rep.applied == ["s1"] and h.skills.get("s1").status == "active"   # promoted

def test_double_gate_rejects_when_skill_stats_disagree():
    # episodes say promote, but skill.stats.expectancy <= 0 -> the gate blocks it
    h = _h(_skill("s2", "incubating", SkillStats(n=5, expectancy=-0.5)))
    log = EditLog()
    rep = forge_skills(h, _store(*_wins("s2")), MetaTools(h, log), asof=date(2026, 6, 20))
    assert rep.applied == [] and any(sid == "s2" for sid, _ in rep.rejected)
    assert h.skills.get("s2").status == "incubating"                        # unchanged

def test_teaching_owned_contest_is_held():
    # an active teaching-owned skill the episodes want to retire -> HELD (with a conflict_queue), not retired
    h = _h(_skill("s3", "active", SkillStats(n=10, expectancy=0.1)))
    log = EditLog()
    # stamp s3 as teaching-owned in the log (a prior teaching create/promote)
    log.append("promote_skill", "skill", "s3", "promote")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    class _Q:
        def __init__(self): self.items = []
        def add(self, **kw): self.items.append(kw)
    q = _Q()
    rep = forge_skills(h, _store(*_nukes("s3")), MetaTools(h, log), asof=date(2026, 6, 20), conflict_queue=q)
    assert rep.held == ["s3"] and len(q.items) == 1
    assert h.skills.get("s3").status == "active"                            # not retired (held)
