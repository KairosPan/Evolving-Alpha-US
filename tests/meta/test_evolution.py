"""Fork-and-propose evolution machinery (charter conformance 2026-07-09).

The blocker regression pinned here: run_forked_evolution must package from the handles the
runner RETURNS — an in-fork breaker rollback rebinds HarnessManager.harness/.log to fresh
objects, so packaging from the handles passed in would ship the discarded timeline."""
import copy

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.state import HarnessState
from alpha.meta.evolution import adopt_proposal, run_forked_evolution
from alpha.meta.proposal_store import ProposalQueue, brain_hash
from alpha.meta.store import LiveBrainStore
from alpha.refine.apply import PASS_TOOLS, try_apply_op
from alpha.refine.ops import RefineOp


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def _add_lesson(h, log, lid: str, proposer: str = "refiner"):
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": lid, "phases": ["trend"], "outcome": "win", "lesson": "x"},
                  rationale="fork evidence")
    rec, reason = try_apply_op(MetaTools(h, log), h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=EditProvenance(path="self_study", proposer=proposer))
    assert rec is not None, reason


def _store(tmp_path, name="brain", materialize=True):
    bstore = LiveBrainStore(str(tmp_path / name))
    if materialize:
        bstore.save(_h(), EditLog())
    return bstore


def test_packages_from_returned_handles_not_the_passed_ones(tmp_path):
    """Simulates the post-breaker-rollback rebind: the runner returns DIFFERENT objects than it
    was handed. The packet must reflect the returned (final) state, and the discarded edits on
    the passed-in handles must not leak into it."""
    bstore = _store(tmp_path)

    def runner(h, log):
        _add_lesson(h, log, "discarded-timeline")     # lands on the PASSED handles
        final_h, final_log = _h(), EditLog()          # 'restored' fresh objects (the rebind)
        _add_lesson(final_h, final_log, "survivor")
        return final_h, final_log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    assert prop is not None
    ids = [r["target_id"] for r in prop.records]
    assert ids == ["survivor"]
    assert not any(m["lesson_id"] == "discarded-timeline" for m in prop.harness_dict["memory"])


def test_live_brain_untouched_and_empty_delta_proposes_nothing(tmp_path):
    bstore = _store(tmp_path)
    before = bstore.load()[0].to_dict()
    q = ProposalQueue(str(tmp_path / "p"))

    prop = run_forked_evolution(bstore, lambda h, log: (h, log), queue=q, kind="refine")
    assert prop is None and q.all() == []
    assert bstore.load()[0].to_dict() == before


def test_adopt_lands_with_human_approver_preserving_principal(tmp_path):
    bstore = _store(tmp_path)

    def runner(h, log):
        _add_lesson(h, log, "m-forked")
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    ok, reason = adopt_proposal(bstore, prop)
    assert ok, reason
    h, log = bstore.load()
    assert h.memory.get("m-forked") is not None
    rec = log.records()[-1]
    assert rec.provenance.path == "self_study"
    assert rec.provenance.proposer == "refiner"
    assert rec.provenance.human_approver == "user"


def test_adopt_rejects_stale_packet_by_content_hash(tmp_path):
    bstore = _store(tmp_path)

    def runner(h, log):
        _add_lesson(h, log, "m-fork")
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")

    # the live brain moves between fork and adopt (a teaching edit lands)
    h, log = bstore.load()
    _add_lesson(h, log, "m-teach", proposer="refiner")
    bstore.save(h, log)

    ok, reason = adopt_proposal(bstore, prop)
    assert ok is False and "stale" in reason
    assert bstore.load()[0].memory.get("m-fork") is None    # nothing landed


def test_stale_check_is_content_based_not_length_based(tmp_path):
    """A land+rollback sequence reproduces the base LENGTH with different content — the hash
    must still accept the true base and reject a different same-length brain."""
    bstore = _store(tmp_path)
    h, log = bstore.load()
    _add_lesson(h, log, "m-a")
    bstore.save(h, log)                                     # base: 1 record (m-a)

    def runner(h2, log2):
        _add_lesson(h2, log2, "m-fork")
        return h2, log2

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")

    # replace the base with a SAME-LENGTH different brain (m-b instead of m-a)
    h3, log3 = _h(), EditLog()
    _add_lesson(h3, log3, "m-b")
    bstore.save(h3, log3)
    assert len(log3) == 1                                   # same length as the packet's base

    ok, reason = adopt_proposal(bstore, prop)
    assert ok is False and "stale" in reason


def test_adopt_materializes_a_seeds_only_store(tmp_path):
    """First adopt against a never-materialized brain dir must not crash in snapshot()."""
    bstore = _store(tmp_path, materialize=False)            # no brain.json on disk
    assert not bstore.is_live()

    def runner(h, log):
        _add_lesson(h, log, "m-first")
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    ok, reason = adopt_proposal(bstore, prop)
    assert ok, reason
    assert bstore.is_live()
    assert bstore.load()[0].memory.get("m-first") is not None


def test_adopt_mints_provenance_when_delta_record_has_none(tmp_path):
    bstore = _store(tmp_path)

    def runner(h, log):
        log.append("process_memory", "memory", "m-bare", "create")   # no provenance stamped
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="forge")
    ok, reason = adopt_proposal(bstore, prop)
    assert ok, reason
    rec = bstore.load()[1].records()[-1]
    assert rec.provenance is not None
    assert rec.provenance.proposer == "forge"               # minted from the packet kind
    assert rec.provenance.human_approver == "user"


def test_brain_hash_round_trips_the_store(tmp_path):
    """The hash computed at fork time must equal the hash of the stored-then-reloaded brain
    (json round-trip stability — the reason to_dict is json-mode)."""
    bstore = _store(tmp_path)
    h, log = bstore.load()
    _add_lesson(h, log, "m-hash")
    bstore.save(h, log)
    h1 = brain_hash(h.to_dict(), log.to_dict())
    h2b, log2 = bstore.load()
    assert brain_hash(h2b.to_dict(), log2.to_dict()) == h1
