from datetime import date
import pandas as pd
import pytest
from alpha.eval.return_oracle import forward_return, ReturnOracle, TERMINAL_LOSS
from alpha.data.source import FakeSource


def _bars(dates, opens, closes):
    return pd.DataFrame({"date": dates, "open": opens, "high": closes, "low": opens,
                         "close": closes, "volume": [1]*len(dates)})


def test_forward_return_basic():
    bars = _bars([date(2026, 6, 11), date(2026, 6, 12)], [10.0, 11.0], [10.5, 13.0])
    # buy open@6/11 (10.0), sell close@6/12 (13.0) -> 0.30
    assert abs(forward_return(bars, date(2026, 6, 11), date(2026, 6, 12)) - 0.30) < 1e-9


def test_forward_return_missing_returns_none():
    bars = _bars([date(2026, 6, 11)], [10.0], [10.5])
    assert forward_return(bars, date(2026, 6, 11), date(2026, 6, 12)) is None     # no exit row
    assert forward_return(pd.DataFrame(), date(2026, 6, 11), date(2026, 6, 12)) is None


def test_oracle_no_same_day():
    src = FakeSource(calendar=[date(2026, 6, 12)], bars={}, snapshots={})
    with pytest.raises(ValueError):
        ReturnOracle(src).score("RUN", date(2026, 6, 12), date(2026, 6, 12))


def test_oracle_delisting_is_terminal_loss():
    cal = [date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    bars = {"DEAD": _bars([date(2026, 6, 11)], [10.0], [10.5])}     # tradable at entry, gone after
    corp = pd.DataFrame({"symbol": ["DEAD"], "announce_date": [date(2026, 6, 10)],
                         "ex_date": [date(2026, 6, 12)], "kind": ["delist"], "ratio": [0.0]})
    src = FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=corp)
    # entry 6/11 (tradable), exit 6/15 (no bar) + delist ex_date 6/12 in (entry, exit] -> terminal loss
    assert ReturnOracle(src).score("DEAD", date(2026, 6, 11), date(2026, 6, 15)) == TERMINAL_LOSS


def test_oracle_genuine_missing_returns_none():
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    src = FakeSource(calendar=cal, bars={}, snapshots={})           # no bars at all, no delist
    assert ReturnOracle(src).score("GHOST", date(2026, 6, 11), date(2026, 6, 12)) is None
