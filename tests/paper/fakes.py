"""Builders for paper-book tests: a FakeSource from (open, close) sequences, constant rules,
and ledger readers."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from alpaca_kit.paper.book import LEDGER_FILE
from alpaca_kit.source import FakeSource

# eight trading days: Mon 2026-06-01 .. Wed 2026-06-10
CAL = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3), date(2026, 6, 4), date(2026, 6, 5),
       date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)]
D0, D1, D2, D3, D4, D5, D6, D7 = CAL

BARS_COLS = ["date", "open", "high", "low", "close", "volume"]
CORP_COLS = ["symbol", "announce_date", "ex_date", "kind", "ratio"]

Seq = list[tuple[float, float] | None]


def flat(price: float, n: int = len(CAL)) -> Seq:
    return [(price, price)] * n


def bars_from(prices: dict[str, Seq], cal: list[date] = CAL) -> dict[str, pd.DataFrame]:
    """prices[sym] = one (open, close) per calendar day, or None for 'no bar that day'."""
    out: dict[str, pd.DataFrame] = {}
    for sym, seq in prices.items():
        rows = []
        for d, oc in zip(cal, seq):
            if oc is None:
                continue
            o, c = oc
            rows.append({"date": d, "open": o, "high": max(o, c), "low": min(o, c), "close": c,
                         "volume": 1_000_000})
        out[sym] = pd.DataFrame(rows, columns=BARS_COLS)
    return out


def source_from(prices: dict[str, Seq], *, corp: list[dict] | None = None, corp_available: bool = True,
                cal: list[date] = CAL, snapshots: dict | None = None) -> FakeSource:
    frame = pd.DataFrame(corp, columns=CORP_COLS) if corp is not None else None
    return FakeSource(calendar=cal, bars=bars_from(prices, cal), snapshots=snapshots or {},
                      corp_actions=frame, corp_actions_available=corp_available)


def constant(targets: dict[str, float]):
    """A rule that answers the same intent every day."""
    def signal(source, day):
        return {"targets": [{"symbol": s, "weight": w} for s, w in targets.items()]}
    return signal


def by_day(plan: dict[date, dict[str, float]], default: dict[str, float] | None = None):
    """A rule that answers a different intent per day (the last given one after the plan ends)."""
    def signal(source, day):
        targets = plan.get(day, default if default is not None else {})
        return {"targets": [{"symbol": s, "weight": w} for s, w in targets.items()]}
    return signal


def ledger(directory: Path, kind: str | None = None) -> list[dict]:
    rows = [json.loads(line) for line in (directory / LEDGER_FILE).read_text("utf-8").splitlines() if line]
    return [r for r in rows if kind is None or r["kind"] == kind]
