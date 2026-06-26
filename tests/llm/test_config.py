import pytest
from alpha.llm.client import MockLLMClient
from alpha.llm.config import make_client


def test_mock_provider(monkeypatch):
    monkeypatch.setenv("ALPHA_AGENT_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"no_trade_reason": "mock"}')
    c = make_client("agent")
    assert isinstance(c, MockLLMClient)
    assert c.complete("s", "u") == '{"no_trade_reason": "mock"}'


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        make_client("refiner")


def test_provider_selects_class_without_keys(monkeypatch):
    # provider=mock for both roles -> offline-safe; assert role-scoped env is read
    monkeypatch.setenv("ALPHA_AGENT_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    assert isinstance(make_client("agent"), MockLLMClient)
    assert isinstance(make_client("refiner"), MockLLMClient)


def test_bad_role_raises():
    with pytest.raises(ValueError):
        make_client("nonsense")


def test_converse_role_resolves(monkeypatch):
    monkeypatch.setenv("ALPHA_CONVERSE_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "{}")
    assert isinstance(make_client("converse"), MockLLMClient)
