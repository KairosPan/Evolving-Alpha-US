"""A3 PART 2 — discarding a self-learning (reflect) proposal mines its directions as negative
constraints; discarding a forge/refine packet records nothing."""
import pytest
from fastapi.testclient import TestClient

from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _stage(kind: str, records: list[dict]):
    from alpha.meta.proposal_store import ProposalQueue, proposals_dir
    q = ProposalQueue(proposals_dir())
    return q.new(kind=kind, base_len=0, base_hash="h", window={}, summary="", records=records,
                 harness_dict={}, log_dict=[])


def _neg_store():
    from alpha.meta.negative_constraint import NegativeConstraintStore
    from alpha.settings import Settings
    return NegativeConstraintStore(Settings.from_env().neg_constraints_dir)


def test_discard_reflect_records_negative_constraints(client):
    prop = _stage("reflect", [{"tool": "promote_skill", "target_kind": "skill", "target_id": "op1"}])
    r = client.post(f"/proposals/{prop.proposal_id}/resolve", json={"decision": "discard"})
    assert r.status_code == 200 and r.json()["constraints_recorded"] == 1
    assert _neg_store().signatures() == frozenset({"promote_skill:op1"})


def test_discard_forge_records_nothing(client):
    prop = _stage("forge", [{"tool": "promote_skill", "target_kind": "skill", "target_id": "op9"}])
    r = client.post(f"/proposals/{prop.proposal_id}/resolve", json={"decision": "discard"})
    assert r.status_code == 200 and r.json()["constraints_recorded"] == 0
    assert _neg_store().signatures() == frozenset()


def test_adopt_reflect_does_not_record_constraints(client):
    """Only a REJECTION (discard) mines a constraint — adopting a direction must not suppress it."""
    prop = _stage("reflect", [{"tool": "promote_skill", "target_kind": "skill", "target_id": "op2"}])
    # a directly-staged packet has an empty base — adopt will 409/short-circuit, but even so it must
    # never write a negative constraint (only the discard branch does).
    client.post(f"/proposals/{prop.proposal_id}/resolve", json={"decision": "adopt"})
    assert _neg_store().signatures() == frozenset()
