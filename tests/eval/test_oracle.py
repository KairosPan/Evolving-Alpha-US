from datetime import date
import pandas as pd
from alpha.eval.oracle import (
    classify_day, outcome, DayMembership, PoolRecord, SCORE, GAINER_PCT, LOSER_PCT,
)


def _snap(symbols, closes, prev_closes):
    return pd.DataFrame({"symbol": symbols, "close": closes, "prev_close": prev_closes})


def test_thresholds_are_module_constants():
    assert GAINER_PCT == 20.0 and LOSER_PCT == -20.0    # fixed, exogenous (not from H)


def test_classify_day():
    snap = _snap(["UP", "FLAT", "DOWN"], [13.0, 10.2, 7.0], [10.0, 10.0, 10.0])
    mem = classify_day(snap)                              # +30% / +2% / -30%
    assert mem.gainers == frozenset({"UP"})
    assert mem.losers == frozenset({"DOWN"})


def test_outcome():
    mem = DayMembership(gainers=frozenset({"UP"}), losers=frozenset({"DOWN"}))
    assert outcome("UP", mem) == "continued"
    assert outcome("DOWN", mem) == "nuked"
    assert outcome("FLAT", mem) == "faded"
    assert SCORE == {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


def test_pool_record():
    rec = PoolRecord()
    snap = _snap(["UP"], [13.0], [10.0])
    rec.record(date(2026, 6, 12), classify_day(snap))
    assert rec.get(date(2026, 6, 12)).gainers == frozenset({"UP"})
    assert rec.get(date(2026, 6, 13)) is None


def test_exogenous_threshold_differs_from_universe_screen():
    # +15% is a universe gainer (build_universe gainer_pct=10%) but NOT an exogenous oracle gainer
    # (GAINER_PCT=20%) -> proves the oracle membership is decoupled from the H-evolvable screen.
    mem = classify_day(_snap(["MID"], [11.5], [10.0]))     # +15%
    assert "MID" not in mem.gainers and "MID" not in mem.losers
