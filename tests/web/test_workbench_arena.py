from pathlib import Path
import pytest


def test_brain_under_workspace_is_rejected(tmp_path, monkeypatch):
    # brain INSIDE the workspace must fail fast (the live shell could reach it)
    ws = tmp_path / "ws"; brain = ws / "brain"
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(brain))
    from workbench.app import _assert_brain_outside_workspace
    with pytest.raises(Exception):
        _assert_brain_outside_workspace()


def test_brain_sibling_of_workspace_is_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    from workbench.app import _assert_brain_outside_workspace
    _assert_brain_outside_workspace()   # no raise


def test_arena_factory_registers_shell_t2(tmp_path):
    # the workbench's factory wires the full computer-use catalog through the policy
    from workbench.app import _arena_factory
    from alpha.arena.contract import CapabilityTier
    from alpha.harness.loader import load_seeds
    factory = _arena_factory(tmp_path)                 # tmp_path stands in for ws.root
    reg, dispatch = factory(load_seeds("seeds"), None, None, read_only=False, write_mode="stage")
    # dispatch is the policy's; an untiered tool fail-closes
    out = dispatch("definitely_not_a_tool", {})
    assert "error" in out
