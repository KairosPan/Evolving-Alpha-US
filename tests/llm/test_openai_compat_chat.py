from alpha.llm.chat import ChatMessage
from alpha.llm.openai_compat import OpenAICompatClient


class _Msg:
    def __init__(self, content): self.content = content


class _Choice:
    def __init__(self, content): self.message = _Msg(content)


class _Resp:
    def __init__(self, content): self.choices = [_Choice(content)]


class _FakeCompletions:
    def __init__(self): self.calls = []
    def create(self, **kw):
        self.calls.append(kw)
        return _Resp("the reply")


class _FakeChat:
    def __init__(self): self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self): self.chat = _FakeChat()


def test_chat_maps_messages_and_omits_json_object():
    c = OpenAICompatClient(model="deepseek-v4-pro", api_key="x")
    c._client = _FakeClient()
    out = c.chat("SYS", [ChatMessage(role="user", text="hello"),
                         ChatMessage(role="assistant", text="hi"),
                         ChatMessage(role="user", text="more")])
    assert out == "the reply"
    sent = c._client.chat.completions.calls[0]
    assert sent["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "more"},
    ]
    assert "response_format" not in sent          # prose+JSON reply, not forced JSON
    assert sent["model"] == "deepseek-v4-pro"


def test_chat_retries_then_raises(monkeypatch):
    c = OpenAICompatClient(api_key="x", max_retries=1, sleep=lambda _s: None)
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                def create(**kw): raise RuntimeError("boom")
    c._client = _Boom()
    import pytest
    with pytest.raises(RuntimeError):
        c.chat("s", [ChatMessage(role="user", text="x")])
