"""RED → GREEN: task aggregator with confirmed-positive counting (PC-7, Task 16).

Tests mirror the existing test_aggregate.py pattern but use kind="task" episodes
and the task vocabulary (succeeded/failed/incomplete).
"""
from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.aggregate import TaskStats, summarize_task


def _task_ep(skill: str, outcome: str, episode_id: str | None = None) -> Episode:
    eid = episode_id or f"{skill}:{outcome}"
    return Episode(
        episode_id=eid,
        symbol="",
        skill_id=skill,
        kind="task",
        entry_date=date(2026, 6, 1),
        exit_date=date(2026, 6, 1),
        outcome=outcome,
        advantage=0.0,
    )


# ---------------------------------------------------------------------------
# (a) task vocabulary counted into observed-n
# ---------------------------------------------------------------------------

def test_task_vocab_counted_into_n():
    eps = [
        _task_ep("op_skill", "succeeded", "ep1"),
        _task_ep("op_skill", "failed", "ep2"),
        _task_ep("op_skill", "incomplete", "ep3"),
    ]
    stats = summarize_task(eps, key=lambda e: e.skill_id)
    s = stats["op_skill"]
    assert s.n == 3
    assert s.succeeded == 1
    assert s.failed == 1
    assert s.incomplete == 1


def test_multiple_skills_grouped_independently():
    eps = [
        _task_ep("skill_a", "succeeded", "ep_a1"),
        _task_ep("skill_a", "failed", "ep_a2"),
        _task_ep("skill_b", "succeeded", "ep_b1"),
    ]
    stats = summarize_task(eps, key=lambda e: e.skill_id)
    assert stats["skill_a"].n == 2
    assert stats["skill_a"].succeeded == 1
    assert stats["skill_b"].n == 1
    assert stats["skill_b"].succeeded == 1


# ---------------------------------------------------------------------------
# (b) synchronous succeeded with NO external confirmation → neutral
#     raises observed-n/succeeded but NOT confirmed_success (anti-Goodhart, verdict 5)
# ---------------------------------------------------------------------------

def test_unconfirmed_succeeded_is_neutral():
    """A default-pass 'succeeded' with no external confirmation must not feed confirmed_success."""
    eps = [_task_ep("op_skill", "succeeded", "ep1")]
    stats = summarize_task(eps, key=lambda e: e.skill_id)  # confirmed_ids defaults to frozenset()
    s = stats["op_skill"]
    assert s.n == 1
    assert s.succeeded == 1
    assert s.confirmed_success == 0
    assert s.confirmed_n == 0
    assert s.confirmed_success_rate == 0.0


def test_multiple_unconfirmed_succeeded_all_neutral():
    eps = [
        _task_ep("op_skill", "succeeded", "ep1"),
        _task_ep("op_skill", "succeeded", "ep2"),
    ]
    stats = summarize_task(eps, key=lambda e: e.skill_id)
    s = stats["op_skill"]
    assert s.n == 2
    assert s.succeeded == 2
    assert s.confirmed_success == 0
    assert s.confirmed_n == 0


# ---------------------------------------------------------------------------
# (c) episode in confirmed_ids → contributes confirmed_success when succeeded
# ---------------------------------------------------------------------------

def test_confirmed_succeeded_counts_as_confirmed_success():
    eps = [_task_ep("op_skill", "succeeded", "ep1")]
    stats = summarize_task(eps, key=lambda e: e.skill_id, confirmed_ids=frozenset({"ep1"}))
    s = stats["op_skill"]
    assert s.confirmed_success == 1
    assert s.confirmed_n == 1
    assert s.confirmed_success_rate == 1.0


def test_confirmed_failed_raises_confirmed_n_but_not_confirmed_success():
    """A confirmed 'failed' episode raises confirmed_n (external arbiter spoke) but not confirmed_success."""
    eps = [_task_ep("op_skill", "failed", "ep1")]
    stats = summarize_task(eps, key=lambda e: e.skill_id, confirmed_ids=frozenset({"ep1"}))
    s = stats["op_skill"]
    assert s.confirmed_n == 1
    assert s.confirmed_success == 0
    assert s.confirmed_success_rate == 0.0


def test_partial_confirmation():
    """Only episodes in confirmed_ids count toward confirmed_n / confirmed_success."""
    eps = [
        _task_ep("op_skill", "succeeded", "ep1"),   # not confirmed
        _task_ep("op_skill", "succeeded", "ep2"),   # confirmed
        _task_ep("op_skill", "failed", "ep3"),       # confirmed
    ]
    stats = summarize_task(
        eps, key=lambda e: e.skill_id, confirmed_ids=frozenset({"ep2", "ep3"})
    )
    s = stats["op_skill"]
    assert s.n == 3
    assert s.confirmed_n == 2
    assert s.confirmed_success == 1   # only ep2
    assert abs(s.confirmed_success_rate - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# (d) confirmed_success_rate = confirmed_success / confirmed_n; 0.0 when confirmed_n == 0
# ---------------------------------------------------------------------------

def test_confirmed_success_rate_calculation():
    eps = [
        _task_ep("op_skill", "succeeded", "ep1"),
        _task_ep("op_skill", "failed", "ep2"),
        _task_ep("op_skill", "succeeded", "ep3"),   # not confirmed
    ]
    stats = summarize_task(
        eps, key=lambda e: e.skill_id, confirmed_ids=frozenset({"ep1", "ep2"})
    )
    s = stats["op_skill"]
    assert s.confirmed_n == 2
    assert s.confirmed_success == 1
    assert abs(s.confirmed_success_rate - 0.5) < 1e-9


def test_confirmed_success_rate_zero_when_no_confirmed():
    eps = [_task_ep("op_skill", "succeeded", "ep1")]
    stats = summarize_task(eps, key=lambda e: e.skill_id)
    assert stats["op_skill"].confirmed_success_rate == 0.0


def test_confirmed_success_rate_zero_on_empty_stats():
    """TaskStats with all-zeros is valid and rate is 0.0."""
    s = TaskStats(n=0, succeeded=0, failed=0, incomplete=0, confirmed_success=0, confirmed_n=0)
    assert s.confirmed_success_rate == 0.0


# ---------------------------------------------------------------------------
# Non-regression: existing trade summarize/is_episode_taboo still work correctly
# alongside the new task aggregator (shared module, no cross-contamination).
# ---------------------------------------------------------------------------

def test_trade_summarize_unaffected_by_task_import():
    """Importing summarize_task does not disturb the existing trade summarize."""
    from alpha.memory.aggregate import summarize, is_episode_taboo, EpisodeStats
    from alpha.memory.episodes import Episode

    trade_eps = [
        Episode(episode_id="t1", symbol="RUN", skill_id="s", kind="trade",
                entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3),
                outcome="nuked", advantage=-1.0),
        Episode(episode_id="t2", symbol="RUN", skill_id="s", kind="trade",
                entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3),
                outcome="continued", advantage=2.0),
    ]
    stats = summarize(trade_eps, key=lambda e: e.symbol)
    run = stats["RUN"]
    assert run.n == 2 and run.nuked == 1 and run.continued == 1
    assert is_episode_taboo(run) is False
