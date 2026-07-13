"""A3 PART 1 — the workbench context-compaction opt-in is DORMANT by default (byte-identical)."""
import pytest

pytest.importorskip("fastapi")
from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from alpha.data.source import FakeSource


def _fake_source():
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    return FakeSource(calendar=cal, bars={}, snapshots=snaps)


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.delenv("ALPHA_CONTEXT_COMPACT_THRESHOLD", raising=False)


def test_compaction_helper_dormant_when_unset(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    from workbench.app import _compaction
    compactor, store = _compaction(tmp_path / "ws")
    assert compactor is None and store is None            # unset → fully dark


def test_compaction_helper_active_when_set(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("ALPHA_CONTEXT_COMPACT_THRESHOLD", "3")
    from workbench.app import _compaction
    from alpha.arena.context import OffloadStore
    compactor, store = _compaction(tmp_path / "ws")
    assert callable(compactor) and isinstance(store, OffloadStore)


def test_converse_dormant_leaves_no_marker(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    from workbench.app import create_app, set_llms
    from alpha.llm.client import MockLLMClient
    set_llms(chat=MockLLMClient(["one", "two", "three"]), agent=MockLLMClient("{}"),
             source=_fake_source())
    client = TestClient(create_app())
    for msg in ("a", "b", "c"):
        assert client.post("/converse", json={"text": msg}).status_code == 200
    msgs = client.get("/project").json()["messages"]
    assert msgs and all("elided" not in m["text"] for m in msgs)    # no compaction fired
