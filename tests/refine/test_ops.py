from alpha.refine.ops import PASS_ORDER, PASS_TOOLS, RefineOp, parse_ops


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
