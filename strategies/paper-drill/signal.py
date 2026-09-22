"""paper-drill's intent rule - the paper book's fixture, not a strategy.

Each day: the N most-traded names on the day's snapshot (close x volume), equal-weighted, with
2% held back as cash. It reads only the guarded source the book hands it, so it replays on any
captured bed (the drill uses `data/pit/massive-2016-2017`, two names, 521 days); it needs daily
snapshots, so it does not run on live keys. Ties break on the symbol, so a run is reproducible.
"""
from __future__ import annotations

from datetime import date

N = 5
CASH_BUFFER = 0.02


def signal(source, day: date) -> dict:
    snap = source.daily_snapshot(day)
    if snap is None or snap.empty:
        return {"targets": [], "note": "no snapshot for the day"}
    df = snap.dropna(subset=["close", "volume"]).copy()
    df["dollar_volume"] = df["close"] * df["volume"]
    top = df.sort_values(["dollar_volume", "symbol"], ascending=[False, True]).head(N)
    weight = (1.0 - CASH_BUFFER) / len(top) if len(top) else 0.0
    return {
        "targets": [{"symbol": str(s), "weight": weight} for s in top["symbol"]],
        "note": f"top {len(top)} by dollar volume, equal weight, {CASH_BUFFER:.0%} cash",
    }


if __name__ == "__main__":
    import json
    import sys

    from alpaca_kit.firewall import AsOfGuard
    from alpaca_kit.registry import make_source
    from alpaca_kit.source import GuardedSource

    as_of = date.fromisoformat(sys.argv[1])
    print(json.dumps(signal(GuardedSource(make_source(), AsOfGuard(as_of)), as_of), indent=2))
