"""P1 acceptance meta-gate (PIT-firewall-quartet style, `tests/test_us0_firewall_surfaces.py`).

Asserts each named trap-battery guarantee's test FUNCTION exists, so deleting one fails this gate the
way deleting a firewall guard does. The functions themselves run as part of the normal suite.

Plus a source-level meta-gate (`test_production_sites_size_outside_guard`) that pins the load-bearing
decorator order `SizingPolicy(GuardedPolicy(...))` at the three production composition sites — the
behavioural counterpart lives in `test_trap_day_battery.test_decorator_order_sizes_post_veto_not_pre_veto`.
"""
from __future__ import annotations

import ast
import importlib
import pathlib

import alpha
import pytest

SURFACES = [
    # the battery is non-empty (no vacuous pass) + each trap day reads its intended regime
    ("tests.guard.test_trap_day_battery", "test_battery_is_non_empty"),
    ("tests.guard.test_trap_day_battery", "test_trap_day_reads_its_intended_regime"),
    # zero new longs through the full SizingPolicy(GuardedPolicy(...)) stack, both packs
    ("tests.guard.test_trap_day_battery", "test_trap_day_yields_zero_new_longs"),
    ("tests.guard.test_trap_day_battery", "test_battery_veto_outcome_is_pack_independent"),
    # the deep finding: the existing stack does NOT block panic rebounds -> the panic veto is needed
    ("tests.guard.test_trap_day_battery", "test_existing_stack_fails_to_block_panic_rebound"),
    # negative controls: the veto is targeted (uptrend) and depth-separated (ordinary correction), not
    # "block all frontside"
    ("tests.guard.test_trap_day_battery", "test_genuine_trend_after_uptrend_is_not_vetoed"),
    ("tests.guard.test_trap_day_battery", "test_choppy_correction_followthrough_is_not_vetoed"),
    # the load-bearing decorator order is observable (sizing sees the post-veto book)
    ("tests.guard.test_trap_day_battery", "test_decorator_order_sizes_post_veto_not_pre_veto"),
    # the panic detector truth table + the waterfall (deep-bear) leg
    ("tests.guard.test_panic_state_veto", "test_sharp_rebound_after_bear_and_vol_is_panic"),
    ("tests.guard.test_panic_state_veto", "test_same_rebound_after_healthy_uptrend_is_not_panic"),
    ("tests.guard.test_panic_state_veto", "test_waterfall_uniform_crash_is_panic"),
    # the additive / default-off (history=None) byte-identity thread — deleting these must trip the gate
    ("tests.guard.test_panic_state_veto", "test_candidate_context_panic_defaults_false"),
    ("tests.guard.test_panic_state_veto", "test_screen_decision_default_history_none_is_byte_identical"),
    ("tests.guard.test_panic_state_veto", "test_guarded_policy_default_state_history_byte_identical"),
]


@pytest.mark.parametrize("module, func", SURFACES)
def test_trap_battery_surface_exists(module: str, func: str) -> None:
    mod = importlib.import_module(module)
    assert callable(getattr(mod, func, None)), f"missing trap-battery surface test {module}::{func}"


# ── source meta-gate: the three production sites size OUTSIDE the guard (post-veto) ─────────────────

_SIZE, _GUARD = "SizingPolicy", "GuardedPolicy"
_REPO = pathlib.Path(alpha.__file__).parent.parent
# every production site that composes the L3 sizing + L4 guard decorators (from a whole-repo grep)
_PRODUCTION_SITES = [
    _REPO / "alpha" / "loop" / "inner_loop.py",
    _REPO / "alpha" / "loop" / "compare.py",
    _REPO / "scripts" / "save_decisions.py",
]


def _ctor(node: ast.AST) -> str | None:
    """Constructor name if `node` is a call to a bare Name (e.g. `SizingPolicy(...)`), else None."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _branches(node: ast.AST) -> list[ast.AST]:
    """Flatten a ternary (`a if c else b`) to its candidate value expressions."""
    if isinstance(node, ast.IfExp):
        return _branches(node.body) + _branches(node.orelse)
    return [node]


def _arg_is(arg: ast.AST, wanted: str, env: dict[str, str | None]) -> bool:
    """Does `arg` resolve to a call of `wanted` — directly, or via a Name bound to it in `env`?"""
    for v in _branches(arg):
        if _ctor(v) == wanted:
            return True
        if isinstance(v, ast.Name) and env.get(v.id) == wanted:
            return True
    return False


def _order_violations(src: str, path: str) -> list[str]:
    """Composition-order violations for one file. Order-aware: walks statements in source order, checks
    each Sizing/Guard call against the CURRENT bindings, THEN updates them — so the variable REUSE these
    sites rely on (`policy` = agent -> guarded -> sized) is resolved correctly rather than conflated."""
    tree = ast.parse(src)
    env: dict[str, str | None] = {}
    violations: list[str] = []
    saw_sizing = False

    def _child_stmts(node: ast.AST) -> list[ast.stmt]:
        return (getattr(node, "body", []) + getattr(node, "orelse", []) + getattr(node, "finalbody", []))

    def walk(stmts: list[ast.stmt]) -> None:
        nonlocal saw_sizing
        for s in stmts:
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If, ast.For,
                              ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)):
                walk(_child_stmts(s))
                continue
            for call in (n for n in ast.walk(s) if isinstance(n, ast.Call)):
                fn = _ctor(call)
                if fn == _SIZE and call.args:
                    saw_sizing = True
                    if not _arg_is(call.args[0], _GUARD, env):
                        violations.append(f"{path}: SizingPolicy() does not wrap GuardedPolicy (order inverted?)")
                if fn == _GUARD and call.args and _arg_is(call.args[0], _SIZE, env):
                    violations.append(f"{path}: GuardedPolicy() wraps SizingPolicy (order inverted!)")
            if isinstance(s, ast.Assign):
                for tgt in s.targets:
                    if isinstance(tgt, ast.Name):
                        ctors = [_ctor(v) for v in _branches(s.value) if _ctor(v)]
                        env[tgt.id] = next((c for c in ctors if c in (_SIZE, _GUARD)),
                                           ctors[0] if ctors else None)

    walk(tree.body)
    if not saw_sizing:
        violations.append(f"{path}: no SizingPolicy composition found (expected the size-outside-guard site)")
    return violations


@pytest.mark.parametrize("site", _PRODUCTION_SITES, ids=lambda p: p.name)
def test_production_sites_size_outside_guard(site: pathlib.Path) -> None:
    """Pin the load-bearing order at each production site: L3 SizingPolicy must wrap the L4 GuardedPolicy
    (size the post-veto survivors), never the reverse. Inverting the composition at any of these sites
    trips this gate (and the behavioural sibling test)."""
    assert site.exists(), f"production composition site moved: {site}"
    violations = _order_violations(site.read_text(), site.name)
    assert not violations, "; ".join(violations)


def test_order_meta_gate_catches_inversion() -> None:
    """The meta-gate itself is non-vacuous: an inverted arrangement (guard OUTSIDE sizing) is flagged."""
    inverted = "policy = SizingPolicy(agent)\nself._agent = GuardedPolicy(policy, source)\n"
    assert _order_violations(inverted, "<inverted>"), "meta-gate failed to catch an inverted composition"
    correct = "p = LLMAgentPolicy(h)\np = GuardedPolicy(p, source)\np = SizingPolicy(p)\n"
    assert not _order_violations(correct, "<correct>"), "meta-gate false-positived on the correct order"
