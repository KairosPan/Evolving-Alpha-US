# tests/test_builder.py
from datetime import date, datetime
import pandas as pd
from youzi.features.builder import build_market_state
from tests.conftest import FakeSource


def _frames():
    d = date(2024, 6, 27)
    return {
        ("zt", d): pd.DataFrame({"code": ["1", "2", "3"],
                                 "name": ["甲", "乙", "丙"], "boards": [7, 3, 1]}),
        ("prev", d): pd.DataFrame({"code": ["x", "y"], "pct": [10.0, -2.0]}),
        ("blowup", d): pd.DataFrame({"code": ["a"]}),
        ("dt", d): pd.DataFrame({"code": ["p", "q"]}),
    }


def test_build_market_state_assembles_fields():
    d = date(2024, 6, 27)
    src = FakeSource(_frames(), [d])
    st = build_market_state(d, src, history=[1.0] * 60,
                            as_of=datetime(2024, 6, 27, 15, 0))
    assert st.max_board_height == 7
    assert st.limit_up_count == 3
    assert st.blowup_count == 1
    assert abs(st.blowup_rate - (1 / 4)) < 1e-9   # 1 炸 /(3 涨停+1 炸)
    assert st.limit_down_count == 2
    assert abs(st.money_effect_raw - 4.0) < 1e-9  # (10-2)/2
    assert st.sentiment_norm is not None          # 60 样本足够
    assert st.echelon[0].height == 7


def test_build_market_state_sentiment_none_when_history_short():
    d = date(2024, 6, 27)
    src = FakeSource(_frames(), [d])
    st = build_market_state(d, src, history=[1.0, 2.0],
                            as_of=datetime(2024, 6, 27, 15, 0))
    assert st.sentiment_norm is None
