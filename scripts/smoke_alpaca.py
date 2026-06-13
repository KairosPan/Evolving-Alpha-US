"""Manual Alpaca probe. Run: python scripts/smoke_alpaca.py AAPL 2026-06-01 2026-06-12"""
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


if __name__ == "__main__":
    main()
