# tests/test_universe_firewall.py
from datetime import date
import pandas as pd
import pytest
from youzi.replay.firewall import AsOfGuard, LookaheadError
from youzi.data.source import GuardedSource
from youzi.universe.universe import build_universe
from tests.conftest import FakeSource


def _src(days):
    frames = {}
    for d in days:
        frames[("zt", d)] = pd.DataFrame({"code": ["1"], "name": ["龙"],
                                          "boards": [3], "pct": [10.0]})
        frames[("blowup", d)] = pd.DataFrame()
        frames[("dt", d)] = pd.DataFrame()
    return FakeSource(frames, days)


def test_build_universe_today_ok_future_blocked():
    days = [date(2024, 6, 27), date(2024, 6, 28)]
    guard = AsOfGuard(days[0])
    gs = GuardedSource(_src(days), guard)
    u = build_universe(gs, days[0])            # 当日 OK
    assert u.get("1").name == "龙"
    with pytest.raises(LookaheadError):        # 未来日被拦截
        build_universe(gs, days[1])
