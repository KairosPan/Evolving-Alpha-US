from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.state.market import RunnerRung
from alpha.universe.stock import StockSnapshot


def consecutive_up_days(bars: pd.DataFrame, day: Date, max_lookback: int = 30) -> int:
    """Count of consecutive up-closes ending at `day` (close[t] > close[t-1]), strictly trailing.

    Uses only bars with date <= day. A non-up day stops the count. Missing/short data -> 0.
    """
    if bars is None or bars.empty or "date" not in bars.columns:
        return 0
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date          # robust to date or datetime64 dtypes
    df = df[df["date"] <= day].sort_values("date")
    closes = list(pd.to_numeric(df["close"], errors="coerce").dropna())
    if len(closes) < 2:
        return 0
    n = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            n += 1
            if n >= max_lookback:
                break
        else:
            break
    return n


def runner_echelon(snapshots: list[StockSnapshot], top_reps: int = 3) -> list[RunnerRung]:
    """Group snapshots by consecutive_up_days tier (>=1), tier descending; reps = first `top_reps`."""
    by_tier: dict[int, list[str]] = {}
    for s in snapshots:
        t = s.consecutive_up_days
        if t is not None and t >= 1:
            by_tier.setdefault(t, []).append(s.symbol)
    return [RunnerRung(tier=t, count=len(syms), representatives=sorted(syms)[:top_reps])
            for t, syms in sorted(by_tier.items(), reverse=True)]
