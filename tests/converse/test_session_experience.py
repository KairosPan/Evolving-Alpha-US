"""TDD PB-7: experience_writer injection into converse_project.

Three tests (a/b/c) from the task-7 brief:

(a) No experience_writer → byte-identical behavior (existing path unaffected).
(b) Injected writer stub is called exactly once per turn with the correct
    positional/keyword arguments: (res, h, asof=<date>, project_id=<str>, turn_seq=<int>).
(c) Integration: record_task_episode bound to a real EpisodeStore, injected as the
    writer, persists exactly one kind='task' episode keyed {turn_date}:{project_id}:{turn_seq}.
"""
from __future__ import annotations

from datetime import date
import pandas as pd
import pytest

from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.converse.session import converse_project


# ── shared fixtures ───────────────────────────────────────────────────────────

def _h():
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills([
            Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern",
                  family="runner", phases=["trend"], status="active"),
        ]),
        memory=MemoryStore.from_lessons([]),
    )


def _fake_source():
    cal = [date(2026, 6, d) for d in range(10, 14)]
    px = 10.0
    closes, prev_closes = [], [10.0]
    for _ in cal:
        px = px * 1.15
        closes.append(px)
    prev_closes = [10.0] + closes[:-1]
    snaps = {}
    for i, d in enumerate(cal):
        snaps[d] = pd.DataFrame({
            "symbol": ["RUN"], "name": ["RUN"],
            "open": [prev_closes[i]], "high": [closes[i]],
            "low": [prev_closes[i]], "close": [closes[i]],
            "volume": [1], "prev_close": [prev_closes[i]],
        })
    bars = {"RUN": pd.DataFrame({
        "date": cal, "open": prev_closes, "high": closes,
        "low": prev_closes, "close": closes, "volume": [1] * len(cal),
    })}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _call(project_id="p1", user_text="hello", *, tmp_path, store=None, experience_writer=None,
          reply="done"):
    if store is None:
        store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    return converse_project(
        project_id, user_text,
        harness=_h(), store=store,
        agent_llm=MockLLMClient("{}"),
        chat_llm=MockLLMClient([reply]),
        source=_fake_source(),
        experience_writer=experience_writer,
    )


# ── (a) no writer → byte-identical ───────────────────────────────────────────

def test_no_writer_turn_is_persisted(tmp_path):
    """Passing no experience_writer leaves existing behaviour unchanged."""
    proj = _call(tmp_path=tmp_path)
    assert len(proj.turns) == 1
    assert proj.turns[0].final_text == "done"


def test_no_writer_no_exception(tmp_path):
    """Omitting experience_writer must not raise."""
    _call(tmp_path=tmp_path)


# ── (b) injected writer is called exactly once with correct args ──────────────

def test_writer_called_exactly_once(tmp_path):
    calls: list[dict] = []

    def stub(res, h, *, asof, project_id, turn_seq):
        calls.append({"res": res, "h": h, "asof": asof,
                      "project_id": project_id, "turn_seq": turn_seq})

    _call(tmp_path=tmp_path, experience_writer=stub)
    assert len(calls) == 1, f"expected 1 call, got {len(calls)}"


def test_writer_receives_conversation_result(tmp_path):
    from alpha.converse.loop import ConversationResult
    calls: list[dict] = []

    def stub(res, h, *, asof, project_id, turn_seq):
        calls.append({"res": res})

    _call(tmp_path=tmp_path, experience_writer=stub)
    assert isinstance(calls[0]["res"], ConversationResult)


def test_writer_receives_harness_state(tmp_path):
    calls: list[dict] = []

    def stub(res, h, *, asof, project_id, turn_seq):
        calls.append({"h": h})

    _call(tmp_path=tmp_path, experience_writer=stub)
    assert isinstance(calls[0]["h"], HarnessState)


def test_writer_receives_date_asof(tmp_path):
    calls: list[dict] = []

    def stub(res, h, *, asof, project_id, turn_seq):
        calls.append({"asof": asof})

    _call(tmp_path=tmp_path, experience_writer=stub)
    assert isinstance(calls[0]["asof"], date)


def test_writer_receives_correct_project_id(tmp_path):
    calls: list[dict] = []

    def stub(res, h, *, asof, project_id, turn_seq):
        calls.append({"project_id": project_id})

    _call("my-proj", tmp_path=tmp_path, experience_writer=stub)
    assert calls[0]["project_id"] == "my-proj"


def test_writer_first_turn_seq_is_zero(tmp_path):
    calls: list[dict] = []

    def stub(res, h, *, asof, project_id, turn_seq):
        calls.append({"turn_seq": turn_seq})

    _call(tmp_path=tmp_path, experience_writer=stub)
    assert calls[0]["turn_seq"] == 0


def test_writer_turn_seq_increments(tmp_path):
    """turn_seq must increment across successive turns of the same project."""
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    calls: list[int] = []

    def stub(res, h, *, asof, project_id, turn_seq):
        calls.append(turn_seq)

    for i in range(3):
        _call(tmp_path=tmp_path, store=store, experience_writer=stub, reply=f"r{i}")

    assert calls == [0, 1, 2]


# ── (c) integration: record_task_episode as the writer ───────────────────────

def test_record_task_episode_as_writer_persists_kind_task(tmp_path):
    """Integration: bind record_task_episode to a real EpisodeStore; after one
    converse_project turn exactly one kind='task' episode exists, keyed
    {turn_date}:{project_id}:{turn_seq}."""
    from alpha.memory.store import EpisodeStore
    from alpha.arena.experience import record_task_episode  # fine in a test

    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    ep_store = EpisodeStore.in_memory()
    captured: dict = {}

    def writer(res, h, *, asof, project_id, turn_seq):
        captured["asof"] = asof
        record_task_episode(res, h, asof=asof, project_id=project_id,
                            turn_seq=turn_seq, episode_store=ep_store)

    _call("proj-x", tmp_path=tmp_path, store=store, experience_writer=writer)

    # Query at the turn's pinned asof — the SAME PIT key the episode was written under, and the kind
    # filter is the verdict-neutrality fence (default is trade). Using date.today() here is a timezone
    # trap: created_at is UTC, so its date can run a day ahead of the local date, and the PIT filter
    # would then (correctly) hide the future-dated episode → 0 rows.
    eps = ep_store.for_asof(captured["asof"], kind="task", limit=None)
    assert len(eps) == 1, f"expected 1 task episode, got {len(eps)}: {eps}"

    ep = eps[0]
    assert ep.kind == "task"
    parts = ep.episode_id.split(":")
    # episode_id = "{turn_date}:{project_id}:{turn_seq}"
    assert parts[0] == captured["asof"].isoformat(), f"date mismatch in episode_id: {ep.episode_id}"
    assert parts[1] == "proj-x", f"project_id mismatch in episode_id: {ep.episode_id}"
    assert parts[2] == "0", f"turn_seq mismatch in episode_id: {ep.episode_id}"


def test_task_episodes_not_visible_via_default_trade_recall(tmp_path):
    """kind='task' episodes must not leak into the default (kind='trade') recall path."""
    from alpha.memory.store import EpisodeStore
    from alpha.arena.experience import record_task_episode

    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    ep_store = EpisodeStore.in_memory()
    captured: dict = {}

    def writer(res, h, *, asof, project_id, turn_seq):
        captured["asof"] = asof
        record_task_episode(res, h, asof=asof, project_id=project_id,
                            turn_seq=turn_seq, episode_store=ep_store)

    _call(tmp_path=tmp_path, store=store, experience_writer=writer)

    # Query at the episode's own asof so the assertion is non-vacuous: a kind='task' episode IS
    # visible at this date, so an empty result proves the kind='trade' filter excludes it — not that
    # the date happened to hide it (date.today() can lag the UTC-derived asof and pass vacuously).
    trade_rows = ep_store.for_asof(captured["asof"], limit=None)  # default kind="trade"
    assert trade_rows == [], f"task episodes leaked into trade recall: {trade_rows}"
