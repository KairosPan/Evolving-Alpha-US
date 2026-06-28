"""Computer-use tool factories. Each returns (schema, fn, tier). File tools are path-guarded to the
workspace; shell routes through the ToolEnvironment seam. NONE of these can import the harness or
reach the brain dir — data rungs only (modification-ladder spec §8)."""
from __future__ import annotations
from pathlib import Path
from alpha.arena.contract import CapabilityTier
from alpha.arena.environment import ToolEnvironment


def _within(workspace: Path, rel: str) -> Path | None:
    root = Path(workspace).resolve()
    p = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def make_read_file_tool(workspace: Path):
    def read_file(path: str) -> dict:
        p = _within(workspace, path)
        if p is None:
            return {"ok": False, "error": f"path outside workspace: {path}"}
        if not p.exists():
            return {"ok": False, "error": f"not found: {path}"}
        return {"ok": True, "content": p.read_text()}
    schema = {"name": "read_file", "description": "Read a file inside the project workspace.",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                             "required": ["path"]}}
    return schema, read_file, CapabilityTier.T0_OBSERVE


def make_write_file_tool(workspace: Path):
    def write_file(path: str, content: str) -> dict:
        p = _within(workspace, path)
        if p is None:
            return {"ok": False, "error": f"path outside workspace: {path}"}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {"ok": True, "path": path}
    schema = {"name": "write_file", "description": "Write a file inside the project workspace.",
              "parameters": {"type": "object",
                             "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                             "required": ["path", "content"]}}
    return schema, write_file, CapabilityTier.T1_WORKSPACE_WRITE


def make_shell_tool(env: ToolEnvironment):
    def shell(argv: list[str]) -> dict:
        r = env.run(list(argv))
        return {"ok": r.ok, "stdout": r.stdout, "stderr": r.stderr, "exit_code": r.exit_code}
    schema = {"name": "shell", "description": "Run a command in the execution environment (confined).",
              "parameters": {"type": "object",
                             "properties": {"argv": {"type": "array", "items": {"type": "string"}}},
                             "required": ["argv"]}}
    return schema, shell, CapabilityTier.T2_EXECUTE
