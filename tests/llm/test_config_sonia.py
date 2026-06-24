import pytest
from alpha.llm.client import MockLLMClient
from alpha.llm.config import make_client


def test_sonia_mock_provider(monkeypatch):
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "{}")
    assert isinstance(make_client("sonia"), MockLLMClient)


def test_sonia_defaults_to_deepseek_openai_compat(monkeypatch):
    # default provider is openai_compat -> a missing DEEPSEEK_API_KEY raises cleanly
    monkeypatch.delenv("ALPHA_SONIA_PROVIDER", raising=False)
    monkeypatch.delenv("ALPHA_SONIA_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        make_client("sonia")
