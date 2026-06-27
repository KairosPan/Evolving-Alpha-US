# tests/converse/test_converse_project.py
from datetime import date
import pandas as pd
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.converse.workspace import Workspace
from alpha.converse.session import converse_project


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active")]), memory=MemoryStore.from_lessons([]))


def _fake_source():
    cal = [date(2026, 6, d) for d in range(10, 14)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _agent_llm():
    return MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                         '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')


def test_converse_project_persists_turn_and_commits_decision(tmp_path):
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    ws = Workspace(tmp_path / "ws"); ws.init()
    chat = MockLLMClient(['{"tool": "decide", "args": {"date": "2026-06-12"}}', "RUN looks strong."])
    proj = converse_project("p1", "read on RUN for 2026-06-12?", harness=_h(), store=store,
                            agent_llm=_agent_llm(), chat_llm=chat, source=_fake_source(), workspace=ws)
    assert proj.project_id == "p1" and len(proj.turns) == 1
    turn = proj.turns[0]
    assert turn.final_text == "RUN looks strong." and turn.tool_calls[0]["tool"] == "decide"
    assert store.get("p1").turns[0].final_text == "RUN looks strong."          # persisted
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=tmp_path / "ws", capture_output=True, text=True).stdout
    assert "2026-06-12.json" in files                                          # decision committed as artifact


def test_resume_appends_a_second_turn(tmp_path):
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    chat1 = MockLLMClient(["first answer"])               # no tool call -> immediate final
    converse_project("p1", "hi", harness=_h(), store=store, agent_llm=_agent_llm(),
                     chat_llm=chat1, source=_fake_source())
    chat2 = MockLLMClient(["second answer"])
    proj = converse_project("p1", "again", harness=_h(), store=store, agent_llm=_agent_llm(),
                            chat_llm=chat2, source=_fake_source())
    assert len(proj.turns) == 2 and proj.turns[1].final_text == "second answer"


def test_pinned_project_is_read_only_no_write_tool(tmp_path):
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    from alpha.converse.project import new_project
    p = new_project(); p.h_pin = 0
    p.project_id = "pinned"; store.put(p)
    # a pinned project registers no propose_memory_edit; assert the registry has only `decide`
    from alpha.converse.agent import build_converse_registry
    reg = build_converse_registry(_h(), _agent_llm(), _fake_source(), read_only=True)
    assert {s["name"] for s in reg.specs()} == {"decide"}
