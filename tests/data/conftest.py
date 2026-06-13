from __future__ import annotations
from datetime import date
import pandas as pd
import pytest
from alpha.data.source import FakeSource


@pytest.fixture
def fake_source():
    """Two symbols over 3 days. RUN gaps up and runs; FLOP fades."""
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {
        "RUN": pd.DataFrame({
            "date": cal,
            "open":  [10.0, 12.5, 16.0], "high": [12.0, 15.0, 18.0],
            "low":   [9.5, 12.0, 15.0],  "close": [11.0, 14.0, 17.0],
            "volume": [1_000_000, 3_000_000, 5_000_000],
        }),
        "FLOP": pd.DataFrame({
            "date": cal,
            "open":  [20.0, 21.0, 18.0], "high": [22.0, 21.5, 18.5],
            "low":   [19.0, 17.5, 16.0], "close": [21.0, 18.0, 16.5],
            "volume": [500_000, 600_000, 700_000],
        }),
    }
    snapshots = {
        date(2026, 6, 12): pd.DataFrame({
            "symbol": ["RUN", "FLOP"], "name": ["Runner Inc", "Flopco"],
            "open": [16.0, 18.0], "high": [18.0, 18.5], "low": [15.0, 16.0],
            "close": [17.0, 16.5], "volume": [5_000_000, 700_000],
            "prev_close": [14.0, 18.0],
        }),
    }
    corp = pd.DataFrame({
        "symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
        "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1],
    })
    return FakeSource(calendar=cal, bars=bars, snapshots=snapshots, corp_actions=corp)
