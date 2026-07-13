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


def test_parses_narrative_for_correlation_netting():
    raw = ('{"candidates": ['
           '{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.8, "narrative": "AI-Compute"}, '
           '{"symbol": "MOON", "pattern": "short_squeeze", "confidence": 0.6}]}')   # no narrative -> ""
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    narratives = {c.symbol: c.narrative for c in pkg.candidates}
    assert narratives == {"RUN": "ai-compute", "MOON": ""}    # normalized (lowercased/stripped)


def test_prose_wrapped_json_extracted():
    raw = 'Here is my call:\n```json\n{"candidates": [{"symbol": "RUN", "pattern": "p"}]}\n```'
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    assert [c.symbol for c in pkg.candidates] == ["RUN"]


def test_parse_ignores_llm_supplied_action_and_size_tier():
    """LOAD-BEARING (P0.6): parse_decision builds Candidate from a FIXED field allowlist
    (symbol/name/pattern/reason/confidence/narrative). That allowlist is the ONLY thing keeping LLM
    output from reaching the L4/L3 action seams — a model that emits "action":"trim" must NOT flip a
    candidate to trim and thereby skip the L4 new-entry veto (nor set its own size_tier). The parser
    drops both fields on the floor, so the produced Candidate stays action=="enter" / size_tier None.
    If a future edit widens the allowlist to pass action through, this pin fails on purpose."""
    raw = ('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.8, '
           '"action": "trim", "size_tier": "heavy"}]}')
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
    assert pkg.candidates[0].action == "enter"           # LLM "trim" ignored -> defaults enter
    assert pkg.candidates[0].size_tier is None            # LLM "heavy" ignored -> unset (L3 assigns it)
