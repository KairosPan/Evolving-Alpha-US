# alpha/data/registry.py
#
# Select the active MarketDataSource by name/env — the data-layer twin of alpha/llm/config.py::make_client.
# Whole-source swap only: each registered source implements the full MarketDataSource Protocol (an
# unsupported capability raises NotImplementedError in that method). Returns a RAW source; callers wrap it
# in GuardedSource at the eval/loop layer.
#
# Add a new vendor:
#   1. Implement the MarketDataSource Protocol in alpha/data/<vendor>.py.
#   2. Add a _build_<vendor>(*, pit_root=None) -> MarketDataSource here.
#   3. Register one line in _SOURCES.
#   4. Select it with ALPHA_DATA_SOURCE=<vendor>.
from __future__ import annotations

import os
from pathlib import Path

from alpha.data.alpaca import AlpacaSource
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.source import MarketDataSource


def _build_alpaca(*, pit_root: str | None = None) -> MarketDataSource:
    return AlpacaSource()                       # reads APCA_* + ALPHA_DATA_FEED from env itself


def _build_snapshot(*, pit_root: str | None = None) -> MarketDataSource:
    root = pit_root or os.environ.get("ALPHA_PIT_ROOT")
    if not root:
        raise ValueError("snapshot source requires pit_root or ALPHA_PIT_ROOT")
    return SnapshotSource(PITStore(Path(root)))


_SOURCES = {"alpaca": _build_alpaca, "snapshot": _build_snapshot}


def make_source(name: str | None = None, *, pit_root: str | None = None) -> MarketDataSource:
    """Build the active data source. Name precedence: explicit arg > ALPHA_DATA_SOURCE env > 'alpaca'.
    Returns a RAW source (callers wrap with GuardedSource at the eval/loop layer)."""
    name = (name or os.environ.get("ALPHA_DATA_SOURCE", "alpaca")).strip().lower()
    if name not in _SOURCES:
        raise ValueError(f"unknown data source: {name!r} (expected one of {sorted(_SOURCES)})")
    return _SOURCES[name](pit_root=pit_root)
