from __future__ import annotations

import pandas as pd


def _n(df: pd.DataFrame) -> int:
    return 0 if df is None or df.empty else len(df)


def blowup_rate(zt: pd.DataFrame, blowup: pd.DataFrame) -> float:
    """炸板率 = 炸板家数 / (涨停家数 + 炸板家数)。无数据返回 0.0。"""
    up, blow = _n(zt), _n(blowup)
    denom = up + blow
    return (blow / denom) if denom > 0 else 0.0
