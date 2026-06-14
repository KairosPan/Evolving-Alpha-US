import pytest
from alpha.llm.client import LLMClient, MockLLMClient
from alpha.llm.extract import extract_json_object


def test_mock_records_and_replays():
    m = MockLLMClient(['{"a": 1}', '{"b": 2}'])
    assert m.complete("sys1", "usr1") == '{"a": 1}'
    assert m.complete("sys2", "usr2") == '{"b": 2}'
    assert m.complete("sys3", "usr3") == '{"b": 2}'           # past the end -> last response repeats
    assert m.calls == [("sys1", "usr1"), ("sys2", "usr2"), ("sys3", "usr3")]
    assert isinstance(m, LLMClient)                            # satisfies the runtime-checkable protocol


def test_mock_empty_rejected():
    with pytest.raises(ValueError):
        MockLLMClient([])


def test_extract_json_object():
    assert extract_json_object('prose {"x": 1} tail') == '{"x": 1}'
    assert extract_json_object('```json\n{"x": {"y": 2}}\n```') == '{"x": {"y": 2}}'
    assert extract_json_object('a string with } brace then {"ok": "}"}') == '{"ok": "}"}'
    assert extract_json_object("no json here") is None
