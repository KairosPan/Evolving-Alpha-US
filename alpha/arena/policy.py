"""The single dispatch choke point (spec §4). EVERY tool call flows through ActivityPolicy.dispatch:
an untiered tool is fail-closed (not callable), and a T4 tool never runs autonomously. T2 execution
confinement lives in LocalEnv; T3 brain-edits in the gate (try_apply_op) inside the tool itself —
the policy's job is the tier gate + the no-bypass guarantee."""
from __future__ import annotations
from typing import Any, Callable
from alpha.arena.contract import CapabilityTier
from alpha.converse.registry import ToolRegistry


class ActivityPolicy:
    def __init__(self, registry: ToolRegistry, tiers: dict[str, CapabilityTier],
                 *, confirm: Callable[[str, dict], bool] | None = None):
        self.registry = registry
        self.tiers = dict(tiers)
        self._confirm = confirm

    def dispatch(self, name: str, args: dict) -> Any:
        if name not in self.tiers:
            return {"error": f"tool not permitted (no tier registered): {name}"}
        tier = self.tiers[name]
        if tier == CapabilityTier.T4_CONFIRM:
            ok = bool(self._confirm(name, args)) if self._confirm is not None else False
            if not ok:
                return {"error": f"tool '{name}' requires human confirmation", "needs_confirmation": True}
        return self.registry.call(name, **(args or {}))
