# tests/universe/test_build_universe.py
from __future__ import annotations
from datetime import date
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
