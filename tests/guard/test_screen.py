from datetime import date, datetime
import pandas as pd
import pytest
from alpha.data.source import FakeSource
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.guard.screen import ssr_active


def _src(sym_closes):
    """sym_closes: {symbol: [close_6/10, close_6/11, close_6/12]}."""
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {s: pd.DataFrame({"date": cal, "open": c, "high": c, "low": c, "close": c,
                             "volume": [1, 1, 1]}) for s, c in sym_closes.items()}
    return FakeSource(calendar=cal, bars=bars, snapshots={})


def test_ssr_active_when_prior_day_dropped_10pct():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})            # 6/11 close 8.8 = -12% vs 6/10 -> SSR on 6/12
    assert ssr_active(src, "KNIFE", date(2026, 6, 12)) is True


def test_ssr_inactive_when_prior_day_drop_below_threshold():
    src = _src({"MILD": [10.0, 9.2, 9.5]})             # -8% prior day -> no SSR
    assert ssr_active(src, "MILD", date(2026, 6, 12)) is False


def test_ssr_inactive_when_bars_missing():
    src = _src({"OTHER": [10.0, 9.0, 8.0]})
    assert ssr_active(src, "ABSENT", date(2026, 6, 12)) is False    # no bars -> never fabricate


def test_ssr_inactive_on_first_day():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})
    assert ssr_active(src, "KNIFE", date(2026, 6, 10)) is False     # no prior trading day


def test_ssr_is_guard_safe():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})
    gs = GuardedSource(src, AsOfGuard(date(2026, 6, 12)))           # reads only prior-day bars (< as_of)
    assert ssr_active(gs, "KNIFE", date(2026, 6, 12)) is True
