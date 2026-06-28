# tests/arena/test_builder.py
from pathlib import Path
from alpha.arena.builder import build_arena
from alpha.arena.contract import CapabilityTier
from alpha.harness.loader import load_seeds


class _LLM:
    def complete(self, *a, **k): return "{}"


def test_build_arena_registers_tiers(tmp_path: Path):
    h = load_seeds("seeds")
    reg, pol = build_arena(h, _LLM(), source=None, workspace=tmp_path)
    assert pol.tiers["decide"] == CapabilityTier.T0_OBSERVE
    assert pol.tiers["read_file"] == CapabilityTier.T0_OBSERVE
    assert pol.tiers["write_file"] == CapabilityTier.T1_WORKSPACE_WRITE
    assert pol.tiers["shell"] == CapabilityTier.T2_EXECUTE
    assert pol.tiers["propose_memory_edit"] == CapabilityTier.T3_BRAIN_EDIT


def test_arena_fail_closes_unknown_tool(tmp_path: Path):
    h = load_seeds("seeds")
    _reg, pol = build_arena(h, _LLM(), source=None, workspace=tmp_path)
    out = pol.dispatch("definitely_not_a_tool", {})
    assert "error" in out and "tier" in out["error"].lower()


def test_arena_no_live_order_tool(tmp_path: Path):
    h = load_seeds("seeds")
    reg, pol = build_arena(h, _LLM(), source=None, workspace=tmp_path)
    # the hard wall: no order-placement tool exists at any tier
    assert not any("order" in name.lower() for name in pol.tiers)
