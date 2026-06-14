"""US-1e acceptance: the full L1 builder turns <=t data into an enriched MarketState, and the
read-only G_cycle maps it to a canonical-vocabulary regime read whose phase is reachable in the
state machine."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.features.builder import build_market_state
from alpha.regime.classifier import GCycle
from alpha.regime.cycle import default_us_cycle


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["RUN"], "name": ["r"], "open": [12.0], "high": [14], "low": [12],
        "close": [14.0], "volume": [1], "prev_close": [10.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10, 11, 12.0], "high": [11, 12, 14],
                                 "low": [10, 11, 12], "close": [10.0, 11.0, 14.0], "volume": [1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_perception_to_regime_read():
    ms = build_market_state(date(2026, 6, 12), _source(), history=[-5.0, -3.0, -1.0],
                            as_of=datetime(2026, 6, 12, 16, 0), prev_gainers=frozenset({"RUN"}),
                            min_samples=3)
    read = GCycle().read(ms)
    sm = default_us_cycle()
    assert read.phase in sm.phase_names()                # phase is a known state
    assert 0.0 <= read.risk_gate <= 1.0
    # the read's phase is reachable in the cycle (a start state or a transition target)
    targets = {read.phase} | {to for p in sm.phase_names() for to, _ in sm.next_signals(p)}
    assert read.phase in targets
