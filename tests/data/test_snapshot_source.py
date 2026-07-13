from __future__ import annotations
from datetime import date
import pandas as pd
import pytest
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource, SnapshotMissingError


def _seed(tmp_path):
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 11), date(2026, 6, 12)])
    store.put_snapshot(date(2026, 6, 12), pd.DataFrame({
        "symbol": ["RUN"], "name": ["Runner Inc"], "open": [16.0], "high": [18.0],
        "low": [15.0], "close": [17.0], "volume": [5_000_000], "prev_close": [14.0]}))
    # RAW bars: a low-priced runner pre reverse-split (would look ~$170 if future-adjusted 1:10)
    store.put_bars("RUN", pd.DataFrame({
        "date": [date(2026, 6, 11), date(2026, 6, 12)],
        "open": [12.5, 16.0], "high": [15.0, 18.0], "low": [12.0, 15.0],
        "close": [14.0, 17.0], "volume": [3_000_000, 5_000_000]}))
    return SnapshotSource(store)


def test_snapshot_present(tmp_path):
    src = _seed(tmp_path)
    snap = src.daily_snapshot(date(2026, 6, 12))
    assert snap.iloc[0]["symbol"] == "RUN"


def test_missing_snapshot_raises(tmp_path):
    src = _seed(tmp_path)
    with pytest.raises(SnapshotMissingError):
        src.daily_snapshot(date(2026, 6, 11))   # not captured


def test_missing_bars_returns_empty(tmp_path):
    src = _seed(tmp_path)
    out = src.daily_bars("NOPE", date(2026, 6, 11), date(2026, 6, 12))
    assert out.empty and list(out.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_bars_are_raw_not_future_adjusted(tmp_path):
    """Firewall surface: stored prices are RAW; a $14 close stays $14, not future-split-rebased."""
    src = _seed(tmp_path)
    bars = src.daily_bars("RUN", date(2026, 6, 11), date(2026, 6, 11))
    assert bars.iloc[0]["close"] == 14.0     # raw, NOT 140.0


def test_corp_actions_available_reflects_artifact_presence(tmp_path):
    """P3: SnapshotSource surfaces the store's MISSING/present distinction so screen_decision can
    tell 'no corp_actions.parquet' (guard blind) apart from 'checked, nothing announced'."""
    store = PITStore(tmp_path)
    src = SnapshotSource(store)
    assert src.corp_actions_available() is False                     # no parquet -> MISSING
    store.put_corp_actions(pd.DataFrame(
        columns=["symbol", "announce_date", "ex_date", "kind", "ratio"]))
    assert src.corp_actions_available() is True                      # present-but-empty -> checkable


# ── earnings (P5a) ────────────────────────────────────────────────────────────────────────────────

def _seed_earnings(tmp_path):
    from alpha.data.earnings import (EarningsCalendarEntry, EarningsFact,
                                     calendar_to_frame, facts_to_frame)
    store = PITStore(tmp_path)
    facts = [EarningsFact(symbol="RUN", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                          filing_date=date(2026, 5, 6), actual_eps=1.2, actual_revenue=5.0e8),
             EarningsFact(symbol="OTH", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                          filing_date=date(2026, 5, 6), actual_eps=0.4)]
    cal = [EarningsCalendarEntry(symbol="RUN", expected_date=date(2026, 5, 6),
                                 known_asof=date(2026, 4, 20), is_confirmed=True, session="amc")]
    store.put_earnings(facts_to_frame(facts))
    store.put_earnings_calendar(calendar_to_frame(cal))
    return SnapshotSource(store), store


def test_snapshot_earnings_pit_and_symbol_filter(tmp_path):
    src, _ = _seed_earnings(tmp_path)
    assert src.earnings_known("RUN", date(2026, 4, 15)) == []        # filed 5/6, invisible on 4/15
    got = src.earnings_known("RUN", date(2026, 5, 6))
    assert len(got) == 1 and got[0].symbol == "RUN" and got[0].actual_revenue == 5.0e8
    assert src.earnings_known("OTH", date(2026, 5, 6))[0].symbol == "OTH"   # symbol filter


def test_snapshot_earnings_calendar_pit(tmp_path):
    src, _ = _seed_earnings(tmp_path)
    assert src.earnings_calendar(date(2026, 4, 19)) == []            # before known_asof 4/20
    cal = src.earnings_calendar(date(2026, 4, 20))
    assert len(cal) == 1 and cal[0].session == "amc" and cal[0].is_confirmed is True


def test_snapshot_earnings_available_reflects_artifact_presence(tmp_path):
    store = PITStore(tmp_path)
    src = SnapshotSource(store)
    assert src.earnings_available() is False                         # no parquet -> MISSING (fail-closed)
    _seed_earnings(tmp_path)
    assert SnapshotSource(store).earnings_available() is True        # present -> checkable
