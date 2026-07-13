# tests/data/test_registry.py
from __future__ import annotations

import pytest

from alpha.data.alpaca import AlpacaSource
from alpha.data.registry import _SOURCES, make_source
from alpha.data.snapshot_source import SnapshotSource


@pytest.fixture
def apca(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")


def test_default_is_alpaca(apca, monkeypatch):
    monkeypatch.delenv("ALPHA_DATA_SOURCE", raising=False)
    assert isinstance(make_source(), AlpacaSource)


def test_env_selects_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHA_DATA_SOURCE", "snapshot")
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    assert isinstance(make_source(), SnapshotSource)


def test_explicit_name_overrides_env(apca, monkeypatch):
    monkeypatch.setenv("ALPHA_DATA_SOURCE", "snapshot")     # env says snapshot...
    assert isinstance(make_source("alpaca"), AlpacaSource)  # ...explicit arg wins


def test_snapshot_via_kwarg(tmp_path):
    assert isinstance(make_source("snapshot", pit_root=str(tmp_path)), SnapshotSource)


def test_name_is_normalized(apca, monkeypatch):
    monkeypatch.delenv("ALPHA_DATA_SOURCE", raising=False)
    assert isinstance(make_source("  ALPACA "), AlpacaSource)   # strip + lowercase


def test_unknown_source_raises_listing_available(monkeypatch):
    monkeypatch.delenv("ALPHA_DATA_SOURCE", raising=False)
    with pytest.raises(ValueError, match="unknown data source"):
        make_source("polygon")


def test_snapshot_requires_pit_root(monkeypatch):
    monkeypatch.setenv("ALPHA_DATA_SOURCE", "snapshot")
    monkeypatch.delenv("ALPHA_PIT_ROOT", raising=False)
    with pytest.raises(ValueError, match="pit_root"):
        make_source()


def test_edgar_is_registered_earnings_backend(monkeypatch):
    from alpha.data.edgar import EdgarSource
    monkeypatch.delenv("ALPHA_DATA_SOURCE", raising=False)
    assert "edgar" in _SOURCES
    assert isinstance(make_source("edgar"), EdgarSource)             # keyless construction (no network)


def test_composite_routes_earnings_to_edgar(apca, monkeypatch):
    # end-to-end env wiring: base=alpaca (bars/snapshot), earnings overridden to the EDGAR backend.
    from alpha.data.composite import CompositeSource
    from alpha.data.edgar import EdgarSource
    monkeypatch.setenv("ALPHA_DATA_COMPOSITE", "earnings=edgar")
    comp = make_source("composite")
    assert isinstance(comp, CompositeSource)
    assert isinstance(comp._route("earnings"), EdgarSource)
    assert comp.earnings_available() is True                         # routed to the (live) EDGAR backend


@pytest.mark.parametrize("name", sorted(_SOURCES))
def test_every_registered_source_implements_corp_actions_available(name, apca, monkeypatch, tmp_path):
    """P3 conformance: corp_actions_available is the MarketDataSource Protocol's ONLY fail-open method —
    omitting any other crashes at first use, but omitting THIS one reads silently as 'checked', re-hiding
    the exact guard-blind class P3 fixed (and the SnapshotSource reference a future vendor copies returns
    empty-on-missing). Every REGISTERED source must expose it (structural test doubles keep the
    spec-adjudicated GuardedSource default-True)."""
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    assert callable(getattr(make_source(name), "corp_actions_available", None))
