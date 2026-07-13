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
    # A7: no H-mutation (propose) tier — "Kairos does not propose".
    assert "propose_memory_edit" not in pol.tiers


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


def test_build_arena_no_workspace_is_decide_only(tmp_path):
    from alpha.arena.contract import CapabilityTier
    h = load_seeds("seeds")
    reg, pol = build_arena(h, _LLM(), source=None)              # workspace=None
    # A7: the worker has no propose tool — with no workspace, only decide remains.
    assert set(pol.tiers) == {"decide"}
    assert pol.tiers["decide"] == CapabilityTier.T0_OBSERVE


def test_build_arena_with_workspace_adds_computer_use(tmp_path):
    from alpha.arena.contract import CapabilityTier
    reg, pol = build_arena(load_seeds("seeds"), _LLM(), source=None, workspace=tmp_path)
    assert pol.tiers["read_file"] == CapabilityTier.T0_OBSERVE
    assert pol.tiers["write_file"] == CapabilityTier.T1_WORKSPACE_WRITE
    assert pol.tiers["shell"] == CapabilityTier.T2_EXECUTE


def test_build_arena_read_only_is_read_and_decide_only(tmp_path):
    reg, pol = build_arena(load_seeds("seeds"), _LLM(), source=None,
                           workspace=tmp_path, read_only=True)
    assert set(pol.tiers) == {"decide", "read_file"}            # no brain-edit/write/shell


def test_build_arena_never_registers_propose_tool(tmp_path):
    # A7: no write_mode registers a brain-edit tool (the worker does not propose).
    for mode in ("none", "stage"):
        reg, pol = build_arena(load_seeds("seeds"), _LLM(), source=None,
                               workspace=tmp_path, write_mode=mode)
        assert "propose_memory_edit" not in pol.tiers
        assert {"decide", "read_file", "write_file", "shell"} <= set(pol.tiers)  # compute-use intact
