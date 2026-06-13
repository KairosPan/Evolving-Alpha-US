# tests/test_features_money_effect.py
import pandas as pd
from youzi.features.money_effect import money_effect


def test_money_effect_is_mean_pct_of_prev_limitups():
    prev = pd.DataFrame({"code": ["1", "2", "3"], "pct": [10.0, -2.0, 1.0]})
    assert abs(money_effect(prev) - 3.0) < 1e-9   # (10-2+1)/3


def test_money_effect_empty_is_zero():
    assert money_effect(pd.DataFrame(columns=["pct"])) == 0.0
