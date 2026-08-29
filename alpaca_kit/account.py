"""Alpaca TRADING-host client (paper account): /v2/account, /v2/positions, /v2/orders.

Same seam pattern as alpaca_kit.alpaca._get_json: stdlib urllib, offline-testable by
monkeypatching _request, actionable error hints. BOTH mutating methods - place_order and
cancel_order - are code-level pinned to the paper host: a non-paper base URL refuses to
mutate at all (the reset's safety line).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

PAPER_HOSTNAME = "paper-api.alpaca.markets"
PAPER_HOST = f"https://{PAPER_HOSTNAME}"
_HINTS = {
    401: "check APCA_API_KEY_ID / APCA_API_SECRET_KEY (source .env.alpaca first)",
    403: "endpoint not entitled for these keys",
    422: "order is no longer cancelable / the order request was rejected",
    429: "rate limited - back off and retry",
}


class TradingAPIError(RuntimeError):
    """Trading API returned an error status; message carries an actionable hint."""


class TradingClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("APCA_API_BASE_URL") or PAPER_HOST).rstrip("/")
        key = os.environ.get("APCA_API_KEY_ID")
        secret = os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("APCA_API_KEY_ID / APCA_API_SECRET_KEY not set (source .env.alpaca first)")
        self._headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                         "Content-Type": "application/json"}

    # -- transport seam (monkeypatched in tests) --------------------------------
    def _request(self, method: str, path: str, params: dict | None = None,
                 body: dict | None = None, timeout: int = 30):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as e:
            try:                                          # the body carries Alpaca's real reason
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                body = ""
            hint = _HINTS.get(e.code, "")
            msg = f"{method} {path} -> HTTP {e.code}. {hint}".strip()
            raise TradingAPIError(f"{msg} Response: {body}" if body else msg) from e
        except urllib.error.URLError as e:
            raise TradingAPIError(f"{method} {path} -> network error: {e.reason}") from e

    # -- read-only ---------------------------------------------------------------
    def get_account(self) -> dict:
        return self._request("GET", "/v2/account")

    def get_positions(self) -> list[dict]:
        return self._request("GET", "/v2/positions") or []

    def get_orders(self, status: str | None = None) -> list[dict]:
        return self._request("GET", "/v2/orders", params={"status": status}) or []

    # -- mutating (registered as MCP tools only behind the operator gate) --------
    def _require_paper(self, action: str) -> None:
        """The reset's safety line: no mutation may leave this process for a live account.

        Compares the parsed HOSTNAME, never a substring. A substring test is defeated by URL
        userinfo: "https://paper-api.alpaca.markets@api.alpaca.markets" contains "paper-api",
        but urllib resolves the host to api.alpaca.markets - a LIVE order with the APCA headers
        attached. Anything urlsplit cannot read a hostname out of (no scheme, junk) is refused
        too: the pin fails closed.
        """
        if urllib.parse.urlsplit(self.base_url).hostname != PAPER_HOSTNAME:
            raise RuntimeError(f"refusing to {action} against non-paper host {self.base_url}")

    def place_order(self, symbol: str, qty: float, side: str, order_type: str = "market",
                    time_in_force: str = "day", limit_price: float | None = None) -> dict:
        self._require_paper("place an order")
        body = {"symbol": symbol, "qty": str(qty), "side": side, "type": order_type,
                "time_in_force": time_in_force}
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        return self._request("POST", "/v2/orders", body=body)

    def cancel_order(self, order_id: str) -> dict:
        self._require_paper("cancel an order")
        return self._request("DELETE", f"/v2/orders/{order_id}") or {"status": "canceled"}
