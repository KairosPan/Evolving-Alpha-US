# tests/data/test_composite.py
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alpha.data.composite import CompositeSource
from alpha.data.firewall import AsOfGuard, LookaheadError
from alpha.data.registry import _SOURCES, make_composite_source, make_source
from alpha.data.source import FakeSource, GuardedSource


def _base_source() -> FakeSource:
    """A base bars/snapshot vendor: RUN bars + a snapshot, and its OWN corp action (symbol RUN)."""
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {"RUN": pd.DataFrame({
        "date": cal, "open": [10.0, 12.5, 16.0], "high": [12.0, 15.0, 18.0],
        "low": [9.5, 12.0, 15.0], "close": [11.0, 14.0, 17.0],
        "volume": [1_000_000, 3_000_000, 5_000_000]})}
    snapshots = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["RUN"], "name": ["Runner"], "open": [16.0], "high": [18.0],
        "low": [15.0], "close": [17.0], "volume": [5_000_000], "prev_close": [14.0]})}
    base_corp = pd.DataFrame({"symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
                              "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    return FakeSource(calendar=cal, bars=bars, snapshots=snapshots, corp_actions=base_corp,
                      corp_actions_available=True)


def _corp_backend() -> FakeSource:
    """A DISTINCT corp-actions backend: a different symbol (COR), no bars, and MISSING availability."""
    corp = pd.DataFrame({"symbol": ["COR"], "announce_date": [date(2026, 6, 1)],
                         "ex_date": [date(2026, 6, 5)], "kind": ["cash_dividend"], "ratio": [0.5]})
    return FakeSource(calendar=[], bars={}, snapshots={}, corp_actions=corp,
                      corp_actions_available=False)


# ── routing ──────────────────────────────────────────────────────────────────────────────────────

def test_corp_capability_routes_to_corp_backend():
    comp = CompositeSource(_base_source(), {"corp_actions": _corp_backend()})
    known = comp.corporate_actions_known(date(2026, 6, 12))
    assert list(known["symbol"]) == ["COR"]                       # corp backend, NOT base's RUN
    assert list(comp.corporate_actions(date(2026, 6, 1), date(2026, 6, 12))["symbol"]) == ["COR"]


def test_non_corp_capabilities_stay_on_base():
    comp = CompositeSource(_base_source(), {"corp_actions": _corp_backend()})
    # bars/snapshot/calendar untouched by the corp override — a misroute to the corp backend (no bars)
    # would surface as an empty frame.
    assert not comp.daily_bars("RUN", date(2026, 6, 10), date(2026, 6, 12)).empty
    assert list(comp.daily_snapshot(date(2026, 6, 12))["symbol"]) == ["RUN"]
    assert comp.trading_calendar() == [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]


def test_unset_capability_falls_through_to_base():
    comp = CompositeSource(_base_source())                        # no overrides at all
    assert list(comp.corporate_actions_known(date(2026, 6, 12))["symbol"]) == ["RUN"]
    assert not comp.daily_bars("RUN", date(2026, 6, 10), date(2026, 6, 12)).empty


# ── corp_actions_available routing (the P3 probe) ──────────────────────────────────────────────────

def test_corp_actions_available_routes_to_corp_backend():
    # base is checkable (True) but the corp backend reports MISSING (False) -> composite reports False:
    # the probe must describe whichever backend actually serves the corp data.
    base = _base_source()
    assert base.corp_actions_available() is True
    comp = CompositeSource(base, {"corp_actions": _corp_backend()})
    assert comp.corp_actions_available() is False


def test_corp_actions_available_true_when_corp_backend_checkable():
    corp_ok = FakeSource(calendar=[], bars={}, snapshots={}, corp_actions_available=True)
    comp = CompositeSource(_base_source(), {"corp_actions": corp_ok})
    assert comp.corp_actions_available() is True


# ── pure-swap contract ─────────────────────────────────────────────────────────────────────────────

def test_unsupported_capability_falls_to_base_and_raises_not_implemented():
    class _NoSnapshot:
        def daily_snapshot(self, day):
            raise NotImplementedError("base has no snapshots")
    # no snapshot override -> routes to base -> base raises NotImplementedError (contract propagates)
    with pytest.raises(NotImplementedError):
        CompositeSource(_NoSnapshot()).daily_snapshot(date(2026, 6, 12))


def test_unknown_capability_key_raises_value_error():
    with pytest.raises(ValueError, match="unknown composite capability"):
        CompositeSource(_base_source(), {"corp_action": _corp_backend()})   # typo: missing trailing 's'


# ── RAW pass-through + firewall preservation ───────────────────────────────────────────────────────

def test_pass_through_returns_backend_frame_unchanged():
    corp = _corp_backend()
    comp = CompositeSource(_base_source(), {"corp_actions": corp})
    direct = corp.corporate_actions_known(date(2026, 6, 12))
    routed = comp.corporate_actions_known(date(2026, 6, 12))
    pd.testing.assert_frame_equal(routed, direct)                 # no mutation/adjustment by the composite


def test_guarded_source_wraps_composite_and_blocks_lookahead():
    comp = CompositeSource(_base_source(), {"corp_actions": _corp_backend()})
    gs = GuardedSource(comp, AsOfGuard(date(2026, 6, 11)))
    gs.daily_snapshot(date(2026, 6, 11))                          # as_of == cursor: ok
    with pytest.raises(LookaheadError):
        gs.daily_snapshot(date(2026, 6, 12))                      # future: firewall still fires
    with pytest.raises(LookaheadError):
        gs.corporate_actions_known(date(2026, 6, 12))            # composite adds no lookahead of its own


def test_guarded_composite_passes_through_corp_availability():
    comp = CompositeSource(_base_source(), {"corp_actions": _corp_backend()})
    assert GuardedSource(comp, AsOfGuard(date(2026, 6, 12))).corp_actions_available() is False


# ── registry integration ───────────────────────────────────────────────────────────────────────────

@pytest.fixture
def apca(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")


def test_composite_is_registered(apca, monkeypatch):
    monkeypatch.delenv("ALPHA_DATA_COMPOSITE", raising=False)
    monkeypatch.delenv("ALPHA_DATA_COMPOSITE_BASE", raising=False)
    assert "composite" in _SOURCES
    assert isinstance(make_source("composite"), CompositeSource)


def test_make_source_composite_env_routes_corp_to_snapshot(apca, monkeypatch, tmp_path):
    # base=alpaca (bars/snapshot vendor), corp_actions overridden to an offline snapshot store.
    import pandas as pd
    from alpha.data.pit_store import PITStore
    store = PITStore(tmp_path)
    store.put_corp_actions(pd.DataFrame({"symbol": ["SNP"], "announce_date": [date(2026, 6, 1)],
                                         "ex_date": [date(2026, 6, 5)], "kind": ["cash_dividend"],
                                         "ratio": [0.2]}))
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    monkeypatch.setenv("ALPHA_DATA_COMPOSITE", "corp_actions=snapshot")
    comp = make_source("composite")
    assert isinstance(comp, CompositeSource)
    assert list(comp.corporate_actions_known(date(2026, 6, 12))["symbol"]) == ["SNP"]   # from snapshot


def test_make_composite_source_accepts_instances_and_names(apca, monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    # base as an instance, override as a registry name string
    comp = make_composite_source(_base_source(), {"corp_actions": "snapshot"})
    assert isinstance(comp, CompositeSource)
    # base instance still answers bars; the string override was resolved via make_source
    assert not comp.daily_bars("RUN", date(2026, 6, 10), date(2026, 6, 12)).empty


def test_composite_malformed_override_raises(apca, monkeypatch):
    monkeypatch.setenv("ALPHA_DATA_COMPOSITE", "corp_actions")            # no '=source'
    with pytest.raises(ValueError, match="capability=source"):
        make_source("composite")


def test_composite_recursion_guard(apca, monkeypatch):
    monkeypatch.setenv("ALPHA_DATA_COMPOSITE_BASE", "composite")
    with pytest.raises(ValueError, match="recurse"):
        make_source("composite")


def test_default_source_byte_identical_when_composite_unused(apca, monkeypatch):
    # Registering 'composite' must not perturb the default path.
    from alpha.data.alpaca import AlpacaSource
    monkeypatch.delenv("ALPHA_DATA_SOURCE", raising=False)
    assert isinstance(make_source(), AlpacaSource)
    assert isinstance(make_source("alpaca"), AlpacaSource)
