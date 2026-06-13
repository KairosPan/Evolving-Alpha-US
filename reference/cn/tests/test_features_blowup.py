# tests/test_features_blowup.py
import pandas as pd
from youzi.features.blowup import blowup_rate


def test_blowup_rate_basic():
    zt = pd.DataFrame({"code": [str(i) for i in range(40)]})       # 40 涨停
    blow = pd.DataFrame({"code": [str(i) for i in range(20)]})     # 20 炸板
    # 炸板率 = 20 / (40 + 20) = 0.3333
    assert abs(blowup_rate(zt, blow) - (20 / 60)) < 1e-9


def test_blowup_rate_zero_when_no_data():
    empty = pd.DataFrame(columns=["code"])
    assert blowup_rate(empty, empty) == 0.0
