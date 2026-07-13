"""A8 part (b): the deliberation-packet counsel fields — KERNEL-GENERATED, never proposer-authored.

behavior diff / dedup / coverage / cost ride on EvolutionProposal, computed by run_forked_evolution
from the delta; a forged behavior_diff is refused at adopt; a pre-A8 packet is byte-identical."""
from __future__ import annotations

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.state import HarnessState
from alpha.meta.evolution import _behavior_diff, adopt_proposal, run_forked_evolution
from alpha.meta.proposal_store import ProposalQueue
from alpha.meta.store import LiveBrainStore
from alpha.refine.apply import PASS_TOOLS, try_apply_op
from alpha.refine.ops import RefineOp


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def _add_lesson(h, log, lid, proposer="refiner"):
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": lid, "phases": ["trend"], "outcome": "win", "lesson": "x"},
                  rationale="fork evidence")
    rec, reason = try_apply_op(MetaTools(h, log), h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=EditProvenance(path="self_study", proposer=proposer))
    assert rec is not None, reason


def _store(tmp_path, name="brain"):
    bstore = LiveBrainStore(str(tmp_path / name))
    bstore.save(_h(), EditLog())
    return bstore


def _packet(tmp_path, bstore, lids=("m-a",), *, window=None, cost=None, queue=None):
    q = queue or ProposalQueue(str(tmp_path / "p"))

    def runner(h, log):
        for lid in lids:
            _add_lesson(h, log, lid)
        return h, log

    return run_forked_evolution(bstore, runner, queue=q, kind="refine", window=window, cost=cost)


def test_behavior_diff_is_one_row_per_delta_record(tmp_path):
    prop = _packet(tmp_path, _store(tmp_path), lids=("m-a", "m-b"))
    assert len(prop.behavior_diff) == 2
    assert [r["target_id"] for r in prop.behavior_diff] == ["m-a", "m-b"]
    # a pure function of the records — matches the re-derivation
    assert prop.behavior_diff == _behavior_diff(prop.records)


def test_coverage_reports_no_applicable_coverage_on_empty_window(tmp_path):
    prop = _packet(tmp_path, _store(tmp_path), window=None)
    assert prop.coverage["has_coverage"] is False and prop.coverage["n_delta"] == 1
    prop2 = _packet(tmp_path, _store(tmp_path, "b2"), window={"start": "2026-01-01"})
    assert prop2.coverage["has_coverage"] is True


def test_dedup_lists_a_landed_collision(tmp_path):
    bstore = _store(tmp_path)
    h, log = bstore.load()
    _add_lesson(h, log, "m-dup")             # a LANDED edit CREATES m-dup
    bstore.save(h, log)
    q = ProposalQueue(str(tmp_path / "p"))

    def runner(h2, log2):                    # the delta UPDATES the same target -> a dedup collision
        op = RefineOp(tool="update_memory", args={"lesson_id": "m-dup", "lesson": "revised"},
                      rationale="revise")
        rec, reason = try_apply_op(MetaTools(h2, log2), h2, op, allowed=PASS_TOOLS["M"],
                                   min_retire_samples=5, min_promote_samples=3,
                                   provenance=EditProvenance(path="self_study", proposer="refiner"))
        assert rec is not None, reason
        return h2, log2

    prop = run_forked_evolution(bstore, runner, queue=q, kind="refine")
    assert prop.dedup and prop.dedup[0]["target_id"] == "m-dup"
    assert prop.dedup[0]["landed_seqs"]                 # the landed collision is listed


def test_cost_rides_when_threaded_else_none(tmp_path):
    prop = _packet(tmp_path, _store(tmp_path), cost={"total_usd": 1.25, "n_calls": 3})
    assert prop.cost == {"total_usd": 1.25, "n_calls": 3}
    prop2 = _packet(tmp_path, _store(tmp_path, "b2"))
    assert prop2.cost is None


def test_forged_behavior_diff_is_refused_at_adopt(tmp_path):
    bstore = _store(tmp_path)
    prop = _packet(tmp_path, bstore, lids=("m-ok",))
    forged = prop.model_copy(update={"behavior_diff": [{"target_id": "LIE", "op": "create"}]})
    ok, reason = adopt_proposal(bstore, forged)
    assert ok is False and "behavior_diff" in reason
    assert bstore.load()[0].memory.get("m-ok") is None      # nothing landed


def test_honest_packet_and_legacy_packet_both_adopt(tmp_path):
    bstore = _store(tmp_path)
    prop = _packet(tmp_path, bstore, lids=("m-honest",))
    ok, reason = adopt_proposal(bstore, prop)                # kernel-built diff matches -> lands
    assert ok, reason
    assert bstore.load()[0].memory.get("m-honest") is not None

    # a legacy/pre-A8 packet carries behavior_diff=[] -> the re-derivation check is skipped
    bstore2 = _store(tmp_path, "b2")
    prop2 = _packet(tmp_path, bstore2, lids=("m-legacy",))
    legacy = prop2.model_copy(update={"behavior_diff": [], "dedup": [], "coverage": {}, "cost": None})
    ok2, reason2 = adopt_proposal(bstore2, legacy)
    assert ok2, reason2
    assert bstore2.load()[0].memory.get("m-legacy") is not None
