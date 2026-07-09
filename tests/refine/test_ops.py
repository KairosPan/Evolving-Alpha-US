from alpha.refine.ops import PASS_ORDER, PASS_TOOLS, RefineOp, parse_extraction, parse_ops


def test_pass_structure():
    assert PASS_ORDER == ("p", "G", "K", "M")
    assert PASS_TOOLS["G"] == frozenset()                        # G is a reserved no-op
    assert PASS_TOOLS["p"] == frozenset({"rewrite_doctrine"})
    assert "promote_skill" in PASS_TOOLS["K"] and "retire_skill" in PASS_TOOLS["K"]
    assert PASS_TOOLS["M"] == frozenset({"process_memory", "update_memory", "demote_memory"})
    # every non-G tool is a real MetaTools method
    from alpha.harness.metatools import MetaTools
    for tools in PASS_TOOLS.values():
        for t in tools:
            assert hasattr(MetaTools, t)


def test_parse_ops_valid():
    raw = ('prose {"ops": [{"tool": "retire_skill", "args": {"skill_id": "x"}, "rationale": "decayed"}, '
           '{"tool": "promote_skill", "args": {"skill_id": "y"}}]} tail')
    ops = parse_ops(raw)
    assert [o.tool for o in ops] == ["retire_skill", "promote_skill"]
    assert ops[0].args == {"skill_id": "x"} and ops[0].rationale == "decayed"
    assert ops[1].rationale == ""                                # missing rationale defaults to ''


def test_parse_ops_robust():
    assert parse_ops("no json") == []
    assert parse_ops('{"ops": "notalist"}') == []
    assert parse_ops('{"ops": 5}') == []          # non-iterable ops must not crash (reject-don't-crash)
    # drops malformed items (non-dict, missing/blank tool, non-dict args) but keeps the good one
    raw = '{"ops": [1, {"args": {}}, {"tool": ""}, {"tool": "x", "args": 5}, {"tool": "promote_skill"}]}'
    assert [o.tool for o in parse_ops(raw)] == ["promote_skill"]


def test_parse_extraction_returns_ops_when_present():
    raw = '{"ops":[{"tool":"process_memory","args":{"lesson_id":"l1"},"rationale":"r"}]}'
    ops, no_edit, reason = parse_extraction(raw)
    assert no_edit is False and reason == ""
    assert [o.tool for o in ops] == ["process_memory"]


def test_parse_extraction_no_edit_carries_reason():
    ops, no_edit, reason = parse_extraction('{"no_edit": true, "reason": "still clarifying"}')
    assert ops == [] and no_edit is True and reason == "still clarifying"


def test_parse_extraction_empty_object_falls_back_never_silent():
    ops, no_edit, reason = parse_extraction("{}")
    assert ops == [] and no_edit is True and reason        # non-empty fallback reason


def test_parse_extraction_malformed_is_no_edit_not_crash():
    for raw in ("not json at all", '{"ops": 5}', '{"ops": []}', ""):
        ops, no_edit, reason = parse_extraction(raw)
        assert ops == [] and no_edit is True and reason


def test_parse_extraction_no_edit_whitespace_reason_falls_back():
    ops, no_edit, reason = parse_extraction('{"no_edit": true, "reason": "   "}')
    assert ops == [] and no_edit is True and reason == "no edit proposed"
