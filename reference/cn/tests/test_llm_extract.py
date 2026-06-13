# tests/test_llm_extract.py
from youzi.llm.extract import extract_json_object


def test_pure_object():
    assert extract_json_object('{"a": 1}') == '{"a": 1}'


def test_prose_prefix():
    assert extract_json_object('好的,结果如下:{"a": 1} 完毕') == '{"a": 1}'


def test_thinking_blob_prefix():
    raw = '让我想想... 也许 {不是JSON 这里} 然后\n最终答案:{"ops": [{"tool": "x"}]}'
    # 第一个 '{' 是 "{不是JSON ...}" —— 它不配平到合法 JSON,但配平扫描按括号深度截断
    out = extract_json_object(raw)
    assert out is not None and out.startswith("{") and out.endswith("}")


def test_markdown_fence():
    raw = '```json\n{"a": 1, "b": {"c": 2}}\n```'
    assert extract_json_object(raw) == '{"a": 1, "b": {"c": 2}}'


def test_nested_object():
    assert extract_json_object('{"a": {"b": {"c": 1}}}') == '{"a": {"b": {"c": 1}}}'


def test_braces_inside_string_not_counted():
    s = '{"k": "有个 } 和 { 在字符串里", "n": 1}'
    assert extract_json_object(s) == s


def test_escaped_quote_inside_string():
    s = '{"k": "他说\\"对\\"了 }", "n": 1}'
    assert extract_json_object(s) == s


def test_multiple_objects_takes_first():
    assert extract_json_object('{"a": 1}{"b": 2}') == '{"a": 1}'


def test_no_object_returns_none():
    assert extract_json_object("没有大括号") is None
    assert extract_json_object("") is None


def test_unbalanced_returns_none():
    assert extract_json_object('{"a": 1') is None
