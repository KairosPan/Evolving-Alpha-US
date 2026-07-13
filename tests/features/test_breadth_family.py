"""Growth-doctrine breadth family (P0.4): % above 200DMA, net new 52-week highs, advance/decline."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from alpha.features.breadth import (
    BreadthReading, advance_decline, market_breadth, net_new_highs, pct_above_ma,
)

DAY = date(2026, 6, 12)


def _bars(closes: list[float], end: date = DAY) -> pd.DataFrame:
    n = len(closes)
    dates = [end - timedelta(days=(n - 1 - i)) for i in range(n)]
    return pd.DataFrame({"date": dates, "close": closes, "open": closes, "high": closes,
                         "low": closes, "volume": [1] * n})


def _rising(n: int) -> list[float]:
    return [10.0 + 0.5 * i for i in range(n)]


def _falling(n: int) -> list[float]:
    return [10.0 + 0.5 * (n - i) for i in range(n)]


def test_pct_above_ma_counts_only_eligible():
    bars = {"UP": _bars(_rising(220)),          # above its own SMA200
            "DOWN": _bars(_falling(220)),        # below its own SMA200
            "SHORT": _bars(_rising(50))}         # < 200 closes -> excluded from denominator
    assert pct_above_ma(bars, DAY, window=200) == 0.5


def test_pct_above_ma_none_when_no_eligible_symbol():
    assert pct_above_ma({"SHORT": _bars(_rising(50))}, DAY, window=200) is None


def test_net_new_highs_high_minus_low():
    bars = {"HI": _bars(_rising(260)),           # latest close is the 52-week max
            "LO": _bars(_falling(260)),          # latest close is the 52-week min
            "HI2": _bars(_rising(260)),
            "SHORT": _bars(_rising(100))}        # excluded
    assert net_new_highs(bars, DAY, window=252) == 1        # 2 highs - 1 low


def test_net_new_highs_none_when_no_eligible_symbol():
    assert net_new_highs({"SHORT": _bars(_rising(10))}, DAY, window=252) is None


def test_advance_decline_uses_last_two_closes():
    bars = {"A": _bars([10.0, 11.0]),            # up
            "B": _bars([11.0, 10.0]),            # down
            "C": _bars([10.0, 10.0]),            # unchanged (neither)
            "D": _bars([12.0])}                  # single bar -> skipped
    assert advance_decline(bars, DAY) == (1, 1)


def test_advance_decline_is_trailing_only():
    # A future-dated row must not be read (belt-and-suspenders on top of the caller's guard).
    df = _bars([10.0, 11.0], end=DAY)
    future = pd.DataFrame({"date": [DAY + timedelta(days=1)], "close": [1.0], "open": [1.0],
                           "high": [1.0], "low": [1.0], "volume": [1]})
    df = pd.concat([df, future], ignore_index=True)
    assert advance_decline({"A": df}, DAY) == (1, 0)          # sees 10->11 (up), ignores the drop to 1.0


def test_advance_decline_skips_stale_symbol():
    # LAG's latest bar is dated one day BEFORE `day` (capture lag): it must contribute to NEITHER
    # advances nor declines — a yesterday-vs-day-before move is not today's advance/decline.
    bars = {"UP": _bars([10.0, 11.0]),                                    # current-day up
            "LAG": _bars([10.0, 11.0], end=DAY - timedelta(days=1))}      # up, but stale -> not counted
    assert advance_decline(bars, DAY) == (1, 0)


def test_market_breadth_all_stale_reports_none_advances():
    # a cross-section of ONLY stale symbols -> advances/declines are None, never a fabricated 0.
    bars = {"LAG": _bars([10.0, 11.0], end=DAY - timedelta(days=1))}
    b = market_breadth(bars, DAY)
    assert b.advances is None and b.declines is None


def test_market_breadth_bundles_all_three():
    bars = {"UP": _bars(_rising(260)), "DOWN": _bars(_falling(260))}
    b = market_breadth(bars, DAY)
    assert isinstance(b, BreadthReading)
    assert b.pct_above_200dma == 0.5
    assert b.net_new_highs == 0                               # one high, one low
    assert b.advances == 1 and b.declines == 1


def test_market_breadth_empty_cross_section_is_all_none():
    b = market_breadth({}, DAY)
    assert b.pct_above_200dma is None and b.net_new_highs is None
    assert b.advances is None and b.declines is None
