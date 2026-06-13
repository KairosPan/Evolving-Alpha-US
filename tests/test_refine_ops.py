# tests/test_refine_ops.py
from youzi.refine.ops import RefineOp, PASS_TOOLS, parse_ops


def test_pass_tools_whitelist():
    assert PASS_TOOLS["p"] == frozenset({"rewrite_doctrine"})
    assert PASS_TOOLS["G"] == frozenset()
    assert "write_skill" in PASS_TOOLS["K"] and "promote_skill" in PASS_TOOLS["K"]
    assert PASS_TOOLS["M"] == frozenset({"process_memory", "update_memory", "demote_memory"})


def test_parse_ops_happy():
    raw = '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "a"}, "rationale": "胜率高"}]}'
    ops = parse_ops(raw)
    assert len(ops) == 1
    assert ops[0].tool == "promote_skill"
    assert ops[0].args == {"skill_id": "a"}
    assert ops[0].rationale == "胜率高"


def test_parse_ops_defaults_and_skips_malformed():
    raw = ('{"ops": ['
           '{"tool": "promote_skill"},'              # 无 args/rationale → 默认 {} / ""
           '{"args": {"x": 1}},'                     # 无 tool → 跳过
           '"不是对象",'                              # 非 dict → 跳过
           '{"tool": "patch_skill", "args": "坏"}'   # args 非 dict → 跳过
           ']}')
    ops = parse_ops(raw)
    assert len(ops) == 1
    assert ops[0].tool == "promote_skill" and ops[0].args == {} and ops[0].rationale == ""


def test_parse_ops_with_prose_prefix():
    raw = '复盘结论:\n{"ops": [{"tool": "demote_memory", "args": {"lesson_id": "l1", "factor": 0.5}, "rationale": "过时"}]}'
    ops = parse_ops(raw)
    assert len(ops) == 1 and ops[0].tool == "demote_memory"


def test_parse_ops_garbage_returns_empty():
    assert parse_ops("毫无 JSON") == []
    assert parse_ops('{"no_ops_key": 1}') == []
    assert parse_ops('{"ops": "不是列表"}') == []
