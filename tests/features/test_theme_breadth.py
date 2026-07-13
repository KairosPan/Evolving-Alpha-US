"""P5b theme/sector breadth: per-group signals + §1.2 lifecycle raw inputs (not the clock)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from alpha.data.sector_map import UNMAPPED, StaticSectorMap
from alpha.features.theme_breadth import (
    GroupBreadthReading, ThemeBreadthReading, theme_breadth,
)

DAY = date(2026, 6, 12)


def _bars(closes: list[float], end: date = DAY) -> pd.DataFrame:
    n = len(closes)
    dates = [end - timedelta(days=(n - 1 - i)) for i in range(n)]
    return pd.DataFrame({"date": dates, "close": closes, "open": closes, "high": closes,
                         "low": closes, "volume": [1] * n})


def _rising(n: int, base: float = 10.0, step: float = 0.5) -> list[float]:
    return [base + step * i for i in range(n)]


def _falling(n: int, base: float = 10.0, step: float = 0.5) -> list[float]:
    return [base + step * (n - i) for i in range(n)]


# ── per-group breadth correctness on a synthetic multi-sector tape ──────────────────────────────────

def test_per_group_breadth_partitions_by_sector():
    smap = StaticSectorMap({"NVDA": "semiconductors", "AMD": "semiconductors",
                            "XOM": "energy", "CVX": "energy"})
    bars = {"NVDA": _bars(_rising(25)), "AMD": _bars(_rising(25)),
            "XOM": _bars(_falling(25)), "CVX": _bars(_falling(25))}
    r = theme_breadth(bars, smap, DAY, ma_window=20, high_low_window=20,
                      rs_short_window=5, rs_long_window=10, min_members=2)
    semi = r.groups["semiconductors"]
    energy = r.groups["energy"]
    assert semi.determined and semi.member_count == 2
    assert semi.pct_above_200dma == 1.0 and semi.net_new_highs == 2
    assert semi.advances == 2 and semi.declines == 0
    assert energy.pct_above_200dma == 0.0 and energy.net_new_highs == -2
    assert energy.advances == 0 and energy.declines == 2
    # RS is cross-sectional over the whole tape: the two risers rank above the two fallers.
    assert semi.rs_mean == 100.0 and energy.rs_mean == 50.0


def test_undetermined_group_when_too_few_members():
    smap = StaticSectorMap({"NVDA": "semiconductors"})
    bars = {"NVDA": _bars(_rising(25))}
    r = theme_breadth(bars, smap, DAY, ma_window=20, high_low_window=20,
                      rs_short_window=5, rs_long_window=10, min_members=3)
    g = r.groups["semiconductors"]
    assert g.determined is False and g.member_count == 1
    # UNDETERMINED = every signal None, never a fabricated 0.
    assert g.pct_above_200dma is None and g.net_new_highs is None
    assert g.advances is None and g.declines is None
    assert g.rs_mean is None and g.rs_dispersion is None
    assert g.breadth_trend is None and g.rs_trend is None


def test_unmapped_bucket_is_its_own_group():
    smap = StaticSectorMap({"AMD": "semiconductors"})
    bars = {"AMD": _bars(_rising(25)), "ZZZZ": _bars(_rising(25))}
    r = theme_breadth(bars, smap, DAY, min_members=1, ma_window=20, high_low_window=20,
                      rs_short_window=5, rs_long_window=10)
    assert set(r.groups) == {"semiconductors", UNMAPPED}
    assert r.groups[UNMAPPED].member_count == 1


def test_empty_cross_section_has_no_groups():
    r = theme_breadth({}, StaticSectorMap({"AMD": "semiconductors"}), DAY)
    assert isinstance(r, ThemeBreadthReading) and r.groups == {}


# ── §1.2 lifecycle raw inputs: leader-vs-laggard dispersion ─────────────────────────────────────────

def test_rs_dispersion_wide_when_leaders_dominate_laggards():
    # four graded software names -> distinct cross-sectional RS percentiles 25/50/75/100.
    smap = StaticSectorMap({s: "software" for s in ("W1", "W2", "W3", "W4")})
    bars = {"W1": _bars(_rising(20, step=2.0)), "W2": _bars(_rising(20, step=1.0)),
            "W3": _bars(_rising(20, step=0.3)), "W4": _bars(_falling(20, step=1.0))}
    g = theme_breadth(bars, smap, DAY, rs_short_window=5, rs_long_window=10,
                      ma_window=10, high_low_window=10, min_members=2).groups["software"]
    # laggards (bottom half) mean = (25+50)/2 = 37.5; leaders (top half) mean = (75+100)/2 = 87.5.
    assert g.laggard_rs_mean == 37.5
    assert g.rs_dispersion == 50.0                       # 87.5 - 37.5


def test_rs_dispersion_compresses_when_laggards_catch_up():
    # laggards running with the leaders (public_laggard tell) -> dispersion collapses to ~0.
    smap = StaticSectorMap({s: "software" for s in ("A", "B", "C", "D")})
    bars = {s: _bars(_rising(20, step=1.0)) for s in ("A", "B", "C", "D")}
    g = theme_breadth(bars, smap, DAY, rs_short_window=5, rs_long_window=10,
                      ma_window=10, high_low_window=10, min_members=2).groups["software"]
    assert g.rs_dispersion == 0.0


# ── §1.2 lifecycle raw inputs: breadth trend + RS trend (self-contained, PIT-safe) ──────────────────

def test_breadth_trend_positive_when_group_participation_broadens():
    # STAY sits above its SMA200 at both as-ofs; CROSS is below 200DMA 21 days ago and above it now
    # (a fresh crossover in the last 15 bars). group pct_above_200dma: 0.5 -> 1.0 => trend +0.5.
    n = 230
    stay = _rising(n)                                    # always above its own SMA200
    cross = [50.0] * (n - 15) + [50.0 + 2.0 * (i + 1) for i in range(15)]
    smap = StaticSectorMap({"STAY": "semiconductors", "CROSS": "semiconductors"})
    bars = {"STAY": _bars(stay), "CROSS": _bars(cross)}
    g = theme_breadth(bars, smap, DAY, trend_lookback=21, min_members=2,
                      rs_short_window=5, rs_long_window=10).groups["semiconductors"]
    assert g.pct_above_200dma == 1.0
    assert g.breadth_trend is not None and g.breadth_trend > 0.0


def test_trend_is_none_without_enough_lookback_history():
    # fewer than trend_lookback+1 trailing days -> no earlier as-of -> trend undetermined (None).
    smap = StaticSectorMap({"NVDA": "semiconductors", "AMD": "semiconductors"})
    bars = {"NVDA": _bars(_rising(25)), "AMD": _bars(_rising(25))}
    g = theme_breadth(bars, smap, DAY, trend_lookback=50, min_members=2,
                      ma_window=20, high_low_window=20, rs_short_window=5,
                      rs_long_window=10).groups["semiconductors"]
    assert g.breadth_trend is None and g.rs_trend is None


def test_rs_trend_sign_tracks_relative_strength_shift():
    # X rises gently the whole time; Y is flat then ramps hard above X in the last 15 bars.
    # X loses cross-sectional rank (rs_trend<0); Y gains it (rs_trend>0).
    n = 280
    x = _rising(n, base=100.0, step=1.5)                 # 100 -> ~518, gentle vs Y's late ramp
    y = [50.0] * (n - 15) + [50.0 + 10.0 * (i + 1) for i in range(15)]   # ends ~200, sharp
    smap = StaticSectorMap({"X": "energy", "Y": "software"})
    r = theme_breadth({"X": _bars(x), "Y": _bars(y)}, smap, DAY,
                      trend_lookback=21, min_members=1, rs_short_window=126, rs_long_window=252)
    assert r.groups["energy"].rs_trend is not None and r.groups["energy"].rs_trend < 0.0
    assert r.groups["software"].rs_trend is not None and r.groups["software"].rs_trend > 0.0


# ── PIT: a future-dated row is ignored (belt-and-suspenders on the caller's AsOfGuard) ──────────────

def test_future_dated_row_is_ignored():
    smap = StaticSectorMap({"A": "semiconductors"})
    df = _bars([10.0, 11.0], end=DAY)
    future = pd.DataFrame({"date": [DAY + timedelta(days=1)], "close": [5.0], "open": [5.0],
                           "high": [5.0], "low": [5.0], "volume": [1]})
    df = pd.concat([df, future], ignore_index=True)
    g = theme_breadth({"A": df}, smap, DAY, min_members=1, ma_window=2, high_low_window=2,
                      rs_short_window=1, rs_long_window=1).groups["semiconductors"]
    assert g.advances == 1 and g.declines == 0           # reads 10->11 (up), ignores the drop to 5.0


# ── swap seam: a custom SectorMap drives the partition ──────────────────────────────────────────────

def test_custom_sector_map_swap_seam():
    class OneGroupMap:
        def sector_of(self, symbol: str) -> str:
            return "ai" if symbol.upper().startswith("A") else UNMAPPED

        def sectors(self) -> frozenset[str]:
            return frozenset({"ai"})

    bars = {"AMD": _bars(_rising(25)), "NVDA": _bars(_rising(25))}
    r = theme_breadth(bars, OneGroupMap(), DAY, min_members=1, ma_window=20, high_low_window=20,
                      rs_short_window=5, rs_long_window=10)
    assert set(r.groups) == {"ai", UNMAPPED}
    assert "AMD" not in r.groups["ai"].group          # group holds the KEY, members are counted
    assert r.groups["ai"].member_count == 1 and r.groups[UNMAPPED].member_count == 1


# ── additive structure is a standalone frozen bundle (byte-identity handoff is out of footprint) ────

def test_reading_is_frozen_additive_structure():
    r = ThemeBreadthReading(day=DAY, groups={})
    with pytest.raises(Exception):
        r.day = date(2000, 1, 1)                         # frozen: cannot mutate
    g = GroupBreadthReading(group="x", member_count=0, determined=False)
    assert g.pct_above_200dma is None and g.rs_dispersion is None   # every signal defaults None
