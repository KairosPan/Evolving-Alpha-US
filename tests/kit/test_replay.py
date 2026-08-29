from __future__ import annotations

from datetime import date

import pytest

from alpaca_kit.firewall import LookaheadError
from alpaca_kit.replay import replay_days


def test_yields_every_calendar_day_guarded(fake_source):
    out = list(replay_days(fake_source))
    assert [d for d, _ in out] == fake_source.trading_calendar()
    first_day, guarded = out[0]
    last_day = out[-1][0]
    with pytest.raises(LookaheadError):
        guarded.daily_snapshot(last_day)          # day-0 guard blocks a later date


def test_range_filter(fake_source):
    cal = fake_source.trading_calendar()
    out = list(replay_days(fake_source, start=cal[1], end=cal[1]))
    assert [d for d, _ in out] == [cal[1]]


def test_requires_source_or_pit_root():
    with pytest.raises(ValueError, match="source or pit_root"):
        list(replay_days())
