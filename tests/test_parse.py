from datetime import date
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.agent.parse import parse_decision


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(code="000001", name="甲", status="limit_up", boards=7),
        StockSnapshot(code="300002", name="乙", status="limit_up", boards=2)])


def test_parse_valid_keeps_universe_codes():
    raw = ('{"regime_read":"主升","candidates":['
           '{"code":"000001","pattern":"highest_board","reason":"龙头","confidence":0.8}],'
           '"no_trade_reason":""}')
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert len(pkg.candidates) == 1
    c = pkg.candidates[0]
    assert c.code == "000001" and c.name == "甲" and c.pattern == "highest_board"
    assert c.confidence == 0.8


def test_parse_regime_read_into_package_and_defaults_empty():
    # A1:regime_read 解析进 DecisionPackage(下一日作 phase_prior);缺字段/null → ""(旧 JSON 兼容)
    raw = ('{"regime_read":" 主升 ","candidates":['
           '{"code":"000001","pattern":"x","confidence":0.5}],"no_trade_reason":""}')
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert pkg.regime_read == "主升"                              # strip 后入包
    old = '{"candidates":[],"no_trade_reason":"观望"}'            # 旧格式无 regime_read
    assert parse_decision(old, date(2024, 6, 27), _uni()).regime_read == ""
    nul = '{"regime_read":null,"candidates":[]}'
    assert parse_decision(nul, date(2024, 6, 27), _uni()).regime_read == ""
    bad = parse_decision("这不是 JSON", date(2024, 6, 27), _uni())
    assert bad.regime_read == ""                                  # 兜底空仓包默认空


def test_parse_drops_hallucinated_code():
    raw = ('{"candidates":[{"code":"999999","pattern":"x","reason":"幻觉","confidence":0.9},'
           '{"code":"300002","pattern":"y","reason":"真","confidence":0.5}]}')
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert {c.code for c in pkg.candidates} == {"300002"}        # 999999 不在候选池,丢弃


def test_parse_clamps_confidence_and_handles_markdown_fence():
    raw = '```json\n{"candidates":[{"code":"000001","confidence":1.7}]}\n```'
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert pkg.candidates[0].confidence == 1.0                    # 钳到 [0,1] + 去围栏


def test_parse_malformed_falls_back_to_no_trade():
    pkg = parse_decision("这不是 JSON", date(2024, 6, 27), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_parse_no_trade_passthrough():
    raw = '{"candidates":[],"no_trade_reason":"退潮空仓"}'
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason == "退潮空仓"


def test_parse_null_fields_become_empty_string():
    raw = '{"candidates":[{"code":"000001","pattern":null,"reason":null,"confidence":0.5}],"no_trade_reason":null}'
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert pkg.no_trade_reason == ""              # null -> "" 而非 "None"
    assert pkg.candidates[0].pattern == "" and pkg.candidates[0].reason == ""


def test_parse_int_code_matches_universe():
    raw = '{"candidates":[{"code":1,"pattern":"x","confidence":0.5}]}'
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())   # _uni() 含 000001
    assert {c.code for c in pkg.candidates} == {"000001"}   # int 1 -> "000001"


def test_parse_tolerates_prose_prefix():
    from datetime import date
    from youzi.agent.parse import parse_decision
    from youzi.universe.universe import CandidateUniverse
    from youzi.universe.stock import StockSnapshot
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(code="000001", name="平安", status="limit_up", boards=2)])
    raw = '我分析后认为:\n{"candidates": [{"code": "000001", "pattern": "接力", "confidence": 0.7}], "no_trade_reason": ""}'
    pkg = parse_decision(raw, date(2024, 6, 27), uni)
    assert [c.code for c in pkg.candidates] == ["000001"]
