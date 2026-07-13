"""A3 PART 1 — the compactor injected into converse_project (dormant by default; recall round-trip).

converse must NOT import arena (layer spine); the compactor + recall tool are arena-owned and
injected, exactly like experience_writer. These tests drive that injection seam end to end."""
from __future__ import annotations

import json
from datetime import date
from functools import partial

import pandas as pd

from alpha.arena.builder import build_arena
from alpha.arena.context import FakeSummarizer, OffloadStore, compact_messages, elided_hashes
from alpha.converse.project import new_project
from alpha.converse.session import converse_project
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.data.source import FakeSource
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.llm.chat import ChatMessage
from alpha.llm.client import MockLLMClient


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
    return FakeSource(calendar=cal, bars={}, snapshots=snaps)


def _seed(store, n=5):
    p = new_project(); p.project_id = "p1"
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        origin = "user" if role == "user" else "model"
        p.messages.append(ChatMessage(role=role, text=f"history {i}", origin=origin))
    store.put(p)


def test_compactor_none_is_dormant(tmp_path):
    """Default (no compactor) accumulates messages with no marker — byte-identical to today."""
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    _seed(store, 5)
    chat = MockLLMClient(["ok"])                            # no tool call -> immediate final
    proj = converse_project("p1", "next", harness=_h(), store=store, agent_llm=MockLLMClient("{}"),
                            chat_llm=chat, source=_fake_source())
    assert all("elided" not in m.text for m in proj.messages)
    # 5 seeded + user turn + (assistant reply appended by the loop only on a tool call; a
    # no-tool final does not append) => the history is intact and uncompacted.
    assert proj.messages[0].text == "history 0"


def test_injected_compactor_prunes_with_recoverable_handle_and_recall(tmp_path):
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    _seed(store, 5)
    offload = OffloadStore(tmp_path / "ws")
    compactor = partial(compact_messages, summarizer=FakeSummarizer(), offload_store=offload,
                        protect_head=1, protect_tail=2, threshold=3)
    chat = MockLLMClient(["done"])
    proj = converse_project("p1", "please continue", harness=_h(), store=store,
                            agent_llm=MockLLMClient("{}"), chat_llm=chat, source=_fake_source(),
                            compactor=compactor)

    # turn-0 task bookend preserved; a kernel-origin elided marker replaced the middle
    assert proj.messages[0].text == "history 0"
    markers = [m for m in proj.messages if "elided" in m.text]
    assert len(markers) == 1 and markers[0].origin == "kernel"

    # the handle recovers the original middle verbatim (lose bytes, not handles)
    hashes = elided_hashes(markers[0].text)
    assert len(hashes) == 1
    recovered = json.loads(offload.get(hashes[0]))
    assert any(r["text"] == "history 1" for r in recovered)

    # and the T0 recall tool, registered over the SAME store, fetches it back through the choke point
    _, policy = build_arena(_h(), MockLLMClient("{}"), _fake_source(), workspace=tmp_path / "ws",
                            offload_store=offload)
    out = policy.dispatch("recall", {"hash": hashes[0]})
    assert out["ok"] is True and "history 1" in out["content"]
