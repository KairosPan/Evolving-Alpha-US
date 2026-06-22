# tests/data/test_registry.py
from __future__ import annotations

import pytest

from alpha.data.alpaca import AlpacaSource
from alpha.data.registry import make_source
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
