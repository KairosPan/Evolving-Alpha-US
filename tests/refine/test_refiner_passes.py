from datetime import date, datetime
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.refiner import Refiner, RefinerConfig
from alpha.refine.credit import CreditReport
from alpha.eval.trajectory import Trajectory
from alpha.llm.client import MockLLMClient


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="winner", name="Winner", type="pattern", status="incubating",
              stats=SkillStats(n=6, expectancy=0.3)),
        Skill(skill_id="loser", name="Loser", type="pattern", status="active", stats=SkillStats(n=8, expectancy=-0.2)),
    ])
    doctrine = Doctrine.from_seed_list([{"section": "trend_play", "regime": "trend", "immutable": False,
                                         "guidance": "ride the leader"}])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def _refiner(h, scripts):
    meta = MetaTools(h, EditLog())
    return Refiner(h, MockLLMClient(scripts), meta, RefinerConfig()), meta


def _empty_traj():
    return Trajectory(steps=[]), CreditReport(), []


def test_g_pass_is_noop_three_live_calls():
    h = _h()
    # scripts replayed in pass order p, K, M (G makes NO call)
    scripts = ['{"ops": []}',                                                              # p
               '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "winner"}, "rationale": "proven"}, '
               '{"tool": "retire_skill", "args": {"skill_id": "loser"}, "rationale": "bleeding"}]}',  # K
               '{"ops": []}']                                                              # M
    r, meta = _refiner(h, scripts)
    traj, credit, sigs = _empty_traj()
    report = r.refine(traj, credit, sigs)
    llm = r._llm
    assert len(llm.calls) == 3                              # p, K, M — G made no call
    assert any("G-pass" in n for n in report.notes)        # G no-op recorded
    assert {e.tool for e in report.applied} == {"promote_skill", "retire_skill"}
    assert h.skills.get("winner").status == "active" and h.skills.get("loser").status == "dormant"
    assert len(meta.log) == 2                               # exactly the 2 applied edits logged


def test_per_pass_cap_enforced():
    h = _h()
    # 6 patch ops in the K pass; cap is 5 per pass -> 6th rejected
    ops = ", ".join('{"tool": "patch_skill", "args": {"skill_id": "loser", "notes": "n%d"}, "rationale": "r"}' % i
                    for i in range(6))
    r, meta = _refiner(h, ['{"ops": []}', '{"ops": [%s]}' % ops, '{"ops": []}'])
    report = r.refine(*_empty_traj())
    assert sum(1 for e in report.applied if e.pass_kind == "K") == 5
    assert any("per-pass limit" in e.reason for e in report.rejected)


def test_edit_history_recorded():
    h = _h()
    r, meta = _refiner(h, ['{"ops": []}',
                           '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "winner"}, "rationale": "ok"}]}',
                           '{"ops": []}'])
    r.refine(*_empty_traj())
    assert len(r._recent_reports) == 1 and r._recent_reports[-1].applied[0].tool == "promote_skill"
