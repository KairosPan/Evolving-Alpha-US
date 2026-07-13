# tests/refine/test_reflect_propose.py
"""A3 PART 2 — the self-learning channel forks-and-proposes: EvolutionProposal, ZERO live H write.

Mirrors evolve_from_episodes: reflect_task_skills runs on a FORK inside run_forked_evolution; the
surviving delta ships as an EvolutionProposal the USER adjudicates. The live brain is byte-untouched.
"""
from __future__ import annotations

from datetime import date

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.meta.conflict_store import ConflictQueue
from alpha.meta.evolution import run_forked_evolution
from alpha.meta.proposal_store import ProposalQueue
from alpha.meta.store import LiveBrainStore
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.refine.apply import try_apply_op
from alpha.refine.reflect import reflect_over_tasks, reflect_task_skills, reflections_summary

_ASOF = date(2026, 6, 20)


def _op_skill(sid, status="incubating"):
    return Skill(skill_id=sid, name=sid, type="pattern", status=status,
                 stats=SkillStats(n=0), domain="operational")


def _h(*skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(list(skills)),
                        memory=MemoryStore.from_lessons([]))


def _ep(eid, skill_id, asof=date(2026, 6, 1)):
    return Episode(episode_id=eid, symbol="", skill_id=skill_id, kind="task", entry_date=asof,
                   exit_date=asof, outcome="succeeded", advantage=0.0, learned_asof=asof)


def _episode_store():
    s = EpisodeStore.in_memory()
    for i in range(5):
        s.add(_ep(f"t{i}", "op1"))
    return s, frozenset({"t0", "t1", "t2"})


def _brain(tmp_path, *skills):
    bstore = LiveBrainStore(str(tmp_path / "brain"))
    bstore.save(_h(*skills), EditLog())
    return bstore


def test_fork_yields_proposal_with_zero_live_write(tmp_path):
    bstore = _brain(tmp_path, _op_skill("op1"))
    before = bstore.load()[0].to_dict()
    eps, confirmed = _episode_store()
    q = ProposalQueue(str(tmp_path / "proposals"))
    box = {}

    # reflections are a deterministic read-only view — the producer computes them before the fork
    # so they can ride the proposal window (the fork's runner recomputes the identical set).
    pre = reflect_over_tasks(eps, bstore.load()[0], asof=_ASOF, confirmed_ids=confirmed)

    def runner(h, log):
        box["report"] = reflect_task_skills(h, eps, MetaTools(h, log), asof=_ASOF,
                                            confirmed_ids=confirmed)
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=q, kind="reflect",
                                window={"asof": _ASOF.isoformat(),
                                        "reflections": reflections_summary(pre)})
    # a proposal landed in /proposals, carrying the promote direction
    assert prop is not None and prop.kind == "reflect"
    assert [r["tool"] for r in prop.records] == ["promote_skill"]
    assert q.get(prop.proposal_id) is not None
    # ...and the live brain is byte-identical (zero live H write)
    assert bstore.load()[0].to_dict() == before
    assert box["report"].applied == ["op1"]


def test_conflict_with_teaching_is_held_no_proposal(tmp_path):
    # stamp a teaching-owned edit on the operational skill so a self-study promote CONTESTS it
    bstore = _brain(tmp_path, _op_skill("op1"))
    with bstore.lock():
        h, log = bstore.load()
        teach = RefineOp(tool="patch_skill", args={"skill_id": "op1", "notes": "sonia owns this"},
                         rationale="teaching")
        rec, _ = try_apply_op(MetaTools(h, log), h, teach, allowed=PASS_TOOLS["K"],
                              min_retire_samples=5, min_promote_samples=3,
                              provenance=EditProvenance(path="teaching", proposer="sonia"))
        assert rec is not None
        bstore.save(h, log)

    before = bstore.load()[0].to_dict()
    eps, confirmed = _episode_store()
    cq = ConflictQueue(str(tmp_path / "conflicts"))
    q = ProposalQueue(str(tmp_path / "proposals"))
    box = {}

    def runner(h, log):
        box["report"] = reflect_task_skills(h, eps, MetaTools(h, log), asof=_ASOF,
                                            confirmed_ids=confirmed, conflict_queue=cq)
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=q, kind="reflect")
    # the direction was HELD (not applied) → empty delta → no proposal; the conflict is queued
    assert prop is None
    assert box["report"].held == ["op1"] and box["report"].applied == []
    assert len(cq.all()) == 1
    assert bstore.load()[0].to_dict() == before        # live brain still untouched


def test_negative_signature_suppresses_across_a_rerun(tmp_path):
    """A rejected direction stored as a negative signature is suppressed on the next fork run —
    never re-proposed."""
    bstore = _brain(tmp_path, _op_skill("op1"))
    eps, confirmed = _episode_store()
    q = ProposalQueue(str(tmp_path / "proposals"))
    box = {}

    def runner(h, log):
        box["report"] = reflect_task_skills(h, eps, MetaTools(h, log), asof=_ASOF,
                                            confirmed_ids=confirmed,
                                            negative_signatures=frozenset({"promote_skill:op1"}))
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=q, kind="reflect")
    assert prop is None                                 # suppressed → no surviving delta
    assert box["report"].suppressed == ["op1"]
