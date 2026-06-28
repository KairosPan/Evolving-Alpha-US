# tests/refine/test_uniform_task_floor.py
"""Task 19 (PC-10) — Uniform gate floor: producer-agnostic task evidence rejection (verdict 3).

The property: the gate-side task floor in try_apply_op is the SOLE enforcement point and is
uniform across ALL producers.  Today the Refiner K-pass and Sonia both emit ops stamped with
evidence_kind=None (trade/teaching-only), so neither currently emits task-evidenced ops.
But IF any producer were to stamp evidence_kind="task" — simulating "as-if from the Refiner
K-pass or Sonia" — the gate floor applies uniformly, regardless of which proposer field is set.

Coverage (verdict 3):
  (a) task_stats=None → REJECTED for proposer="refiner" (as-if from K-pass).
  (b) task_stats=None → REJECTED for proposer="sonia".
  (c) task_stats below floor (low confirmed_n) → REJECTED for proposer="refiner".
  (d) task_stats below floor (low confirmed_n) → REJECTED for proposer="sonia".
  (e) task_stats below floor (low success_rate) → REJECTED for proposer="refiner".
  (f) task_stats below floor (low success_rate) → REJECTED for proposer="sonia".
  (g) task-evidenced op targeting TRADING skill → REJECTED for proposer="refiner".
  (h) task-evidenced op targeting TRADING skill → REJECTED for proposer="sonia".
  (i) sufficient task_stats + operational target → PASSES for proposer="refiner".
  (j) sufficient task_stats + operational target → PASSES for proposer="sonia".

Investigation note (Task 19):
  - alpha/refine/refiner.py::_apply_op always stamps
      EditProvenance(path="self_study", proposer="refiner")
    with evidence_kind defaulting to None — the Refiner K-pass is trade/trajectory-driven only.
    It NEVER emits evidence_kind="task".
  - alpha/meta/agent.py::MetaAgent.apply always stamps
      EditProvenance(path="teaching", proposer="sonia")
    with evidence_kind defaulting to None — Sonia is teaching-driven only.
    It NEVER emits evidence_kind="task".
  There is no current natural seam where either emits task evidence; the gate (try_apply_op)
  is the uniform enforcement point BY CONSTRUCTION.  These tests pin that invariant: any future
  path from the Refiner K-pass or Sonia that stamps evidence_kind="task" will be subject to the
  same floor, and a task op targeting a trading skill will always be rejected at the gate.
"""
from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import TaskStats
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import PASS_TOOLS, RefineOp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _h(skills=None):
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills(skills or []),
        memory=MemoryStore.from_lessons([]),
    )


def _skill(sid: str, *, domain: str = "trading", n: int = 0, expectancy=None,
           status: str = "incubating") -> Skill:
    return Skill(skill_id=sid, name=sid, type="pattern", status=status,
                 stats=SkillStats(n=n, expectancy=expectancy), domain=domain)


def _op(tool: str = "patch_skill", skill_id: str = "sk") -> RefineOp:
    if tool == "patch_skill":
        return RefineOp(tool="patch_skill", args={"skill_id": skill_id, "notes": "uniform floor test"},
                        rationale="producer-agnostic gate floor test")
    if tool == "promote_skill":
        return RefineOp(tool="promote_skill", args={"skill_id": skill_id},
                        rationale="producer-agnostic gate floor test")
    raise ValueError(tool)


def _prov(proposer: str) -> EditProvenance:
    """Build a task-evidenced EditProvenance with the given proposer."""
    return EditProvenance(path="self_study", proposer=proposer, evidence_kind="task")


def _passing_stats(confirmed_n: int = 3, confirmed_success: int = 2) -> TaskStats:
    """task_stats that meets the strict default floor (confirmed_n>=3, rate>=0.5)."""
    return TaskStats(n=confirmed_n + 2, succeeded=confirmed_success, failed=1,
                     incomplete=1, confirmed_success=confirmed_success,
                     confirmed_n=confirmed_n)


def _low_confirmed_n_stats() -> TaskStats:
    """task_stats with confirmed_n=1 — below the default gate floor of 3."""
    return TaskStats(n=5, succeeded=3, failed=1, incomplete=1,
                     confirmed_success=1, confirmed_n=1)


def _low_rate_stats() -> TaskStats:
    """task_stats with confirmed_n=4 but rate=0.25 — below the default floor of 0.5."""
    return TaskStats(n=5, succeeded=1, failed=3, incomplete=1,
                     confirmed_success=1, confirmed_n=4)


# ---------------------------------------------------------------------------
# (a)/(b) task_stats=None → REJECTED regardless of proposer
# ---------------------------------------------------------------------------

def test_task_stats_none_rejected_proposer_refiner():
    """(a) task_stats=None → gate rejects for proposer='refiner' (simulated K-pass)."""
    sk = _skill("op_a", domain="operational")
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("patch_skill", "op_a"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("refiner"), task_stats=None)
    assert rec is None, "task_stats=None must be rejected"
    assert reason is not None and "task floor" in reason
    assert len(log) == 0


def test_task_stats_none_rejected_proposer_sonia():
    """(b) task_stats=None → gate rejects for proposer='sonia' (simulated Sonia)."""
    sk = _skill("op_b", domain="operational")
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("patch_skill", "op_b"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("sonia"), task_stats=None)
    assert rec is None, "task_stats=None must be rejected for sonia too"
    assert reason is not None and "task floor" in reason
    assert len(log) == 0


# ---------------------------------------------------------------------------
# (c)/(d) low confirmed_n → REJECTED regardless of proposer
# ---------------------------------------------------------------------------

def test_low_confirmed_n_rejected_proposer_refiner():
    """(c) confirmed_n below floor → gate rejects for proposer='refiner'."""
    sk = _skill("op_c", domain="operational")
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("patch_skill", "op_c"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("refiner"),
                               task_stats=_low_confirmed_n_stats(),
                               min_task_confirmed_samples=3)
    assert rec is None
    assert reason is not None and "task floor" in reason and "confirmed_n" in reason
    assert len(log) == 0


def test_low_confirmed_n_rejected_proposer_sonia():
    """(d) confirmed_n below floor → gate rejects for proposer='sonia'."""
    sk = _skill("op_d", domain="operational")
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("patch_skill", "op_d"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("sonia"),
                               task_stats=_low_confirmed_n_stats(),
                               min_task_confirmed_samples=3)
    assert rec is None
    assert reason is not None and "task floor" in reason and "confirmed_n" in reason
    assert len(log) == 0


# ---------------------------------------------------------------------------
# (e)/(f) low success_rate → REJECTED regardless of proposer
# ---------------------------------------------------------------------------

def test_low_success_rate_rejected_proposer_refiner():
    """(e) confirmed_success_rate below floor → gate rejects for proposer='refiner'."""
    sk = _skill("op_e", domain="operational")
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("patch_skill", "op_e"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("refiner"),
                               task_stats=_low_rate_stats(),
                               min_task_confirmed_samples=3, min_task_success_rate=0.5)
    assert rec is None
    assert reason is not None and "task floor" in reason
    assert len(log) == 0


def test_low_success_rate_rejected_proposer_sonia():
    """(f) confirmed_success_rate below floor → gate rejects for proposer='sonia'."""
    sk = _skill("op_f", domain="operational")
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("patch_skill", "op_f"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("sonia"),
                               task_stats=_low_rate_stats(),
                               min_task_confirmed_samples=3, min_task_success_rate=0.5)
    assert rec is None
    assert reason is not None and "task floor" in reason
    assert len(log) == 0


# ---------------------------------------------------------------------------
# (g)/(h) TRADING skill → REJECTED regardless of proposer (separation gate)
# ---------------------------------------------------------------------------

def test_trading_skill_rejected_proposer_refiner():
    """(g) task-evidenced op targeting domain='trading' skill → rejected for proposer='refiner'.
    Separation gate fires BEFORE the task floor, so task_stats is not consulted."""
    sk = _skill("tr_g", domain="trading", n=10, expectancy=0.5)
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("promote_skill", "tr_g"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("refiner"),
                               task_stats=_passing_stats())  # passing stats, but domain=trading
    assert rec is None
    assert reason is not None and "separation:" in reason
    # Skill status unchanged; log empty
    assert h.skills.get("tr_g").status == "incubating"
    assert len(log) == 0


def test_trading_skill_rejected_proposer_sonia():
    """(h) task-evidenced op targeting domain='trading' skill → rejected for proposer='sonia'.
    Even passing task_stats cannot bypass the separation wall for a trading element."""
    sk = _skill("tr_h", domain="trading", n=10, expectancy=0.5)
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("promote_skill", "tr_h"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("sonia"),
                               task_stats=_passing_stats())  # passing stats, but domain=trading
    assert rec is None
    assert reason is not None and "separation:" in reason
    assert h.skills.get("tr_h").status == "incubating"
    assert len(log) == 0


def test_trading_skill_rejected_all_valid_proposers():
    """BONUS: task-evidenced op targeting domain='trading' → rejected for ALL valid proposers.
    The gate is the sole enforcement point; no proposer field value can bypass the separation wall."""
    sk = _skill("tr_i", domain="trading", n=10, expectancy=0.5)
    for proposer in ("refiner", "forge", "sonia", "hermes"):
        h2 = _h([sk]); log2 = EditLog(); meta2 = MetaTools(h2, log2)
        rec, reason = try_apply_op(meta2, h2, _op("promote_skill", "tr_i"), allowed=PASS_TOOLS["K"],
                                   min_retire_samples=5, min_promote_samples=3,
                                   provenance=EditProvenance(path="self_study", proposer=proposer,
                                                             evidence_kind="task"),
                                   task_stats=_passing_stats())
        assert rec is None, f"trading skill must be rejected for proposer={proposer!r}"
        assert reason is not None and "separation:" in reason, (
            f"wrong rejection reason for proposer={proposer!r}: {reason!r}")


# ---------------------------------------------------------------------------
# (i)/(j) sufficient task_stats + operational target → PASSES for all producers
# ---------------------------------------------------------------------------

def test_operational_target_passes_proposer_refiner():
    """(i) all floors met + operational target → PASSES for proposer='refiner'."""
    sk = _skill("op_i", domain="operational")
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("patch_skill", "op_i"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("refiner"),
                               task_stats=_passing_stats(),
                               min_task_confirmed_samples=3, min_task_success_rate=0.5)
    assert reason is None, f"unexpected rejection for refiner proposer: {reason!r}"
    assert rec is not None
    assert len(log) == 1
    assert log.records()[-1].provenance.evidence_kind == "task"


def test_operational_target_passes_proposer_sonia():
    """(j) all floors met + operational target → PASSES for proposer='sonia'.
    Proves the gate grants on merit alone, independent of which producer issued the op."""
    sk = _skill("op_j", domain="operational")
    h = _h([sk]); log = EditLog(); meta = MetaTools(h, log)
    rec, reason = try_apply_op(meta, h, _op("patch_skill", "op_j"), allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=_prov("sonia"),
                               task_stats=_passing_stats(),
                               min_task_confirmed_samples=3, min_task_success_rate=0.5)
    assert reason is None, f"unexpected rejection for sonia proposer: {reason!r}"
    assert rec is not None
    assert len(log) == 1
    assert log.records()[-1].provenance.evidence_kind == "task"
