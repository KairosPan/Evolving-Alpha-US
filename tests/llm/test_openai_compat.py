import pytest
from alpha.llm.openai_compat import OpenAICompatClient


class _FakeResp:
    def __init__(self, text, usage=None):
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]
        self.usage = usage


class _Usage:
    def __init__(self, pt, ct): self.prompt_tokens, self.completion_tokens = pt, ct


class _FakeChat:
    """Fails `fail_n` times then returns the text (exercises retry/backoff)."""
    def __init__(self, text, fail_n=0, usage=None):
        self._text, self._fail_n, self.calls, self._usage = text, fail_n, 0, usage
        self.chat = type("X", (), {"completions": self})()
    def create(self, **kw):
        self.calls += 1
        if self.calls <= self._fail_n:
            raise RuntimeError("transient 503")
        return _FakeResp(self._text, usage=self._usage)


def _client(fake, sleeps):
    c = OpenAICompatClient(model="deepseek-chat", api_key="test", backoff=0.0,
                           sleep=lambda s: sleeps.append(s))
    c._client = fake                       # inject transport (no network)
    return c


def test_returns_content():
    fake = _FakeChat('{"ok": 1}')
    assert _client(fake, []).complete("s", "u") == '{"ok": 1}'


def test_captures_provider_usage_when_present():
    from alpha.llm.metering import Usage
    c = _client(_FakeChat('{"ok": 1}', usage=_Usage(11, 7)), [])
    assert c.complete("s", "u") == '{"ok": 1}'
    assert c.last_usage == Usage(tokens_in=11, tokens_out=7)


def test_last_usage_none_when_provider_omits_usage():
    fake = _FakeChat('{"ok": 1}')                        # _FakeResp default usage=None
    c = _client(fake, [])
    c.complete("s", "u")
    assert c.last_usage is None                           # graceful: no usage -> None (wrapper estimates)


def test_retries_then_succeeds():
    fake = _FakeChat('{"ok": 1}', fail_n=2)
    sleeps = []
    assert _client(fake, sleeps).complete("s", "u") == '{"ok": 1}'
    assert fake.calls == 3 and len(sleeps) == 2          # 2 retries before success


def test_raises_after_exhaustion():
    fake = _FakeChat('{"ok": 1}', fail_n=99)
    with pytest.raises(RuntimeError):
        _client(fake, []).complete("s", "u")


def test_exposes_model_and_temperature_for_cache_key():
    c = OpenAICompatClient(model="deepseek-chat", api_key="test", temperature=0.0)
    assert c.model == "deepseek-chat" and c.temperature == 0.0


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)   # session-safe; pytest auto-restores
    with pytest.raises(RuntimeError):
        OpenAICompatClient(model="deepseek-chat", api_key=None, api_key_env="DEEPSEEK_API_KEY")
