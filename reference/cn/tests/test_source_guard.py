# tests/test_source_guard.py
from datetime import date
import pandas as pd
import pytest
from youzi.replay.firewall import AsOfGuard, LookaheadError
from youzi.data.source import GuardedSource
from tests.conftest import FakeSource


def _src():
    frames = {("zt", date(2024, 6, 27)): pd.DataFrame({"code": ["000001"]})}
    return FakeSource(frames, [date(2024, 6, 27), date(2024, 6, 28)])


def test_guarded_source_allows_past():
    g = AsOfGuard(date(2024, 6, 27))
    gs = GuardedSource(_src(), g)
    df = gs.zt_pool(date(2024, 6, 27))
    assert list(df["code"]) == ["000001"]


def test_guarded_source_blocks_future():
    g = AsOfGuard(date(2024, 6, 27))
    gs = GuardedSource(_src(), g)
    with pytest.raises(LookaheadError):
        gs.zt_pool(date(2024, 6, 28))
