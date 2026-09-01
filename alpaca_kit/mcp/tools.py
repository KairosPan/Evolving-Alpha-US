"""The MCP toolset, SDK-free and fully offline-testable.

Registration rules (spec section 4/5, as amended by the Task 6 review): keyless EDGAR always;
key-or-bed market tools (daily_bars, calendar, corp_actions) behind APCA keys OR an offline PIT
root; snapshot-backed tools (market_snapshot, screen, breadth) behind ALPHA_PIT_ROOT alone, since
AlpacaSource.daily_snapshot raises NotImplementedError and a daily cross-section exists only on a
captured bed; account queries behind keys; order tools behind keys AND the operator-only
ALPACA_KIT_ENABLE_ORDERS flag (set in the dsh profile, outside the agent's workspace). Every tool
body is fail-soft: exceptions return ok=False with an actionable message, never raise into the
harness. The snapshot-walk tools (screen, breadth) disk-cache their ok=True results per
(bed, code version, day, kind) — alpaca_kit/mcp/cache.py — with the lookahead check hoisted
above the cache read and errors never cached, so the contracts above survive a hit.

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
from datetime import timezone

import pandas as pd

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.mcp import cache as screen_cache
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


def _utcnow() -> str:
    return DateTime.now(timezone.utc).isoformat()


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


def _latest_captured_day(src, today: Date, *, max_probes: int = 10) -> Date | None:
    """Newest day <= `today` the source actually HAS a cross-section for, or None.

    Not answerable from the calendar alone: a captured bed's trading_calendar() OUTRUNS its
    snapshots, because the calendar is fetched whole while the capture stops at its own end
    date (2yr: calendar to 2026-07-13, snapshots to 2026-07-09; broad: calendar to 2026-06-22,
    snapshots to 2026-03-27). "Newest calendar day" would therefore pick a day with no data on
    both shipped beds.

    Two paths. A PITStore-backed source answers by file existence, which is cheap enough to
    walk the whole calendar - broad needs ~60 steps, so a small probe cap would not reach it.
    Any other source is probed by CALLING daily_snapshot backwards from the newest candidate,
    capped at `max_probes` so a source that never answers still terminates. A day is "captured"
    only if the call neither raises nor returns an empty frame: FakeSource-style sources return
    an empty frame instead of raising, and a default must not land on an empty cross-section.
    """
    days = sorted(d for d in src.trading_calendar() if d <= today)
    # Duck-typed on purpose: covers the bed built here AND an injected SnapshotSource, without
    # this module having to know which one it was handed.
    store = getattr(src, "_store", None)
    if hasattr(store, "has_snapshot"):
        return next((d for d in reversed(days) if store.has_snapshot(d)), None)
    for d in reversed(days[-max_probes:]):
        try:
            df = src.daily_snapshot(d)
        except Exception:
            continue
        if df is not None and not df.empty:
            return d
    return None


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
            # Spec section 4 asks for a "latest trading day" default because today is not a
            # trading day on weekends and holidays. On these beds that is not enough: the
            # calendar outruns the capture, so the default resolves to the newest day actually
            # CAPTURED at or before today (see _latest_captured_day). The as_of cursor below
            # still defaults to today, never to the resolved day.
            if date:
                day = _d(date)
            else:
                day = _latest_captured_day(snapshot_factory(), today)
                if day is None:
                    return {"ok": False, "error": "no captured snapshot on or before today - "
                                                  "check ALPHA_PIT_ROOT and the bed's window"}
            g = _guarded(snapshot_factory, _d(as_of) if as_of else today)
            return _frame(g.daily_snapshot(day))
        add("market_snapshot", "full-market daily cross-section for a date (offline PIT bed); "
                               "date defaults to the newest day with a captured snapshot at or "
                               "before today", market_snapshot)

        # The slow bed walks (screen(trend_template) ~188 s for ONE day on the 2yr bed, measured
        # 2026-08-31; breadth walks every symbol's bars too) cache their results on disk per
        # (bed, code version, day, kind) — see alpaca_kit/mcp/cache.py. Only the real bed is
        # cached: an injected factory supplies a source the bed path does not name, so nothing
        # on disk keys it.
        cached_root = None if injected_source else pit_root

        def screen(date: str, kind: str = "gainer", as_of: str | None = None):
            from alpaca_kit.universe import build_universe, resolve_universe_screen
            day = _d(date)
            # Resolved BEFORE keying, through the universe module's own resolver, so an explicit
            # kind beats ambient ALPHA_UNIVERSE_SCREEN, an unknown kind raises -> ok=False, and
            # the cache never files an entry under an unresolved spelling (kind="" falls through
            # to the env inside build_universe).
            resolved = resolve_universe_screen(kind)
            guard = AsOfGuard(_d(as_of) if as_of else Date.today())
            # The lookahead check runs BEFORE the cache read — a cached day must never leak past
            # an earlier cursor. Equivalent to the in-walk checks (every fetch in the walk is
            # dated <= day), just hoisted above the cache.
            guard.check(day)
            path = (screen_cache.cache_path(cached_root, f"screen-{resolved}", day)
                    if cached_root else None)
            if path is not None:
                hit = screen_cache.read(path)
                if hit is not None:
                    return hit
            uni = build_universe(GuardedSource(snapshot_factory(), guard), day, screen=resolved)
            # CandidateUniverse indexes StockSnapshots by symbol; .all() is its list accessor.
            out = {"ok": True, "computed_at": _utcnow(),
                   "rows": [s.model_dump(mode="json") for s in uni.all()][:MAX_ROWS]}
            if path is not None:
                screen_cache.write(path, out)     # ok=True only: an error is never cached
            return out
        add("screen", "daily screen (offline PIT bed): kind=gainer or trend_template; results "
                      "are disk-cached per (bed, day, kind), so only the first call for a day "
                      "is slow", screen)

        def breadth(date: str):
            from alpaca_kit.features.breadth import market_breadth
            from alpaca_kit.pit.pit_store import PITStore
            from alpaca_kit.pit.snapshot_source import SnapshotSource
            day = _d(date)
            # Unlike screen, breadth reads PITStore(pit_root) directly — injection never reaches
            # it — so the bed path names the source unconditionally and the cache always applies.
            path = screen_cache.cache_path(pit_root, "breadth", day)
            hit = screen_cache.read(path)
            if hit is not None:
                return hit
            store = PITStore(pit_root)
            src = SnapshotSource(store)
            snap = GuardedSource(src, AsOfGuard(day)).daily_snapshot(day)
            bars = {sym: src.daily_bars(sym, Date(1990, 1, 1), day)
                    for sym in snap["symbol"].tolist()}
            reading = market_breadth(bars, day)
            out = {"ok": True, "computed_at": _utcnow(), **reading.model_dump(mode="json")}
            screen_cache.write(path, out)         # ok=True only: an error is never cached
            return out
        add("breadth", "market breadth for a date (offline PIT bed); disk-cached per (bed, day)",
            breadth)

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
