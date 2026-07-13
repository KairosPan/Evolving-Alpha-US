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


def _clean_packet(tmp_path, bstore):
    def runner(h, log):
        _add_lesson(h, log, "m-ok")
        return h, log
    return run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")


def test_adopt_rejects_reviewed_records_differing_from_landing_delta(tmp_path):
    """base_hash pins the BASE, these checks pin the RESULT (final review): the delta the user
    reviewed must be exactly what lands."""
    bstore = _store(tmp_path)
    prop = _clean_packet(tmp_path, bstore)
    tampered = prop.model_copy(update={"records": []})      # user shown nothing, delta lands
    ok, reason = adopt_proposal(bstore, tampered)
    assert ok is False and "reviewed records" in reason
    assert bstore.load()[0].memory.get("m-ok") is None


def test_adopt_rejects_mutated_red_line_doctrine(tmp_path):
    """A hand-edited packet whose harness_dict tampers with an immutable red-line entry must be
    rejected — red-lines can never change through the gate, so any honest fork preserves them."""
    from alpha.harness.loader import load_seeds

    bstore = LiveBrainStore(str(tmp_path / "brain"))
    bstore.save(load_seeds("seeds"), EditLog())             # seeds carry immutable red-lines

    def runner(h, log):
        _add_lesson(h, log, "m-rl")
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    hd = copy.deepcopy(prop.harness_dict)
    reds = [e for e in hd["doctrine"]["entries"] if e.get("immutable")]
    assert reds, "seeds must contain red-line entries for this test"
    reds[0]["guidance"] = "LOOSENED BY A TAMPERED PACKET"
    tampered = prop.model_copy(update={"harness_dict": hd})
    ok, reason = adopt_proposal(bstore, tampered)
    assert ok is False and "red-line" in reason


def test_adopt_rejects_non_extending_fork_log(tmp_path):
    """The fork log must EXTEND the live log — a packet whose prefix rewrites history (or whose
    base_len lies) must not land, and base_len must not mis-scope the human_approver re-stamp."""
    bstore = _store(tmp_path)
    h, log = bstore.load()
    _add_lesson(h, log, "m-base")
    bstore.save(h, log)                                     # non-empty base: 1 record

    def runner(h2, log2):
        _add_lesson(h2, log2, "m-delta")
        return h2, log2

    prop = _clean = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                         kind="refine")

    lied = prop.model_copy(update={"base_len": prop.base_len + 1})
    ok, reason = adopt_proposal(bstore, lied)
    assert ok is False and "base_len" in reason

    tampered_prefix = [dict(r) for r in prop.log_dict]
    tampered_prefix[0] = {**tampered_prefix[0], "summary": "forged history"}
    forged = prop.model_copy(update={"log_dict": tampered_prefix})
    ok2, reason2 = adopt_proposal(bstore, forged)
    assert ok2 is False and "prefix" in reason2
    assert bstore.load()[0].memory.get("m-delta") is None   # nothing landed


def _write_unchained_brain(root, h, log):
    """Persist a brain.json with an UNCHAINED log — a pre-A4 (legacy) live brain, before the A4
    integrity chain existed. (LiveBrainStore.save now finalizes the chain, so we write the file
    directly to reconstruct the on-disk legacy state.)"""
    import json
    root.mkdir(parents=True, exist_ok=True)
    (root / "brain.json").write_text(json.dumps({"harness": h.to_dict(), "log": log.to_dict()}))


def test_adopt_legacy_unchained_base_brain_still_extends(tmp_path):
    """Regression (A4 review MEDIUM): a fork's in-run checkpoint finalizes its base prefix in
    place, so a fork built on a LEGACY unchained live brain ships a chained base prefix. The
    extends-check must be chain-agnostic — this valid packet must ADOPT, not bounce on a
    metadata-only prefix difference. (At ship time every operator brain is unchained + fork-and-
    propose is THE conformant self-study path, so this is the central path on first adopt.)"""
    root = tmp_path / "brain"
    h0, log0 = _h(), EditLog()
    _add_lesson(h0, log0, "m-legacy-base")
    _write_unchained_brain(root, h0, log0)
    bstore = LiveBrainStore(str(root))
    assert bstore.load()[1].records()[0].chain_hash is None      # legacy base is unchained on disk

    def runner(h, log):
        log.finalize_chain()                                     # an in-fork checkpoint chains the base
        _add_lesson(h, log, "m-delta")
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    ok, reason = adopt_proposal(bstore, prop)
    assert ok, reason
    assert bstore.load()[0].memory.get("m-delta") is not None    # the delta landed


def test_adopt_still_extends_when_fork_chains_a_chained_base(tmp_path):
    """The complement: a normally-persisted (A4-chained) live brain adopts fine too — the
    chain-agnostic compare is a no-op when both sides are already chained."""
    bstore = _store(tmp_path)
    h, log = bstore.load()
    _add_lesson(h, log, "m-base")
    bstore.save(h, log)                                          # chained base on disk

    def runner(h2, log2):
        log2.finalize_chain()
        _add_lesson(h2, log2, "m-delta")
        return h2, log2

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    ok, reason = adopt_proposal(bstore, prop)
    assert ok, reason
    assert bstore.load()[0].memory.get("m-delta") is not None


def test_adopt_still_rejects_genuine_prefix_content_tamper(tmp_path):
    """The extends-check must still catch a REAL prefix rewrite — the fix relaxes only the derived
    chain metadata, never a semantic edit field. A legacy unchained base whose prefix summary is
    forged must still bounce."""
    root = tmp_path / "brain"
    h0, log0 = _h(), EditLog()
    _add_lesson(h0, log0, "m-legacy-base")
    _write_unchained_brain(root, h0, log0)
    bstore = LiveBrainStore(str(root))

    def runner(h, log):
        log.finalize_chain()
        _add_lesson(h, log, "m-delta")
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    tampered_prefix = [dict(r) for r in prop.log_dict]
    tampered_prefix[0] = {**tampered_prefix[0], "summary": "forged history"}   # a SEMANTIC change
    forged = prop.model_copy(update={"log_dict": tampered_prefix})
    ok, reason = adopt_proposal(bstore, forged)
    assert ok is False and "prefix" in reason
    assert bstore.load()[0].memory.get("m-delta") is None        # nothing landed


def test_adopt_not_stale_when_live_base_only_gets_chained(tmp_path):
    """Residual closed (A4 review): a legacy unchained live base gets CHAINED the moment ANY
    LiveBrainStore.save runs (adding NO new edits). The base_hash staleness pin compares CONTENT,
    so a chain-metadata-only change must NOT be flagged 'stale: re-run' — otherwise every ship-time
    (unchained) operator brain would spuriously flag all outstanding packets stale on its first
    chaining write."""
    root = tmp_path / "brain"
    h0, log0 = _h(), EditLog()
    _add_lesson(h0, log0, "m-base")
    _write_unchained_brain(root, h0, log0)
    bstore = LiveBrainStore(str(root))

    def runner(h, log):
        _add_lesson(h, log, "m-delta")
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    # an unrelated save chains the legacy base in place — NO new edits, only derived metadata
    h, log = bstore.load()
    assert log.records()[0].chain_hash is None                   # unchained before the save
    bstore.save(h, log)
    assert bstore.load()[1].records()[0].chain_hash is not None  # chained after, identical edits

    ok, reason = adopt_proposal(bstore, prop)
    assert ok, reason                                            # NOT stale — content unchanged
    assert bstore.load()[0].memory.get("m-delta") is not None


def test_adopt_still_stale_on_genuine_base_content_change(tmp_path):
    """The complement: a REAL base content change between propose and adopt IS still flagged stale —
    the chain-agnostic base_hash strips ONLY the derived chain fields, never a semantic edit."""
    root = tmp_path / "brain"
    h0, log0 = _h(), EditLog()
    _add_lesson(h0, log0, "m-base")
    _write_unchained_brain(root, h0, log0)
    bstore = LiveBrainStore(str(root))

    def runner(h, log):
        _add_lesson(h, log, "m-delta")
        return h, log

    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(str(tmp_path / "p")),
                                kind="refine")
    h, log = bstore.load()                                       # a teaching edit lands (real change)
    _add_lesson(h, log, "m-teach")
    bstore.save(h, log)

    ok, reason = adopt_proposal(bstore, prop)
    assert ok is False and "stale" in reason
    assert bstore.load()[0].memory.get("m-delta") is None        # nothing landed


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
