from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.calendar import prev_trading_day

SSR_DROP_PCT = -10.0   # Reg SHO Rule 201: a >=10% prior-day decline restricts short sales the next session


def _prior_day_pct(source, symbol: str, prev: Date) -> float | None:
    """Close-to-close % change for `symbol` ENDING at `prev` (the trading day before the decision day).
    Missing/short data -> None (never fabricate). Reads only bars dated <= prev (firewall-safe)."""
    cal = source.trading_calendar()
    le = [d for d in cal if d <= prev]
    if len(le) < 2:
        return None
    bars = source.daily_bars(symbol, le[-2], prev)
    if bars is None or bars.empty or "date" not in bars.columns:
        return None
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    closes = list(pd.to_numeric(df[df["date"] <= prev].sort_values("date")["close"], errors="coerce").dropna())
    if len(closes) < 2 or closes[-2] == 0:
        return None
    return (closes[-1] - closes[-2]) / closes[-2] * 100.0


def ssr_active(source, symbol: str, as_of: Date) -> bool:
    """Reg SHO Rule 201: True iff `symbol` fell >= 10% (close-to-close) on the PRIOR trading day, so a
    short-sale restriction is in effect on `as_of` (don't chase a one-sided tape). Missing data -> False."""
    prev = prev_trading_day(source.trading_calendar(), as_of)
    if prev is None:
        return False
    pct = _prior_day_pct(source, symbol, prev)
    return pct is not None and pct <= SSR_DROP_PCT
