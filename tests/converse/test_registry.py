import pytest
from alpha.converse.registry import ToolRegistry

def test_register_call_and_specs():
    reg = ToolRegistry()
    reg.register("echo", {"name": "echo", "description": "echoes"}, lambda msg: f"got:{msg}")
    assert reg.call("echo", msg="hi") == "got:hi"
    assert reg.specs() == [{"name": "echo", "description": "echoes"}]

def test_unknown_tool_raises():
    with pytest.raises(KeyError):
        ToolRegistry().call("nope")
