from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.data.source import MarketDataSource
from alpha.features.sentiment import DEFAULT_MIN_SAMPLES
from alpha.state.builder import build_market_state as _build_market_state
from alpha.state.market import MarketState
from alpha.universe.universe import build_universe


def build_market_state(day: Date, source: MarketDataSource, history: list[float], as_of: DateTime,
                       prev_gainers: frozenset[str] = frozenset(),
                       min_samples: int = DEFAULT_MIN_SAMPLES) -> MarketState:
    """Back-compat shim: build the day's universe then delegate to the unified state builder. Prefer
    calling alpha.state.builder.build_market_state with a prebuilt universe on the live path (avoids a
    second build_universe). FIREWALL: the caller must pass a GuardedSource(AsOfGuard(day)).

    DEFAULT_MIN_SAMPLES is imported from the leaf alpha.features.sentiment (NOT re-exported here): this
    module imports build_market_state from alpha.state.builder, so re-exporting the constant from here
    would form a features/builder -> state/builder -> features/builder cycle.
    """
    return _build_market_state(build_universe(source, day), day, as_of=as_of,
                               history=history, prev_gainers=prev_gainers, min_samples=min_samples)
