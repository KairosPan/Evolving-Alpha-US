from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.features.breadth import (
    counts, failed_breakout_count, follow_through_rate, gap_and_go_count,
)


def _u():
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol="RUN", status="gainer", name="r", pct_change=30.0, gap_pct=8.0,
                      close=13.0, prev_close=10.0),
        StockSnapshot(symbol="GAP", status="gap_up", name="g", pct_change=-2.0, gap_pct=9.0,
                      close=9.8, prev_close=10.0),         # gapped up, closed red -> failed breakout
        StockSnapshot(symbol="DIP", status="loser", name="d", pct_change=-25.0,
                      close=7.5, prev_close=10.0),
    ])


def test_counts():
    g, gu, lo = counts(_u())
    assert (g, gu, lo) == (1, 1, 1)


def test_failed_breakout():
    assert failed_breakout_count(_u()) == 1            # GAP gapped up (gap_pct>0) and closed red


def test_gap_and_go():
    assert gap_and_go_count(_u()) == 1                 # RUN is a gainer that gapped up and held


def test_follow_through_rate():
    # of yesterday's gainers {RUN, OLD}, RUN is a gainer again today -> 1/2
    assert follow_through_rate(_u(), frozenset({"RUN", "OLD"})) == 0.5
    assert follow_through_rate(_u(), frozenset()) is None     # no prior gainers -> undefined
