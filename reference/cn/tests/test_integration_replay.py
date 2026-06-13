# tests/test_integration_replay.py
from datetime import date
import pandas as pd
import pytest
from youzi.replay.engine import ReplayEngine
from youzi.replay.firewall import LookaheadError
from youzi.schemas.market import MarketState
from tests.conftest import FakeSource


def _make_source(days):
    frames = {}
    for i, d in enumerate(days):
        frames[("zt", d)] = pd.DataFrame({
            "code": [str(i * 10 + j) for j in range(3)],
            "name": [f"龙{i}", f"中{i}", f"低{i}"],
            "boards": [min(i + 1, 9), 3, 1],
        })
        frames[("prev", d)] = pd.DataFrame({"code": ["x", "y"], "pct": [5.0, -1.0]})
        frames[("blowup", d)] = pd.DataFrame({"code": ["b"]})
        frames[("dt", d)] = pd.DataFrame({"code": ["d"]})
    return FakeSource(frames, days)


def test_full_replay_no_lookahead():
    days = [date(2024, 6, d) for d in range(3, 28)]   # 一段交易日
    eng = ReplayEngine(_make_source(days), start=days[0], end=days[-1])

    states: list[MarketState] = []
    while True:
        st = eng.observe()
        # ② as_of 不得超过游标
        assert st.as_of.date() <= eng.cursor
        assert st.date == eng.cursor
        states.append(st)
        if not eng.step():
            break

    # ① 每日合法 MarketState,数量 = 交易日数
    assert len(states) == len(days)
    assert all(isinstance(s, MarketState) for s in states)
    # 历史足够后 sentiment_norm 应从 None 变为有值
    assert states[0].sentiment_norm is None
    # ③ 末日游标处,取下一日(不存在/未来)被拦截
    future = date(2024, 7, 1)
    with pytest.raises(LookaheadError):
        eng.guarded_source.zt_pool(future)
