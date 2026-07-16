"""Subagent (A) write-waist ops routed through the ONE gate (try_apply_op) — the sixth Body
component's waist, mirroring the connector + workflow op tests.

Covers create/patch/retire through MetaTools + the subagent lints (description char cap +
tools-subset: a `tools` name outside the registerable parent set is refused) + the
worker-propose refusal (charter A7).
"""
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.connectors import ConnectorRegistry
from alpha.harness.workflows import WorkflowRegistry
from alpha.harness.subagents import SubagentRegistry  # noqa: F401
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.refine.apply import try_apply_op


def _h():
    return HarnessState(doctrine=Doctrine(entries=[]), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]), connectors=ConnectorRegistry.empty(),
                        workflows=WorkflowRegistry.empty(), subagents=SubagentRegistry.empty())


def _args(**kw):
    a = dict(subagent_id="screener", name="Screener",
             description="find gap-up leaders and summarize",
             system_prompt="You surface the day's leaders.",
             tools=["market_snapshot", "decide"])
    a.update(kw)
    return a


def _apply(h, log, tool, args, rationale="because", **kw):
    return try_apply_op(MetaTools(h, log), h, RefineOp(tool=tool, args=args, rationale=rationale),
                        allowed=PASS_TOOLS["A"], min_retire_samples=0, min_promote_samples=0, **kw)


def test_write_subagent_creates_entry():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_subagent", _args())
    assert reason is None and rec is not None
    a = h.subagents.get("screener")
    assert a is not None and a.name == "Screener"
    assert rec.target_kind == "subagent" and rec.op == "create"
    assert a.tools == ["market_snapshot", "decide"] and a.status == "active"


def test_write_subagent_rejects_overlong_description():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_subagent", _args(description="x" * 1537))
    assert rec is None and "description" in reason


def test_write_subagent_allows_max_description():
    """A description exactly at the 1536-char budget is accepted (boundary)."""
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_subagent", _args(description="x" * 1536))
    assert reason is None and rec is not None


def test_write_subagent_rejects_tool_outside_registerable_set():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_subagent",
                         _args(tools=["decide", "shell_exec"]))
    assert rec is None and "tools" in reason


def test_write_subagent_allows_registerable_tool_subset():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_subagent",
                         _args(tools=["view_doctrine", "search_episodes", "view_subagent"]))
    assert reason is None and rec is not None


def test_patch_subagent_updates_fields():
    h, log = _h(), EditLog()
    _apply(h, log, "write_subagent", _args())
    rec, reason = _apply(h, log, "patch_subagent",
                         {"subagent_id": "screener", "name": "Renamed"})
    assert reason is None and h.subagents.get("screener").name == "Renamed"


def test_patch_subagent_relint_rejects_bad_tool():
    """A follow-up patch cannot smuggle a non-registerable tool past the create-time lint."""
    h, log = _h(), EditLog()
    _apply(h, log, "write_subagent", _args())
    rec, reason = _apply(h, log, "patch_subagent",
                         {"subagent_id": "screener", "tools": ["decide", "rm_rf"]})
    assert rec is None and "tools" in reason


def test_patch_subagent_unknown_id_rejected_cleanly():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "patch_subagent", {"subagent_id": "ghost", "name": "x"})
    assert rec is None and reason


def test_retire_subagent_sets_retired():
    h, log = _h(), EditLog()
    _apply(h, log, "write_subagent", _args())
    rec, reason = _apply(h, log, "retire_subagent", {"subagent_id": "screener"})
    assert reason is None and h.subagents.get("screener").status == "retired"


def test_subagent_op_refused_for_worker_proposer():
    h, log = _h(), EditLog()
    rec, reason = try_apply_op(MetaTools(h, log), h,
                               RefineOp(tool="write_subagent", args=_args(), rationale="x"),
                               allowed=PASS_TOOLS["A"], min_retire_samples=0, min_promote_samples=0,
                               provenance=EditProvenance(path="self_study", proposer="kairos"))
    assert rec is None and reason  # worker-propose refusal fires first (charter A7)
