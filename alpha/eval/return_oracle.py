from __future__ import annotations

from datetime import date as Date

import pandas as pd

TERMINAL_LOSS = -1.0


def forward_return(bars: pd.DataFrame, entry_day: Date, exit_day: Date) -> float | None:
    """Buy next-open, sell t+N-close: (close@exit_day - open@entry_day) / open@entry_day.

    entry/exit not in bars, open missing/<=0, or close missing -> None (honest, never fabricated).
    Pure: reads the given df only.
    """
    if bars is None or bars.empty or "date" not in bars.columns:
        return None
    e = bars.loc[bars["date"] == entry_day]
    x = bars.loc[bars["date"] == exit_day]
    if e.empty or x.empty:
        return None
    op = e.iloc[0].get("open")
    cl = x.iloc[0].get("close")
    if op is None or cl is None or pd.isna(op) or pd.isna(cl) or op <= 0:
        return None
    return float((cl - op) / op)


class ReturnOracle:
    """Forward-return oracle (uses realized OHLCV at scoring time). Pass a GuardedSource to bound it.

    Delisting/halt-to-zero rule: a symbol tradable at entry but with no exit bar AND a known delist
    ex_date in (entry, exit] is a TERMINAL LOSS (-1.0), never discarded as missing data.
    """

    def __init__(self, source) -> None:
        self._source = source

    def score(self, symbol: str, entry_day: Date, exit_day: Date) -> float | None:
        if entry_day == exit_day:
            raise ValueError(f"no same-day round-trip: entry_day == exit_day == {entry_day} "
                             f"(use horizon>=2)")
        bars = self._source.daily_bars(symbol, entry_day, exit_day)
        ret = forward_return(bars, entry_day, exit_day)
        if ret is not None:
            return ret
        if self._tradable_at(bars, entry_day) and self._delisted_between(symbol, entry_day, exit_day):
            return TERMINAL_LOSS
        return None

    @staticmethod
    def _tradable_at(bars: pd.DataFrame, entry_day: Date) -> bool:
        if bars is None or bars.empty or "date" not in bars.columns:
            return False
        e = bars.loc[bars["date"] == entry_day]
        if e.empty:
            return False
        op = e.iloc[0].get("open")
        return op is not None and not pd.isna(op) and op > 0

    def _delisted_between(self, symbol: str, entry_day: Date, exit_day: Date) -> bool:
        corp = self._source.corporate_actions(entry_day, exit_day)
        if corp is None or corp.empty:
            return False
        rows = corp[(corp["symbol"] == symbol) & (corp["kind"] == "delist")
                    & (corp["ex_date"] > entry_day) & (corp["ex_date"] <= exit_day)]
        return not rows.empty
