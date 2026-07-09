"""Charter conformance (2026-07-09): the worker face is stage-only. write_mode="apply" (the
agent landing its own edit live) is retired — it must raise, never silently downgrade — and the
default mode stages proposals for the user's approval."""
import pytest

import alpha.converse.agent as agent_mod
from alpha.harness.loader import load_seeds


def test_apply_mode_is_retired_and_raises():
    with pytest.raises(ValueError, match="retired"):
        agent_mod.build_converse_registry(load_seeds("seeds"), None, None, write_mode="apply")


def test_default_mode_is_stage_and_registers_propose_tool():
    reg = agent_mod.build_converse_registry(load_seeds("seeds"), None, None)
    assert {s["name"] for s in reg.specs()} == {"decide", "propose_memory_edit"}
    # the staged tool never touches the live harness: its result is a staged preview, not "applied"
    out = reg.call("propose_memory_edit", tool="process_memory",
                   args={"lesson_id": "prov-1", "phases": ["trend"], "outcome": "win", "lesson": "x"},
                   rationale="stage default")
    assert out.get("staged") is True and "status" not in out


def test_read_only_drops_propose_tool():
    reg = agent_mod.build_converse_registry(load_seeds("seeds"), None, None, read_only=True)
    assert {s["name"] for s in reg.specs()} == {"decide"}
