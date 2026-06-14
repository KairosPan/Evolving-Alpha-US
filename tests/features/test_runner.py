from datetime import date
import pandas as pd
from alpha.universe.stock import StockSnapshot
from alpha.features.runner import consecutive_up_days, runner_echelon


def _bars(dates, closes):
    return pd.DataFrame({"date": dates, "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1]*len(dates)})


def test_consecutive_up_days():
    # closes 10,11,12,13 over 4 days -> at the last day, 3 consecutive up-closes
    bars = _bars([date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)],
                 [10.0, 11.0, 12.0, 13.0])
    assert consecutive_up_days(bars, date(2026, 6, 12)) == 3
    # a down day resets the count
    bars2 = _bars([date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)], [12.0, 11.0, 13.0])
    assert consecutive_up_days(bars2, date(2026, 6, 12)) == 1


def test_consecutive_up_days_missing():
    assert consecutive_up_days(pd.DataFrame(), date(2026, 6, 12)) == 0
    one = _bars([date(2026, 6, 12)], [10.0])
    assert consecutive_up_days(one, date(2026, 6, 12)) == 0      # single bar -> no prior to compare


def test_runner_echelon_groups_by_tier_descending():
    snaps = [
        StockSnapshot(symbol="A", status="gainer", name="a", consecutive_up_days=3),
        StockSnapshot(symbol="B", status="gainer", name="b", consecutive_up_days=3),
        StockSnapshot(symbol="C", status="gainer", name="c", consecutive_up_days=1),
        StockSnapshot(symbol="D", status="gainer", name="d", consecutive_up_days=0),  # not a runner
    ]
    rungs = runner_echelon(snaps)
    assert [(r.tier, r.count) for r in rungs] == [(3, 2), (1, 1)]
    assert rungs[0].representatives == ["A", "B"]
