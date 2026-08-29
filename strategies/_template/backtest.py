"""Backtest skeleton for <strategy>. Follows docs/backtest-rules.md - all five rules."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpaca_kit.replay import replay_days

# Paths are anchored on this file, never on the CWD: a copied strategy sits at
# strategies/<name>/backtest.py, so parents[2] is the repo root. Run it from anywhere.
_REPO = Path(__file__).resolve().parents[2]
PIT_ROOT = str(_REPO / "data" / "pit" / "2yr")
# Rule 1: a bed's trading_calendar() starts in 2016, but snapshots only cover the window
# below (526 days). Outside it a snapshot read raises SnapshotMissingError while bar and
# corp-action reads return EMPTY frames silently, so an unbounded replay either dies on day
# one or quietly undercounts ~2,100 days. The window is a default, not an option.
# data/pit/broad's window is 2025-11-17 .. 2026-03-27 (90 days).
BED_START = date(2024, 6, 3)
BED_END = date(2026, 7, 9)


def run(start: date = BED_START, end: date = BED_END) -> dict:
    picks: list = []
    for day, source in replay_days(pit_root=PIT_ROOT, start=start, end=end):
        # rule 1: use `source` (guarded) for every read on this day
        ...
    return {"window": [str(start), str(end)], "n": len(picks)}


if __name__ == "__main__":
    result = run()
    out = Path(__file__).parent / "backtests" / f"{date.today()}-run.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(out)
