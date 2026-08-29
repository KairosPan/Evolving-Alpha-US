"""Backtest skeleton for <strategy>. Follows docs/backtest-rules.md - all five rules."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpaca_kit.replay import replay_days

PIT_ROOT = "data/pit/2yr"
# Rule 1: a bed's trading_calendar() starts in 2016, but snapshots only cover the window
# below (526 days). An unbounded replay walks the empty years first and dies with
# SnapshotMissingError, so the window is a default, not an option. data/pit/broad's
# window is 2025-11-17 .. 2026-03-27 (90 days).
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
    out = Path("backtests") / f"{date.today()}-run.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(out)
