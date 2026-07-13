"""Meta-gate (mirrors tests/test_us0_firewall_surfaces.py / tests/arena/test_no_converse_arena_cycle.py):
no PRODUCTION code constructs `Candidate(action=...)`.

LOAD-BEARING (P0.6): `Candidate.action` defaults to "enter", and the L4 guard skips its new-entry
veto for a trim/exit while L3 sizing derisks the tier. Today NO producer emits a trim/exit — holdings
are not modeled, so every real Candidate is an "enter" and the seams are inert/byte-identical. If a
producer starts setting `action` before the verdict/eval SCORING FENCE (P0.5 spec §8) is implemented,
trim/exit candidates would be scored as fresh forward-return LONGs and corrupt the metric. This gate
fails the moment production code passes `action=` to a Candidate, forcing the fence to land first.
Tests may construct `Candidate(action=...)` freely (this walks only the production tree).
"""
from __future__ import annotations

import ast
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]
_PROD_DIRS = ("alpha", "scripts", "alpha_web")


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_no_production_code_constructs_candidate_with_action():
    offenders: list[str] = []
    for d in _PROD_DIRS:
        for py in (_REPO / d).rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and _callee_name(node.func) == "Candidate"
                        and any(kw.arg == "action" for kw in node.keywords)):
                    offenders.append(f"{py.relative_to(_REPO)}:{node.lineno}")
    assert offenders == [], (
        "production code constructs Candidate(action=...) — the verdict/eval SCORING FENCE "
        f"(P0.5 spec §8) must land first, else trim/exit is scored as a new long: {offenders}")
