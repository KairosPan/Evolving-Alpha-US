from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Literal

import pandas as pd

Outcome = Literal["continued", "faded", "nuked"]
SCORE: dict[str, float] = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}

# EXOGENOUS fixed thresholds (% daily move). Deliberately NOT from H or the universe screen, so the
# oracle label cannot be gamed by editing the harness (spec §7 de-circularization).
GAINER_PCT = 20.0
LOSER_PCT = -20.0


@dataclass(frozen=True)
class DayMembership:
    """A day's exogenous pool: big-gainer and loser symbol sets (fixed-threshold)."""
    gainers: frozenset[str]
    losers: frozenset[str]


def classify_day(snapshot: pd.DataFrame) -> DayMembership:
    """Classify a day's cross-section into gainer/loser pools by the fixed exogenous thresholds.

    pct = (close - prev_close) / prev_close * 100. Reads only symbol/close/prev_close; rows missing
    close/prev_close (or prev_close<=0) are unclassified (in neither pool).
    """
    if snapshot is None or snapshot.empty:
        return DayMembership(gainers=frozenset(), losers=frozenset())
    gainers: set[str] = set()
    losers: set[str] = set()
    for rec in snapshot.to_dict("records"):
        close, prev = rec.get("close"), rec.get("prev_close")
        if close is None or prev is None or pd.isna(close) or pd.isna(prev) or prev <= 0:
            continue
        pct = (close - prev) / prev * 100.0
        if pct >= GAINER_PCT:
            gainers.add(str(rec["symbol"]))
        elif pct <= LOSER_PCT:
            losers.add(str(rec["symbol"]))
    return DayMembership(gainers=frozenset(gainers), losers=frozenset(losers))


def outcome(symbol: str, mem: DayMembership) -> Outcome:
    """Realized category at a day: nuked (in losers) > continued (in gainers) > faded (neither)."""
    if symbol in mem.losers:
        return "nuked"
    if symbol in mem.gainers:
        return "continued"
    return "faded"


class PoolRecord:
    """Records per-day exogenous membership during a walk (each cursor records <= cursor only).

    record() takes a pre-computed DayMembership (from classify_day on the raw snapshot) — this keeps
    the oracle decoupled from the H-evolvable universe screen (the caller supplies the exogenous set).
    """

    def __init__(self) -> None:
        self._by_day: dict[Date, DayMembership] = {}

    def record(self, day: Date, mem: DayMembership) -> None:
        self._by_day[day] = mem

    def get(self, day: Date) -> DayMembership | None:
        return self._by_day.get(day)
