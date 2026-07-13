"""RS + Minervini Trend Template feature unit tests (P0.4). Fully offline, synthetic bar frames."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from alpha.features.trend_template import (
    TREND_TEMPLATE_CRITERIA, evaluate_trend_template, rs_percentiles, rs_raw_score,
    trend_template_screen,
)

DAY = date(2026, 6, 12)


def _bars(closes: list[float], end: date = DAY) -> pd.DataFrame:
    """A bar frame whose LAST row is dated `end`, one trading day per element (weekends ignored — the
    trend template only reads closes and ordering, not the calendar)."""
    n = len(closes)
    dates = [end - timedelta(days=(n - 1 - i)) for i in range(n)]
    return pd.DataFrame({"date": dates, "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1] * n})


def _rising(n: int, start: float = 10.0, step: float = 0.5) -> list[float]:
    """A clean monotonic uptrend of `n` closes — passes every price-based criterion."""
    return [start + step * i for i in range(n)]


def test_rs_raw_score_blends_6_and_12_month_returns():
    closes = _rising(300)
    # close=closes[-1]; 6mo-ago=closes[-127]; 12mo-ago=closes[-253]
    expected = 0.5 * (closes[-1] / closes[-127] - 1) + 0.5 * (closes[-1] / closes[-253] - 1)
    assert abs(rs_raw_score(_bars(closes), DAY) - expected) < 1e-12


def test_rs_raw_score_insufficient_history_is_none():
    assert rs_raw_score(_bars(_rising(252)), DAY) is None      # need long_window+1 == 253 closes


def test_rs_percentiles_rank_cross_sectionally():
    pct = rs_percentiles({"A": 0.1, "B": 0.5, "C": 0.9, "D": None})
    assert pct["C"] == 100.0 and pct["A"] < pct["B"] < pct["C"]
    assert "D" not in pct                                       # None raw score dropped from the pool


def test_trend_template_full_pass():
    res = evaluate_trend_template(_bars(_rising(300)), DAY, rs_percentile=85.0)
    assert res.passes is True
    assert all(res.criteria[c] for c in TREND_TEMPLATE_CRITERIA)
    assert res.insufficient_history is False


def test_trend_template_rs_below_threshold_fails():
    res = evaluate_trend_template(_bars(_rising(300)), DAY, rs_percentile=65.0)
    assert res.criteria["rs_ge_70"] is False and res.passes is False


def test_trend_template_below_sma_fails():
    # A long uptrend then a sharp drop on the last bar -> close below its own SMAs.
    closes = _rising(299) + [1.0]
    res = evaluate_trend_template(_bars(closes), DAY, rs_percentile=99.0)
    assert res.criteria["above_sma50"] is False and res.passes is False


def test_trend_template_downtrend_fails_sma_stack_and_rising():
    closes = _rising(300)[::-1]        # monotonic DOWNtrend
    res = evaluate_trend_template(_bars(closes), DAY, rs_percentile=99.0)
    assert res.criteria["sma_stack"] is False
    assert res.criteria["sma200_rising"] is False
    assert res.passes is False


def test_trend_template_insufficient_history_fails_explicitly():
    # 150 closes: cannot form the 200-day SMA -> criteria 3/4/5 False, flagged, and NEVER passes.
    res = evaluate_trend_template(_bars(_rising(150)), DAY, rs_percentile=99.0)
    assert res.insufficient_history is True
    assert res.criteria["above_sma200"] is False
    assert res.passes is False


def test_trend_template_no_bars_fails():
    res = evaluate_trend_template(None, DAY, rs_percentile=99.0)
    assert res.passes is False and res.insufficient_history is True


def test_trend_template_near_52w_high_and_low_bounds():
    # Rising then a mild pullback that stays within 25% of the high and >30% above the low.
    closes = _rising(300)
    res = evaluate_trend_template(_bars(closes), DAY, rs_percentile=80.0)
    assert res.criteria["above_52w_low"] is True and res.criteria["near_52w_high"] is True


def test_trend_template_far_below_high_fails_near_high():
    # 252 flat-high bars then a 40% drop over the final stretch: below 75% of the 52-week high.
    closes = _rising(260) + [130.0 - i for i in range(40)]     # ends well under the high
    res = evaluate_trend_template(_bars(closes), DAY, rs_percentile=80.0)
    assert res.criteria["near_52w_high"] is False and res.passes is False


def test_evaluate_trend_template_stale_current_day_fails_closed():
    # a clean 300-bar uptrend whose latest bar predates `day` (capture lag) has no usable current-day
    # price -> fail-closed: every criterion False, never evaluated on the stale close.
    stale = _bars(_rising(300), end=DAY - timedelta(days=1))
    res = evaluate_trend_template(stale, DAY, rs_percentile=99.0)
    assert res.passes is False
    assert all(res.criteria[c] is False for c in TREND_TEMPLATE_CRITERIA)


def test_rs_raw_score_stale_current_day_is_none():
    # stale latest bar -> excluded from the RS ranking pool (None), so its close cannot contaminate
    # the cross-sectional percentile of the current-day names.
    stale = _bars(_rising(300), end=DAY - timedelta(days=1))
    assert rs_raw_score(stale, DAY) is None


def test_trend_template_screen_drops_stale_from_rs_pool():
    # STALE is a strong uptrend but one day behind; it must fail the screen AND leave the RS pool, so
    # STRONG ranks against a clean pool (percentile == 100 of the single current-day survivor).
    strong = _bars(_rising(300))
    stale = _bars(_rising(300), end=DAY - timedelta(days=1))
    res = trend_template_screen({"STRONG": strong, "STALE": stale}, DAY)
    assert res["STALE"].passes is False and res["STALE"].rs_percentile is None
    assert res["STRONG"].passes is True and res["STRONG"].rs_percentile == 100.0


def test_trend_template_screen_batch_ranks_rs_then_filters():
    strong = _bars(_rising(300, start=10.0, step=1.0))         # steepest 12mo return -> top RS
    weak = _bars(_rising(300, start=100.0, step=0.1))          # shallow return -> low RS
    short = _bars(_rising(150))                                 # insufficient history
    res = trend_template_screen({"STRONG": strong, "WEAK": weak, "SHORT": short}, DAY)
    assert res["STRONG"].rs_percentile == 100.0 and res["STRONG"].criteria["rs_ge_70"] is True
    assert res["WEAK"].rs_percentile is not None and res["WEAK"].rs_percentile < 100.0
    assert res["SHORT"].rs_percentile is None and res["SHORT"].passes is False
    assert res["STRONG"].symbol == "STRONG"
