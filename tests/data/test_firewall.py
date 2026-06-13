# tests/data/test_firewall.py
from datetime import date
import pytest
from alpha.data.firewall import AsOfGuard, LookaheadError


def test_allows_past_and_equal_dates():
    g = AsOfGuard(date(2026, 6, 12))
    g.check(date(2026, 6, 10))   # past: ok
    g.check(date(2026, 6, 12))   # equal: ok


def test_rejects_future_date():
    g = AsOfGuard(date(2026, 6, 12))
    with pytest.raises(LookaheadError):
        g.check(date(2026, 6, 13))


def test_advance_is_monotonic():
    g = AsOfGuard(date(2026, 6, 12))
    g.advance(date(2026, 6, 13))
    assert g.as_of == date(2026, 6, 13)
    with pytest.raises(ValueError):
        g.advance(date(2026, 6, 12))
