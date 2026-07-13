# tests/refine/test_reflect.py
"""A3 PART 2 — reflection→directions detector: task-only, signature-stable, negative-filtered."""
from __future__ import annotations

from datetime import date

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.ops import RefineOp
from alpha.refine.reflect import (direction_signature, reflect_over_tasks, reflect_task_skills,
                                  signature_from_record)

_ASOF = date(2026, 6, 20)


def _h(*skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(list(skills)),
                        memory=MemoryStore.from_lessons([]))


def _op_skill(sid, status="incubating"):
    return Skill(skill_id=sid, name=sid, type="pattern", status=status,
                 stats=SkillStats(n=0), domain="operational")


def _ep(eid, skill_id, *, kind="task", outcome="succeeded", failure_kind="",
        asof=date(2026, 6, 1)):
    return Episode(episode_id=eid, symbol="", skill_id=skill_id, kind=kind, entry_date=asof,
                   exit_date=asof, outcome=outcome, advantage=0.0, failure_kind=failure_kind,
                   learned_asof=asof)


def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s


def _confirmed_task_store():
    """5 task episodes for op1 (3 confirmed positive) → a promote candidate; returns (store, confirmed_ids)."""
    eps = [_ep(f"t{i}", "op1", outcome="succeeded", failure_kind=("timeout" if i < 2 else "stall"))
           for i in range(5)]
    confirmed = frozenset({"t0", "t1", "t2"})
    return _store(*eps), confirmed


def test_reflect_reads_only_task_episodes():
    store, confirmed = _confirmed_task_store()
    # add TRADE episodes for the SAME skill — they must NOT be seen (verdict fence / PIT).
    store.add(_ep("trade1", "op1", kind="trade", outcome="continued"))
    store.add(_ep("trade2", "op1", kind="trade", outcome="continued"))
    refl = reflect_over_tasks(store, _h(_op_skill("op1")), asof=_ASOF, confirmed_ids=confirmed)
    assert len(refl) == 1
    r = refl[0]
    assert r.skill_id == "op1" and r.signal == "proven"
    assert r.evidence["n"] == 5                        # 5 task episodes, NOT the 2 trade ones
    assert r.op.tool == "promote_skill"
    # a trade-kind read still sees the trade episodes (unaffected) — symmetry both ways
    assert len(store.for_asof(_ASOF, kind="trade", limit=None)) == 2


def test_dominant_failure_kind_is_deterministic():
    store, confirmed = _confirmed_task_store()          # 2 'timeout' + 3 'stall'
    refl = reflect_over_tasks(store, _h(_op_skill("op1")), asof=_ASOF, confirmed_ids=confirmed)
    assert refl[0].dominant_failure_kind == "stall"     # the modal failure_kind


def test_direction_signature_matches_record_signature():
    op = RefineOp(tool="promote_skill", args={"skill_id": "op1"}, rationale="x")
    assert direction_signature(op) == "promote_skill:op1"
    # a landed/proposed EditRecord dict for the same direction yields the SAME key
    rec = {"tool": "promote_skill", "target_kind": "skill", "target_id": "op1"}
    assert signature_from_record(rec) == direction_signature(op)


def test_negative_constraint_suppresses_the_direction():
    store, confirmed = _confirmed_task_store()
    h = _h(_op_skill("op1"))
    meta = MetaTools(h, EditLog())
    neg = frozenset({"promote_skill:op1"})
    report = reflect_task_skills(h, store, meta, asof=_ASOF, confirmed_ids=confirmed,
                                 negative_signatures=neg)
    assert report.suppressed == ["op1"]                 # rejected direction is NOT re-proposed
    assert report.applied == [] and len(meta.log) == 0  # nothing sent to the gate


def test_without_negative_constraint_the_direction_applies():
    store, confirmed = _confirmed_task_store()
    h = _h(_op_skill("op1"))
    meta = MetaTools(h, EditLog())
    report = reflect_task_skills(h, store, meta, asof=_ASOF, confirmed_ids=confirmed)
    assert report.applied == ["op1"] and report.suppressed == []
    assert len(meta.log) == 1


def test_pit_masking_hides_future_episodes():
    # a task episode learned AFTER asof is invisible → not enough samples → no direction
    eps = [_ep(f"t{i}", "op1", asof=date(2026, 6, 1)) for i in range(2)]
    eps.append(_ep("future", "op1", asof=date(2026, 12, 31)))   # learned_asof > asof
    store = _store(*eps)
    refl = reflect_over_tasks(store, _h(_op_skill("op1")), asof=_ASOF,
                              confirmed_ids=frozenset({"t0", "t1", "future"}))
    assert refl == []                                   # only 2 visible < promote_min_samples(3)
