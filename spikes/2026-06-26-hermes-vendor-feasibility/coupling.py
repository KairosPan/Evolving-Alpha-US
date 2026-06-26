# spikes/2026-06-26-hermes-vendor-feasibility/coupling.py
"""Static AST import-graph over the pinned Hermes tree. For an entry module, compute the set of
*Hermes-internal* .py files it transitively imports, whether it reaches the `agent/` package, and
the total file/LOC weight. This is the narrow-waist measurement: a small reachable set that does
NOT drag in `agent/` => Strategy C (vendor the module) is viable for that module.

Two metrics are reported:
- EAGER: follows only module-top-level imports (fires when the module is merely `import`-ed).
- TOTAL: follows all imports at any nesting depth including lazy/function-level ones (full static
  footprint, but those imports only fire when those code paths actually run).
"""
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
    """Return all module names imported anywhere in the file (any nesting depth)."""
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

def _eager_imports(relpath: str) -> set[str]:
    """Return module names imported at module top-level ONLY (not inside functions/classes/if).
    These are the imports that execute when the module is merely `import`-ed."""
    src = open(os.path.join(HERMES, relpath), encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in tree.body:                     # module top-level ONLY (not ast.walk)
        if isinstance(node, ast.Import):
            for n in node.names:
                out.add(n.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out

def _drags_agent(seen: set[str], entry_relpath: str) -> bool:
    return any(r.startswith("agent" + os.sep) or r == "agent.py" for r in seen if r != entry_relpath)

def _loc(seen: set[str]) -> int:
    return sum(sum(1 for _ in open(os.path.join(HERMES, r), errors="replace")) for r in seen)

def transitive_internal_imports(entry_relpath: str) -> dict:
    """TOTAL metric: transitive closure over ALL imports at any nesting depth."""
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
    return {
        "reachable": seen,
        "drags_agent_pkg": _drags_agent(seen, entry_relpath),
        "file_count": len(seen),
        "loc": _loc(seen),
    }

def eager_internal_imports(entry_relpath: str) -> dict:
    """EAGER metric: transitive closure over module-top-level imports only.
    A module that loads cleanly here (small file_count, drags_agent_pkg=False) is a
    candidate for Strategy C vendoring — you can `import` it without pulling the monolith."""
    seen: set[str] = set()
    stack = [entry_relpath]
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.add(rel)
        for mod in _eager_imports(rel):
            rp = _module_to_relpath(mod)
            if rp and rp not in seen:
                stack.append(rp)
    return {
        "reachable": seen,
        "drags_agent_pkg": _drags_agent(seen, entry_relpath),
        "file_count": len(seen),
        "loc": _loc(seen),
    }

if __name__ == "__main__":
    targets = ["tools/registry.py", "hermes_state.py", "agent/conversation_loop.py"]
    lines = [
        "# Hermes coupling measurement\n",
        "> **EAGER** = imports that execute on `import` (module top-level only); "
        "**TOTAL** = full static footprint including lazy/function-level imports that only fire "
        "when those code paths run. Vendor feasibility is driven by the EAGER metric.\n",
    ]
    for t in targets:
        e = eager_internal_imports(t)
        total = transitive_internal_imports(t)
        if not e["drags_agent_pkg"] and e["file_count"] <= 10:
            verdict = "**liftable (eager leaf)** — candidate for Strategy C vendoring"
        elif e["drags_agent_pkg"]:
            verdict = "**eager-coupled** — investigate/sever agent dependency or reimplement"
        else:
            verdict = f"**investigate** — eager footprint {e['file_count']} files, no agent drag"
        lines.append(f"## `{t}`\n")
        lines.append(f"| Metric | file_count | loc | drags_agent_pkg |")
        lines.append(f"|--------|-----------|-----|-----------------|")
        lines.append(f"| EAGER  | **{e['file_count']}** | {e['loc']} | **{e['drags_agent_pkg']}** |")
        lines.append(f"| TOTAL  | **{total['file_count']}** | {total['loc']} | **{total['drags_agent_pkg']}** |")
        lines.append(f"\n- verdict: {verdict}\n")
    out_path = os.path.join(os.path.dirname(__file__), "COUPLING.md")
    open(out_path, "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))
