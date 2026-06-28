import ast
import pathlib


def test_converse_never_imports_arena():
    """Layer spine (CLAUDE.md §2): alpha/arena may import converse, never the reverse.
    The live-face wiring is injected (registry_factory) precisely so converse stays arena-free."""
    converse_dir = pathlib.Path("alpha/converse")
    offenders = []
    for py in converse_dir.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("alpha.arena"):
                offenders.append(f"{py}: from {node.module}")
            if isinstance(node, ast.Import):
                for n in node.names:
                    if n.name.startswith("alpha.arena"):
                        offenders.append(f"{py}: import {n.name}")
    assert offenders == [], f"converse must not import arena: {offenders}"
