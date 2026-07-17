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


# ── Item 1: patch_connector must re-VALIDATE the merged entry (no model_copy bypass) ────────────
def test_patch_connector_rejects_invalid_bool_value():
    """A non-bool `enabled` (e.g. "maybe") must bounce at the lint — model_copy(update=) used to
    store it un-validated, which then bricked to_dict()->from_dict() (LiveBrainStore.load)."""
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    rec, reason = _apply(h, log, "patch_connector",
                         {"connector_id": "alpaca", "enabled": "maybe"})
    assert rec is None and reason                              # rejected, reason truthy
    assert h.connectors.get("alpaca").enabled is True         # unchanged (patch never landed)


def test_patch_connector_rejects_scalar_for_list_field():
    """env_keys is list[str]; a bare string must be refused, not coerced into per-char keys."""
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    rec, reason = _apply(h, log, "patch_connector",
                         {"connector_id": "alpaca", "env_keys": "APCA_API_KEY_ID"})
    assert rec is None and reason


def test_connector_patches_round_trip_without_brick():
    """After a series of valid patches, to_dict()->from_dict() must round-trip (brick scenario closed)."""
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    _apply(h, log, "patch_connector", {"connector_id": "alpaca", "notes": "n1"})
    _apply(h, log, "patch_connector", {"connector_id": "alpaca", "enabled": False})
    _apply(h, log, "patch_connector", {"connector_id": "alpaca", "instructions": "updated bars."})
    h2 = HarnessState.from_dict(h.to_dict())                   # no ValidationError
    c = h2.connectors.get("alpaca")
    assert c.notes == "n1" and c.enabled is False and c.instructions == "updated bars."


# ── Item 2: write_connector is an upsert (create/replace) — a replace must log what it clobbered ──
def test_write_connector_replace_logs_non_none_before():
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args(notes="original"))
    _apply(h, log, "write_connector", _args(notes="replacement"))
    last = log.records()[-1]
    assert last.payload["before"] is not None                 # the clobbered entry is audited
    assert last.payload["before"]["notes"] == "original"
    assert last.payload["after"]["notes"] == "replacement"


def test_write_connector_fresh_id_logs_none_before():
    h, log = _h(), EditLog()
    _apply(h, log, "write_connector", _args())
    assert log.records()[-1].payload["before"] is None        # a true create records no clobber


class _FakeQueue:
    def __init__(self): self.items = []
    def add(self, **kw): self.items.append(kw)


def test_write_connector_self_study_replace_over_teaching_is_held():
    """A self-study write_connector replacing a teaching-owned entry is held for adjudication
    (write_connector is now a _CONTEST_VERB — it can contest on replace, no-op on a fresh id)."""
    h, log = _h(), EditLog()
    try_apply_op(MetaTools(h, log), h,
                 RefineOp(tool="write_connector", args=_args(), rationale="seed"),
                 allowed=PASS_TOOLS["C"], min_retire_samples=0, min_promote_samples=0,
                 provenance=EditProvenance(path="teaching", proposer="sonia"))
    q = _FakeQueue()
    rec, reason = try_apply_op(MetaTools(h, log), h,
                               RefineOp(tool="write_connector", args=_args(notes="machine"),
                                        rationale="self-study wants to replace"),
                               allowed=PASS_TOOLS["C"], min_retire_samples=0, min_promote_samples=0,
                               provenance=EditProvenance(path="self_study", proposer="refiner"),
                               conflict_queue=q)
    assert rec is None and "held_for_review" in reason
    assert len(q.items) == 1


def test_write_connector_self_study_fresh_id_not_held():
    """A fresh-id self-study write_connector is NOT held (latest_for -> None): contest only on replace."""
    h, log = _h(), EditLog()
    q = _FakeQueue()
    rec, reason = try_apply_op(MetaTools(h, log), h,
                               RefineOp(tool="write_connector", args=_args(), rationale="new"),
                               allowed=PASS_TOOLS["C"], min_retire_samples=0, min_promote_samples=0,
                               provenance=EditProvenance(path="self_study", proposer="refiner"),
                               conflict_queue=q)
    assert reason is None and rec is not None and q.items == []


# ── kind="mcp" connectors: impl_ref resolves against the operator MCP registry (server_names) ────
def test_write_connector_mcp_resolves_registered_server(monkeypatch):
    import alpha.mcp.registry as mcp_reg
    from alpha.mcp.registry import McpServerSpec
    monkeypatch.setitem(mcp_reg._SERVERS, "demo",
                        McpServerSpec(server_id="demo", command=["demo-server"], allowed_tools=["echo"]))
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_connector",
                         _args(connector_id="demo", name="Demo MCP", kind="mcp", impl_ref="demo",
                               capabilities=["echo"], env_keys=["DEMO_TOKEN"], instructions="demo."))
    assert reason is None and rec is not None
    assert h.connectors.get("demo").kind == "mcp"


def test_write_connector_mcp_rejects_unregistered_server():
    h, log = _h(), EditLog()                                   # registry ships empty -> "ghost" unresolvable
    rec, reason = _apply(h, log, "write_connector",
                         _args(connector_id="ghost", name="Ghost", kind="mcp", impl_ref="ghost",
                               capabilities=[], env_keys=[], instructions="x"))
    assert rec is None and "impl_ref" in reason


def test_connector_impl_resolves_mcp_unit(monkeypatch):
    """Direct unit over the write-waist predicate: mcp resolves against the MCP registry; data_source
    lint byte-identical."""
    import alpha.mcp.registry as mcp_reg
    from alpha.mcp.registry import McpServerSpec
    from alpha.refine.apply import _connector_impl_resolves
    monkeypatch.setitem(mcp_reg._SERVERS, "demo", McpServerSpec(server_id="demo", command=["x"]))
    ok = ConnectorEntry(connector_id="c", name="c", kind="mcp", impl_ref="demo")
    bad = ConnectorEntry(connector_id="c", name="c", kind="mcp", impl_ref="nope")
    assert _connector_impl_resolves(ok) is True and _connector_impl_resolves(bad) is False
    ds = ConnectorEntry(connector_id="c", name="c", kind="data_source", impl_ref="alpaca")
    assert _connector_impl_resolves(ds) is True                # data_source path unchanged
