import pytest
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.refine.refiner import Refiner, RefinerConfig
from alpha.llm.client import MockLLMClient


def _skill(sid, status="active", n=0, expectancy=None):
    st = SkillStats(n=n, expectancy=expectancy)
    return Skill(skill_id=sid, name=sid, type="pattern", status=status, stats=st)


def _refiner(skills):
    h = HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(skills),
                     memory=MemoryStore.from_lessons([]))
    meta = MetaTools(h, EditLog())
    return Refiner(h, MockLLMClient("{}"), meta, RefinerConfig()), h, meta


def test_tool_not_in_pass_rejected():
    r, h, meta = _refiner([_skill("a")])
    ok, edit = r._apply_op(RefineOp(tool="rewrite_doctrine", args={}, rationale="x"), "K", PASS_TOOLS["K"])
    assert ok is False and "not in this pass" in edit.reason and len(meta.log) == 0


def test_missing_rationale_rejected():
    r, h, meta = _refiner([_skill("a")])
    ok, edit = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="  "),
                           "K", PASS_TOOLS["K"])
    assert ok is False and "rationale" in edit.reason and len(meta.log) == 0


def test_retire_evidence_gate():
    r, h, meta = _refiner([_skill("a", n=2)])             # n < min_retire_samples (5)
    ok, edit = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "a"}, rationale="decayed"),
                           "K", PASS_TOOLS["K"])
    assert ok is False and "retire blocked" in edit.reason and h.skills.get("a").status == "active"
    # with enough samples it applies and is logged
    r2, h2, meta2 = _refiner([_skill("a", n=9)])
    ok2, edit2 = r2._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "a"}, rationale="decayed"),
                              "K", PASS_TOOLS["K"])
    assert ok2 is True and h2.skills.get("a").status == "dormant" and len(meta2.log) == 1


def test_promote_evidence_gate():
    r, h, meta = _refiner([_skill("a", status="incubating", n=5, expectancy=-0.1)])   # expectancy<=0
    ok, edit = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="ready"),
                           "K", PASS_TOOLS["K"])
    assert ok is False and "expectancy" in edit.reason and h.skills.get("a").status == "incubating"
    r2, h2, meta2 = _refiner([_skill("a", status="incubating", n=5, expectancy=0.2)])
    ok2, _ = r2._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="ready"),
                          "K", PASS_TOOLS["K"])
    assert ok2 is True and h2.skills.get("a").status == "active"


def test_dispatch_error_becomes_rejection():
    r, h, meta = _refiner([_skill("a")])
    # missing target -> KeyError inside MetaTools -> RejectedEdit, nothing logged
    ok, edit = r._apply_op(RefineOp(tool="patch_skill", args={"skill_id": "ghost", "entry": "x"},
                                    rationale="fix"), "K", PASS_TOOLS["K"])
    assert ok is False and edit.target_id == "ghost" and len(meta.log) == 0


def test_empty_patch_rejected():
    r, h, meta = _refiner([_skill("a")])
    ok, edit = r._apply_op(RefineOp(tool="patch_skill", args={"skill_id": "a"}, rationale="noop"),
                           "K", PASS_TOOLS["K"])
    assert ok is False and "empty patch" in edit.reason and len(meta.log) == 0
