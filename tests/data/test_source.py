from __future__ import annotations
from datetime import date
import pytest
from alpha.data.firewall import AsOfGuard, LookaheadError
from alpha.data.source import GuardedSource


def test_fake_source_daily_snapshot(fake_source):
    snap = fake_source.daily_snapshot(date(2026, 6, 12))
    assert set(snap["symbol"]) == {"RUN", "FLOP"}


def test_fake_source_daily_bars_window(fake_source):
    bars = fake_source.daily_bars("RUN", date(2026, 6, 11), date(2026, 6, 12))
    assert list(bars["date"]) == [date(2026, 6, 11), date(2026, 6, 12)]


def test_guarded_source_blocks_future_snapshot(fake_source):
    guard = AsOfGuard(date(2026, 6, 11))
    gs = GuardedSource(fake_source, guard)
    gs.daily_snapshot(date(2026, 6, 11))                 # equal: ok
    with pytest.raises(LookaheadError):
        gs.daily_snapshot(date(2026, 6, 12))             # future: blocked


def test_guarded_source_blocks_future_bars_end(fake_source):
    guard = AsOfGuard(date(2026, 6, 11))
    gs = GuardedSource(fake_source, guard)
    with pytest.raises(LookaheadError):
        gs.daily_bars("RUN", date(2026, 6, 10), date(2026, 6, 12))


def test_guarded_source_blocks_future_corp_actions(fake_source):
    guard = AsOfGuard(date(2026, 6, 11))
    gs = GuardedSource(fake_source, guard)
    with pytest.raises(LookaheadError):
        gs.corporate_actions(date(2026, 6, 1), date(2026, 6, 12))
