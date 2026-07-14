import pytest
from alpha.llm.client import MockLLMClient
from alpha.llm.config import make_client


def test_sonia_mock_provider(monkeypatch):
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "{}")
    assert isinstance(make_client("sonia"), MockLLMClient)


def test_sonia_defaults_to_claude_code_subscription(monkeypatch):
    # default is now claude_sdk (Fable 5 on subscription quota); construction needs no API key and
    # does not raise when the CLI is absent (it raises only on an actual call — see test_claude_code).
    monkeypatch.delenv("ALPHA_SONIA_PROVIDER", raising=False)
    monkeypatch.delenv("ALPHA_SONIA_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from alpha.llm.claude_sdk import ClaudeSdkClient
    c = make_client("sonia")
    assert isinstance(c, ClaudeSdkClient) and c.model == "claude-fable-5"


def test_sonia_openai_compat_override_still_needs_key(monkeypatch):
    # the DeepSeek path is still reachable per-role via env; a missing key raises cleanly
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "openai_compat")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        make_client("sonia")
