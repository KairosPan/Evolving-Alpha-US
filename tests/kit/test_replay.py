from __future__ import annotations

import pytest

from alpaca_kit.firewall import LookaheadError
from alpaca_kit.replay import replay_days


def test_yields_every_calendar_day_guarded(fake_source):
    out = list(replay_days(fake_source))
    assert [d for d, _ in out] == fake_source.trading_calendar()
    first_day, guarded = out[0]
    last_day, last_guarded = out[-1]
    with pytest.raises(LookaheadError):
        guarded.daily_snapshot(last_day)          # day-0 guard blocks a later date
    # ...and the other half of the contract: each day's source CAN read its own day.
    # A guard set one day too TIGHT still blocks the future, so without these the
    # off-by-one-tight mutant survives and every backtest goes silently blind on day t.
    assert not guarded.daily_bars("RUN", first_day, first_day).empty
    assert not last_guarded.daily_snapshot(last_day).empty


def test_range_filter(fake_source):
    cal = fake_source.trading_calendar()
    out = list(replay_days(fake_source, start=cal[1], end=cal[1]))
    assert [d for d, _ in out] == [cal[1]]


def test_requires_source_or_pit_root():
    with pytest.raises(ValueError, match="source or pit_root"):
        list(replay_days())
