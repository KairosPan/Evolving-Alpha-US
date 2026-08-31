"""face_data - the face's instrument-data producer.

Two modes, JSON to stdout: `market` (the PIT bed through production code
paths) and `account` (TradingClient read-only). Spawned by face/src/data.ts;
also runnable by hand. Read-only by construction: this module must never
import or call an order-placing code path (tests grep for it).
"""
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpaca_kit.features.breadth import market_breadth
from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.source import GuardedSource
from alpaca_kit.universe import build_universe

# Facts about the SHIPPED 2yr bed (window + maturity boundaries). Constants,
# not measurements: they describe the capture, and the page renders them as
# the maturity rail. A different bed needs different values.
BED_INFO = {
    "root": "data/pit/2yr",
    "window": {"start": "2024-06-03", "end": "2026-07-09"},
    "warmup": {
        "sma200_valid_from": "2025-03-20",
        "week52_valid_from": "2025-06-04",
        "trend_template_valid_from": "2025-06-05",
        "note": "bars start AT the window start; long-indicator readings "
                "before these dates are immature, not missing",
    },
}

SPARK_BARS = 60          # trailing closes per screen-row sparkline
_ALL_HISTORY = Date(1990, 1, 1)   # bar-fetch start: take whatever history the source holds, so the
                                  # 200DMA/52wk windows see it even when `days` covers less


def market_payload(source, days, end, *, breadth_days=60, tape_days=250,
                   screen_limit=40):
    """Assemble the /market payload. `source` implements daily_snapshot +
    daily_bars; `days` = ascending captured trading days <= end. Pure w.r.t.
    its inputs; the CLI supplies the real bed."""
    guard = GuardedSource(source, AsOfGuard(end))
    snap = guard.daily_snapshot(end)
    symbols = [] if snap is None or snap.empty else snap["symbol"].tolist()

    # One full-history fetch per symbol, guard-checked (end == as_of), reused by every window below.
    bars = {}
    for sym in symbols:
        df = guard.daily_bars(sym, _ALL_HISTORY, end)
        if df is not None and not df.empty:
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            bars[sym] = df.sort_values("date").reset_index(drop=True)

    breadth_series = []
    for day in days[-breadth_days:]:
        # market_breadth is trailing-only by contract; the pre-slice is defense in depth so a past
        # day's reading can never see a later bar even if that contract ever loosened.
        sliced = {s: df[df["date"] <= day] for s, df in bars.items()}
        r = market_breadth(sliced, day)
        breadth_series.append({"date": day.isoformat(),
                               "pct_above_200dma": r.pct_above_200dma,
                               "net_new_highs": r.net_new_highs,
                               "advances": r.advances, "declines": r.declines})

    tape_days_list = days[-tape_days:]
    start_day = tape_days_list[0]
    base = {}
    for s, df in bars.items():
        d0 = df[df["date"] >= start_day]
        if not d0.empty and float(d0.iloc[0]["close"]) > 0:
            base[s] = float(d0.iloc[0]["close"])
    tape = []
    for day in tape_days_list:
        vals = []
        for s, df in bars.items():
            if s not in base:
                continue
            rows = df[df["date"] == day]
            if not rows.empty:
                vals.append(float(rows.iloc[0]["close"]) / base[s])
        tape.append({"date": day.isoformat(),
                     "level": round(100 * sum(vals) / len(vals), 2) if vals else None,
                     "n": len(vals)})

    def screen_rows(kind):
        uni = build_universe(guard, end, screen=kind)
        out = []
        for s in uni.all()[:screen_limit]:
            d = s.model_dump(mode="json")
            df = bars.get(s.symbol)
            if df is not None:
                closes = df[df["date"] <= end].tail(SPARK_BARS)["close"].tolist()
                # No fabricated baseline: a missing or zero first close means no spark, not a 1.0 divisor.
                d["spark"] = ([round(c / closes[0], 4) for c in closes]
                              if closes and closes[0] > 0 else [])
            out.append(d)
        return out

    return {
        "ok": True,
        "bed": BED_INFO,
        "as_of": end.isoformat(),
        "breadth": {"series": breadth_series,
                    "raw": "alpaca_kit.features.breadth.market_breadth"},
        "tape": {"series": tape,
                 "note": "equal-weight composite, 100 = window start",
                 "raw": "derived from the bed's bars"},
        "screens": {
            kind: {"rows": screen_rows(kind),
                   "raw": f"alpaca_kit.universe.build_universe(screen='{kind}')"}
            for kind in ("trend_template", "gainer")
        },
    }
