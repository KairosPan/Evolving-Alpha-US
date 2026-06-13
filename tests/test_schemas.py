# tests/test_schemas.py
from datetime import date, datetime
import pytest
from pydantic import ValidationError
from youzi.schemas.market import MarketState, EchelonRung


def test_market_state_construction_and_bounds():
    s = MarketState(
        date=date(2024, 6, 27),
        max_board_height=7,
        limit_up_count=40,
        blowup_count=20,
        blowup_rate=0.333,
        limit_down_count=5,
        echelon=[EchelonRung(height=7, count=1, representatives=["中马传动"])],
        money_effect_raw=-1.2,
        sentiment_raw=12.5,
        sentiment_norm=None,
        as_of=datetime(2024, 6, 27, 15, 0),
    )
    assert s.max_board_height == 7
    assert s.echelon[0].representatives == ["中马传动"]
    # 冻结模型仍可序列化往返,且按值相等
    assert MarketState.model_validate(s.model_dump()) == s
    # blowup_rate 越界应报错
    with pytest.raises(ValidationError):
        MarketState(
            date=date(2024, 6, 27), max_board_height=1, limit_up_count=1,
            blowup_count=0, blowup_rate=1.5, limit_down_count=0, echelon=[],
            money_effect_raw=0.0, sentiment_raw=0.0, sentiment_norm=None,
            as_of=datetime(2024, 6, 27, 15, 0),
        )
