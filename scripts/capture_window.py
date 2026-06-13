"""Build an offline PIT snapshot DB. Run:
   python scripts/capture_window.py 2026-06-01 2026-06-12 snap AAPL MSFT NVDA"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from alpha.data.alpaca import AlpacaSource
from alpha.data.capture import capture_window
from alpha.data.pit_store import PITStore


def main() -> None:
    start, end, root = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]), Path(sys.argv[3])
    symbols = sys.argv[4:]
    capture_window(AlpacaSource(), PITStore(root), start, end, symbols)
    print(f"captured {len(symbols)} symbols {start}..{end} -> {root}")


if __name__ == "__main__":
    main()
