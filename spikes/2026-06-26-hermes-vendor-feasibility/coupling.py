# spikes/2026-06-26-hermes-vendor-feasibility/coupling.py
"""Static AST import-graph over the pinned Hermes tree. For an entry module, compute the set of
*Hermes-internal* .py files it transitively imports, whether it reaches the `agent/` package, and
the total file/LOC weight. This is the narrow-waist measurement: a small reachable set that does
NOT drag in `agent/` => Strategy C (vendor the module) is viable for that module."""
from __future__ import annotations
import ast, os

HERMES = os.path.join(os.path.dirname(__file__), "_hermes")

def _module_to_relpath(mod: str) -> str | None:
    """Map a dotted module name to a file under _hermes, if it is Hermes-internal."""
    parts = mod.split(".")
    cand_mod = os.path.join(HERMES, *parts) + ".py"
    cand_pkg = os.path.join(HERMES, *parts, "__init__.py")
    if os.path.isfile(cand_mod):
        return os.path.relpath(cand_mod, HERMES)
    if os.path.isfile(cand_pkg):
        return os.path.relpath(cand_pkg, HERMES)
    return None

def _imports_of(relpath: str) -> set[str]:
    src = open(os.path.join(HERMES, relpath), encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                out.add(n.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out

def transitive_internal_imports(entry_relpath: str) -> dict:
    seen: set[str] = set()
    stack = [entry_relpath]
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.add(rel)
        for mod in _imports_of(rel):
            rp = _module_to_relpath(mod)
            if rp and rp not in seen:
                stack.append(rp)
    loc = sum(sum(1 for _ in open(os.path.join(HERMES, r), errors="replace")) for r in seen)
    return {
        "reachable": seen,
        "drags_agent_pkg": any(r.startswith("agent" + os.sep) or r == "agent.py" for r in seen if r != entry_relpath),
        "file_count": len(seen),
        "loc": loc,
    }

if __name__ == "__main__":
    targets = ["tools/registry.py", "hermes_state.py", "agent/conversation_loop.py"]
    lines = ["# Hermes coupling measurement\n"]
    for t in targets:
        r = transitive_internal_imports(t)
        lines.append(f"## `{t}`\n")
        lines.append(f"- reachable Hermes-internal files: **{r['file_count']}**, total LOC: **{r['loc']}**")
        lines.append(f"- drags in the `agent/` package: **{r['drags_agent_pkg']}**")
        lines.append(f"- verdict: **{'DRAGS MONOLITH' if r['drags_agent_pkg'] else 'liftable'}**\n")
    open(os.path.join(os.path.dirname(__file__), "COUPLING.md"), "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))
