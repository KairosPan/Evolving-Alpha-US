"""US-0 acceptance gate: each firewall surface has a specific guarding test.

Asserts each surface's named guarding test FUNCTION exists (deleting one fails this gate);
the functions themselves run as part of the normal suite.
"""
from __future__ import annotations

import importlib

import pytest

SURFACES = [
    ("tests.data.test_source", "test_guarded_source_blocks_future_snapshot"),       # 1 date-lookahead
    ("tests.data.test_corp_actions", "test_has_reverse_split_pending_pit"),         # 2 corp-action announce-date PIT
    ("tests.data.test_snapshot_source", "test_bars_are_raw_not_future_adjusted"),   # 3 split-vintage raw-PIT
    ("tests.universe.test_build_universe", "test_rvol_uses_only_trailing_bars"),     # 4 windowed-rank trailing-only
    ("tests.kit.test_replay", "test_yields_every_calendar_day_guarded"),           # 5 backtest replay PIT channel
    ("tests.kit.test_mcp_tools", "test_pit_guard_blocks_future_as_of"),           # 6 MCP tool-layer guard wrapping
]


@pytest.mark.parametrize("module, func", SURFACES)
def test_firewall_surface_guard_exists(module: str, func: str) -> None:
    mod = importlib.import_module(module)
    assert callable(getattr(mod, func, None)), f"missing firewall-surface test {module}::{func}"
