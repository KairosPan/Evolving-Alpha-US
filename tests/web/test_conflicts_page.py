import os

import pytest

pytest.importorskip("fastapi", reason="install: pip install -e '.[web,sonia]'")

from fastapi.testclient import TestClient

from alpha_web.sonia_client import SoniaClient


def _sonia_tc(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_CONFLICTS_DIR", str(tmp_path / "conflicts"))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    from sonia.app import create_app
    return TestClient(create_app())


def _seed(tmp_path):
    from alpha.meta.conflict_store import ConflictQueue
    return ConflictQueue(str(tmp_path / "conflicts")).add(
        op={"tool": "demote_memory", "args": {"lesson_id": "m1"}, "rationale": "weak"},
        provenance={"path": "self_study", "proposer": "refiner"},
        contested={"target_id": "m1"},
    )


def test_sonia_client_list_and_resolve(tmp_path, monkeypatch):
    held = _seed(tmp_path)
    sc = SoniaClient(client=_sonia_tc(tmp_path, monkeypatch))
    assert sc.list_conflicts()[0]["conflict_id"] == held.conflict_id
    assert sc.resolve_conflict(held.conflict_id, "keep_teaching")["resolved"] == held.conflict_id
    assert sc.list_conflicts() == []
