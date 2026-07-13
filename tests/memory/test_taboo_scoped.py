# tests/memory/test_taboo_scoped.py
from datetime import date, timedelta

import pytest

from alpha.memory.episodes import Episode
from alpha.memory.aggregate import (
    is_episode_taboo,
    is_episode_taboo_scoped,
    matching_phase,
    summarize,
    within_recency_window,
)

ASOF = date(2026, 6, 20)
_n = 0


def _ep(outcome, *, phase="trend", learned=ASOF, sym="RUN"):
    global _n
    _n += 1
    return Episode(episode_id=f"{sym}:{outcome}:{phase}:{learned}:{_n}", symbol=sym, skill_id="s1",
                   phase=phase, entry_date=learned - timedelta(days=2), exit_date=learned,
                   outcome=outcome, advantage=-2.0 if outcome == "nuked" else 1.0, learned_asof=learned)


def test_scoped_default_reduces_to_v1():
    # no phase, no window -> exactly is_episode_taboo(summarize(...).get(symbol))
    eps = [_ep("nuked"), _ep("nuked"), _ep("nuked"), _ep("continued")]   # n=4, nuke_rate=0.75
    v1 = is_episode_taboo(summarize(eps, key=lambda e: e.symbol).get("RUN"))
    assert is_episode_taboo_scoped(eps, "RUN") == v1 is True


def test_phase_scoped_vetoes_only_in_regime():
    # RUN nukes in "flush" but is clean in "trend"
    eps = ([_ep("nuked", phase="flush") for _ in range(3)]
           + [_ep("continued", phase="trend") for _ in range(3)])
    assert is_episode_taboo_scoped(eps, "RUN", phase="flush") is True     # nukes in this regime
    assert is_episode_taboo_scoped(eps, "RUN", phase="trend") is False    # clean here
    # global (no phase): n=6, nuke_rate=0.5 -> tabooed regardless of regime (v1 behavior)
    assert is_episode_taboo_scoped(eps, "RUN") is True


def test_recency_window_expires_an_old_blowup():
    old = [_ep("nuked", learned=ASOF - timedelta(days=200)) for _ in range(3)]   # ancient nukes
    recent = [_ep("continued", learned=ASOF - timedelta(days=5)) for _ in range(3)]
    eps = old + recent
    # global: n=6, nuke_rate=0.5 -> tabooed forever
    assert is_episode_taboo_scoped(eps, "RUN") is True
    # windowed 30d: only the 3 recent cleans remain -> not tabooed
    assert is_episode_taboo_scoped(eps, "RUN", window_days=30, asof=ASOF) is False


def test_phase_and_window_compose():
    eps = ([_ep("nuked", phase="flush", learned=ASOF - timedelta(days=2)) for _ in range(3)]
           + [_ep("nuked", phase="flush", learned=ASOF - timedelta(days=200)) for _ in range(3)]
           + [_ep("continued", phase="trend", learned=ASOF) for _ in range(3)])
    # flush + within 30d -> the 3 recent flush nukes -> tabooed
    assert is_episode_taboo_scoped(eps, "RUN", phase="flush", window_days=30, asof=ASOF) is True
    # trend + within 30d -> the recent cleans -> not tabooed
    assert is_episode_taboo_scoped(eps, "RUN", phase="trend", window_days=30, asof=ASOF) is False


def test_within_recency_window_enforces_both_bounds_pit():
    inside = _ep("nuked", learned=ASOF - timedelta(days=10))
    too_old = _ep("nuked", learned=ASOF - timedelta(days=100))
    future = _ep("nuked", learned=ASOF + timedelta(days=5))        # PIT: must be excluded
    kept = within_recency_window([inside, too_old, future], asof=ASOF, window_days=30)
    assert kept == [inside]


def test_matching_phase_uses_normalizer():
    eps = [_ep("nuked", phase="trend frontside"), _ep("nuked", phase="flush")]
    # a normalizer that maps the raw prose to a canonical token
    phase_of = lambda p: "trend" if "trend" in p else p
    kept = matching_phase(eps, phase="trend", phase_of=phase_of)
    assert [e.phase for e in kept] == ["trend frontside"]


def test_window_without_asof_raises():
    with pytest.raises(ValueError):
        is_episode_taboo_scoped([_ep("nuked")], "RUN", window_days=30)
