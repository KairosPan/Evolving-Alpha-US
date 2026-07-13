# tests/refine/test_apply_task_activation.py
"""A2 — P-B/P-C live-activation gate wiring (try_apply_op task branch).

Pins the three try_apply_op (TCB) changes that A2 adds to the ALREADY-BUILT domain-aware task
branch.  All are additive: with the new inputs absent the branch behaves byte-identically to the
dormant P-C build (existing tests/refine/test_apply_separation.py + test_uniform_task_floor.py
stay green).

Item 1 — conflict-queue routing (runbook §2 step 1):
  the task branch used to short-circuit and return BEFORE the trade path's conflict check, so an
  operational task op that contests a teaching/user-owned OPERATIONAL element applied silently.
  Now it is HELD for adjudication like the trade path.  (A TRADING target still rejects on domain
  first — pinned in test_apply_separation.py; the conflict queue is only reachable for operational
  targets that pass the domain wall.)

Item 2 — operational-M scope decision (runbook §2 step 2):
  arena-spec §5 scopes the task signal to K + G + operational DOCTRINE only — never M (Lessons).
  The create path let a task-evidenced process_memory(domain="operational") slip through.  A2
  rejects every task-evidenced memory op, closing that gap.

Item 3 + before-live (a) — gate-side re-derivation of task evidence (runbook §2 step 3, §1):
  the task floor used to read caller-supplied task_stats, which a producer could forge.  When a
  read-only PIT-pinned task-recall handle is threaded in, the gate recomputes task_stats ITSELF
  and derives confirmed_ids from DURABLE records (EditLog human_approver stamps) — mirroring the
  verdict's read-only recall_store split so the gate can never become a self-write channel.
"""
from __future__ import annotations

from datetime import date

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import TaskStats
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import PASS_TOOLS, RefineOp

_ASOF = date(2026, 6, 20)


# ── helpers ───────────────────────────────────────────────────────────────────

def _h(skills=None):
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills(skills or []),
        memory=MemoryStore.from_lessons([]),
    )


def _skill(sid, *, domain="operational", n=0, expectancy=None, status="incubating"):
    return Skill(skill_id=sid, name=sid, type="pattern", status=status,
                 stats=SkillStats(n=n, expectancy=expectancy), domain=domain)


def _task_prov(proposer="forge", **kw):
    return EditProvenance(path="self_study", proposer=proposer, evidence_kind="task", **kw)


def _passing_stats():
    return TaskStats(n=5, succeeded=4, failed=0, incomplete=1, confirmed_success=3, confirmed_n=3)


_ep_ctr = 0


def _task_ep(skill_id, outcome="succeeded", asof=date(2026, 6, 1)):
    global _ep_ctr
    _ep_ctr += 1
    return Episode(episode_id=f"task:{skill_id}:{_ep_ctr}", symbol="", skill_id=skill_id,
                   kind="task", entry_date=asof, exit_date=asof, outcome=outcome,
                   advantage=0.0, learned_asof=asof)


def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s


class _FakeQueue:
    def __init__(self):
        self.items = []

    def add(self, **kw):
        self.items.append(kw)


# ===========================================================================
# Item 1 — conflict-queue routing for operational task ops
# ===========================================================================

def test_operational_task_op_contesting_teaching_is_held_not_applied():
    """An operational task op that contests a teaching-owned operational element is HELD for
    review (conflict_queue), not silently applied — the trade-path discipline now reaches the
    task branch."""
    sk = _skill("op_held", domain="operational")
    h = _h([sk])
    log = EditLog()
    meta = MetaTools(h, log)

    # Stamp a teaching-owned edit on the operational skill so is_conflict() fires.
    teach_op = RefineOp(tool="patch_skill", args={"skill_id": "op_held", "notes": "sonia set this"},
                        rationale="teaching update")
    try_apply_op(meta, h, teach_op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                 min_promote_samples=3, provenance=EditProvenance(path="teaching", proposer="sonia"))
    assert len(log) == 1

    # A task-evidenced self-study op now contests the SAME operational element.
    cq = _FakeQueue()
    task_op = RefineOp(tool="patch_skill", args={"skill_id": "op_held", "notes": "task contests"},
                       rationale="task says otherwise")
    rec, reason = try_apply_op(meta, h, task_op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(proposer="forge"),
                               task_stats=_passing_stats(), conflict_queue=cq)

    assert rec is None
    assert reason is not None and reason.startswith("held_for_review")
    assert len(cq.items) == 1, "the contest must land in the conflict queue for adjudication"
    assert len(log) == 1, "nothing new written — the op is held, not applied"


def test_operational_task_op_without_conflict_applies():
    """A non-contesting operational task op with a queue present still applies — the routing does
    not block legitimate operational evolution."""
    sk = _skill("op_ok", domain="operational")
    h = _h([sk])
    log = EditLog()
    meta = MetaTools(h, log)
    cq = _FakeQueue()
    op = RefineOp(tool="patch_skill", args={"skill_id": "op_ok", "notes": "clean operational patch"},
                  rationale="task evidence, no contest")

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(),
                               task_stats=_passing_stats(), conflict_queue=cq)

    assert reason is None
    assert rec is not None
    assert len(cq.items) == 0
    assert len(log) == 1


# ===========================================================================
# Item 2 — operational-M is out of scope (K + operational-doctrine only)
# ===========================================================================

def test_task_evidenced_operational_memory_create_rejected():
    """CLOSES THE GAP: a task-evidenced process_memory(domain='operational') used to slip through
    the create path.  arena-spec §5 scopes the task signal to K + operational-doctrine only, never
    M — so it is now rejected."""
    h = _h()
    log = EditLog()
    meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L_op", "phases": ["trend"], "outcome": "win",
                        "lesson": "operational lesson", "domain": "operational"},
                  rationale="task run wants an operational lesson")

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(proposer="refiner"))

    assert rec is None
    assert reason is not None and reason.startswith("separation:") and "operational-M" in reason
    assert len(log) == 0


def test_task_evidenced_plain_memory_op_rejected():
    """Any task-evidenced memory op (no operational label) is also out of scope."""
    h = _h()
    log = EditLog()
    meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L_tr", "phases": ["trend"], "outcome": "win", "lesson": "x"},
                  rationale="task run")

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov())

    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    assert len(log) == 0


# ===========================================================================
# Item 3 + before-live (a) — gate-side re-derivation of task evidence
# ===========================================================================

def test_forged_task_stats_cannot_promote_when_recall_threaded():
    """FORGERY-RESISTANCE: the caller passes a PASSING task_stats, but the read-only recall store
    holds only agent-authored (unconfirmed) episodes and the EditLog carries no human_approver
    task record.  The gate re-derives confirmed_n=0 and rejects — the caller's forged stats are
    ignored once the recall handle is threaded in."""
    sk = _skill("op_forge", domain="operational")
    h = _h([sk])
    log = EditLog()
    meta = MetaTools(h, log)
    recall = _store(*[_task_ep("op_forge", "succeeded") for _ in range(6)])
    op = RefineOp(tool="promote_skill", args={"skill_id": "op_forge"},
                  rationale="forged: caller claims confirmed evidence")

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(),
                               task_stats=_passing_stats(),  # forged — gate must ignore it
                               task_recall=recall, asof=_ASOF)

    assert rec is None
    assert reason is not None and "task floor" in reason and "confirmed_n" in reason
    assert h.skills.get("op_forge").status == "incubating"
    assert len(log) == 0


def test_gate_derives_confirmed_from_human_approver_records_and_promotes():
    """POSITIVE PATH: the EditLog carries a human_approver-stamped task record naming the confirmed
    episode ids.  The gate derives confirmed_n from that DURABLE record (not caller input),
    the floor passes, and the operational skill is promoted."""
    sk = _skill("op_promote", domain="operational", status="incubating")
    h = _h([sk])
    log = EditLog()
    meta = MetaTools(h, log)
    eps = [_task_ep("op_promote", "succeeded") for _ in range(4)]
    recall = _store(*eps)

    # A DURABLE external-confirmation record: human_approver set + confirmed episode ids listed.
    # task_forge cannot stamp human_approver, so this is the forgery-resistant source.
    log.append("noop", "skill", "op_promote", "update", summary="approval marker")
    log.stamp_last(EditProvenance(path="user_direct", proposer="user", human_approver="user",
                                  evidence_kind="task",
                                  evidence_ref={"confirmed_episode_ids": [e.episode_id for e in eps]}))

    op = RefineOp(tool="promote_skill", args={"skill_id": "op_promote"},
                  rationale="task evidence, externally confirmed")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(),
                               task_stats=None,  # caller supplies nothing — gate derives it
                               task_recall=recall, asof=_ASOF)

    assert reason is None, f"expected promote to pass on derived confirmed evidence, got: {reason!r}"
    assert rec is not None
    assert h.skills.get("op_promote").status == "active"


def test_recall_none_uses_caller_task_stats_byte_identical():
    """OPT-IN: with no recall handle the gate trusts caller-supplied task_stats exactly as the
    dormant P-C build did (this is the byte-identical-when-off half of the re-derivation)."""
    sk = _skill("op_off", domain="operational")
    h = _h([sk])
    log = EditLog()
    meta = MetaTools(h, log)
    op = RefineOp(tool="patch_skill", args={"skill_id": "op_off", "notes": "patch"},
                  rationale="task evidence")

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(),
                               task_stats=_passing_stats())  # no task_recall → caller stats trusted

    assert reason is None
    assert rec is not None
    assert len(log) == 1


def test_recall_threaded_without_asof_fails_closed():
    """Fail-closed: a recall handle with no asof cannot PIT-mask, so re-derivation refuses."""
    sk = _skill("op_noasof", domain="operational")
    h = _h([sk])
    log = EditLog()
    meta = MetaTools(h, log)
    recall = _store(_task_ep("op_noasof", "succeeded"))
    op = RefineOp(tool="promote_skill", args={"skill_id": "op_noasof"}, rationale="task")

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(),
                               task_stats=_passing_stats(), task_recall=recall, asof=None)

    assert rec is None
    assert reason is not None and "asof" in reason
    assert len(log) == 0


# ===========================================================================
# Review fix — human_approver is waist-enforced, not producer-trusted
# (the confirmation signal _derive_confirmed_task_ids harvests must be a HUMAN act)
# ===========================================================================

def test_self_study_op_cannot_self_stamp_human_approver():
    """LEG 1 (waist enforcement): a self-study op that carries its own human_approver is refused at
    the waist, before any durable record — a proposer must not be able to forge the external
    confirmation that the confirmed-positive floor counts. Holds for task AND trade evidence."""
    sk = _skill("op_selfapprove", domain="operational")
    for ek in ("task", None):
        h = _h([sk])
        log = EditLog()
        meta = MetaTools(h, log)
        prov = EditProvenance(path="self_study", proposer="forge", evidence_kind=ek,
                              human_approver="forge",
                              evidence_ref={"confirmed_episode_ids": ["forged"]})
        op = RefineOp(tool="promote_skill", args={"skill_id": "op_selfapprove"},
                      rationale="self-study tries to self-approve")
        rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                                   min_promote_samples=3, provenance=prov)
        assert rec is None, f"self_study+human_approver must be refused (evidence_kind={ek!r})"
        assert reason is not None and "human_approver" in reason
        assert len(log) == 0, "no durable record may be written for a self-approved op"


def test_derivation_ignores_confirmed_ids_on_self_study_record():
    """LEG 2 (defense-in-depth): a self_study record carrying human_approver + confirmed_episode_ids
    — e.g. laundered via adopt_proposal's post-gate direct save, which never reaches the waist — is
    NOT a valid confirmation source. The gate harvests confirmed ids only from teaching/user_direct
    records, so it re-derives confirmed_n=0 here and the floor rejects."""
    sk = _skill("op_launder", domain="operational")
    h = _h([sk])
    log = EditLog()
    meta = MetaTools(h, log)
    eps = [_task_ep("op_launder", "succeeded") for _ in range(4)]
    recall = _store(*eps)
    # Persist the self_study confirmation marker DIRECTLY (the waist would refuse it via try_apply_op;
    # this simulates a laundered/legacy record reaching the log by another path).
    log.append("noop", "skill", "op_launder", "update", summary="laundered marker")
    log.stamp_last(EditProvenance(path="self_study", proposer="forge", human_approver="forge",
                                  evidence_kind="task",
                                  evidence_ref={"confirmed_episode_ids": [e.episode_id for e in eps]}))

    op = RefineOp(tool="promote_skill", args={"skill_id": "op_launder"}, rationale="laundered promote")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(),
                               task_stats=None, task_recall=recall, asof=_ASOF)

    assert rec is None
    assert reason is not None and "confirmed_n" in reason  # derived confirmed_n=0 → floor rejects
    assert h.skills.get("op_launder").status == "incubating"


def test_gate_derives_confirmed_from_teaching_record_and_promotes():
    """POSITIVE (leg 2 must not over-filter): a TEACHING human-approved record (the workbench
    approve path's provenance) is a valid confirmation source — its confirmed_episode_ids seed the
    derivation and the operational skill is promoted."""
    sk = _skill("op_teach", domain="operational", status="incubating")
    h = _h([sk])
    log = EditLog()
    meta = MetaTools(h, log)
    eps = [_task_ep("op_teach", "succeeded") for _ in range(4)]
    recall = _store(*eps)
    log.append("noop", "skill", "op_teach", "update", summary="approve marker")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia", human_approver="user",
                                  evidence_kind="task",
                                  evidence_ref={"confirmed_episode_ids": [e.episode_id for e in eps]}))

    op = RefineOp(tool="promote_skill", args={"skill_id": "op_teach"}, rationale="teaching-confirmed")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"], min_retire_samples=5,
                               min_promote_samples=3, provenance=_task_prov(),
                               task_stats=None, task_recall=recall, asof=_ASOF)

    assert reason is None, f"teaching-confirmed promote should pass, got: {reason!r}"
    assert rec is not None
    assert h.skills.get("op_teach").status == "active"
