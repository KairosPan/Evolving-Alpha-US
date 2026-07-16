"""Connector (C) write-waist ops routed through the ONE gate (try_apply_op).

Mirrors the K/M op tests: create/patch/disable through MetaTools + the structural lints
(impl_ref must resolve, env_keys must be env-var NAMES only, instructions char cap) + the
worker-propose refusal (charter A7) that fires for every tool before any content check.
"""
from alpha.harness.connectors import ConnectorEntry, ConnectorRegistry  # noqa: F401
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.refine.apply import try_apply_op


def _h():
    return HarnessState(doctrine=Doctrine(entries=[]), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]), connectors=ConnectorRegistry.empty())


def _args(**kw):
    a = dict(connector_id="alpaca", name="Alpaca", kind="data_source", impl_ref="alpaca",
             capabilities=["bars"], env_keys=["APCA_API_KEY_ID"], instructions="bars.")
    a.update(kw)
    return a


def _apply(h, log, tool, args, rationale="because", **kw):
    return try_apply_op(MetaTools(h, log), h, RefineOp(tool=tool, args=args, rationale=rationale),
                        allowed=PASS_TOOLS["C"], min_retire_samples=0, min_promote_samples=0, **kw)


def test_write_connector_creates_entry():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector", _args())
    assert reason is None and rec is not None
    assert h.connectors.get("alpaca").impl_ref == "alpaca"
    assert rec.target_kind == "connector" and rec.op == "create"


def test_write_connector_rejects_unresolvable_impl_ref():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector", _args(impl_ref="not_a_real_source"))
    assert rec is None and "impl_ref" in reason


def test_write_connector_rejects_value_shaped_env_key():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector", _args(env_keys=["APCA_KEY=sk-secret-value"]))
    assert rec is None and "env_keys" in reason


def test_write_connector_rejects_overlong_instructions():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector", _args(instructions="x" * 2001))
    assert rec is None and "instructions" in reason


def test_write_connector_accepts_llm_role_impl_ref():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector",
                         _args(connector_id="agent_llm", name="Agent LLM", kind="llm_role",
                               impl_ref="agent", env_keys=["ALPHA_AGENT_MODEL"]))
    assert reason is None and rec is not None


def test_patch_connector_updates_fields():
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    rec, reason = _apply(h, log, "patch_connector", {"connector_id": "alpaca", "notes": "note"})
    assert reason is None and h.connectors.get("alpaca").notes == "note"


def test_patch_connector_relint_rejects_bad_env_key():
    """A follow-up patch cannot defeat the create-time lint (PC-9 pattern)."""
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    rec, reason = _apply(h, log, "patch_connector",
                         {"connector_id": "alpaca", "env_keys": ["K=leak"]})
    assert rec is None and "env_keys" in reason


def test_patch_connector_unknown_id_rejected_cleanly():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "patch_connector", {"connector_id": "ghost", "notes": "x"})
    assert rec is None and reason


def test_disable_connector_sets_enabled_false():
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    rec, reason = _apply(h, log, "disable_connector", {"connector_id": "alpaca"})
    assert reason is None and h.connectors.get("alpaca").enabled is False


def test_connector_op_refused_for_worker_proposer():
    h, log = _h(), EditLog()
    rec, reason = try_apply_op(MetaTools(h, log), h,
                               RefineOp(tool="write_connector", args=_args(), rationale="x"),
                               allowed=PASS_TOOLS["C"], min_retire_samples=0, min_promote_samples=0,
                               provenance=EditProvenance(path="self_study", proposer="kairos"))
    assert rec is None and reason  # worker-propose refusal fires first (charter A7)
