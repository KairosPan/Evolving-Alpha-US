from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest

from alpaca_kit.account import TradingAPIError, TradingClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    monkeypatch.delenv("APCA_API_BASE_URL", raising=False)   # never inherit the operator's host
    return TradingClient()


class _FakeResp:
    """Minimal urlopen() context-manager stand-in."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *exc) -> bool:
        return False


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
    # hermetic: if the pin ever stops firing this fails on the assertion, never on a live socket.
    monkeypatch.setattr(c, "_request",
                        lambda *a, **k: pytest.fail("transport reached - the paper pin did not fire"))
    with pytest.raises(RuntimeError, match="paper"):
        c.place_order("AAPL", 1, "buy")


def test_cancel_order_refuses_non_paper_host(monkeypatch):
    # C1: cancelling a live protective leg is as harmful as placing one -> same pin, same shape.
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    c = TradingClient()
    monkeypatch.setattr(c, "_request",
                        lambda *a, **k: pytest.fail("transport reached - the paper pin did not fire"))
    with pytest.raises(RuntimeError, match="paper"):
        c.cancel_order("order-1")


def test_cancel_order_deletes_the_order_path(client, monkeypatch):
    calls = []
    monkeypatch.setattr(client, "_request",
                        lambda method, path, **kw: calls.append((method, path)) or None)
    assert client.cancel_order("abc") == {"status": "canceled"}   # 204/empty body fallback
    assert calls == [("DELETE", "/v2/orders/abc")]


def test_request_get_positions_empty_body_returns_empty_list(client, monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        return _FakeResp(b"")                                    # 200 with no body

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert client.get_positions() == []
    assert seen["url"] == "https://paper-api.alpaca.markets/v2/positions"
    assert seen["method"] == "GET"


def test_request_401_is_actionable_and_keeps_the_body(client, monkeypatch):
    def boom(*a, **k):
        raise urllib.error.HTTPError("https://paper-api.alpaca.markets/v2/account", 401,
                                     "Unauthorized", {}, io.BytesIO(b'{"message":"forbidden"}'))

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(TradingAPIError) as ei:
        client.get_account()
    msg = str(ei.value)
    assert "401" in msg and "/v2/account" in msg
    assert "APCA_API_KEY_ID" in msg                               # the actionable hint
    assert "forbidden" in msg                                     # I4: response body survives


def test_request_422_body_survives(client, monkeypatch):
    # the module's real failure mode: DELETE /v2/orders/{id} -> 422 "order status is not cancelable"
    def boom(*a, **k):
        raise urllib.error.HTTPError("https://paper-api.alpaca.markets/v2/orders/abc", 422,
                                     "Unprocessable", {},
                                     io.BytesIO(b'{"message":"order status is not cancelable"}'))

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(TradingAPIError, match="not cancelable"):
        client.cancel_order("abc")


def test_request_network_error_is_actionable(client, monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(TradingAPIError, match="network"):
        client.get_account()
