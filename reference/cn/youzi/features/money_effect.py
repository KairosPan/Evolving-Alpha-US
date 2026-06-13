from __future__ import annotations

import pandas as pd


def money_effect(prev_zt: pd.DataFrame) -> float:
    """赚钱效应 = 昨日涨停板今日平均涨跌幅(%)。无数据返回 0.0。"""
    if prev_zt is None or prev_zt.empty or "pct" not in prev_zt.columns:
        return 0.0
    s = pd.to_numeric(prev_zt["pct"], errors="coerce").dropna()
    return float(s.mean()) if not s.empty else 0.0
