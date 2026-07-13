"""Switchable universe entry (P0.4): the Trend Template screen as an alternative to the gainer screen,
default OFF and byte-identical when off."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from alpha.data.firewall import AsOfGuard
from alpha.data.source import FakeSource, GuardedSource
from alpha.universe.universe import build_trend_template_universe, build_universe

DAY = date(2026, 6, 12)


def _calendar(n: int, end: date = DAY) -> list[date]:
    return [end - timedelta(days=(n - 1 - i)) for i in range(n)]


def _series(cal: list[date], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"date": cal, "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1_000] * len(cal)})


def _trend_source() -> FakeSource:
    """STRONG: a clean 320-bar uptrend (passes all eight criteria). WEAK: a downtrend (fails). SHORT:
    only 100 bars (insufficient history -> explicit fail)."""
    cal = _calendar(320)
    strong = [10.0 + 0.5 * i for i in range(320)]
    weak = [10.0 + 0.5 * (320 - i) for i in range(320)]
    short_cal = cal[-100:]
    bars = {"STRONG": _series(cal, strong), "WEAK": _series(cal, weak),
            "SHORT": _series(short_cal, [5.0 + 0.5 * i for i in range(100)])}
    snap = pd.DataFrame({
        "symbol": ["STRONG", "WEAK", "SHORT"], "name": ["S", "W", "H"],
        "open": [strong[-2], weak[-2], 54.0], "high": [strong[-1], weak[-2], 55.0],
        "low": [strong[-2], weak[-1], 53.0],
        "close": [strong[-1], weak[-1], 54.5], "volume": [1_000, 1_000, 1_000],
        "prev_close": [strong[-2], weak[-2], 54.0]})
    return FakeSource(calendar=cal, bars=bars, snapshots={DAY: snap})


def test_default_screen_is_gainer(fake_source):
    # No screen arg, no env -> the momo gainer path. RUN is screened, no trend_template status appears.
    u = build_universe(fake_source, DAY, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN") is not None and u.get("RUN").status in ("gainer", "gap_up")
    assert all(s.status != "trend_template" for s in u.all())


def test_off_is_byte_identical(fake_source):
    # Explicit screen="gainer" must produce exactly the same snapshots as the default path.
    default = build_universe(fake_source, DAY, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    explicit = build_universe(fake_source, DAY, gainer_pct=10.0, gap_pct=5.0, rvol_window=2,
                              screen="gainer")
    assert {s.symbol: s.model_dump() for s in default.all()} == \
           {s.symbol: s.model_dump() for s in explicit.all()}


def test_env_switch_selects_trend_template(monkeypatch):
    monkeypatch.setenv("ALPHA_UNIVERSE_SCREEN", "trend_template")
    u = build_universe(_trend_source(), DAY)
    assert u.get("STRONG") is not None and u.get("STRONG").status == "trend_template"
    assert u.get("WEAK") is None and u.get("SHORT") is None       # fail the filter -> excluded


def test_env_default_still_gainer(fake_source, monkeypatch):
    monkeypatch.delenv("ALPHA_UNIVERSE_SCREEN", raising=False)
    u = build_universe(fake_source, DAY, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN").status in ("gainer", "gap_up")


def test_explicit_arg_overrides_env(fake_source, monkeypatch):
    monkeypatch.setenv("ALPHA_UNIVERSE_SCREEN", "trend_template")
    u = build_universe(fake_source, DAY, gainer_pct=10.0, gap_pct=5.0, rvol_window=2, screen="gainer")
    assert u.get("RUN").status in ("gainer", "gap_up")           # explicit arg wins over env


def test_unknown_screen_raises(fake_source):
    import pytest
    with pytest.raises(ValueError, match="unknown universe screen"):
        build_universe(fake_source, DAY, screen="minervini")


def test_empty_env_screen_falls_back_to_gainer_byte_identical(fake_source, monkeypatch):
    # a SET-but-EMPTY ALPHA_UNIVERSE_SCREEN must behave like unset (gainer path, no crash) and be
    # byte-identical to the default build — the `or DEFAULT` idiom, not `os.environ.get(k, DEFAULT)`.
    monkeypatch.delenv("ALPHA_UNIVERSE_SCREEN", raising=False)
    default = build_universe(fake_source, DAY, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    monkeypatch.setenv("ALPHA_UNIVERSE_SCREEN", "")
    empty = build_universe(fake_source, DAY, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert empty.get("RUN").status in ("gainer", "gap_up")
    assert {s.symbol: s.model_dump() for s in default.all()} == \
           {s.symbol: s.model_dump() for s in empty.all()}


def test_resolve_universe_screen(monkeypatch):
    import pytest
    from alpha.universe import resolve_universe_screen
    monkeypatch.delenv("ALPHA_UNIVERSE_SCREEN", raising=False)
    assert resolve_universe_screen() == "gainer"                  # unset -> default
    monkeypatch.setenv("ALPHA_UNIVERSE_SCREEN", "")
    assert resolve_universe_screen() == "gainer"                  # SET-but-EMPTY -> default (no crash)
    monkeypatch.setenv("ALPHA_UNIVERSE_SCREEN", "trend_template")
    assert resolve_universe_screen() == "trend_template"          # env read
    assert resolve_universe_screen("gainer") == "gainer"          # explicit arg wins over env
    with pytest.raises(ValueError, match="unknown universe screen"):
        resolve_universe_screen("minervini")


def test_trend_template_universe_keeps_passers_with_rs():
    u = build_trend_template_universe(_trend_source(), DAY)
    strong = u.get("STRONG")
    assert strong is not None and strong.status == "trend_template"
    assert strong.rs_percentile is not None and strong.rs_percentile >= 70.0
    assert strong.close is not None and strong.pct_change is not None


def test_trend_template_universe_insufficient_history_excluded():
    u = build_trend_template_universe(_trend_source(), DAY)
    assert u.get("SHORT") is None                                # 100 bars -> fails, never silently kept


def test_trend_template_universe_is_guard_safe():
    gs = GuardedSource(_trend_source(), AsOfGuard(DAY))
    u = build_trend_template_universe(gs, DAY)                    # end==day fetches must not trip the guard
    assert u.get("STRONG") is not None


def test_trend_template_universe_empty_snapshot():
    src = FakeSource(calendar=_calendar(10), bars={}, snapshots={})
    assert len(build_trend_template_universe(src, DAY)) == 0
