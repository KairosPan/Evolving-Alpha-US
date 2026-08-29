"""PIT backtest day iterator: for each trading day, a source that cannot see past it.

Makes the lookahead-safe backtest the path of least resistance: strategies loop over
replay_days(...) and use the yielded GuardedSource exactly like the live source.
Honest-eval rules live in docs/backtest-rules.md.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import date as Date

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.source import GuardedSource


def replay_days(source=None, *, pit_root: str | None = None,
                start: Date | None = None, end: Date | None = None,
                ) -> Iterator[tuple[Date, GuardedSource]]:
    if source is None:
        if pit_root is None:
            raise ValueError("pass a source or pit_root")
        from alpaca_kit.pit.pit_store import PITStore
        from alpaca_kit.pit.snapshot_source import SnapshotSource
        source = SnapshotSource(PITStore(pit_root))
    for day in source.trading_calendar():
        if start is not None and day < start:
            continue
        if end is not None and day > end:
            break
        yield day, GuardedSource(source, AsOfGuard(day))
