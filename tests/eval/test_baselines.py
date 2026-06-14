from datetime import date, datetime
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.state.market import MarketState
from alpha.eval.baselines import NoTradePolicy, ChaseBiggestGainerPolicy, PoolAveragePolicy


def _state():
    return MarketState(date=date(2026, 6, 12), gainer_count=2, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
                       sentiment_norm=None, as_of=datetime(2026, 6, 12, 16, 0))


def _universe():
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol="BIG", name="Big", status="gainer", pct_change=40.0),
        StockSnapshot(symbol="SMALL", name="Small", status="gainer", pct_change=22.0),
        StockSnapshot(symbol="DIP", name="Dip", status="loser", pct_change=-25.0),
    ])


def test_no_trade():
    d = NoTradePolicy().decide(_state(), _universe())
    assert d.candidates == [] and d.no_trade_reason


def test_chase_biggest_gainer():
    d = ChaseBiggestGainerPolicy().decide(_state(), _universe())
    assert [c.symbol for c in d.candidates] == ["BIG"]          # biggest pct_change among gainers
    assert d.candidates[0].pattern == "chase_biggest_gainer"


def test_pool_average_buys_all_gainers_sorted():
    d = PoolAveragePolicy().decide(_state(), _universe())
    assert [c.symbol for c in d.candidates] == ["BIG", "SMALL"]  # all gainers, sorted, deterministic


def test_chase_no_gainers():
    empty = CandidateUniverse.from_stocks([])
    d = ChaseBiggestGainerPolicy().decide(_state(), empty)
    assert d.candidates == [] and d.no_trade_reason


def test_chase_ties_broken_by_symbol():
    u = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="ZED", name="Z", status="gainer", pct_change=30.0),
        StockSnapshot(symbol="ACE", name="A", status="gainer", pct_change=30.0),
    ])
    d = ChaseBiggestGainerPolicy().decide(_state(), u)
    assert [c.symbol for c in d.candidates] == ["ACE", "ZED"]    # both top, sorted by symbol
