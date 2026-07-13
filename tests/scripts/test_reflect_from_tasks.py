"""A3 PART 2 — the reflect-from-tasks producer forks-and-proposes; negative constraints suppress."""
from datetime import date
import importlib

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.meta.store import LiveBrainStore

_ASOF = date(2026, 6, 20)


def _seed_brain(brain_dir):
    """An operational incubating skill 'op1' + a durable human-approved confirmation record that
    marks t0/t1/t2 as externally confirmed (as a prior adoption would), so the gate's §2.3
    re-derivation lets the promote survive. The confirmation targets a SEPARATE anchor skill so
    op1's latest record is not teaching-owned (no spurious conflict-hold)."""
    h = HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills([
            Skill(skill_id="op1", name="op1", type="pattern", status="incubating",
                  stats=SkillStats(n=0), domain="operational"),
            Skill(skill_id="anchor", name="anchor", type="pattern", status="active",
                  stats=SkillStats(n=1), domain="operational")]),
        memory=MemoryStore.from_lessons([]))
    log = EditLog()
    log.append("patch_skill", "skill", "anchor", "update", "", {})
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia", evidence_kind="task",
                                  human_approver="user",
                                  evidence_ref={"confirmed_episode_ids": ["t0", "t1", "t2"]}))
    LiveBrainStore(str(brain_dir)).save(h, log)


def _seed_episodes(db_path):
    s = EpisodeStore.open(str(db_path))
    for i in range(5):
        s.add(Episode(episode_id=f"t{i}", symbol="", skill_id="op1", kind="task",
                      entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3),
                      outcome="succeeded", advantage=0.0))
    s.close()


def _run(tmp_path, **over):
    mod = importlib.import_module("scripts.reflect_from_tasks")
    kw = dict(brain_dir=str(tmp_path / "brain"), conflicts_dir=str(tmp_path / "conflicts"),
              episodes_db=str(tmp_path / "brain.db"), neg_constraints_dir=str(tmp_path / "neg"),
              asof=_ASOF, proposals_root=str(tmp_path / "proposals"))
    kw.update(over)
    return mod.run_reflect_from_tasks(**kw)


def test_producer_proposes_a_direction_zero_live_write(tmp_path):
    _seed_brain(tmp_path / "brain"); _seed_episodes(tmp_path / "brain.db")
    before = LiveBrainStore(str(tmp_path / "brain")).load()[0].to_dict()
    out = _run(tmp_path)
    assert out["mode"] == "propose" and out["applied"] == ["op1"]
    assert out["proposal_id"] is not None and out["n_delta"] == 1

    from alpha.meta.proposal_store import ProposalQueue
    prop = ProposalQueue(str(tmp_path / "proposals")).get(out["proposal_id"])
    assert prop.kind == "reflect"
    assert [r["tool"] for r in prop.records] == ["promote_skill"]
    assert prop.window.get("reflections")                       # human-readable directions surfaced
    # the live brain is byte-identical (zero live H write) — the USER adjudicates in the cockpit
    assert LiveBrainStore(str(tmp_path / "brain")).load()[0].to_dict() == before

    # ...and the human CAN adopt it — the direction then lands with the true principal preserved
    from alpha.meta.evolution import adopt_proposal
    ok, reason = adopt_proposal(LiveBrainStore(str(tmp_path / "brain")), prop)
    assert ok, reason
    h2, log2 = LiveBrainStore(str(tmp_path / "brain")).load()
    assert h2.skills.get("op1").status == "active"              # promoted on USER adoption
    assert log2.records()[-1].provenance.proposer == "forge"
    assert log2.records()[-1].provenance.human_approver == "user"


def test_producer_suppresses_a_rejected_direction(tmp_path):
    _seed_brain(tmp_path / "brain"); _seed_episodes(tmp_path / "brain.db")
    # a previously-rejected direction lives in the negative-constraint store
    from alpha.meta.negative_constraint import NegativeConstraintStore
    NegativeConstraintStore(str(tmp_path / "neg")).add(
        signature="promote_skill:op1", tool="promote_skill", target_id="op1", reason="user_discard")
    out = _run(tmp_path)
    assert out["proposal_id"] is None                           # nothing proposed
    assert out["suppressed"] == ["op1"] and out["applied"] == []


def test_producer_autonomous_refuses_without_unsafe_env(tmp_path, monkeypatch):
    import pytest
    monkeypatch.delenv("ALPHA_UNSAFE_AUTONOMOUS", raising=False)
    _seed_brain(tmp_path / "brain"); _seed_episodes(tmp_path / "brain.db")
    with pytest.raises(RuntimeError, match="ALPHA_UNSAFE_AUTONOMOUS"):
        _run(tmp_path, mode="autonomous")
    # live brain untouched
    assert LiveBrainStore(str(tmp_path / "brain")).load()[0].skills.get("op1").status == "incubating"
