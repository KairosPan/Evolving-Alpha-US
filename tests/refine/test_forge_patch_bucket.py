# tests/refine/test_forge_patch_bucket.py
"""P7 forge refinements: per-phase/narrative bucketed promotion evidence + patch-on-promote."""
from datetime import date

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.forge import forge_skills, propose_skill_ops

ASOF = date(2026, 6, 20)
_n = 0


def _skill(sid, status, *, phases=("trend",), applies_all=False, stats=None):
    return Skill(skill_id=sid, name=sid, type="pattern", family="runner", phases=list(phases),
                 applies_all_phases=applies_all, status=status, stats=stats or SkillStats())


def _h(*skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(list(skills)),
                        memory=MemoryStore.from_lessons([]))


def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s


def _ep(skill_id, outcome, adv, *, phase="trend", narrative="", sym="RUN"):
    global _n
    _n += 1
    return Episode(episode_id=f"{skill_id}:{phase}:{narrative}:{outcome}:{adv}:{_n}", symbol=sym,
                   skill_id=skill_id, phase=phase, narrative=narrative,
                   entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3), outcome=outcome, advantage=adv)


def _mixed_phase_eps(sid):
    # trend bucket: strong (win_rate 0.8, n=5, mean_adv>0); flush bucket: all nuked (drags the GLOBAL down)
    return ([_ep(sid, "continued", 2.0, phase="trend") for _ in range(4)]
            + [_ep(sid, "faded", 0.5, phase="trend")]
            + [_ep(sid, "nuked", -2.0, phase="flush") for _ in range(6)])


def test_global_average_fails_but_phase_bucket_promotes():
    h = _h(_skill("s1", "incubating"))
    store = _store(*_mixed_phase_eps("s1"))
    # global: n=11, win_rate=4/11≈0.36 < 0.5 -> default proposes nothing
    assert propose_skill_ops(h, store, asof=ASOF) == []
    # phase-bucketed: the "trend" bucket (n=5, win_rate 0.8) clears the floor -> a promote op
    ops = propose_skill_ops(h, store, asof=ASOF, bucket_by="phase")
    assert len(ops) == 1 and ops[0].tool == "promote_skill" and ops[0].args["skill_id"] == "s1"
    assert "phase='trend'" in ops[0].rationale


def test_patch_on_promote_narrows_phases_after_promote():
    # skill applies to trend+flush; the winning bucket is trend -> patch narrows to ["trend"]
    h = _h(_skill("s1", "incubating", phases=("trend", "flush"),
                  stats=SkillStats(n=5, expectancy=1.0)))            # gate double-gate passes
    log = EditLog()
    rep = forge_skills(h, _store(*_mixed_phase_eps("s1")), MetaTools(h, log), asof=ASOF,
                       bucket_by="phase", patch_on_promote=True)
    sk = h.skills.get("s1")
    assert sk.status == "active"                                     # promoted
    assert sk.phases == ["trend"] and sk.applies_all_phases is False  # patch landed
    assert rep.applied.count("s1") == 2                             # promote + patch both applied


def test_patch_skipped_when_promote_rejected_by_double_gate():
    # episodes (bucketed) propose promote, but skill.stats.expectancy<=0 -> the gate blocks the promote
    h = _h(_skill("s1", "incubating", phases=("trend", "flush"),
                  stats=SkillStats(n=5, expectancy=-0.5)))
    log = EditLog()
    rep = forge_skills(h, _store(*_mixed_phase_eps("s1")), MetaTools(h, log), asof=ASOF,
                       bucket_by="phase", patch_on_promote=True)
    sk = h.skills.get("s1")
    assert sk.status == "incubating"                                # not promoted
    assert sk.phases == ["trend", "flush"]                          # NOT narrowed (no patch on a rejected promote)
    assert rep.applied == [] and any(x == "s1" for x, _ in rep.rejected)


def test_retire_stays_global_under_bucketing():
    # an active skill nuking globally must still retire even when bucketed (bucketing must not hide failure)
    h = _h(_skill("s2", "active", stats=SkillStats(n=5)))
    eps = ([_ep("s2", "nuked", -2.0, phase="flush") for _ in range(3)]
           + [_ep("s2", "continued", 1.0, phase="trend") for _ in range(2)])   # global nuke_rate 0.6
    ops = propose_skill_ops(h, _store(*eps), asof=ASOF, bucket_by="phase")
    assert len(ops) == 1 and ops[0].tool == "retire_skill" and ops[0].args["skill_id"] == "s2"


def test_narrative_bucket_promotes_without_a_phase_patch():
    h = _h(_skill("s3", "incubating", phases=("trend", "flush"),
                  stats=SkillStats(n=5, expectancy=1.0)))
    eps = [_ep("s3", "continued", 2.0, phase="trend", narrative="AI") for _ in range(5)]
    log = EditLog()
    rep = forge_skills(h, _store(*eps), MetaTools(h, log), asof=ASOF,
                       bucket_by="narrative", patch_on_promote=True)
    sk = h.skills.get("s3")
    assert sk.status == "active"                                    # promoted on narrative evidence
    assert sk.phases == ["trend", "flush"]                          # narrative has no skill field -> no patch
    assert rep.applied == ["s3"]                                    # promote only (no patch op)


def test_default_bucketing_off_matches_v1_ops():
    # a globally-qualifying incubating skill -> the SAME single promote op with or without the new param
    h = _h(_skill("s4", "incubating"))
    eps = [_ep("s4", "continued", 2.0) for _ in range(4)] + [_ep("s4", "faded", 0.5)]
    default = propose_skill_ops(h, _store(*eps), asof=ASOF)
    explicit_none = propose_skill_ops(h, _store(*eps), asof=ASOF, bucket_by=None)
    assert [o.model_dump() for o in default] == [o.model_dump() for o in explicit_none]
    assert len(default) == 1 and default[0].tool == "promote_skill"
    assert "phase=" not in default[0].rationale and "narrative=" not in default[0].rationale
