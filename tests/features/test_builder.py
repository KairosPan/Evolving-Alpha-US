from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.features.builder import build_market_state


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["RUN", "DIP"], "name": ["r", "d"],
        "open": [12.0, 9.0], "high": [14, 9], "low": [12, 7], "close": [14.0, 7.0],
        "volume": [1, 1], "prev_close": [10.0, 10.0]})}                  # RUN +40%, DIP -30%
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10, 11, 12.0], "high": [11, 12, 14],
                                 "low": [10, 11, 12], "close": [10.0, 11.0, 14.0], "volume": [1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_build_market_state_enriched():
    ms = build_market_state(date(2026, 6, 12), _source(), history=[],
                            as_of=datetime(2026, 6, 12, 16, 0), prev_gainers=frozenset({"RUN"}))
    assert ms.gainer_count == 1 and ms.loser_count == 1
    assert ms.gap_and_go_count == 1                          # RUN gapped (12 vs 10) and is a gainer
    assert ms.follow_through_rate == 1.0                     # RUN was a prior gainer and still is
    assert ms.max_runner_tier == 2                           # RUN: 10<11<14 -> 2 consecutive up-days
    assert ms.echelon and ms.echelon[0].tier == 2 and ms.echelon[0].representatives == ["RUN"]
    assert ms.sentiment_norm is None                         # empty history -> insufficient samples


def test_sentiment_norm_with_history():
    ms = build_market_state(date(2026, 6, 12), _source(), history=[-100.0, -50.0, 0.0],
                            as_of=datetime(2026, 6, 12, 16, 0), prev_gainers=frozenset(),
                            min_samples=3)
    assert ms.sentiment_norm == 1.0                          # today's strong raw > all history
