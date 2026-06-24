from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.client import MockLLMClient


def test_chat_message_fields():
    m = ChatMessage(role="user", text="hi")
    assert m.role == "user" and m.text == "hi"
    assert ChatMessage(role="assistant").text == ""


def test_mock_chat_replays_and_records():
    m = MockLLMClient(['{"a": 1}', "second"])
    msgs = [ChatMessage(role="user", text="u1")]
    assert m.chat("sys", msgs) == '{"a": 1}'
    assert m.chat("sys2", msgs) == "second"
    assert m.chat("sys3", msgs) == "second"            # past end -> last repeats
    assert isinstance(m, ChatLLMClient)                # satisfies runtime-checkable protocol
    assert m.chat_calls[0] == ("sys", msgs) and len(m.chat_calls) == 3
