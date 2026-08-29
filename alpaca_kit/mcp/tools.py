"""The MCP toolset, SDK-free and fully offline-testable.

Registration rules (spec section 4/5, as amended by the Task 6 review): keyless EDGAR always;
key-or-bed market tools (daily_bars, calendar, corp_actions) behind APCA keys OR an offline PIT
root; snapshot-backed tools (market_snapshot, screen, breadth) behind ALPHA_PIT_ROOT alone, since
AlpacaSource.daily_snapshot raises NotImplementedError and a daily cross-section exists only on a
captured bed; account queries behind keys; order tools behind keys AND the operator-only
ALPACA_KIT_ENABLE_ORDERS flag (set in the dsh profile, outside the agent's workspace). Every tool
body is fail-soft: exceptions return ok=False with an actionable message, never raise into the
harness.

PIT: every dated market call wraps the RAW source in GuardedSource(AsOfGuard(as_of)) - the tool
layer is the guard-wrapping caller the data-layer contract demands - and as_of defaults to TODAY,
never to the requested date, because a cursor set to the request is a tautology that guards
nothing. `earnings` is the deliberate exception: EdgarSource.earnings_known filters on
filing_date <= as_of itself, so a wrap would only check as_of against as_of.

Every frame leaves through _frame, which is JSON-safe by construction: dates become ISO strings
and NaN/NaT become null (a bare NaN is invalid JSON per RFC 8259 and strict parsers reject it).
"""
from __future__ import annotations

import functools
import math
import os
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime as DateTime

import pandas as pd

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


def _jsonable(v):
    """One cell -> a JSON-encodable value. date/datetime -> ISO string; NaN/NaT/None -> None."""
    if isinstance(v, float):                 # numpy float64 subclasses float
        return v if math.isfinite(v) else None   # bare NaN/Infinity is invalid JSON (RFC 8259)
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, (DateTime, Date)):      # datetime / pd.Timestamp are date subclasses
        return v.isoformat()
    return v


def _frame(df) -> dict:
    rows = [{k: _jsonable(v) for k, v in rec.items()} for rec in df.to_dict(orient="records")]
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

    def _bed_source():
        """The captured-bed source. Its daily_snapshot is the only working one (AlpacaSource
        raises NotImplementedError), so it backs the snapshot tools even when keys are present."""
        from alpaca_kit.registry import make_source
        return make_source("snapshot", pit_root=pit_root)

    injected_source = source_factory is not None
    if not injected_source:
        if has_keys:
            from alpaca_kit.registry import make_source
            source_factory = lambda: make_source("alpaca")            # noqa: E731
        elif pit_root:
            source_factory = _bed_source
    # market_snapshot/screen read a CAPTURED bed, never live Alpaca: gate them on ALPHA_PIT_ROOT
    # alone. An injected factory SUPPLIES the source but never OPENS the gate, so registration
    # stays a pure function of `env` (the same posture the order gate takes).
    snapshot_factory = source_factory if injected_source else _bed_source

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

        def calendar(start: str, end: str):
            cal = source_factory().trading_calendar()
            return {"ok": True, "days": [d.isoformat() for d in cal
                                         if _d(start) <= d <= _d(end)]}
        add("calendar", "trading days in a date range", calendar)

        def corp_actions(symbol: str | None = None, as_of: str | None = None):
            day = _d(as_of) if as_of else Date.today()
            g = _guarded(source_factory, day)
            if not g.corp_actions_available():
                # Never collapse MISSING into checked-and-clean: an empty ok=True here would tell
                # the agent "no split/delisting pending" when the truth is "could not check".
                return {"ok": False, "error": "corp actions artifact missing - could not check"}
            df = g.corporate_actions_known(day)
            if symbol is not None and not df.empty:
                df = df[df["symbol"] == symbol]
            if "announce_date" in df.columns:
                df = df.sort_values("announce_date", ascending=False)   # newest-first BEFORE the cap
            return _frame(df)
        add("corp_actions", "corporate actions known as of a date (announce-date keyed), newest "
                            "first; optionally filtered to one symbol", corp_actions)

    # ---- snapshot-backed: captured PIT bed only (a live cross-section does not exist) ----------
    if pit_root:
        def market_snapshot(date: str | None = None, as_of: str | None = None):
            today = Date.today()
            # Spec section 4: the DEFAULT is the latest trading day, not today. Today is not a
            # trading day every weekend and holiday, and a captured bed's calendar can end long
            # before today - both cases used to fail soft with SnapshotMissingError on a bare
            # call. The as_of cursor below still defaults to today, never to the resolved day.
            if date:
                day = _d(date)
            else:
                past = [d for d in snapshot_factory().trading_calendar() if d <= today]
                if not past:
                    return {"ok": False,
                            "error": "no trading day on or before today in the bed's calendar"}
                day = max(past)
            g = _guarded(snapshot_factory, _d(as_of) if as_of else today)
            return _frame(g.daily_snapshot(day))
        add("market_snapshot", "full-market daily cross-section for a date (offline PIT bed); "
                               "date defaults to the latest trading day at or before today",
            market_snapshot)

        def screen(date: str, kind: str = "gainer", as_of: str | None = None):
            from alpaca_kit.universe import build_universe
            day = _d(date)
            g = _guarded(snapshot_factory, _d(as_of) if as_of else Date.today())
            # screen=kind routes through the universe module's own resolver, so an explicit kind
            # beats ambient ALPHA_UNIVERSE_SCREEN and an unknown kind raises -> ok=False.
            uni = build_universe(g, day, screen=kind)
            # CandidateUniverse indexes StockSnapshots by symbol; .all() is its list accessor.
            return {"ok": True, "rows": [s.model_dump(mode="json") for s in uni.all()][:MAX_ROWS]}
        add("screen", "daily screen (offline PIT bed): kind=gainer or trend_template", screen)

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

    # ---- reserved: operator gate (spec section 5, Gate 1) -----------------------
    # Gated on has_keys, NOT on trading_factory: an injected factory must never be able to
    # register the mutating tools for a keyless process.
    if orders_on and has_keys:
        def place_order(symbol: str, qty: float, side: str, order_type: str = "market",
                        limit_price: float | None = None):
            return {"ok": True, **(trading_factory().place_order(
                symbol, qty, side, order_type=order_type, limit_price=limit_price) or {})}
        add("place_order", "submit a PAPER order (operator-gated)", place_order)

        def cancel_order(order_id: str):
            return {"ok": True, **(trading_factory().cancel_order(order_id) or {})}
        add("cancel_order", "cancel a paper order by id (operator-gated)", cancel_order)

    return tools
