import asyncio

import pytest

pytest.importorskip("claude_agent_sdk", reason="install: pip install claude-agent-sdk")

from claude_agent_sdk.types import ResultMessage

from alpha.llm.chat import ChatMessage
from alpha.llm.claude_sdk import ClaudeSdkClient


def _result_msg(result="{\"ok\": 1}", usage=None, is_error=False, subtype="success"):
    return ResultMessage(subtype=subtype, duration_ms=10, duration_api_ms=8,
                         is_error=is_error, num_turns=1, session_id="s1",
                         usage=usage, result=result)


class _FakeQuery:
    """Records (prompt, options) per call and replays a scripted message stream; fails the first
    `fail_n` calls to exercise retry/backoff. Mirrors claude_agent_sdk.query's keyword-only shape."""

    def __init__(self, messages=None, fail_n=0):
        self._messages = messages if messages is not None else [_result_msg()]
        self._fail_n = fail_n
        self.calls: list[tuple[str, object]] = []

    def __call__(self, *, prompt, options):
        self.calls.append((prompt, options))
        if len(self.calls) <= self._fail_n:
            raise RuntimeError("spawn failed")

        async def _gen():
            for m in self._messages:
                yield m
        return _gen()


def _client(fake, sleeps=None, **kw):
    return ClaudeSdkClient(model="claude-fable-5", backoff=0.0,
                           sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
                           query_fn=fake, **kw)


def test_returns_result_text():
    assert _client(_FakeQuery()).complete("s", "u") == '{"ok": 1}'


def test_options_pin_the_neutral_surface():
    # The SDK's whole point here: no filesystem settings, no tools, one turn.
    f = _FakeQuery()
    _client(f).complete("SYS", "the user prompt")
    prompt, opts = f.calls[0]
    assert prompt == "the user prompt"
    assert opts.system_prompt == "SYS"
    assert opts.model == "claude-fable-5"
    assert opts.tools == []                  # all built-in tools disabled
    assert opts.max_turns == 1               # pure completion, no agent loop
    assert opts.setting_sources is None      # loads NO CLAUDE.md / settings (SDK default, pinned)


def test_empty_system_prompt_maps_to_none():
    f = _FakeQuery()
    _client(f).complete("", "u")
    assert f.calls[0][1].system_prompt is None


def test_captures_usage_with_cache_folded_into_input():
    from alpha.llm.metering import Usage
    c = _client(_FakeQuery([_result_msg(usage={
        "input_tokens": 20, "output_tokens": 8,
        "cache_read_input_tokens": 100, "cache_creation_input_tokens": 5})]))
    c.complete("s", "u")
    assert c.last_usage == Usage(tokens_in=125, tokens_out=8)


def test_last_usage_none_when_usage_missing():
    c = _client(_FakeQuery([_result_msg(usage=None)]))
    c.complete("s", "u")
    assert c.last_usage is None


def test_retries_then_succeeds():
    f = _FakeQuery(fail_n=2)
    sleeps: list = []
    assert _client(f, sleeps).complete("s", "u") == '{"ok": 1}'
    assert len(f.calls) == 3 and len(sleeps) == 2


def test_raises_after_exhaustion():
    with pytest.raises(RuntimeError):
        _client(_FakeQuery(fail_n=99)).complete("s", "u")


def test_is_error_result_raises():
    # ResultMessage.is_error is typed — an error envelope must never flow downstream as a reply.
    with pytest.raises(RuntimeError, match="error"):
        _client(_FakeQuery([_result_msg(result="rate limited", is_error=True,
                                        subtype="error_during_execution")])).complete("s", "u")


def test_missing_result_message_raises():
    class _Empty:
        def __call__(self, *, prompt, options):
            async def _gen():
                return
                yield  # pragma: no cover
            return _gen()
    with pytest.raises(RuntimeError, match="no ResultMessage"):
        _client(_Empty()).complete("s", "u")


def test_timeout_cancels_a_hung_query():
    class _Hang:
        def __call__(self, *, prompt, options):
            async def _gen():
                await asyncio.sleep(30)
                yield _result_msg()
            return _gen()
    with pytest.raises(Exception):          # TimeoutError surfaces after retry exhaustion
        ClaudeSdkClient(model="claude-fable-5", query_fn=_Hang(), timeout=0.05,
                        max_retries=0, backoff=0.0, sleep=lambda _s: None).complete("s", "u")


def test_chat_flattens_history_into_one_prompt():
    f = _FakeQuery([_result_msg("the reply")])
    out = _client(f).chat("SYS", [ChatMessage(role="user", text="hello"),
                                  ChatMessage(role="assistant", text="hi"),
                                  ChatMessage(role="user", text="more")])
    assert out == "the reply"
    prompt, opts = f.calls[0]
    assert prompt == "User: hello\n\nAssistant: hi\n\nUser: more"
    assert opts.system_prompt == "SYS"


def test_exposes_model_and_temperature():
    c = _client(_FakeQuery(), )
    assert c.model == "claude-fable-5" and c.temperature == 0.0
