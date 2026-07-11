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
    # D3 end-to-end pin: a prompt-audit sidecar lands beside each day's decision file
    import json
    for d in store.dates():
        side_path = tmp_path / f"{d.isoformat()}.prompt.json"
        assert side_path.exists(), f"missing prompt sidecar for {d}"
        side = json.loads(side_path.read_text())
        assert side["date"] == d.isoformat()
        assert side["records"], "sidecar records must be non-empty"
        assert side["assembled"], "sidecar must carry the assembled prompt text"
        assert all(r["kind"] != "assembled" for r in side["records"])   # lifted to the top-level field


# ---------------------------------------------------------------------------
# Task 7: optional read-only brain -> §6 recall+taboo on the act-only path
# ---------------------------------------------------------------------------

def _seed_taboo_store(symbol="RUN", n=3):
    """recall_store seeded so `symbol` is taboo: n PIT-old nuked episodes (learned long before the run)."""
    from alpha.memory.store import EpisodeStore
    from alpha.memory.episodes import Episode
    s = EpisodeStore.in_memory()
    for i in range(n):
        s.add(Episode(episode_id=f"{symbol}:{i}", symbol=symbol, skill_id="gap_and_go",
                      entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 2),
                      outcome="nuked", advantage=-2.0, learned_asof=date(2026, 1, 2)))
    return s


def test_produce_decisions_taboo_drops_candidate():
    """With a seeded brain, the act-only path drops a taboo symbol from the daily packages; with no brain
    (episode_store=None) RUN survives the frontside L4 guard (so ONLY taboo, not the regime, drops it)."""
    src, start, end = _fake()
    store = _seed_taboo_store("RUN")
    pkgs = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT, episode_store=store))
    assert all("RUN" not in [c.symbol for c in p.candidates] for p in pkgs)
    pkgs_off = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT, episode_store=None))
    assert any("RUN" in [c.symbol for c in p.candidates] for p in pkgs_off)   # off -> not dropped


def test_screen_off_skips_the_guard():
    src, start, end = _fake()
    pkgs = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT, screen=False, size=False))
    # unguarded: RUN surfaces every day (no regime veto), and packages are unsized
    assert all(p.candidates and p.candidates[0].symbol == "RUN" for p in pkgs)
    assert all(p.candidates[0].size_tier is None for p in pkgs)
