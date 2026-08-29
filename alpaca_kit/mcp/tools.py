"""The MCP toolset, SDK-free and fully offline-testable.

Registration rules (spec section 4/5): keyless EDGAR always; market tools behind APCA keys
or an offline PIT root; account queries behind keys; order tools behind keys AND the
operator-only ALPACA_KIT_ENABLE_ORDERS flag (set in the dsh profile, outside the agent's
workspace). Every tool body is fail-soft: exceptions return ok=False with an actionable
message, never raise into the harness.

PIT: every dated call wraps the RAW source in GuardedSource(AsOfGuard(as_of)) - the tool
layer is the guard-wrapping caller the data-layer contract demands.
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from datetime import date as Date

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.source import GuardedSource

MAX_ROWS = 2000

READ_ONLY_TOOLS = frozenset({
    "daily_bars", "market_snapshot", "calendar", "corp_actions",
    "screen", "breadth", "earnings", "account", "positions", "orders",
})


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: object  # callable(**kwargs) -> dict


def _soft(fn):
    @functools.wraps(fn)
    def inner(**kw):
        try:
            return fn(**kw)
        except Exception as e:  # fail-soft by contract: the loop never sees a raise
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return inner


def _d(s: str) -> Date:
    return Date.fromisoformat(s)


def _frame(df) -> dict:
    rows = df.to_dict(orient="records")
    out = {"ok": True, "rows": rows[:MAX_ROWS]}
    if len(rows) > MAX_ROWS:
        out["truncated"] = f"{len(rows)} rows, first {MAX_ROWS} shown"
    return out


def _guarded(source_factory, as_of: Date) -> GuardedSource:
    return GuardedSource(source_factory(), AsOfGuard(as_of))


def build_tools(env=None, *, source_factory=None, trading_factory=None,
                edgar_factory=None) -> dict[str, Tool]:
    env = os.environ if env is None else env
    has_keys = bool(env.get("APCA_API_KEY_ID")) and bool(env.get("APCA_API_SECRET_KEY"))
    pit_root = env.get("ALPHA_PIT_ROOT")
    orders_on = env.get("ALPACA_KIT_ENABLE_ORDERS") == "1"

    if source_factory is None:
        from alpaca_kit.registry import make_source
        if has_keys:
            source_factory = lambda: make_source("alpaca")            # noqa: E731
        elif pit_root:
            source_factory = lambda: make_source("snapshot", pit_root=pit_root)  # noqa: E731
    if edgar_factory is None:
        from alpaca_kit.feeds.edgar import EdgarSource
        edgar_factory = EdgarSource
    if trading_factory is None and has_keys:
        from alpaca_kit.account import TradingClient
        trading_factory = TradingClient

    tools: dict[str, Tool] = {}

    def add(name: str, description: str, fn) -> None:
        tools[name] = Tool(name=name, description=description, fn=_soft(fn))

    # ---- always: keyless EDGAR ------------------------------------------------
    def earnings(symbol: str, as_of: str | None = None):
        src = edgar_factory()
        facts = src.earnings_known(symbol, _d(as_of) if as_of else Date.today())
        return {"ok": True, "rows": [f.model_dump(mode="json") for f in facts][:MAX_ROWS]}
    add("earnings", "EDGAR XBRL earnings facts for a symbol, PIT-filtered by filing date", earnings)

    # ---- market (keys or offline pit root) -------------------------------------
    if source_factory is not None:
        def daily_bars(symbol: str, start: str, end: str, as_of: str | None = None):
            g = _guarded(source_factory, _d(as_of) if as_of else Date.today())
            return _frame(g.daily_bars(symbol, _d(start), _d(end)))
        add("daily_bars", "RAW unadjusted daily bars for a symbol", daily_bars)

        def market_snapshot(date: str | None = None, as_of: str | None = None):
            day = _d(date) if date else Date.today()
            g = _guarded(source_factory, _d(as_of) if as_of else day)
            return _frame(g.daily_snapshot(day))
        add("market_snapshot", "full-market daily cross-section for a date", market_snapshot)

        def calendar(start: str, end: str):
            cal = source_factory().trading_calendar()
            return {"ok": True, "days": [d.isoformat() for d in cal
                                         if _d(start) <= d <= _d(end)]}
        add("calendar", "trading days in a date range", calendar)

        def corp_actions(as_of: str | None = None):
            day = _d(as_of) if as_of else Date.today()
            g = _guarded(source_factory, day)
            return _frame(g.corporate_actions_known(day))
        add("corp_actions", "corporate actions known as of a date (announce-date keyed)", corp_actions)

        def screen(date: str, kind: str = "gainer", as_of: str | None = None):
            from alpaca_kit.universe import build_trend_template_universe, build_universe
            day = _d(date)
            g = _guarded(source_factory, _d(as_of) if as_of else day)
            uni = (build_trend_template_universe(g, day) if kind == "trend_template"
                   else build_universe(g, day))
            # CandidateUniverse indexes StockSnapshots by symbol; .all() is its list accessor.
            return {"ok": True, "rows": [s.model_dump(mode="json") for s in uni.all()][:MAX_ROWS]}
        add("screen", "daily screen: kind=gainer or trend_template", screen)

    # ---- breadth (offline bed only: bars must be local) -------------------------
    if pit_root:
        def breadth(date: str):
            from alpaca_kit.features.breadth import market_breadth
            from alpaca_kit.pit.pit_store import PITStore
            from alpaca_kit.pit.snapshot_source import SnapshotSource
            day = _d(date)
            store = PITStore(pit_root)
            src = SnapshotSource(store)
            snap = GuardedSource(src, AsOfGuard(day)).daily_snapshot(day)
            bars = {sym: src.daily_bars(sym, Date(1990, 1, 1), day)
                    for sym in snap["symbol"].tolist()}
            reading = market_breadth(bars, day)
            return {"ok": True, **reading.model_dump(mode="json")}
        add("breadth", "market breadth for a date (offline PIT bed)", breadth)

    # ---- account (keys) ---------------------------------------------------------
    if trading_factory is not None:
        # `or {}` guards the empty-200-body case: TradingClient._request json-decodes an empty
        # body to None, and `**None` would TypeError inside the tool.
        add("account", "paper account summary",
            lambda: {"ok": True, **(trading_factory().get_account() or {})})
        add("positions", "open positions", lambda: {"ok": True, "rows": trading_factory().get_positions()})

        def orders(status: str | None = None):
            return {"ok": True, "rows": trading_factory().get_orders(status=status)}
        add("orders", "order list; Alpaca returns the 50 most recent OPEN orders by default - "
                      "pass status=closed or status=all for others", orders)

        # ---- reserved: operator gate (spec section 5, Gate 1) -------------------
        if orders_on:
            def place_order(symbol: str, qty: float, side: str, order_type: str = "market",
                            limit_price: float | None = None):
                return {"ok": True, **(trading_factory().place_order(
                    symbol, qty, side, order_type=order_type, limit_price=limit_price) or {})}
            add("place_order", "submit a PAPER order (operator-gated)", place_order)

            def cancel_order(order_id: str):
                return {"ok": True, **(trading_factory().cancel_order(order_id) or {})}
            add("cancel_order", "cancel a paper order by id (operator-gated)", cancel_order)

    return tools
