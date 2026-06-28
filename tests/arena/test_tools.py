from pathlib import Path
from alpha.arena.contract import CapabilityTier
from alpha.arena.environment import InProcessEnv, LocalEnv
from alpha.arena.tools import make_read_file_tool, make_write_file_tool, make_shell_tool


def test_write_then_read_within_workspace(tmp_path: Path):
    _ws, wfn, wtier = make_write_file_tool(tmp_path)
    _rs, rfn, rtier = make_read_file_tool(tmp_path)
    assert wtier == CapabilityTier.T1_WORKSPACE_WRITE and rtier == CapabilityTier.T0_OBSERVE
    assert wfn(path="note.txt", content="hi")["ok"] is True
    assert rfn(path="note.txt")["content"] == "hi"


def test_file_tools_refuse_escape(tmp_path: Path):
    _s, wfn, _t = make_write_file_tool(tmp_path)
    out = wfn(path="../escape.txt", content="x")
    assert out["ok"] is False and "outside workspace" in out["error"].lower()


def test_shell_tool_tier_and_inprocess_refusal():
    schema, fn, tier = make_shell_tool(InProcessEnv())
    assert tier == CapabilityTier.T2_EXECUTE and schema["name"] == "shell"
    out = fn(argv=["echo", "hi"])
    assert out["ok"] is False   # InProcessEnv refuses


def test_shell_tool_runs_under_localenv(tmp_path: Path):
    _s, fn, _t = make_shell_tool(LocalEnv(workspace=tmp_path))
    out = fn(argv=["python", "-c", "print('x')"])
    assert out["ok"] is True and "x" in out["stdout"]
