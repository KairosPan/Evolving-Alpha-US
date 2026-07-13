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
from alpha.data.composite import CompositeSource
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


def make_composite_source(base: MarketDataSource | str | None = None,
                          overrides: dict[str, MarketDataSource | str] | None = None,
                          *, pit_root: str | None = None) -> MarketDataSource:
    """Build a CompositeSource routing each capability to a (possibly different) backend.

    `base` and each override VALUE may be a MarketDataSource instance (P5 wires constructed feed backends
    directly) or a registry NAME string (built via make_source). `base` defaults to 'alpaca'. Returns a
    RAW source — the caller wraps with GuardedSource at the eval/loop layer, like any make_source result.
    """
    def _resolve(x: MarketDataSource | str) -> MarketDataSource:
        return make_source(x, pit_root=pit_root) if isinstance(x, str) else x
    base_src = _resolve(base if base is not None else "alpaca")
    resolved = {cap: _resolve(v) for cap, v in (overrides or {}).items()}
    return CompositeSource(base_src, resolved)


def _build_composite(*, pit_root: str | None = None) -> MarketDataSource:
    # Env-driven composite: ALPHA_DATA_COMPOSITE_BASE (default alpaca) + ALPHA_DATA_COMPOSITE, a
    # comma-separated list of `capability=source_name` overrides (e.g. "corp_actions=snapshot").
    base = (os.environ.get("ALPHA_DATA_COMPOSITE_BASE") or "alpaca").strip().lower()
    if base == "composite":
        raise ValueError("composite base cannot itself be 'composite' (would recurse)")
    overrides: dict[str, str] = {}
    for pair in os.environ.get("ALPHA_DATA_COMPOSITE", "").split(","):
        pair = pair.strip()
        if not pair:
            continue
        cap, sep, name = pair.partition("=")
        cap, name = cap.strip(), name.strip().lower()
        if not sep or not name:
            raise ValueError(f"composite override must be 'capability=source': {pair!r}")
        if name == "composite":
            raise ValueError("composite override backend cannot be 'composite' (would recurse)")
        overrides[cap] = name
    return make_composite_source(base, overrides, pit_root=pit_root)


_SOURCES = {"alpaca": _build_alpaca, "snapshot": _build_snapshot, "composite": _build_composite}


def make_source(name: str | None = None, *, pit_root: str | None = None) -> MarketDataSource:
    """Build the active data source. Name precedence: explicit arg > ALPHA_DATA_SOURCE env > 'alpaca'.
    Returns a RAW source (callers wrap with GuardedSource at the eval/loop layer)."""
    name = (name or os.environ.get("ALPHA_DATA_SOURCE", "alpaca")).strip().lower()
    if name not in _SOURCES:
        raise ValueError(f"unknown data source: {name!r} (expected one of {sorted(_SOURCES)})")
    return _SOURCES[name](pit_root=pit_root)
