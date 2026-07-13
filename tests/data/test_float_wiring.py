"""Float capability wired through the five source shapes (P5b; spec 2026-07-13-p5b-float-feed-design.md):
FakeSource (default-off), GuardedSource (guard + fail-closed), SnapshotSource/PITStore, CompositeSource
routing + fail-closed availability, and the registry `float_feed` backend."""
from datetime import date
from pathlib import Path

import pytest

from alpha.data.composite import CompositeSource
from alpha.data.firewall import AsOfGuard
from alpha.data.float_feed import FloatSource
from alpha.data.float_shares import FloatFact, float_to_frame
from alpha.data.pit_store import PITStore
from alpha.data.registry import make_composite_source, make_source
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.source import FakeSource, GuardedSource

CUR = date(2026, 6, 12)


def _fact(sym="ACME", knowable=date(2026, 5, 1), free_float=8_000_000.0):
    return FloatFact(symbol=sym, free_float=free_float, knowable_date=knowable, as_of_period=date(2026, 3, 31))


def _fake(**kw):
    return FakeSource(calendar=[CUR], bars={}, snapshots={}, **kw)


# ── FakeSource default-off (byte-identical when no float passed) ────────────────────────────────────

def test_fakesource_float_default_off():
    assert _fake().float_available() is False           # no float_facts -> MISSING (byte-identical pre-P5b)
    assert _fake().float_known("ACME", CUR) == []


def test_fakesource_float_present_and_pit_and_symbol_filtered():
    src = _fake(float_facts=[_fact(knowable=date(2026, 5, 1)), _fact("BETA", knowable=date(2026, 7, 1))])
    assert src.float_available() is True
    assert [f.symbol for f in src.float_known("ACME", CUR)] == ["ACME"]     # symbol filter
    assert src.float_known("BETA", CUR) == []                              # 7/1 not knowable at 6/12 (PIT)


def test_fakesource_float_present_but_empty_is_available():
    assert _fake(float_facts=[]).float_available() is True                 # present-empty != MISSING


# ── GuardedSource: guard as_of, fail-closed default-False when inner lacks capability ───────────────

def test_guarded_float_guards_as_of():
    src = GuardedSource(_fake(float_facts=[_fact()]), AsOfGuard(CUR))
    with pytest.raises(Exception):
        src.float_known("ACME", date(2026, 6, 13))       # as_of > guard -> lookahead blocked
    assert len(src.float_known("ACME", CUR)) == 1


def test_guarded_float_available_fail_closed_for_legacy_inner():
    class _Legacy:                                        # an inner predating the float capability
        pass
    assert GuardedSource(_Legacy(), AsOfGuard(CUR)).float_available() is False


# ── SnapshotSource / PITStore round-trip + tri-state MISSING ────────────────────────────────────────

def test_pitstore_float_roundtrip_and_tristate(tmp_path: Path):
    store = PITStore(tmp_path)
    assert store.has_float() is False                    # MISSING artifact
    store.put_float(float_to_frame([_fact(free_float=8_000_000.0)]))
    assert store.has_float() is True
    snap = SnapshotSource(store)
    assert snap.float_available() is True
    got = snap.float_known("ACME", CUR)
    assert len(got) == 1 and got[0].free_float == 8_000_000.0 and got[0].knowable_date == date(2026, 5, 1)


def test_pitstore_float_empty_present_is_available(tmp_path: Path):
    store = PITStore(tmp_path)
    store.put_float(float_to_frame([]))
    assert store.has_float() is True                      # present-empty != MISSING
    assert SnapshotSource(store).float_available() is True


# ── CompositeSource: route the `float` group to a per-capability backend ─────────────────────────────

def test_composite_routes_float_to_override():
    base = _fake()                                        # base has no float (default-off)
    float_backend = _fake(float_facts=[_fact()])
    comp = CompositeSource(base, {"float": float_backend})
    assert comp.float_available() is True                 # reports the FLOAT backend, not base
    assert len(comp.float_known("ACME", CUR)) == 1


def test_composite_float_falls_through_to_base_fail_closed():
    # un-overridden float -> base (default-off) -> fail-closed False, pure-swap preserved
    assert CompositeSource(_fake()).float_available() is False


def test_composite_unknown_capability_still_rejected():
    with pytest.raises(ValueError):
        CompositeSource(_fake(), {"flaot": _fake()})      # typo -> unknown capability


# ── registry: the float_feed backend + composite override string ────────────────────────────────────

def test_registry_builds_float_feed():
    assert isinstance(make_source("float_feed"), FloatSource)


def test_registry_composite_float_override_keyless():
    # `ALPHA_DATA_COMPOSITE=float=float_feed`-shaped wiring resolves the override string via make_source
    # without keys (a keyless FakeSource base avoids the live alpaca default; UA only matters on fetch).
    comp = make_composite_source(_fake(), {"float": "float_feed"})
    assert isinstance(comp._route("float"), FloatSource)
    assert comp.float_available() is True                 # the FloatSource backend reports checkable
