# tests/test_firewall.py
from datetime import date
import pytest
from youzi.replay.firewall import AsOfGuard, LookaheadError


def test_guard_allows_past_and_present_blocks_future():
    g = AsOfGuard(as_of=date(2024, 6, 27))
    g.check(date(2024, 6, 26))   # 过去:允许
    g.check(date(2024, 6, 27))   # 当日:允许
    with pytest.raises(LookaheadError):
        g.check(date(2024, 6, 28))   # 未来:拦截


def test_guard_advance_moves_boundary():
    g = AsOfGuard(as_of=date(2024, 6, 27))
    g.advance(date(2024, 6, 28))
    g.check(date(2024, 6, 28))   # 推进后允许
    with pytest.raises(LookaheadError):
        g.check(date(2024, 6, 29))


def test_guard_advance_rejects_backward():
    g = AsOfGuard(as_of=date(2024, 6, 27))
    with pytest.raises(ValueError):
        g.advance(date(2024, 6, 26))
