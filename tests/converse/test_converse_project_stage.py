# tests/converse/test_converse_project_stage.py
import copy
from datetime import date
import pandas as pd
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.converse.session import converse_project

def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]), memory=MemoryStore.from_lessons([]))

def _src():
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def test_worker_cannot_stage_a_proposal(tmp_path):
    """A7 (charter First Founding Principle: "Kairos does not propose at all"): the propose tool is
    retired, so a model call to propose_memory_edit stages NOTHING — the turn completes with an
    'unknown tool' result and the live brain is byte-untouched."""
    h = _h(); before = copy.deepcopy(h.to_dict())
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    chat = MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "I cannot stage that.",
    ])
    proj = converse_project("default", "remember this", harness=h, store=store,
                            agent_llm=MockLLMClient("{}"), chat_llm=chat, source=_src(), write_mode="stage")
    assert proj.staged_edits == []                                 # nothing staged (no propose tool)
    assert h.to_dict() == before                                  # live brain untouched
    assert store.get("default").staged_edits == []                # persisted state also empty
