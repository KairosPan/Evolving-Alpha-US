from __future__ import annotations
from datetime import date, datetime
from alpha.state.builder import build_market_state
from alpha.universe.universe import CandidateUniverse
from alpha.universe.stock import StockSnapshot


def _u():
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol="RUN", name="Runner", status="gainer", pct_change=21.0,
                      close=17.0, prev_close=14.0, consecutive_up_days=3),
        StockSnapshot(symbol="GAP", name="Gapper", status="gap_up", gap_pct=8.0,
                      close=9.0, prev_close=10.0, consecutive_up_days=1),  # gapped up, closed red
        StockSnapshot(symbol="DIP", name="Dipper", status="loser", pct_change=-12.0,
                      close=8.0, prev_close=9.1, consecutive_up_days=0),
    ])


def test_counts_and_echelon():
    ms = build_market_state(_u(), date(2026, 6, 12), as_of=datetime(2026, 6, 12, 16, 0))
    assert ms.gainer_count == 1
    assert ms.gap_up_count == 1
    assert ms.loser_count == 1
    assert ms.failed_breakout_count == 1          # GAP gapped up but close < prev_close
    assert ms.max_runner_tier == 3
    assert ms.echelon[0].tier == 3 and ms.echelon[0].representatives == ["RUN"]
    assert ms.sentiment_norm is None
