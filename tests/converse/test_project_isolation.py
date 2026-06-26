# tests/converse/test_project_isolation.py
from datetime import date
import pandas as pd, subprocess
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.store import ProjectStore
from alpha.converse.workspace import Workspace
from alpha.converse.session import converse_project

def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active")]), memory=MemoryStore.from_lessons([]))

def _src():
    cal = [date(2026, 6, d) for d in range(10, 14)]; snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def _agent():
    return MockLLMClient('{"regime_read": "trend frontside", "candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')

def test_two_projects_share_brain_isolate_workspaces(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    h = _h()                                              # ONE shared brain instance
    wsA = Workspace(tmp_path / "A"); wsA.init()
    wsB = Workspace(tmp_path / "B"); wsB.init()
    converse_project("A", "read for 2026-06-11?", harness=h, store=store, agent_llm=_agent(),
                     chat_llm=MockLLMClient(['{"tool": "decide", "args": {"date": "2026-06-11"}}', "A done"]),
                     source=_src(), workspace=wsA)
    converse_project("B", "read for 2026-06-12?", harness=h, store=store, agent_llm=_agent(),
                     chat_llm=MockLLMClient(['{"tool": "decide", "args": {"date": "2026-06-12"}}', "B done"]),
                     source=_src(), workspace=wsB)
    filesA = subprocess.run(["git", "ls-files"], cwd=tmp_path / "A", capture_output=True, text=True).stdout
    filesB = subprocess.run(["git", "ls-files"], cwd=tmp_path / "B", capture_output=True, text=True).stdout
    assert "2026-06-11.json" in filesA and "2026-06-11.json" not in filesB    # workspaces isolated
    assert "2026-06-12.json" in filesB and "2026-06-12.json" not in filesA
    assert store.get("A").project_id == "A" and store.get("B").project_id == "B"   # two distinct projects
    assert {p.project_id for p in store.list()} == {"A", "B"}                 # one shared store, no fork
