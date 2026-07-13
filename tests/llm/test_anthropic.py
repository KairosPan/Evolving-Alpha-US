import pytest
from alpha.llm.anthropic import ClaudeClient


class _Block:
    def __init__(self, text): self.text = text


class _Msg:
    def __init__(self, text, usage=None): self.content, self.usage = [_Block(text)], usage


class _Usage:
    def __init__(self, it, ot): self.input_tokens, self.output_tokens = it, ot


class _FakeMessages:
    def __init__(self, text, fail_n=0, usage=None):
        self._text, self._fail_n, self.calls, self._usage = text, fail_n, 0, usage
        self.messages = self
    def create(self, **kw):
        self.calls += 1
        if self.calls <= self._fail_n:
            raise RuntimeError("overloaded")
        return _Msg(self._text, usage=self._usage)


def _client(fake, sleeps):
    c = ClaudeClient(model="claude-sonnet-4-6", api_key="test", backoff=0.0,
                     sleep=lambda s: sleeps.append(s))
    c._client = fake
    return c


def test_returns_text():
    assert _client(_FakeMessages('{"ok": 1}'), []).complete("s", "u") == '{"ok": 1}'


def test_captures_provider_usage_when_present():
    from alpha.llm.metering import Usage
    c = _client(_FakeMessages('{"ok": 1}', usage=_Usage(21, 8)), [])
    assert c.complete("s", "u") == '{"ok": 1}'
    assert c.last_usage == Usage(tokens_in=21, tokens_out=8)


def test_last_usage_none_when_provider_omits_usage():
    c = _client(_FakeMessages('{"ok": 1}'), [])          # default usage=None
    c.complete("s", "u")
    assert c.last_usage is None


def test_retries_then_succeeds():
    fake = _FakeMessages('{"ok": 1}', fail_n=2)
    sleeps = []
    assert _client(fake, sleeps).complete("s", "u") == '{"ok": 1}'
    assert fake.calls == 3 and len(sleeps) == 2


def test_raises_after_exhaustion():
    with pytest.raises(RuntimeError):
        _client(_FakeMessages('{"ok": 1}', fail_n=99), []).complete("s", "u")


def test_exposes_model_and_temperature():
    c = ClaudeClient(model="claude-sonnet-4-6", api_key="test", temperature=0.0)
    assert c.model == "claude-sonnet-4-6" and c.temperature == 0.0
