# tests/universe/test_build_universe.py
from __future__ import annotations
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.universe.universe import build_universe


def test_build_universe_screens_gainers(fake_source):
    # day 6/12: RUN +21.4% (14->17), FLOP -8.3% (18->16.5). Gainer threshold 10%.
    u = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN") is not None
    assert u.get("RUN").status in ("gainer", "gap_up")
    assert u.get("FLOP") is None or u.get("FLOP").status == "loser"


def test_rvol_uses_only_trailing_bars(fake_source):
    # RUN volume 6/12 = 5M; trailing (6/10,6/11) avg = (1M+3M)/2 = 2M -> RVOL = 2.5
    u = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert abs(u.get("RUN").rvol - 2.5) < 1e-9


def test_build_universe_is_guard_safe(fake_source):
    # A guard at 6/12 must not block building the 6/12 universe (uses <=6/12 only).
    from alpha.data.firewall import AsOfGuard
    from alpha.data.source import GuardedSource
    gs = GuardedSource(fake_source, AsOfGuard(date(2026, 6, 12)))
    u = build_universe(gs, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN") is not None


def test_build_universe_populates_consecutive_up_days(fake_source):
    # RUN closes 11 -> 14 -> 17 over 6/10..6/12 -> 2 consecutive up-days ending 6/12.
    u = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN").consecutive_up_days == 2


def test_build_universe_runner_tier_is_guard_safe(fake_source):
    # cud bars are fetched with end == day <= as_of, so the firewall does not trip.
    from alpha.data.firewall import AsOfGuard
    from alpha.data.source import GuardedSource
    gs = GuardedSource(fake_source, AsOfGuard(date(2026, 6, 12)))
    u = build_universe(gs, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN").consecutive_up_days == 2


def test_build_universe_loser_consecutive_up_days_zero():
    # A loser is down on the day -> its trailing up-count ending today is 0 by construction (no probe).
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["DROP"], "name": ["d"], "open": [10.0], "high": [10.0],
        "low": [8.0], "close": [8.0], "volume": [1], "prev_close": [10.0]})}   # -20% loser
    src = FakeSource(calendar=cal, bars={}, snapshots=snaps)
    u = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("DROP").status == "loser" and u.get("DROP").consecutive_up_days == 0


def test_build_universe_missing_day_bar_runner_tier_unknown():
    # A gainer present in the day snapshot but whose bars lack the day row (capture lag) -> tier UNKNOWN
    # (None), not a stale-positive count ending one day early.
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["LAG"], "name": ["l"], "open": [13.0], "high": [18.0],
        "low": [13.0], "close": [17.0], "volume": [1], "prev_close": [14.0]})}   # +21% gainer on 6/12
    bars = {"LAG": pd.DataFrame({"date": [date(2026, 6, 10), date(2026, 6, 11)],   # NO 6/12 row
                                 "open": [10.0, 12.5], "high": [12, 15], "low": [9.5, 12],
                                 "close": [11.0, 14.0], "volume": [1, 1]})}
    src = FakeSource(calendar=cal, bars=bars, snapshots=snaps)
    u = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("LAG").status == "gainer" and u.get("LAG").consecutive_up_days is None


def test_build_universe_populates_short_interest():
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["SQZ"], "name": ["Squeezer"], "open": [10.0], "high": [13.0], "low": [10.0],
        "close": [12.0], "volume": [5], "prev_close": [10.0],
        "short_interest": [30.0], "days_to_cover": [6.0]})}                 # +20% gainer w/ high SI
    src = FakeSource(calendar=cal, bars={}, snapshots=snaps)
    s = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("SQZ")
    assert s.short_interest == 30.0 and s.days_to_cover == 6.0


def test_build_universe_short_interest_absent_is_none(fake_source):
    # conftest fake_source snapshots have no short_interest columns -> fields stay None (never fabricated)
    s = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("RUN")
    assert s.short_interest is None and s.days_to_cover is None


def test_build_universe_short_interest_nan_is_none():
    # FINRA coverage is partial: a present column can carry NaN for uncovered symbols -> None, not si=nan%
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["SQZ"], "name": ["Sq"], "open": [10.0], "high": [13.0], "low": [10.0],
        "close": [12.0], "volume": [5], "prev_close": [10.0],
        "short_interest": [float("nan")], "days_to_cover": [float("nan")]})}
    src = FakeSource(calendar=cal, bars={}, snapshots=snaps)
    s = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("SQZ")
    assert s.short_interest is None and s.days_to_cover is None
