from __future__ import annotations

import pytest

from alpaca_kit.account import TradingAPIError, TradingClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    return TradingClient()


def test_requires_keys(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="APCA_API_KEY_ID"):
        TradingClient()


def test_defaults_to_paper_host(client):
    assert client.base_url == "https://paper-api.alpaca.markets"


def test_get_account_hits_v2_account(client, monkeypatch):
    calls = []
    monkeypatch.setattr(client, "_request",
                        lambda method, path, **kw: calls.append((method, path)) or {"cash": "100"})
    assert client.get_account() == {"cash": "100"}
    assert calls == [("GET", "/v2/account")]


def test_get_orders_passes_status(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(client, "_request",
                        lambda method, path, params=None, **kw: seen.update(params or {}) or [])
    client.get_orders(status="open")
    assert seen["status"] == "open"


def test_place_order_posts_v2_orders(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(client, "_request",
                        lambda method, path, body=None, **kw: captured.update(
                            {"method": method, "path": path, **(body or {})}) or {"id": "1"})
    client.place_order("AAPL", 1, "buy")
    assert captured["method"] == "POST" and captured["path"] == "/v2/orders"
    assert captured["symbol"] == "AAPL" and captured["side"] == "buy"


def test_place_order_refuses_non_paper_host(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    c = TradingClient()
    with pytest.raises(RuntimeError, match="paper"):
        c.place_order("AAPL", 1, "buy")
