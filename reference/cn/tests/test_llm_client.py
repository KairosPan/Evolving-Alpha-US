from youzi.llm.client import MockLLMClient


def test_mock_returns_fixed_and_records_calls():
    m = MockLLMClient('{"x":1}')
    assert m.complete("sys", "u1") == '{"x":1}'
    assert m.complete("sys", "u2") == '{"x":1}'
    assert m.calls == [("sys", "u1"), ("sys", "u2")]


def test_mock_scripted_list_repeats_last():
    m = MockLLMClient(["a", "b"])
    assert m.complete("s", "x") == "a"
    assert m.complete("s", "y") == "b"
    assert m.complete("s", "z") == "b"      # 用尽后重复最后一个


def test_mock_satisfies_llmclient_protocol():
    from youzi.llm.client import LLMClient
    m = MockLLMClient("ok")
    assert isinstance(m, LLMClient)          # runtime-checkable Protocol
