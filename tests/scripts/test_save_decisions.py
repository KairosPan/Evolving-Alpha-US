"""Offline smoke for scripts/save_decisions.py: produce real daily DecisionPackages from a source via
the live agent + L4 guard + L3 sizing composition (injected MockLLM, no keys/data needed) and persist
them to a DecisionStore the web console can browse."""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.data.source import FakeSource
from alpha.eval.decision_store import DecisionStore
from alpha.llm.client import MockLLMClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import save_decisions as sd   # noqa: E402

_AGENT = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')


def _fake(n=8):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps), cal[0], cal[-1]


def test_produce_decisions_one_per_trading_day():
    src, start, end = _fake()
    pkgs = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT))
    assert len(pkgs) == 8
    assert [p.date for p in pkgs] == src.trading_calendar()


def test_produced_package_is_sized_and_guarded():
    src, start, end = _fake()
    pkgs = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT))
    sized = [p for p in pkgs if p.candidates]      # a frontside-trend day keeps RUN past the L4 guard
    assert sized, "expected at least one day to surface a candidate"
    last = sized[-1]
    assert last.regime is not None and last.portfolio is not None       # L4 set regime, L3 set portfolio
    assert last.candidates[0].size_tier in {"flat", "probe", "core", "heavy"}


def test_save_decisions_persists_browsable_by_date(tmp_path):
    src, start, end = _fake()
    store = DecisionStore(tmp_path)
    n = sd.save_decisions(src, start, end, store, agent_llm_factory=_AGENT)
    assert n == 8 and len(store) == 8
    assert store.dates() == src.trading_calendar()
    assert store.latest() is not None and store.get(store.dates()[0]) is not None


def test_screen_off_skips_the_guard():
    src, start, end = _fake()
    pkgs = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT, screen=False, size=False))
    # unguarded: RUN surfaces every day (no regime veto), and packages are unsized
    assert all(p.candidates and p.candidates[0].symbol == "RUN" for p in pkgs)
    assert all(p.candidates[0].size_tier is None for p in pkgs)
