"""Screen for <strategy>: emits candidate symbols for a given day.

Usage (offline bed) — ALPHA_PIT_ROOT is resolved against the CWD, so run this from the
repo root (or give it an absolute path):
    ALPHA_DATA_SOURCE=snapshot ALPHA_PIT_ROOT=data/pit/2yr \
        python strategies/<name>/screen.py 2026-03-02

The registry picks the source (ALPHA_DATA_SOURCE, default alpaca); the guard is ours to
apply, per the RAW-source contract. Note the cross-section screen needs daily snapshots,
which only a captured bed serves — live APCA keys give bars, not snapshots.
"""
from __future__ import annotations

import sys
from datetime import date

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.registry import make_source
from alpaca_kit.source import GuardedSource
from alpaca_kit.universe import build_universe


def screen(day: date) -> list[str]:
    src = GuardedSource(make_source(), AsOfGuard(day))
    return [s.symbol for s in build_universe(src, day).all()]


if __name__ == "__main__":
    print(screen(date.fromisoformat(sys.argv[1])))
