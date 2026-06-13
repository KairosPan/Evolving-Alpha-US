# tests/test_deepseek_retry.py
import types
import pytest
from youzi.llm.client import DeepSeekClient


class _FakeCreate:
    def __init__(self, fails, content):
        self.calls = 0
        self.fails = fails
        self.content = content

    def __call__(self, **kw):
        self.calls += 1
        if self.calls <= self.fails:
            raise RuntimeError("boom")
        msg = types.SimpleNamespace(content=self.content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def _client_with_fake(fails, content='{"ok": 1}', max_retries=3):
    sleeps = []
    c = DeepSeekClient(api_key="test", max_retries=max_retries, backoff=1.0,
                       sleep=lambda d: sleeps.append(d))
    fake = _FakeCreate(fails, content)
    c._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=fake)))
    return c, fake, sleeps


def test_retry_then_success():
    c, fake, sleeps = _client_with_fake(fails=2)
    assert c.complete("s", "u") == '{"ok": 1}'
    assert fake.calls == 3
    assert sleeps == [1.0, 2.0]          # backoff*2**0, *2**1


def test_retry_exhausted_raises():
    c, fake, sleeps = _client_with_fake(fails=10, max_retries=3)
    with pytest.raises(RuntimeError):
        c.complete("s", "u")
    assert fake.calls == 4               # 1 + 3 retries
    assert sleeps == [1.0, 2.0, 4.0]


def test_success_first_try_no_sleep():
    c, fake, sleeps = _client_with_fake(fails=0)
    assert c.complete("s", "u") == '{"ok": 1}'
    assert fake.calls == 1
    assert sleeps == []
