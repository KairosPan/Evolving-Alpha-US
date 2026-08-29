from __future__ import annotations

from alpaca_kit.mcp.tools import READ_ONLY_TOOLS, build_tools

KEYS = {"APCA_API_KEY_ID": "k", "APCA_API_SECRET_KEY": "s"}


def test_no_env_registers_only_keyless_tools():
    tools = build_tools(env={})
    assert set(tools) == {"earnings"}


def test_keys_register_market_and_account_but_never_orders():
    tools = build_tools(env=dict(KEYS))
    assert {"daily_bars", "market_snapshot", "calendar", "corp_actions",
            "screen", "account", "positions", "orders", "earnings"} <= set(tools)
    assert "place_order" not in tools and "cancel_order" not in tools


def test_default_registration_is_read_only():          # capability-absence meta-gate
    for env in ({}, dict(KEYS), {**KEYS, "ALPHA_PIT_ROOT": "/tmp/x"}):
        assert set(build_tools(env=env)) <= READ_ONLY_TOOLS


def test_order_tools_need_flag_and_keys():
    flagged = {**KEYS, "ALPACA_KIT_ENABLE_ORDERS": "1"}
    assert {"place_order", "cancel_order"} <= set(build_tools(env=flagged))
    assert "place_order" not in build_tools(env={"ALPACA_KIT_ENABLE_ORDERS": "1"})  # flag w/o keys


def test_breadth_needs_pit_root():
    assert "breadth" not in build_tools(env=dict(KEYS))
    assert "breadth" in build_tools(env={**KEYS, "ALPHA_PIT_ROOT": "/tmp/x"})


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
    tools = build_tools(env=dict(KEYS), source_factory=lambda: fake_source)
    out = tools["screen"].fn(date="2026-06-12")
    assert out["ok"] is True
    assert [r["symbol"] for r in out["rows"]] == ["RUN"]
    assert out["rows"][0]["status"] == "gainer"


def test_pit_guard_blocks_future_as_of(fake_source):
    tools = build_tools(env=dict(KEYS), source_factory=lambda: fake_source)
    out = tools["market_snapshot"].fn(date="2026-06-12", as_of="2026-06-10")
    assert out["ok"] is False and "lookahead" in out["error"].lower()
