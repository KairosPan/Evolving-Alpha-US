# tests/refine/test_apply_separation.py
"""PB-9/PC-5: evidence-kind carrier + domain-aware separation gate.
PC-8 (Task 17): gate-side task floor (verdict 3 + 5).

PB-9 (still valid):
(a) Back-compat: EditProvenance without evidence_kind has .evidence_kind is None.
(b) task-evidenced ops targeting non-operational H are rejected before trade floors.
(c) evidence_kind=None is byte-identical to today (existing passing op still applies).

PC-5 (new in Task 14):
(d) task-evidenced op targeting domain="trading" element → rejected with domain-aware message.
(e) task-evidenced op targeting missing/legacy element (domain=None) → rejected (fail-closed).
(f) task-evidenced op targeting domain="operational" element → PASSES separation, applied + logged.
(g) a task op that is also a self-study-vs-teaching conflict is REJECTED on domain grounds, not held.

PC-8 (new in Task 17): gate-side task floor lives at the waist (BEFORE _dispatch):
(h) task_stats=None → reject (fail-closed).
(i) confirmed_n < min_task_confirmed_samples → reject.
(j) confirmed_success_rate < min_task_success_rate → reject.
(k) all floors met + operational skill with n==0/expectancy=None → dispatch succeeds,
    trade promote-floor is bypassed (stats never consulted).
"""
from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import TaskStats
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import PASS_TOOLS, RefineOp


def _h(skills=None):
    sk = skills or []
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills(sk),
        memory=MemoryStore.from_lessons([]),
    )


def _skill(sid, status="incubating", n=10, expectancy=0.5, domain="trading"):
    return Skill(skill_id=sid, name=sid, type="pattern", status=status,
                 stats=SkillStats(n=n, expectancy=expectancy), domain=domain)


def _passing_task_stats(confirmed_n=3, confirmed_success=2) -> TaskStats:
    """A TaskStats that passes the strict default floor knobs (confirmed_n>=3, rate>=0.5)."""
    return TaskStats(n=confirmed_n + 2, succeeded=confirmed_success, failed=1,
                     incomplete=1, confirmed_success=confirmed_success,
                     confirmed_n=confirmed_n)


# ── (a) back-compat: evidence_kind defaults to None ─────────────────────────

def test_edit_provenance_evidence_kind_defaults_to_none():
    p = EditProvenance(path="self_study", proposer="refiner")
    assert p.evidence_kind is None


def test_edit_provenance_evidence_kind_explicit_trade():
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="trade")
    assert p.evidence_kind == "trade"


def test_edit_provenance_evidence_kind_explicit_task():
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    assert p.evidence_kind == "task"


# ── (b) task-evidenced op is blanket-rejected (short-circuits trade floors) ──

def test_task_evidence_rejects_memory_op():
    """Task-evidenced process_memory is rejected with the separation message."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L1", "phases": ["trend"], "outcome": "win", "lesson": "x"},
                  rationale="came from a task run")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    assert len(log) == 0  # nothing written


def test_task_evidence_rejects_skill_op():
    """Task-evidenced write_skill is rejected with the separation message."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="write_skill",
                  args={"skill_id": "s1", "name": "s1", "type": "pattern",
                        "trigger": "t", "action": "a", "guard": "g",
                        "phases": ["trend"], "lesson": "works"},
                  rationale="came from task evidence")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    assert len(log) == 0


def test_task_evidence_rejects_doctrine_op():
    """Task-evidenced rewrite_doctrine is rejected with the separation message."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="rewrite_doctrine",
                  args={"section": "risk_rules", "new_guidance": "never lose"},
                  rationale="task insight")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["p"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    assert len(log) == 0


def test_task_evidence_short_circuits_trade_floors():
    """A task-evidenced promote_skill on a skill with n>=min and expectancy>0 (would pass the
    trade floor) is still rejected by the separation wall, proving we short-circuit the floors."""
    # Build a skill that WOULD pass the promote trade floor (n=10, expectancy=0.5, status=incubating)
    sk = _skill("s_good", status="incubating", n=10, expectancy=0.5)
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="promote_skill", args={"skill_id": "s_good"}, rationale="task says ready")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    # The skill was NOT promoted (the wall held)
    assert h.skills.get("s_good").status == "incubating"
    assert len(log) == 0


# ── (c) evidence_kind=None is byte-identical (existing passing op still applies) ──

def test_none_evidence_kind_applies_normally():
    """Op with evidence_kind=None (or absent provenance) applies just like today."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L2", "phases": ["trend"], "outcome": "win", "lesson": "y"},
                  rationale="trade-based learning")
    # None explicitly
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind=None)
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert reason is None
    assert rec is not None
    assert len(log) == 1


def test_no_provenance_applies_normally():
    """Op without any provenance (legacy path) is completely unaffected."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L3", "phases": ["trend"], "outcome": "win", "lesson": "z"},
                  rationale="legacy path")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3)
    assert reason is None
    assert rec is not None
    assert len(log) == 1


# ── PC-4 (a): set-once relabel guard (ALL provenances) ──────────────────────

def test_set_once_guard_patch_skill_any_provenance():
    """patch_skill with domain in args is rejected for any provenance."""
    h = _h(skills=[_skill("s1")]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="patch_skill", args={"skill_id": "s1", "domain": "operational"},
                  rationale="trying to relabel")
    # trade provenance
    p_trade = EditProvenance(path="self_study", proposer="refiner", evidence_kind=None)
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p_trade)
    assert rec is None
    assert reason == "domain is set-once; cannot be relabeled"
    assert len(log) == 0


def test_set_once_guard_patch_skill_task_provenance():
    """patch_skill with domain in args is rejected even for task provenance."""
    h = _h(skills=[_skill("s2")]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="patch_skill", args={"skill_id": "s2", "domain": "trading"},
                  rationale="trying to relabel back")
    p_task = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p_task)
    assert rec is None
    assert reason == "domain is set-once; cannot be relabeled"
    assert len(log) == 0


def test_set_once_guard_patch_skill_no_provenance():
    """patch_skill with domain in args is rejected even with no provenance."""
    h = _h(skills=[_skill("s3")]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="patch_skill", args={"skill_id": "s3", "domain": "operational"},
                  rationale="no provenance relabel")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3)
    assert rec is None
    assert reason == "domain is set-once; cannot be relabeled"
    assert len(log) == 0


def test_set_once_guard_update_memory_any_provenance():
    """update_memory with domain in args is rejected for any provenance (guard fires before dispatch)."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="update_memory", args={"lesson_id": "L9", "domain": "operational"},
                  rationale="trying to relabel memory")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3)
    assert rec is None
    assert reason == "domain is set-once; cannot be relabeled"
    assert len(log) == 0


# ── PC-4 (b): create-path mislabel guard (trade-evidenced operational create) ─

def test_create_guard_trade_evidenced_write_skill_operational():
    """A trade-evidenced write_skill declaring domain='operational' is rejected."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="write_skill",
                  args={"skill_id": "s_op", "name": "s_op", "type": "pattern",
                        "trigger": "t", "action": "a", "guard": "g",
                        "phases": ["trend"], "lesson": "works",
                        "domain": "operational"},
                  rationale="minting an operational skill under trade evidence")
    p_trade = EditProvenance(path="self_study", proposer="refiner", evidence_kind=None)
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p_trade)
    assert rec is None
    assert reason == "create may not mint operational under trade evidence"
    assert len(log) == 0


def test_create_guard_no_provenance_write_skill_operational():
    """A no-provenance write_skill declaring domain='operational' is also rejected."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="write_skill",
                  args={"skill_id": "s_op2", "name": "s_op2", "type": "pattern",
                        "trigger": "t", "action": "a", "guard": "g",
                        "phases": ["trend"], "lesson": "works",
                        "domain": "operational"},
                  rationale="minting operational with no provenance")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3)
    assert rec is None
    assert reason == "create may not mint operational under trade evidence"
    assert len(log) == 0


def test_create_guard_trade_evidenced_process_memory_operational():
    """A trade-evidenced process_memory declaring domain='operational' is rejected."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "L_op", "phases": ["trend"], "outcome": "win",
                        "lesson": "op lesson", "domain": "operational"},
                  rationale="minting operational memory under trade evidence")
    p_trade = EditProvenance(path="self_study", proposer="refiner", evidence_kind="trade")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p_trade)
    assert rec is None
    assert reason == "create may not mint operational under trade evidence"
    assert len(log) == 0


def test_create_guard_trade_evidenced_write_skill_trading_passes():
    """A trade-evidenced write_skill with domain='trading' (explicit) is NOT blocked by the create guard."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    # Use only valid Skill fields so this reaches dispatch successfully
    op = RefineOp(tool="write_skill",
                  args={"skill_id": "s_tr", "name": "s_tr", "type": "pattern",
                        "trigger": "look for runner", "phases": ["trend"],
                        "domain": "trading", "taboo": ["thesis broken"]},   # PC-9: trading pattern needs a taboo
                  rationale="normal trading create")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3)
    assert reason is None
    assert rec is not None
    assert len(log) == 1


# ── PC-9: red-line lint — a NEW trading pattern skill MUST carry >=1 taboo (魂骨宪法 §4) ──

def _pc9_op(*, type="pattern", domain="trading", taboo=None):
    args = {"skill_id": "s", "name": "S", "type": type, "trigger": "t", "phases": ["trend"]}
    if domain is not None:
        args["domain"] = domain
    if taboo is not None:
        args["taboo"] = taboo
    return RefineOp(tool="write_skill", args=args, rationale="create")


def _apply_k(h, op):
    meta = MetaTools(h, EditLog())
    return try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                        min_retire_samples=5, min_promote_samples=3)


def test_pc9_taboo_less_trading_pattern_is_rejected():
    rec, reason = _apply_k(_h(), _pc9_op(taboo=[]))          # empty taboo
    assert rec is None and reason is not None and "red-line" in reason
    rec2, reason2 = _apply_k(_h(), _pc9_op(taboo=None))      # missing taboo -> same reject
    assert rec2 is None and "red-line" in reason2


def test_pc9_trading_pattern_with_a_taboo_passes():
    rec, reason = _apply_k(_h(), _pc9_op(taboo=["thesis broken"]))
    assert reason is None and rec is not None


def test_pc9_exempts_non_pattern_skills():
    # a feature/failure_detector isn't a "do X" pattern -> no taboo required
    rec, reason = _apply_k(_h(), _pc9_op(type="feature", taboo=[]))
    assert reason is None and rec is not None


def test_pc9_default_domain_trading_is_covered():
    # domain omitted defaults to 'trading' -> the lint still fires (no relabel escape)
    rec, reason = _apply_k(_h(), _pc9_op(domain=None, taboo=[]))
    assert rec is None and "red-line" in reason


# operational patterns are structurally exempt: an operational create routes through the
# task-evidence branch (returns before PC-9), and a TRADE-evidenced operational create is already
# rejected by PC-4 — so PC-9 never sees an operational pattern. (Covered by the PC-4/PC-5 tests.)


# ── PC-9 patch-bypass closure (review-confirmed 2026-07-13): type/taboo are freely patchable, so a
#    create-only gate is defeated by a follow-up patch — PC-9 also fires on patch_skill. ──

def _sk(sid, *, type="pattern", domain="trading", taboo=None):
    return Skill(skill_id=sid, name=sid, type=type, domain=domain,
                 taboo=(taboo if taboo is not None else ["thesis broken"]))


def test_pc9_patch_feature_to_trading_pattern_without_taboo_is_rejected():
    # Vector 4a: an exempt trading FEATURE (no taboo) patched INTO a pattern -> would be a red-line-less
    # trading pattern; the patch is rejected.
    h = _h(skills=[_sk("sf", type="feature", taboo=[])])
    rec, reason = _apply_k(h, RefineOp(tool="patch_skill", args={"skill_id": "sf", "type": "pattern"},
                                       rationale="flip to pattern"))
    assert rec is None and "red-line" in reason


def test_pc9_patch_stripping_taboo_from_a_trading_pattern_is_rejected():
    # Vector 4b: an already-passed trading pattern patched to an EMPTY taboo -> strips the red-line; rejected.
    h = _h(skills=[_sk("sp", taboo=["thesis broken"])])
    rec, reason = _apply_k(h, RefineOp(tool="patch_skill", args={"skill_id": "sp", "taboo": []},
                                       rationale="strip the taboo"))
    assert rec is None and "red-line" in reason


def test_pc9_patch_flip_to_pattern_WITH_a_taboo_passes():
    # feature -> pattern in ONE patch that also supplies a taboo -> the result is a valid red-lined pattern.
    h = _h(skills=[_sk("sf2", type="feature", taboo=[])])
    rec, reason = _apply_k(h, RefineOp(
        tool="patch_skill", args={"skill_id": "sf2", "type": "pattern", "taboo": ["thesis broken"]},
        rationale="flip with a taboo"))
    assert reason is None and rec is not None


def test_pc9_patch_not_touching_type_or_taboo_is_not_relinted():
    # A patch to an unrelated field on a (grandfathered) taboo-less trading pattern is NOT re-linted —
    # PC-9 only fires when the patch itself touches type/taboo (no over-reach on unrelated edits).
    h = _h(skills=[_sk("sg", type="pattern", taboo=[])])          # a pre-existing taboo-less pattern
    rec, reason = _apply_k(h, RefineOp(tool="patch_skill", args={"skill_id": "sg", "trigger": "new t"},
                                       rationale="edit trigger only"))
    assert reason is None and rec is not None


def test_pc9_blank_taboo_string_is_not_a_red_line():
    # taboo=[''] is a non-empty list but a BLANK red-line -> PC-9 rejects it at create (loophole closed).
    rec, reason = _apply_k(_h(), _pc9_op(taboo=[""]))
    assert rec is None and "red-line" in reason


# ── PC-4 (c) → PC-5: task-evidenced create with domain='operational' now SUCCEEDS ──

def test_create_guard_task_evidenced_write_skill_operational_now_succeeds():
    """PC-5/PC-8: task-evidenced write_skill(domain='operational') passes the separation gate
    and the task floor (passing task_stats) and is applied + logged."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="write_skill",
                  args={"skill_id": "s_op3", "name": "s_op3", "type": "pattern",
                        "trigger": "operational trigger",
                        "phases": ["trend"],
                        "domain": "operational"},
                  rationale="task evidence, operational domain")
    p_task = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p_task,
                               task_stats=_passing_task_stats())
    # Operational target: passes separation gate + task floor, applied + logged.
    assert reason is None
    assert rec is not None
    assert len(log) == 1
    # Provenance is stamped on the record.
    assert log.records()[-1].provenance is not None
    assert log.records()[-1].provenance.evidence_kind == "task"


# ── PC-5: domain-aware separation gate ──────────────────────────────────────

def test_domain_aware_gate_trading_domain_skill_rejected():
    """PC-5 (a): task-evidenced op targeting an explicit domain='trading' skill is rejected
    with the domain-aware message (not the old blanket message)."""
    sk = Skill(skill_id="s_tr", name="s_tr", type="pattern", status="incubating",
               stats=SkillStats(n=10, expectancy=0.5))  # domain defaults to "trading"
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="promote_skill", args={"skill_id": "s_tr"}, rationale="task says promote")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason == "separation: task-evidence may only target operational H (target domain=trading)"
    assert len(log) == 0


def test_domain_aware_gate_missing_target_rejected():
    """PC-5 (b): task-evidenced op targeting a non-existent skill (domain=None, fail-closed)
    is rejected."""
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="promote_skill", args={"skill_id": "ghost"}, rationale="no such skill")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert rec is None
    assert reason == "separation: task-evidence may only target operational H (target domain=None)"
    assert len(log) == 0


def test_domain_aware_gate_operational_skill_passes():
    """PC-5/PC-8 (c): task-evidenced patch_skill on a domain='operational' skill passes the
    separation gate and the task floor (passing task_stats) and is applied + logged."""
    from alpha.harness.skill import Skill, SkillStats
    sk = Skill(skill_id="s_op_ex", name="s_op_ex", type="pattern", status="incubating",
               stats=SkillStats(n=0, expectancy=None), domain="operational")
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    # patch_skill on an operational skill (n=0 would fail the promote floor — proves short-circuit)
    op = RefineOp(tool="patch_skill",
                  args={"skill_id": "s_op_ex", "notes": "operational check"},
                  rationale="task-evidence operational patch")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p,
                               task_stats=_passing_task_stats())
    assert reason is None
    assert rec is not None
    assert len(log) == 1
    assert log.records()[-1].provenance is not None and log.records()[-1].provenance.evidence_kind == "task"


def test_domain_aware_gate_task_conflict_rejected_on_domain_not_held():
    """PC-5: a task-evidenced op that is ALSO a self-study-vs-teaching conflict is rejected
    on domain grounds (separation gate fires before the conflict queue)."""
    class _FakeQueue:
        def __init__(self): self.items = []
        def add(self, **kw): self.items.append(kw)

    # Skill owned by teaching (default trading domain)
    sk = _skill("s_teach", status="incubating", n=10, expectancy=0.5)
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    # Stamp a teaching-owned edit for s_teach so is_conflict() fires
    teach_prov = EditProvenance(path="teaching", proposer="sonia")
    teach_op = RefineOp(tool="patch_skill",
                        args={"skill_id": "s_teach", "notes": "sonia updated"},
                        rationale="teaching update")
    try_apply_op(meta, h, teach_op, allowed=PASS_TOOLS["K"],
                 min_retire_samples=5, min_promote_samples=3, provenance=teach_prov)
    assert len(log) == 1

    # Now a task-evidenced self-study op contests the same teaching-owned element
    cq = _FakeQueue()
    task_op = RefineOp(tool="patch_skill",
                       args={"skill_id": "s_teach", "notes": "task update"},
                       rationale="task contests teaching")
    p_task = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, task_op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=p_task, conflict_queue=cq)
    # Domain=trading → rejected by separation gate, NOT held in conflict queue
    assert rec is None
    assert reason is not None and reason.startswith("separation:")
    assert len(cq.items) == 0  # conflict queue untouched


# ── PC-8 (Task 17): gate-side task floor ────────────────────────────────────

def test_task_floor_none_task_stats_fails_closed():
    """PC-8 (h): task-evidenced op targeting operational H with task_stats=None is rejected
    (fail-closed). The caller MUST supply task evidence; None is not a bypass."""
    sk = _skill("s_op_fc", domain="operational", n=0, expectancy=None, status="incubating")
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="patch_skill",
                  args={"skill_id": "s_op_fc", "notes": "floor test"},
                  rationale="task evidence, no stats")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p,
                               task_stats=None)
    assert rec is None
    assert reason is not None and "task floor" in reason
    assert len(log) == 0


def test_task_floor_insufficient_confirmed_n_rejects():
    """PC-8 (i): task_stats.confirmed_n < min_task_confirmed_samples → reject."""
    sk = _skill("s_op_cn", domain="operational", n=0, expectancy=None, status="incubating")
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="patch_skill",
                  args={"skill_id": "s_op_cn", "notes": "floor test"},
                  rationale="task evidence, low confirmed_n")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    low_stats = TaskStats(n=5, succeeded=3, failed=1, incomplete=1,
                          confirmed_success=1, confirmed_n=2)  # confirmed_n=2 < 3
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p,
                               task_stats=low_stats, min_task_confirmed_samples=3)
    assert rec is None
    assert reason is not None and "task floor" in reason
    assert len(log) == 0


def test_task_floor_insufficient_success_rate_rejects():
    """PC-8 (j): confirmed_success_rate < min_task_success_rate → reject."""
    sk = _skill("s_op_sr", domain="operational", n=0, expectancy=None, status="incubating")
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="patch_skill",
                  args={"skill_id": "s_op_sr", "notes": "floor test"},
                  rationale="task evidence, low success rate")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    # confirmed_n=4 >= 3 (passes confirmed_n check), but rate=0.25 < 0.5
    low_rate_stats = TaskStats(n=5, succeeded=1, failed=3, incomplete=1,
                               confirmed_success=1, confirmed_n=4)
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p,
                               task_stats=low_rate_stats,
                               min_task_confirmed_samples=3, min_task_success_rate=0.5)
    assert rec is None
    assert reason is not None and "task floor" in reason
    assert len(log) == 0


def test_task_floor_all_met_promotes_n0_skill_bypasses_trade_floor():
    """PC-8 (k): all task floors met → promote_skill dispatches successfully on an operational
    skill with stats.n==0 / expectancy=None, proving:
    (1) the task floor governs (sufficient confirmed evidence gates the op), AND
    (2) the trade promote-floor is fully bypassed (n=0 would block a trade promote)."""
    sk = Skill(skill_id="s_op_promo", name="s_op_promo", type="pattern", status="incubating",
               stats=SkillStats(n=0, expectancy=None), domain="operational")
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="promote_skill", args={"skill_id": "s_op_promo"},
                  rationale="task evidence: n=0 operational skill, task floor met")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    passing_stats = TaskStats(n=5, succeeded=3, failed=1, incomplete=1,
                              confirmed_success=2, confirmed_n=3)
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p,
                               task_stats=passing_stats,
                               min_task_confirmed_samples=3, min_task_success_rate=0.5)
    # Task floor met + trade floor bypassed → promotes successfully
    assert reason is None, f"unexpected rejection: {reason}"
    assert rec is not None
    assert len(log) == 1
    # Skill was actually promoted (status changed from incubating)
    assert h.skills.get("s_op_promo").status != "incubating"
    # Provenance stamped correctly
    assert log.records()[-1].provenance is not None
    assert log.records()[-1].provenance.evidence_kind == "task"


def test_task_floor_zero_confirmations_default_rejects():
    """RED→GREEN: PC-8 default-floor gate is now strict.

    task_stats has task evidence (n=5, all succeeded) but ZERO external confirmations
    (confirmed_n=0, confirmed_success=0).  With the OLD defaults (0/0.0) this would
    PASS; with the new strict defaults (min_task_confirmed_samples=3, min_task_success_rate=0.5)
    it must be REJECTED — proving the anti-Goodhart floor is on by default.
    """
    sk = Skill(skill_id="s_op_zero", name="s_op_zero", type="pattern", status="incubating",
               stats=SkillStats(n=0, expectancy=None), domain="operational")
    h = _h(skills=[sk]); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="promote_skill", args={"skill_id": "s_op_zero"},
                  rationale="task shows all success but zero external confirmations")
    p = EditProvenance(path="self_study", proposer="refiner", evidence_kind="task")
    zero_conf_stats = TaskStats(n=5, succeeded=5, failed=0, incomplete=0,
                                confirmed_success=0, confirmed_n=0)
    # Do NOT pass explicit min_task_* — use the defaults, which are now strict.
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p,
                               task_stats=zero_conf_stats)
    # Zero confirmed evidence cannot promote — default gate rejects.
    assert rec is None, "expected rejection but got a record"
    assert reason is not None and "task floor" in reason and "confirmed_n" in reason, (
        f"expected task-floor/confirmed_n rejection, got: {reason!r}"
    )
    assert len(log) == 0  # nothing written
