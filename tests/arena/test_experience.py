"""Tests for alpha/arena/experience.py — record_task_episode (PB-4)."""
from __future__ import annotations
import json
from datetime import date

import pytest

from alpha.converse.loop import ConversationResult
from alpha.harness.loader import load_seeds
from alpha.memory.store import EpisodeStore
from alpha.arena.experience import record_task_episode

_D = date(2026, 6, 28)


@pytest.fixture()
def store():
    return EpisodeStore.in_memory()


@pytest.fixture()
def h():
    return load_seeds("seeds")


# ── happy-path ────────────────────────────────────────────────────────────────

def test_record_task_episode_writes_one_episode(store, h):
    res = ConversationResult(
        tool_calls=[{"tool": "shell", "args": {"argv": ["echo", "hi"]},
                     "result": {"ok": True, "exit_code": 0}}],
        final_text="done",
        hit_max_iters=False,
    )
    ep = record_task_episode(res, h, asof=_D, project_id="p", turn_seq=3,
                             episode_store=store)

    assert ep is not None
    assert ep.kind == "task"
    assert ep.entry_date == _D
    assert ep.exit_date == _D
    assert ep.learned_asof == _D
    assert ep.episode_id == f"{_D.isoformat()}:p:3"
    assert ep.advantage == 0.0
    assert ep.score == 0.0
    assert ep.outcome == "succeeded"
    assert ep.symbol == ""
    assert ep.reflection_text != ""
    # reflection_text must be parseable JSON and list the tool name
    body = json.loads(ep.reflection_text)
    assert isinstance(body, dict)
    tool_names = [t["tool"] for t in body.get("tools", [])]
    assert "shell" in tool_names

    # exactly one episode in the store
    all_eps = store.all()
    assert len(all_eps) == 1
    assert all_eps[0].episode_id == ep.episode_id


def test_record_task_episode_none_store_returns_none(h):
    res = ConversationResult(
        tool_calls=[{"tool": "shell", "args": {}, "result": {"ok": True, "exit_code": 0}}],
        final_text="done", hit_max_iters=False,
    )
    result = record_task_episode(res, h, asof=_D, project_id="p", turn_seq=1,
                                 episode_store=None)
    assert result is None


def test_record_task_episode_none_store_writes_nothing(h, store):
    """Sanity: passing None leaves the given store untouched."""
    res = ConversationResult(final_text="x", hit_max_iters=False)
    record_task_episode(res, h, asof=_D, project_id="p", turn_seq=99,
                        episode_store=None)
    assert store.all() == []


# ── outcome precedence — parametrized (PB-5 §1.4) ────────────────────────────

@pytest.mark.parametrize("tool_calls,hit_max_iters,expected", [
    # (a) hit_max_iters → "incomplete" regardless of tool results
    (
        [{"tool": "shell", "args": {}, "result": {"ok": True, "exit_code": 0}}],
        True,
        "incomplete",
    ),
    # (b) shell ExecResult ok=False → "failed" (checked before error key)
    (
        [{"tool": "shell", "args": {}, "result": {"ok": False, "exit_code": 1}}],
        False,
        "failed",
    ),
    # (c) any tool result carrying {"error": ...} → "failed"
    (
        [{"tool": "anything", "args": {}, "result": {"error": "boom"}}],
        False,
        "failed",
    ),
    # (d) no failure signal → "succeeded"
    (
        [{"tool": "shell", "args": {}, "result": {"ok": True, "exit_code": 0}}],
        False,
        "succeeded",
    ),
])
def test_task_outcome_precedence(tool_calls, hit_max_iters, expected):
    """Parametrized spec §1.4 coverage for _task_outcome (PB-5)."""
    from alpha.arena.experience import _task_outcome
    res = ConversationResult(tool_calls=tool_calls, final_text="x", hit_max_iters=hit_max_iters)
    assert _task_outcome(res) == expected


def test_outcome_incomplete_when_hit_max_iters(store, h):
    res = ConversationResult(
        tool_calls=[{"tool": "shell", "args": {}, "result": {"ok": True, "exit_code": 0}}],
        final_text="...", hit_max_iters=True,
    )
    ep = record_task_episode(res, h, asof=_D, project_id="p", turn_seq=10,
                             episode_store=store)
    assert ep.outcome == "incomplete"


def test_outcome_failed_on_tool_error(store, h):
    res = ConversationResult(
        tool_calls=[{"tool": "shell", "args": {}, "result": {"error": "bad"}}],
        final_text="done", hit_max_iters=False,
    )
    ep = record_task_episode(res, h, asof=_D, project_id="p", turn_seq=11,
                             episode_store=store)
    assert ep.outcome == "failed"


def test_outcome_failed_on_shell_exit_nonzero(store, h):
    res = ConversationResult(
        tool_calls=[{"tool": "shell", "args": {}, "result": {"ok": False, "exit_code": 1}}],
        final_text="done", hit_max_iters=False,
    )
    ep = record_task_episode(res, h, asof=_D, project_id="p", turn_seq=12,
                             episode_store=store)
    assert ep.outcome == "failed"


def test_outcome_incomplete_beats_failure(store, h):
    """hit_max_iters takes precedence over tool errors (§1.4 precedence)."""
    res = ConversationResult(
        tool_calls=[{"tool": "shell", "args": {}, "result": {"error": "boom"}}],
        final_text="...", hit_max_iters=True,
    )
    ep = record_task_episode(res, h, asof=_D, project_id="p", turn_seq=13,
                             episode_store=store)
    assert ep.outcome == "incomplete"


# ── idempotency ───────────────────────────────────────────────────────────────

def test_insert_or_ignore_idempotency(store, h):
    res = ConversationResult(final_text="ok", hit_max_iters=False)
    record_task_episode(res, h, asof=_D, project_id="p", turn_seq=5, episode_store=store)
    record_task_episode(res, h, asof=_D, project_id="p", turn_seq=5, episode_store=store)
    assert len(store.all()) == 1


# ── PIT recall fence ─────────────────────────────────────────────────────────

def test_task_episodes_not_visible_in_default_trade_recall(store, h):
    """kind='task' rows must NOT appear when for_asof is called with the default kind='trade'."""
    res = ConversationResult(final_text="ok", hit_max_iters=False)
    ep = record_task_episode(res, h, asof=_D, project_id="p", turn_seq=7, episode_store=store)
    assert ep is not None

    trade_rows = store.for_asof(_D, limit=None)   # default kind="trade"
    assert not any(e.episode_id == ep.episode_id for e in trade_rows)

    task_rows = store.for_asof(_D, kind="task", limit=None)
    assert any(e.episode_id == ep.episode_id for e in task_rows)


# ── membrane: no H mutation ───────────────────────────────────────────────────

def test_harness_to_dict_unchanged_after_record(store, h):
    """record_task_episode must not mutate H (§1.6 / BINDING observation-channel)."""
    before = h.to_dict()
    res = ConversationResult(
        tool_calls=[{"tool": "shell", "args": {}, "result": {"ok": True, "exit_code": 0}}],
        final_text="done", hit_max_iters=False,
    )
    record_task_episode(res, h, asof=_D, project_id="p", turn_seq=20, episode_store=store)
    assert h.to_dict() == before


# ── PB-6: comprehensive observation-channel membrane pin ─────────────────────

def _h_with_stats() -> object:
    """Return a fresh harness whose every skill has nonzero stats (PB-6 membrane fixture)."""
    hh = load_seeds("seeds")
    for sk in hh.skills.all():
        sk.stats.record(True)
        sk.stats.record(False)
    return hh


def test_observation_channel_membrane_comprehensive(store):
    """PB-6 BINDING: after record_task_episode on a turn referencing an existing skill_id:

    1. json.dumps(h.to_dict(), sort_keys=True, default=str) is byte-identical before vs after.
    2. Every Skill.stats (n/wins/losses/ewma_winrate/expectancy) is unchanged.
    3. The episode's skill_id matches the referenced skill (confirms the skill was resolved,
       not silently dropped).

    Edit-log absence of EditRecord is pinned structurally by test_experience_no_forbidden_imports.
    """
    hh = _h_with_stats()
    real_skill_id = hh.skills.all()[0].skill_id

    before_json = json.dumps(hh.to_dict(), sort_keys=True, default=str)
    before_stats = {sk.skill_id: sk.stats.model_dump() for sk in hh.skills.all()}

    res = ConversationResult(
        tool_calls=[{
            "tool": "propose_skill_edit",
            "args": {"skill_id": real_skill_id},
            "result": {"status": "applied"},
        }],
        final_text="done",
        hit_max_iters=False,
    )
    ep = record_task_episode(res, hh, asof=_D, project_id="p", turn_seq=30,
                             episode_store=store)
    assert ep is not None
    assert ep.skill_id == real_skill_id, "episode must record the resolved skill_id"

    # 1. byte-identical JSON snapshot of full harness
    after_json = json.dumps(hh.to_dict(), sort_keys=True, default=str)
    assert before_json == after_json, "record_task_episode must not mutate h (JSON mismatch)"

    # 2. per-skill stats unchanged — snapshot every SkillStats field
    after_stats = {sk.skill_id: sk.stats.model_dump() for sk in hh.skills.all()}
    for sid, snap in before_stats.items():
        assert after_stats[sid] == snap, (
            f"Skill.stats mutated for {sid}: before={snap}, after={after_stats[sid]}"
        )


def test_experience_no_forbidden_imports():
    """PB-6 BINDING: structural/AST pin — experience.py must not import
    try_apply_op, MetaTools, or SkillStats (observation-channel membrane).

    These names belong to the write-waist (refine/apply.py, harness/metatools.py,
    harness/skill.py) and must never appear in the observation-only arena layer.
    """
    import ast
    import inspect

    from alpha.arena import experience as _exp

    src = inspect.getsource(_exp)
    tree = ast.parse(src)

    forbidden = {"try_apply_op", "MetaTools", "SkillStats"}
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)

    violations = forbidden & imported_names
    assert not violations, (
        f"experience.py imports forbidden names {violations} — "
        "observation-channel membrane breach (spec §1.3)"
    )
