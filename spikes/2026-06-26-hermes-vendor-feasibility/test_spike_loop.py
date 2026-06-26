# spikes/2026-06-26-hermes-vendor-feasibility/test_spike_loop.py
from spike_loop import Registry, run_turn
from alpha.llm.client import MockLLMClient

def test_registry_dispatches_one_tool_call():
    reg = Registry()
    reg.register("echo", {"name": "echo"}, lambda msg: f"got:{msg}")
    llm = MockLLMClient('{"tool": "echo", "args": {"msg": "hi"}}')
    assert run_turn(reg, llm) == "got:hi"

def test_unknown_tool_raises():
    import pytest
    reg = Registry()
    llm = MockLLMClient('{"tool": "nope", "args": {}}')
    with pytest.raises(KeyError):
        run_turn(reg, llm)
