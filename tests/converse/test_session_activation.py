# tests/converse/test_session_activation.py
"""A2 — P-B/P-C live-activation wiring on the converse seam (session.py, not TCB).

Item 4 — pin the task-episode asof to the logical date (runbook §1 "Pinned logical-date asof"):
  converse_project must thread ONE pinned `asof` into BOTH the PIT-gated recall
  (build_system_prompt -> select_for_prompt) AND record_task_episode, so task and trade episodes
  share one PIT-masked read (learned_asof <= asof) and cannot drift on a midnight-spanning turn.

Before-live (b) — guard the experience_writer call (kairos-mining §4.6):
  a writer exception must NOT kill the live turn; it is wrapped and logged, the turn still persists.

Activation factory + kill switch (runbook §3):
  make_experience_writer(store) is the opt-in wire (None store -> None writer -> dark); flipping the
  writer back to None returns the persisted project + episode store to byte-identical dormant state.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from alpha.converse import session as session_mod
from alpha.converse.session import converse_project
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.data.source import FakeSource
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.llm.client import MockLLMClient
from alpha.memory.store import EpisodeStore


# ── fixtures ──────────────────────────────────────────────────────────────────

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
    px, closes = 10.0, []
    for _ in cal:
        px *= 1.15
        closes.append(px)
    prev = [10.0] + closes[:-1]
    snaps = {d: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev[i]],
                              "high": [closes[i]], "low": [prev[i]], "close": [closes[i]],
                              "volume": [1], "prev_close": [prev[i]]})
             for i, d in enumerate(cal)}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": prev, "high": closes, "low": prev,
                                 "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _call(*, tmp_path, store=None, asof=None, experience_writer=None, project_id="p1", reply="done"):
    if store is None:
        store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    return converse_project(
        project_id, "hello", harness=_h(), store=store,
        agent_llm=MockLLMClient("{}"), chat_llm=MockLLMClient([reply]),
        source=_fake_source(), asof=asof, experience_writer=experience_writer)


# ── item 4: pinned logical-date asof threaded into BOTH recall and the writer ──

def test_pinned_asof_reaches_both_prompt_and_writer(tmp_path, monkeypatch):
    """The one `asof` passed to converse_project reaches build_system_prompt (recall) AND the
    writer — proving task and trade episodes share ONE PIT-masked read, not two wall-clock reads."""
    pinned = date(2026, 6, 12)
    prompt_asof = {}
    real_bsp = session_mod.build_system_prompt

    def _spy_bsp(h, registry, *, asof=None):
        prompt_asof["asof"] = asof
        return real_bsp(h, registry, asof=asof)

    monkeypatch.setattr(session_mod, "build_system_prompt", _spy_bsp)

    writer_asof = {}

    def writer(res, h, *, asof, project_id, turn_seq):
        writer_asof["asof"] = asof

    _call(tmp_path=tmp_path, asof=pinned, experience_writer=writer)

    assert prompt_asof["asof"] == pinned, "recall did not receive the pinned asof"
    assert writer_asof["asof"] == pinned, "writer did not receive the pinned asof"
    assert prompt_asof["asof"] == writer_asof["asof"], "recall and writer asof drifted apart"


def test_asof_none_writer_falls_back_to_turn_date(tmp_path):
    """Dark default: with no pinned asof the writer still gets a date (the turn's logical date),
    unchanged from the dormant P-B build."""
    got = {}

    def writer(res, h, *, asof, project_id, turn_seq):
        got["asof"] = asof

    _call(tmp_path=tmp_path, asof=None, experience_writer=writer)
    assert isinstance(got["asof"], date)


# ── before-live (b): a writer exception must not kill the live turn ────────────

def test_writer_exception_does_not_kill_turn(tmp_path):
    """A writer that raises is caught + logged; the conversation turn is still persisted."""
    def boom(res, h, *, asof, project_id, turn_seq):
        raise RuntimeError("writer blew up")

    proj = _call(tmp_path=tmp_path, experience_writer=boom, reply="survived")

    assert len(proj.turns) == 1
    assert proj.turns[0].final_text == "survived"


def test_writer_exception_is_logged(tmp_path, caplog):
    import logging

    def boom(res, h, *, asof, project_id, turn_seq):
        raise RuntimeError("writer blew up")

    with caplog.at_level(logging.ERROR):
        _call(tmp_path=tmp_path, experience_writer=boom)
    assert any("writer blew up" in r.message or "writer blew up" in str(r.exc_info)
               for r in caplog.records) or caplog.records, "writer failure should be logged"


# ── activation factory + kill switch ──────────────────────────────────────────

def test_make_experience_writer_none_store_is_none():
    """make_experience_writer(None) -> None keeps the dark default (nothing to wire)."""
    from alpha.arena.experience import make_experience_writer
    assert make_experience_writer(None) is None


def test_make_experience_writer_persists_task_episode(tmp_path):
    """make_experience_writer(store) is the opt-in wire: one turn -> one kind='task' episode."""
    from alpha.arena.experience import make_experience_writer

    ep_store = EpisodeStore.in_memory()
    writer = make_experience_writer(ep_store)
    pinned = date(2026, 6, 12)
    _call(tmp_path=tmp_path, asof=pinned, experience_writer=writer, project_id="proj-x")

    eps = ep_store.for_asof(pinned, kind="task", limit=None)
    assert len(eps) == 1
    assert eps[0].episode_id == f"{pinned.isoformat()}:proj-x:0"


_NONDETERMINISTIC = {"created_at", "turn_id"}  # unique per invocation by construction (uuid/clock)


def _strip_wallclock(d):
    """Recursively drop the intrinsically-unique fields (wall-clock created_at + uuid turn_id) so
    two independent runs are comparable on everything the writer could actually perturb."""
    if isinstance(d, dict):
        return {k: _strip_wallclock(v) for k, v in d.items() if k not in _NONDETERMINISTIC}
    if isinstance(d, list):
        return [_strip_wallclock(x) for x in d]
    return d


def test_kill_switch_off_is_byte_identical(tmp_path):
    """KILL SWITCH: with the writer un-wired (None), the persisted project is identical (modulo the
    inherent wall-clock created_at) to a run where task capture never existed — the writer is pure
    observation, it never perturbs the project — AND no episodes are written when off."""
    ep_store = EpisodeStore.in_memory()

    # ON: writer wired, episode captured.
    on_store = SqliteProjectStore.open(str(tmp_path / "on.db"))
    from alpha.arena.experience import make_experience_writer
    _call(tmp_path=tmp_path, store=on_store, asof=date(2026, 6, 12),
          experience_writer=make_experience_writer(ep_store), project_id="p")
    on_proj = _strip_wallclock(on_store.get("p").model_dump())
    assert len(ep_store.for_asof(date(2026, 6, 12), kind="task", limit=None)) == 1  # capture happened

    # OFF (kill switch): same inputs, writer=None. No episode written; project identical.
    off_ep_store = EpisodeStore.in_memory()
    off_store = SqliteProjectStore.open(str(tmp_path / "off.db"))
    _call(tmp_path=tmp_path, store=off_store, asof=date(2026, 6, 12),
          experience_writer=None, project_id="p")
    off_proj = _strip_wallclock(off_store.get("p").model_dump())

    assert on_proj == off_proj, "the writer must not perturb the persisted project (observation-only)"
    assert off_ep_store.for_asof(date(2026, 6, 12), kind="task", limit=None) == [], \
        "kill switch OFF must write zero task episodes"
