from datetime import date, datetime
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.agent.parse import parse_decision


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol="RUN", name="Runner", status="gainer"),
        StockSnapshot(symbol="MOON", name="Moon", status="gainer"),
    ])


def test_parses_valid_and_drops_hallucinations():
    raw = ('{"regime_read": "trend frontside", "candidates": ['
           '{"symbol": "RUN", "pattern": "gap_and_go", "reason": "held VWAP", "confidence": 0.8}, '
           '{"symbol": "GHOST", "pattern": "x", "confidence": 0.9}, '          # not in universe -> drop
           '{"symbol": "RUN", "pattern": "dup", "confidence": 0.5}], '          # duplicate -> drop
           '"no_trade_reason": ""}')
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
    assert pkg.candidates[0].confidence == 0.8 and pkg.candidates[0].name == "Runner"
    assert pkg.regime_read == "trend frontside"


def test_clamps_confidence():
    raw = '{"candidates": [{"symbol": "MOON", "pattern": "p", "confidence": 5.0}]}'
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    assert pkg.candidates[0].confidence == 1.0


def test_malformed_is_no_trade():
    pkg = parse_decision("the model rambled with no json", date(2026, 6, 12), _uni(),
                         as_of=datetime(2026, 6, 12, 16, 0))
    assert pkg.candidates == [] and pkg.no_trade_reason
    assert pkg.as_of == datetime(2026, 6, 12, 16, 0)     # as_of stamped even on the no-trade path


def test_prose_wrapped_json_extracted():
    raw = 'Here is my call:\n```json\n{"candidates": [{"symbol": "RUN", "pattern": "p"}]}\n```'
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
