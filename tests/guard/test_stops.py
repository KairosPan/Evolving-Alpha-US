from alpha.regime.classifier import RegimeRead
from alpha.guard.stops import Position, stop_signals


def _pos(**kw):
    base = dict(symbol="RUN", entry_price=10.0, current_price=11.0, stop_price=9.0,
               days_held=1, narrative="ai")
    base.update(kw)
    return Position(**base)


_TREND = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.7)
_FLUSH = RegimeRead(phase="flush", confidence=0.6, frontside=False, risk_gate=0.2)


def test_no_stop_when_healthy():
    assert stop_signals(_pos(), _TREND, max_hold_days=5) == []


def test_form_stop_when_below_stop_price():
    sigs = stop_signals(_pos(current_price=8.5), _TREND, max_hold_days=5)
    assert [s.kind for s in sigs] == ["form"]


def test_regime_stop_on_backside():
    sigs = stop_signals(_pos(), _FLUSH, max_hold_days=5)
    assert "regime" in [s.kind for s in sigs]


def test_time_stop_when_held_too_long():
    sigs = stop_signals(_pos(days_held=6), _TREND, max_hold_days=5)
    assert "time" in [s.kind for s in sigs]
