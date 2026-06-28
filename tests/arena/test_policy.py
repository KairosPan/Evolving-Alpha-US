from alpha.arena.contract import CapabilityTier
from alpha.arena.policy import ActivityPolicy
from alpha.converse.registry import ToolRegistry


def _registry():
    reg = ToolRegistry()
    reg.register("look", {"name": "look"}, lambda: {"saw": "ok"})
    reg.register("send", {"name": "send"}, lambda to: {"sent": to})
    return reg


def test_untiered_tool_is_fail_closed():
    reg = _registry()
    pol = ActivityPolicy(reg, tiers={"look": CapabilityTier.T0_OBSERVE})   # "send" has NO tier
    assert pol.dispatch("look", {}) == {"saw": "ok"}
    out = pol.dispatch("send", {"to": "x"})
    assert "error" in out and "tier" in out["error"].lower()


def test_t4_blocked_without_confirmation():
    reg = ToolRegistry()
    ran: list[str] = []
    reg.register("send", {"name": "send"}, lambda to: (ran.append(to), {"sent": to})[1])
    pol = ActivityPolicy(reg, tiers={"send": CapabilityTier.T4_CONFIRM})
    out = pol.dispatch("send", {"to": "x"})
    assert out.get("needs_confirmation") is True
    assert ran == []   # the fn must NOT have run without confirmation


def test_t4_runs_when_confirmed():
    reg = _registry()
    pol = ActivityPolicy(reg, tiers={"send": CapabilityTier.T4_CONFIRM},
                         confirm=lambda name, args: True)
    assert pol.dispatch("send", {"to": "x"}) == {"sent": "x"}
