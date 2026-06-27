"""Tests: episode-taboo veto threaded through screen_decision + GuardedPolicy.

Load-bearing contract:
- A symbol with >= 3 nuked episodes (learned by state.date) is DROPPED, not annotated.
- A nuke whose exit_date is AFTER state.date is invisible (PIT mask).
- No store (episode_store=None) or empty store -> byte-identical pass-through.
- GuardedPolicy(inner, source, episode_store=store) drops the taboo symbol end-to-end.
"""
from datetime import date

import pytest

from alpha.eval.decision import Candidate, DecisionPackage
from alpha.guard.screen import GuardedPolicy, screen_decision
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.universe.universe import CandidateUniverse

# Reuse the exact fixture helpers from test_screen.py so "CLEAN" is truly clean
# (sn=0.7 -> trend/frontside, no SSR on rising bars, no corp-action veto).
from tests.guard.test_screen import _src, _state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SYMBOL = "CLEAN"
_PATTERN = "gap_and_go"


def _clean_src():
    """Rising bars for CLEAN -> no SSR, no halt-then-dump."""
    return _src({_SYMBOL: [10.0, 11.0, 12.0]})


def _nuked_store(symbol: str = _SYMBOL, n: int = 3, exit_d: date = date(2026, 6, 3)) -> EpisodeStore:
    """EpisodeStore seeded with `n` nuked episodes for `symbol` exiting on `exit_d`."""
    s = EpisodeStore.in_memory()
    for i in range(n):
        s.add(Episode(
            episode_id=f"{symbol}:{i}",
            symbol=symbol,
            skill_id=_PATTERN,
            entry_date=date(2026, 6, 1),
            exit_date=exit_d,
            outcome="nuked",
            advantage=-2.0,
        ))
    return s


def _pkg(symbol: str = _SYMBOL) -> DecisionPackage:
    return DecisionPackage(
        date=date(2026, 6, 12),
        candidates=[Candidate(symbol=symbol, pattern=_PATTERN)],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_episode_taboo_drops_the_candidate():
    """3 nuked episodes (exit 2026-06-03) are visible by state.date 2026-06-12 -> symbol vetoed."""
    src = _clean_src()
    state = _state()                                    # date = 2026-06-12 (after exit 2026-06-03)
    store = _nuked_store(exit_d=date(2026, 6, 3))

    out = screen_decision(_pkg(), source=src, state=state, episode_store=store)

    assert all(c.symbol != _SYMBOL for c in out.candidates), "taboo symbol must be dropped"
    assert any("episode taboo" in n for n in out.key_risks), "key_risks must mention episode taboo"


def test_pit_future_nuke_does_not_taboo():
    """3 nuked episodes with exit_date AFTER state.date are invisible (PIT) -> symbol kept."""
    src = _clean_src()
    state = _state()                                    # date = 2026-06-12
    store = _nuked_store(exit_d=date(2026, 9, 1))      # learned AFTER state.date -> invisible

    out = screen_decision(_pkg(), source=src, state=state, episode_store=store)

    assert any(c.symbol == _SYMBOL for c in out.candidates), "future nuke must NOT veto (PIT)"


def test_no_store_unchanged():
    """episode_store=None and episode_store=EpisodeStore.in_memory() (empty) are byte-identical."""
    src = _clean_src()
    state = _state()

    out_none = screen_decision(_pkg(), source=src, state=state)
    out_empty = screen_decision(_pkg(), source=src, state=state, episode_store=EpisodeStore.in_memory())

    assert [c.symbol for c in out_none.candidates] == [c.symbol for c in out_empty.candidates]
    assert out_none.key_risks == out_empty.key_risks


def test_guarded_policy_episode_store_end_to_end():
    """GuardedPolicy(inner, source, episode_store=store) drops the taboo symbol via decide()."""
    src = _clean_src()
    state = _state()
    store = _nuked_store(exit_d=date(2026, 6, 3))

    class _Stub:
        def decide(self, state, universe):
            return _pkg()

    gp = GuardedPolicy(_Stub(), src, episode_store=store)
    out = gp.decide(state, CandidateUniverse.from_stocks([]))

    assert all(c.symbol != _SYMBOL for c in out.candidates), "GuardedPolicy must drop taboo symbol"
    assert any("episode taboo" in n for n in out.key_risks)
