"""A5 face wiring: with ALPHA_BODY_GIT on, a landing through the Sonia face produces a Body commit,
and the revert lever (POST /snapshots/{name}/restore) emits a forward revert commit while the
cross-face reconcile sweep still runs. Off (the default, exercised by every other sonia test) the
face is a plain LiveBrainStore — byte-identical."""
import os
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from sonia.app import create_app

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture()
def git_on(monkeypatch):
    monkeypatch.setenv("ALPHA_BODY_GIT", "1")   # read per-call by _brain_store()


@pytest.fixture()
def client():
    return TestClient(create_app())


def _git(root, *args) -> str:
    return subprocess.run(["git", "-C", root, *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit_count(root) -> int:
    out = subprocess.run(["git", "-C", root, "rev-list", "--count", "HEAD"],
                         capture_output=True, text=True)
    return int(out.stdout.strip()) if out.returncode == 0 else 0


@requires_git
def test_edit_commits_then_restore_reverts(client, git_on):
    brain = os.environ["ALPHA_LIVE_BRAIN_DIR"]
    r = client.post("/edit", json={
        "tool": "process_memory",
        "args": {"lesson_id": "u-1", "phases": ["trend"], "outcome": "principle",
                 "lesson": "the user teaches directly"},
        "rationale": "user direct edit"})
    assert r.status_code == 200 and r.json()["applied"] is True
    # genesis (materialize) + the apply -> the landing is the tip commit, carrying provenance.
    assert _commit_count(brain) >= 2
    msg = _git(brain, "log", "-1", "--format=%B")
    assert msg.startswith("apply") and "process_memory" in msg and "user_direct" in msg

    names = client.get("/snapshots").json()
    assert names
    rr = client.post(f"/snapshots/{names[0]}/restore")
    assert rr.status_code == 200 and rr.json()["ok"] is True
    # rolled back (derived state reconciled) AND a forward revert commit on the git trail
    assert client.get("/healthz").json()["edit_count"] == 0
    assert _git(brain, "log", "-1", "--format=%s").startswith("revert")


def test_default_off_creates_no_repo(client):
    """No ALPHA_BODY_GIT -> the face is a plain LiveBrainStore; no git repo appears."""
    r = client.post("/edit", json={
        "tool": "process_memory",
        "args": {"lesson_id": "u-2", "phases": ["trend"], "outcome": "principle", "lesson": "x"},
        "rationale": "user direct edit"})
    assert r.status_code == 200
    assert not os.path.exists(os.path.join(os.environ["ALPHA_LIVE_BRAIN_DIR"], ".git"))
