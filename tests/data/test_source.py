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


def test_corporate_actions_known_sees_pending_future_ex_split(fake_source):
    # conftest fake_source: RUN reverse_split announced 6/9, ex 6/20 (pending as of 6/12).
    from alpha.data.corp_actions import has_reverse_split_pending
    known = fake_source.corporate_actions_known(date(2026, 6, 12))
    assert list(known["symbol"]) == ["RUN"]                       # announced <= 6/12, future ex kept
    # the ex_date-filtered accessor MISSES it (ex 6/20 not in [6/1, 6/12]) -> the trap this primitive fixes
    assert fake_source.corporate_actions(date(2026, 6, 1), date(2026, 6, 12)).empty
    assert has_reverse_split_pending(known, "RUN", date(2026, 6, 12)) is True


def test_corporate_actions_known_is_guard_safe(fake_source):
    gs = GuardedSource(fake_source, AsOfGuard(date(2026, 6, 12)))
    assert list(gs.corporate_actions_known(date(2026, 6, 12))["symbol"]) == ["RUN"]   # as_of == cursor ok
    with pytest.raises(LookaheadError):
        gs.corporate_actions_known(date(2026, 6, 13))                                 # future as_of blocked


def test_fake_source_corp_actions_available_defaults_true(fake_source):
    # P3: in-memory sources are always checkable -> default True (present-but-empty & rows both report True)
    assert fake_source.corp_actions_available() is True


def test_fake_source_corp_actions_available_flag_simulates_missing():
    from alpha.data.source import FakeSource
    src = FakeSource(calendar=[date(2026, 6, 12)], bars={}, snapshots={},
                     corp_actions_available=False)
    assert src.corp_actions_available() is False


def test_guarded_source_passes_through_corp_actions_available(fake_source):
    from alpha.data.source import FakeSource
    assert GuardedSource(fake_source, AsOfGuard(date(2026, 6, 12))).corp_actions_available() is True
    blind = FakeSource(calendar=[date(2026, 6, 12)], bars={}, snapshots={},
                       corp_actions_available=False)
    assert GuardedSource(blind, AsOfGuard(date(2026, 6, 12))).corp_actions_available() is False


def test_guarded_source_tolerates_inner_without_probe():
    # a minimal structural source predating the capability -> treated as available (byte-identical posture)
    class _Stub:
        pass
    assert GuardedSource(_Stub(), AsOfGuard(date(2026, 6, 12))).corp_actions_available() is True


# ── earnings capability (P5a) ───────────────────────────────────────────────────────────────────────

def _earnings_fake():
    from alpha.data.source import FakeSource
    from alpha.data.earnings import EarningsFact, EarningsCalendarEntry
    facts = [EarningsFact(symbol="RUN", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                          filing_date=date(2026, 5, 6), actual_eps=1.2),
             EarningsFact(symbol="FLOP", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                          filing_date=date(2026, 5, 8), actual_eps=-0.3)]
    cal = [EarningsCalendarEntry(symbol="RUN", expected_date=date(2026, 5, 6),
                                 known_asof=date(2026, 4, 20), is_confirmed=True)]
    return FakeSource(calendar=[], bars={}, snapshots={}, earnings=facts, earnings_calendar=cal)


def test_fake_source_earnings_known_pit_and_symbol_filter():
    src = _earnings_fake()
    assert src.earnings_known("RUN", date(2026, 4, 15)) == []          # filed 5/6, invisible on 4/15
    got = src.earnings_known("RUN", date(2026, 5, 7))
    assert [f.fiscal_period for f in got] == ["2026Q1"]                # RUN only, FLOP excluded by symbol
    assert src.earnings_known("FLOP", date(2026, 5, 8))[0].symbol == "FLOP"   # FLOP filed 5/8


def test_fake_source_earnings_calendar_pit():
    src = _earnings_fake()
    assert src.earnings_calendar(date(2026, 4, 19)) == []              # before known_asof 4/20
    assert len(src.earnings_calendar(date(2026, 4, 20))) == 1


def test_fake_source_earnings_available_flag():
    from alpha.data.source import FakeSource
    assert _earnings_fake().earnings_available() is True               # earnings passed -> present
    bare = FakeSource(calendar=[date(2026, 6, 12)], bars={}, snapshots={})
    assert bare.earnings_available() is False                         # none passed -> MISSING (fail-closed)


def test_guarded_source_blocks_future_earnings():
    src = _earnings_fake()
    gs = GuardedSource(src, AsOfGuard(date(2026, 5, 6)))
    assert [f.symbol for f in gs.earnings_known("RUN", date(2026, 5, 6))] == ["RUN"]   # as_of == cursor ok
    with pytest.raises(LookaheadError):
        gs.earnings_known("RUN", date(2026, 5, 7))                    # future as_of blocked
    with pytest.raises(LookaheadError):
        gs.earnings_calendar(date(2026, 5, 7))


def test_guarded_source_earnings_available_defaults_false_when_absent():
    # fail-closed: an inner predating the capability reports MISSING (False), NOT the corp default-True.
    class _Stub:
        pass
    assert GuardedSource(_Stub(), AsOfGuard(date(2026, 6, 12))).earnings_available() is False


def test_snapshot_source_corporate_actions_known(tmp_path):
    # SnapshotSource is the production OFFLINE source (PITStore-backed) — lock the new primitive there too.
    import pandas as pd
    from alpha.data.pit_store import PITStore
    from alpha.data.snapshot_source import SnapshotSource
    from alpha.data.corp_actions import has_reverse_split_pending
    store = PITStore(tmp_path)
    store.put_corp_actions(pd.DataFrame({"symbol": ["RS"], "announce_date": [date(2026, 6, 9)],
                                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"],
                                         "ratio": [0.1]}))
    known = SnapshotSource(store).corporate_actions_known(date(2026, 6, 12))
    assert has_reverse_split_pending(known, "RS", date(2026, 6, 12)) is True   # announced 6/9, ex 6/20 future
