from __future__ import annotations

import json
from datetime import date

import pandas as pd

from alpaca_kit.mcp.tools import READ_ONLY_TOOLS, _frame, build_tools
from alpaca_kit.pit.pit_store import PITStore
from alpaca_kit.source import FakeSource

KEYS = {"APCA_API_KEY_ID": "k", "APCA_API_SECRET_KEY": "s"}
PIT = {"ALPHA_PIT_ROOT": "/tmp/x"}
KEY_TOOLS = {"daily_bars", "calendar", "corp_actions"}
BED_TOOLS = {"market_snapshot", "screen", "breadth"}


def _corp_source(rows: list[dict], *, available: bool = True) -> FakeSource:
    """A FakeSource carrying only a corp-actions frame (the other capabilities stay empty)."""
    corp = pd.DataFrame(rows, columns=["symbol", "announce_date", "ex_date", "kind", "ratio"])
    return FakeSource(calendar=[], bars={}, snapshots={}, corp_actions=corp,
                      corp_actions_available=available)


# ── registration rules (spec section 4/5) ──────────────────────────────────────────────────────

def test_no_env_registers_only_keyless_tools():
    tools = build_tools(env={})
    assert set(tools) == {"earnings"}


def test_keys_register_market_and_account_but_never_orders():
    tools = build_tools(env=dict(KEYS))
    assert KEY_TOOLS | {"account", "positions", "orders", "earnings"} <= set(tools)
    assert "place_order" not in tools and "cancel_order" not in tools


def test_snapshot_tools_need_a_pit_bed_not_keys():
    # AlpacaSource.daily_snapshot is NotImplementedError: a daily cross-section exists only on a
    # captured bed, so keys alone must not advertise tools that can never succeed.
    assert BED_TOOLS.isdisjoint(build_tools(env=dict(KEYS)))
    assert BED_TOOLS <= set(build_tools(env=dict(PIT)))


def test_pit_root_alone_registers_the_market_tools():
    assert KEY_TOOLS <= set(build_tools(env=dict(PIT)))


def test_snapshot_tools_read_the_bed_even_when_keys_are_present(tmp_path):
    # The real consequence of gating on the bed: with keys AND a bed, market_snapshot/screen must
    # resolve the CAPTURED bed, not live Alpaca (whose daily_snapshot raises NotImplementedError).
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 11), date(2026, 6, 12)])
    store.put_snapshot(date(2026, 6, 12), pd.DataFrame({
        "symbol": ["RUN"], "name": ["Runner"], "open": [16.0], "high": [18.0], "low": [15.0],
        "close": [17.0], "volume": [5e6], "prev_close": [14.0]}))
    tools = build_tools(env={**KEYS, "ALPHA_PIT_ROOT": str(tmp_path)})      # no injected factory
    out = tools["market_snapshot"].fn(date="2026-06-12")
    assert out["ok"] is True and [r["symbol"] for r in out["rows"]] == ["RUN"]


def test_default_registration_is_read_only():          # capability-absence meta-gate
    for env in ({}, dict(KEYS), dict(PIT), {**KEYS, **PIT}):
        assert set(build_tools(env=env)) <= READ_ONLY_TOOLS
    # ...and the frozen set itself excludes the mutating tools, so widening it cannot defeat the gate
    assert {"place_order", "cancel_order"}.isdisjoint(READ_ONLY_TOOLS)


def test_order_tools_need_flag_and_keys():
    flagged = {**KEYS, "ALPACA_KIT_ENABLE_ORDERS": "1"}
    assert {"place_order", "cancel_order"} <= set(build_tools(env=flagged))
    assert "place_order" not in build_tools(env={"ALPACA_KIT_ENABLE_ORDERS": "1"})  # flag w/o keys


def test_injected_trading_factory_cannot_open_the_order_gate():
    # The order gate reads has_keys, never the injected seam: injection supplies a client,
    # it must never register the mutating tools for a keyless process.
    tools = build_tools(env={"ALPACA_KIT_ENABLE_ORDERS": "1"}, trading_factory=lambda: None)
    assert {"place_order", "cancel_order"}.isdisjoint(tools)
    assert set(tools) <= READ_ONLY_TOOLS


# ── fail-soft + PIT ────────────────────────────────────────────────────────────────────────────

def test_tool_calls_are_fail_soft(fake_source):
    tools = build_tools(env=dict(KEYS), source_factory=lambda: fake_source)
    out = tools["daily_bars"].fn(symbol="RUN", start="not-a-date", end="2026-06-12")
    assert out["ok"] is False and "error" in out


def test_daily_bars_happy_path_over_fake_source(fake_source):
    tools = build_tools(env=dict(KEYS), source_factory=lambda: fake_source)
    out = tools["daily_bars"].fn(symbol="RUN", start="2026-06-10", end="2026-06-12")
    assert out["ok"] is True and len(out["rows"]) == 3


def test_screen_returns_screened_stock_records(fake_source):
    # Pins the CandidateUniverse accessor: a wrong one raises AttributeError, which fail-soft would
    # bury as a plain ok=False, so nothing else in this file would notice.
    tools = build_tools(env=dict(PIT), source_factory=lambda: fake_source)
    out = tools["screen"].fn(date="2026-06-12")
    assert out["ok"] is True
    assert [r["symbol"] for r in out["rows"]] == ["RUN"]
    assert out["rows"][0]["status"] == "gainer"


def test_market_snapshot_defaults_to_the_latest_trading_day_not_today(fake_source):
    # Spec section 4: "default: latest trading day". fake_source's calendar ends 2026-06-12,
    # which is in the past relative to today - exactly the weekend/holiday shape, where a bare
    # Date.today() default fails soft with SnapshotMissingError instead of answering.
    tools = build_tools(env=dict(PIT), source_factory=lambda: fake_source)
    out = tools["market_snapshot"].fn()
    assert out["ok"] is True, out
    assert [r["symbol"] for r in out["rows"]] == ["RUN", "FLOP"]     # the 2026-06-12 snapshot


def test_market_snapshot_default_is_fail_soft_on_an_empty_calendar():
    empty = FakeSource(calendar=[], bars={}, snapshots={}, corp_actions=pd.DataFrame())
    tools = build_tools(env=dict(PIT), source_factory=lambda: empty)
    out = tools["market_snapshot"].fn()
    assert out["ok"] is False and "calendar" in out["error"]


def test_pit_guard_blocks_future_as_of(fake_source):
    tools = build_tools(env=dict(PIT), source_factory=lambda: fake_source)
    out = tools["market_snapshot"].fn(date="2026-06-12", as_of="2026-06-10")
    assert out["ok"] is False and "lookahead" in out["error"].lower()


def test_default_cursor_is_today_not_the_requested_date(fake_source):
    # as_of defaulting to the requested date makes AsOfGuard(day).check(day) a tautology: the
    # firewall would pass any future date on the default path.
    tools = build_tools(env=dict(PIT), source_factory=lambda: fake_source)
    for name, kwargs in (("market_snapshot", {"date": "2099-01-04"}),
                         ("screen", {"date": "2099-01-04"})):
        out = tools[name].fn(**kwargs)
        assert out["ok"] is False and "lookahead" in out["error"].lower(), name


# ── screen kind resolution ─────────────────────────────────────────────────────────────────────

def test_explicit_kind_beats_ambient_universe_screen_env(fake_source, monkeypatch):
    monkeypatch.setenv("ALPHA_UNIVERSE_SCREEN", "trend_template")
    tools = build_tools(env=dict(PIT), source_factory=lambda: fake_source)
    out = tools["screen"].fn(date="2026-06-12", kind="gainer")
    assert out["ok"] is True
    assert [r["symbol"] for r in out["rows"]] == ["RUN"]     # not silently trend-templated away


def test_unknown_screen_kind_fails_soft_instead_of_returning_gainers(fake_source):
    tools = build_tools(env=dict(PIT), source_factory=lambda: fake_source)
    out = tools["screen"].fn(date="2026-06-12", kind="bogus")
    assert out["ok"] is False and "bogus" in out["error"]


# ── corp actions ───────────────────────────────────────────────────────────────────────────────

def test_corp_actions_reports_a_missing_artifact_instead_of_a_clean_frame():
    # MISSING and checked-and-clean must not collapse: "no split pending" is not "could not check".
    tools = build_tools(env=dict(KEYS), source_factory=lambda: _corp_source([], available=False))
    out = tools["corp_actions"].fn(as_of="2026-06-12")
    assert out["ok"] is False and "missing" in out["error"].lower()


def test_corp_actions_filters_by_symbol_and_sorts_newest_first():
    rows = [
        {"symbol": "RUN", "announce_date": date(2026, 6, 1), "ex_date": date(2026, 6, 20),
         "kind": "split", "ratio": 2.0},
        {"symbol": "FLOP", "announce_date": date(2026, 6, 5), "ex_date": date(2026, 6, 21),
         "kind": "cash_dividend", "ratio": 0.5},
        {"symbol": "RUN", "announce_date": date(2026, 6, 9), "ex_date": date(2026, 6, 22),
         "kind": "reverse_split", "ratio": 0.1},
    ]
    tools = build_tools(env=dict(KEYS), source_factory=lambda: _corp_source(rows))
    every = tools["corp_actions"].fn(as_of="2026-06-12")
    assert [r["announce_date"] for r in every["rows"]] == ["2026-06-09", "2026-06-05", "2026-06-01"]
    just_run = tools["corp_actions"].fn(symbol="RUN", as_of="2026-06-12")
    assert [r["symbol"] for r in just_run["rows"]] == ["RUN", "RUN"]
    assert [r["announce_date"] for r in just_run["rows"]] == ["2026-06-09", "2026-06-01"]


# ── JSON safety at the _frame chokepoint ───────────────────────────────────────────────────────

def test_frame_output_is_strict_json_encodable(fake_source):
    # allow_nan=False is the real RFC 8259 check: json.dumps emits a bare NaN by default, and
    # strict parsers on the far side of an MCP transport reject it.
    tools = build_tools(env=dict(KEYS), source_factory=lambda: fake_source)
    corp = tools["corp_actions"].fn(as_of="2026-06-12")
    bars = tools["daily_bars"].fn(symbol="RUN", start="2026-06-10", end="2026-06-12")
    assert corp["ok"] is True and bars["ok"] is True
    assert corp["rows"][0]["announce_date"] == "2026-06-09"      # date -> ISO string
    assert bars["rows"][0]["date"] == "2026-06-10"
    json.dumps(corp, allow_nan=False)
    json.dumps(bars, allow_nan=False)


def test_frame_converts_nan_to_null():
    out = _frame(pd.DataFrame({"symbol": ["X"], "short_interest": [float("nan")]}))
    assert out["rows"][0]["short_interest"] is None
    json.dumps(out, allow_nan=False)
