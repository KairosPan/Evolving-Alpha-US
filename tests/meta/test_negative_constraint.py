"""A3 PART 2 — negative-constraint store + human-rejection mining from a discarded proposal."""
from __future__ import annotations

from alpha.meta.negative_constraint import NegativeConstraintStore
from alpha.meta.proposal_store import EvolutionProposal
from alpha.refine.reflect import record_directions_from_proposal


def test_store_add_all_signatures_resolve(tmp_path):
    store = NegativeConstraintStore(tmp_path / "neg")
    assert store.all() == [] and store.signatures() == frozenset()
    c = store.add(signature="promote_skill:op1", tool="promote_skill", target_id="op1",
                  reason="user_discard", source_proposal_id="p1")
    assert store.signatures() == frozenset({"promote_skill:op1"})
    assert len(store.all()) == 1 and store.all()[0].tool == "promote_skill"
    store.resolve(c.constraint_id)
    assert store.signatures() == frozenset()


def test_record_directions_from_discarded_proposal(tmp_path):
    store = NegativeConstraintStore(tmp_path / "neg")
    prop = EvolutionProposal(
        proposal_id="pX", created_at="2026-07-13T00:00:00Z", kind="reflect", base_len=0,
        base_hash="h",
        records=[{"tool": "promote_skill", "target_kind": "skill", "target_id": "op1"},
                 {"tool": "retire_skill", "target_kind": "skill", "target_id": "op2"}])
    n = record_directions_from_proposal(store, prop, reason="user_discard")
    assert n == 2
    assert store.signatures() == frozenset({"promote_skill:op1", "retire_skill:op2"})
    assert all(c.source_proposal_id == "pX" for c in store.all())


def test_record_skips_records_without_tool(tmp_path):
    store = NegativeConstraintStore(tmp_path / "neg")
    prop = EvolutionProposal(proposal_id="pY", created_at="t", kind="reflect", base_len=0,
                             base_hash="h", records=[{"target_id": "op1"}])   # no tool
    assert record_directions_from_proposal(store, prop) == 0
    assert store.signatures() == frozenset()
