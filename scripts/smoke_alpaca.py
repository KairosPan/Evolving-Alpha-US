"""Manual Alpaca probe (needs APCA_API_KEY_ID/SECRET + the `live` extra for bars).
Run: python scripts/smoke_alpaca.py AAPL 2026-06-01 2026-06-12"""
from __future__ import annotations

import sys
from datetime import date

from alpha.data.alpaca import AlpacaSource


def main() -> None:
    sym, start, end = sys.argv[1], date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])
    src = AlpacaSource()

    bars = src.daily_bars(sym, start, end)
    print(f"{sym} bars rows={len(bars)} cols={list(bars.columns)}")
    print(bars.tail())

    # corp actions: announce-keyed (process_date<=end, incl. pending future-ex) vs ex-windowed [start,end].
    known = src.corporate_actions_known(end)
    kinds = sorted(known["kind"].unique().tolist()) if not known.empty else []
    print(f"\ncorp actions known by {end}: rows={len(known)} kinds={kinds}")
    print(known[known["symbol"] == sym].head() if not known.empty else "(none)")

    ex_win = src.corporate_actions(start, end)
    print(f"\ncorp actions ex_date in [{start},{end}]: rows={len(ex_win)}")
    print(ex_win.head() if not ex_win.empty else "(none)")


if __name__ == "__main__":
    main()
