# tests/refine/test_apply_separation.py
"""PB-9: evidence-kind carrier + interim blanket reject (the wall).

(a) Back-compat: EditProvenance without evidence_kind has .evidence_kind is None.
(b) task-evidenced ops are blanket-rejected before trade floors.
(c) evidence_kind=None is byte-identical to today (existing passing op still applies).
"""
from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import PASS_TOOLS, RefineOp


def _h(skills=None):
    sk = skills or []
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills(sk),
        memory=MemoryStore.from_lessons([]),
    )


def _skill(sid, status="incubating", n=10, expectancy=0.5):
    return Skill(skill_id=sid, name=sid, type="pattern", status=status,
                 stats=SkillStats(n=n, expectancy=expectancy))


# ── (a) back-compat: evidence_kind defaults to None ─────────────────────────

def test_edit_provenance_evidence_kind_defaults_to_none():
    p = EditProvenance(path="self_study", proposer="refiner")
    assert p.evidence_kind is None


def test_edit_provenance_evidence_kind_explicit_trade():
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="trade")
    assert p.evidence_kind == "trade"


def test_edit_provenance_evidence_kind_explicit_task():
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    assert p.evidence_kind == "task"


# ── (b) task-evidenced op is blanket-rejected (short-circuits trade floors) ──

def test_task_evidence_rejects_memory_op():
    """Task-evidenced process_memory is rejected with the separation message."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L1", "phases": ["trend"], "outcome": "win", "lesson": "x"},
                  rationale="came from a task run")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    assert len(log) == 0  # nothing written


def test_task_evidence_rejects_skill_op():
    """Task-evidenced write_skill is rejected with the separation message."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="write_skill",
                  args={"skill_id": "s1", "name": "s1", "type": "pattern",
                        "trigger": "t", "action": "a", "guard": "g",
                        "phases": ["trend"], "lesson": "works"},
                  rationale="came from task evidence")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    assert len(log) == 0


def test_task_evidence_rejects_doctrine_op():
    """Task-evidenced rewrite_doctrine is rejected with the separation message."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="rewrite_doctrine",
                  args={"section": "risk_rules", "new_guidance": "never lose"},
                  rationale="task insight")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["p"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    assert len(log) == 0


def test_task_evidence_short_circuits_trade_floors():
    """A task-evidenced promote_skill on a skill with n>=min and expectancy>0 (would pass the
    trade floor) is still rejected by the separation wall, proving we short-circuit the floors."""
    # Build a skill that WOULD pass the promote trade floor (n=10, expectancy=0.5, status=incubating)
    sk = _skill("s_good", status="incubating", n=10, expectancy=0.5)
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="promote_skill", args={"skill_id": "s_good"}, rationale="task says ready")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    # The skill was NOT promoted (the wall held)
    assert h.skills.get("s_good").status == "incubating"
    assert len(log) == 0


# ── (c) evidence_kind=None is byte-identical (existing passing op still applies) ──

def test_none_evidence_kind_applies_normally():
    """Op with evidence_kind=None (or absent provenance) applies just like today."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L2", "phases": ["trend"], "outcome": "win", "lesson": "y"},
                  rationale="trade-based learning")
    # None explicitly
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind=None)
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert reason is None
    assert rec is not None
    assert len(log) == 1


def test_no_provenance_applies_normally():
    """Op without any provenance (legacy path) is completely unaffected."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L3", "phases": ["trend"], "outcome": "win", "lesson": "z"},
                  rationale="legacy path")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3)
    assert reason is None
    assert rec is not None
    assert len(log) == 1
