"""POST /edit — the charter's second hand (user direct edit): lands through the same gate,
stamped user/user_direct/human_approver, sample floors lifted for the user, structural checks
(rationale, red-lines) still binding."""
import os

import pytest
from fastapi.testclient import TestClient

from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _last_record():
    from alpha.meta.store import LiveBrainStore
    _, log = LiveBrainStore(os.environ["ALPHA_LIVE_BRAIN_DIR"]).load()
    return log.records()[-1]


def test_user_direct_edit_lands_with_user_provenance(client):
    r = client.post("/edit", json={
        "tool": "process_memory",
        "args": {"lesson_id": "u-1", "phases": ["trend"], "outcome": "principle",
                 "lesson": "the user teaches directly"},
        "rationale": "user direct edit"})
    assert r.status_code == 200 and r.json()["applied"] is True
    assert r.json()["snapshot_before"]
    assert client.get("/healthz").json()["edit_count"] == 1
    rec = _last_record()
    assert rec.provenance.path == "user_direct"
    assert rec.provenance.proposer == "user"
    assert rec.provenance.human_approver == "user"


def test_user_hand_lifts_sample_floors(client):
    # gap_and_go has stats.n == 0 in the seeds: an agent retire would be floor-blocked
    # (min_retire_samples=5); the USER's hand is not sample-floored.
    r = client.post("/edit", json={"tool": "retire_skill", "args": {"skill_id": "gap_and_go"},
                                   "rationale": "user retires an unused skill"})
    assert r.status_code == 200 and r.json()["applied"] is True


def test_mechanical_validation_still_binds_the_user(client):
    # missing rationale → mechanical rejection, no write
    r = client.post("/edit", json={"tool": "process_memory",
                                   "args": {"lesson_id": "u-2", "phases": ["trend"],
                                            "outcome": "win", "lesson": "x"},
                                   "rationale": ""})
    assert r.status_code == 422 and r.json()["applied"] is False
    assert client.get("/healthz").json()["edit_count"] == 0


def test_red_lines_bind_the_user_too(client):
    # "stop_discipline" is an immutable red-line doctrine entry: even the user's direct hand
    # cannot rewrite it (the gate rejects cleanly, never 500s).
    r = client.post("/edit", json={"tool": "rewrite_doctrine",
                                   "args": {"section": "stop_discipline", "new_guidance": "loosen it"},
                                   "rationale": "try to loosen a red line"})
    assert r.status_code == 422 and r.json()["applied"] is False
    assert "Immutable" in r.json()["reason"] or "immutable" in r.json()["reason"]
    assert client.get("/healthz").json()["edit_count"] == 0
