"""Offline pin for scripts/calibrate_growth_clock.py — the P2 acceptance-evidence producer.

Runs the calibration's library function against a SYNTHETIC FakeSource tape (bull -> deep bear ->
sharp rebound), NOT the gitignored real window, so the script's replay + distribution accounting is
regression-locked and reproducible without any captured data or keys.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.data.source import FakeSource

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import calibrate_growth_clock as cg   # noqa: E402

_N = 10                                   # symbols; each day a fraction gap +12% (gainer), the rest -12% (loser)
# bull (confirmed) -> a long deep bear (correction) -> a sharp rebound (panic) -> continuation
_UP_FRACS = [0.9] * 5 + [0.1] * 13 + [0.9] * 3


def _tape():
    cal = [date(2026, 3, i + 1) for i in range(len(_UP_FRACS))]
    prev = {f"S{k}": 100.0 for k in range(_N)}
    snaps = {}
    for i, day in enumerate(cal):
        up = round(_UP_FRACS[i] * _N)
        rows = []
        for k in range(_N):
            p = prev[f"S{k}"]
            close = p * 1.12 if k < up else p * 0.88     # +/-12% -> gainer/loser under the 10% screen
            rows.append({"symbol": f"S{k}", "name": f"S{k}", "open": p, "high": max(p, close),
                         "low": min(p, close), "close": close, "volume": 1, "prev_close": p})
            prev[f"S{k}"] = close
        snaps[day] = pd.DataFrame(rows)
    return FakeSource(calendar=cal, bars={}, snapshots=snaps), cal


def test_calibrate_distribution_covers_all_three_states_and_panic():
    src, days = _tape()
    r = cg.calibrate(src, days)
    assert r.n_days == len(days)
    assert sum(r.states.values()) == len(days)                 # every day classified into one state
    assert r.states.get("confirmed_uptrend", 0) > 0            # the bull run confirms
    assert (r.states.get("under_pressure", 0) + r.states.get("correction", 0)) > 0   # the bear stretch
    assert r.frontside == r.states.get("confirmed_uptrend", 0)  # frontside <=> confirmed_uptrend
    assert r.panic > 0                                          # the sharp rebound out of the bear is panic
    assert r.start == days[0] and r.end == days[-1]


def test_calibrate_breadth_variant_runs_and_is_wellformed():
    """The --breadth path threads full advance/decline into the read; it must produce a well-formed
    distribution (still summing to n_days) — the a/d read can differ from the gainer-tail read."""
    src, days = _tape()
    r = cg.calibrate(src, days, breadth=True)
    assert r.n_days == len(days) and sum(r.states.values()) == len(days)
    assert r.frontside == r.states.get("confirmed_uptrend", 0)


def test_format_report_renders_the_table():
    src, days = _tape()
    text = cg.format_report(cg.calibrate(src, days))
    assert "growth market-clock calibration" in text
    for s in ("confirmed_uptrend", "under_pressure", "correction"):
        assert f"market:{s}" in text
    assert "frontside" in text and "panic-flag" in text


def test_market_state_from_snapshot_matches_the_universe_screen():
    """The producer's gainer/loser counts use the same +/-10% screen as build_universe, so gainer_share
    matches the live path. Pin: 7 up (+12% -> gainer), 3 down (-12% -> loser) reads gainer_count 7."""
    src, days = _tape()
    snap = src.daily_snapshot(days[0])                         # day 0: up-frac 0.9 -> 9 gainers, 1 loser
    st = cg.market_state_from_snapshot(snap, days[0])
    assert st.gainer_count == 9 and st.loser_count == 1
    assert st.advances is None                                 # breadth off by default (live-path parity)
    st_b = cg.market_state_from_snapshot(snap, days[0], breadth=True)
    assert st_b.advances == 9 and st_b.declines == 1           # full a/d threaded under --breadth
