"""Sonia /proposals — the user's adopt/discard surface for fork-evolution packets."""
import os

import pytest
from fastapi.testclient import TestClient

from sonia.app import create_app


@pytest.fixture(autouse=True)
def _proposals_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_PROPOSALS_DIR", str(tmp_path / "proposals"))


@pytest.fixture()
def client():
    return TestClient(create_app())


def _stage_packet(lid: str = "m-fork"):
    """Run a real fork evolution against the app's brain store and queue the packet."""
    from alpha.harness.edit_log import EditProvenance
    from alpha.harness.metatools import MetaTools
    from alpha.meta.evolution import run_forked_evolution
    from alpha.meta.proposal_store import ProposalQueue, proposals_dir
    from alpha.meta.store import LiveBrainStore
    from alpha.refine.apply import PASS_TOOLS, try_apply_op
    from alpha.refine.ops import RefineOp

    bstore = LiveBrainStore(os.environ["ALPHA_LIVE_BRAIN_DIR"])

    def runner(h, log):
        op = RefineOp(tool="process_memory",
                      args={"lesson_id": lid, "phases": ["trend"], "outcome": "win",
                            "lesson": "fork"},
                      rationale="fork evidence")
        rec, reason = try_apply_op(MetaTools(h, log), h, op, allowed=PASS_TOOLS["M"],
                                   min_retire_samples=5, min_promote_samples=3,
                                   provenance=EditProvenance(path="self_study", proposer="refiner"))
        assert rec is not None, reason
        return h, log

    return run_forked_evolution(bstore, runner, queue=ProposalQueue(proposals_dir()),
                                kind="refine")


def test_list_drops_heavy_brain_payloads(client):
    prop = _stage_packet()
    rows = client.get("/proposals").json()
    assert [r["proposal_id"] for r in rows] == [prop.proposal_id]
    assert "harness_dict" not in rows[0] and "log_dict" not in rows[0]
    assert rows[0]["records"]                       # the review surface stays


def test_adopt_lands_and_removes_packet(client):
    prop = _stage_packet()
    assert client.get("/healthz").json()["edit_count"] == 0
    r = client.post(f"/proposals/{prop.proposal_id}/resolve", json={"decision": "adopt"})
    assert r.status_code == 200 and r.json()["decision"] == "adopt"
    assert client.get("/healthz").json()["edit_count"] == 1
    assert client.get("/proposals").json() == []


def test_stale_adopt_409s_and_keeps_packet(client):
    prop = _stage_packet()
    # the live brain moves before adoption (a user direct edit lands)
    r = client.post("/edit", json={"tool": "process_memory",
                                   "args": {"lesson_id": "u-move", "phases": ["trend"],
                                            "outcome": "win", "lesson": "moved"},
                                   "rationale": "move the base"})
    assert r.status_code == 200
    r = client.post(f"/proposals/{prop.proposal_id}/resolve", json={"decision": "adopt"})
    assert r.status_code == 409 and "stale" in r.json()["reason"]
    assert client.get("/proposals").json() != []    # kept: the user sees why and may discard


def test_discard_removes_packet_without_touching_brain(client):
    prop = _stage_packet()
    r = client.post(f"/proposals/{prop.proposal_id}/resolve", json={"decision": "discard"})
    assert r.status_code == 200 and r.json()["decision"] == "discard"
    assert client.get("/proposals").json() == []
    assert client.get("/healthz").json()["edit_count"] == 0


def test_resolve_unknown_packet_404s(client):
    r = client.post("/proposals/nope/resolve", json={"decision": "adopt"})
    assert r.status_code == 404
