# tests/refine/test_task_forge.py
"""Task 18 (PC-9) — deterministic task proposer (forge twin).

Coverage:
  (a) propose_task_skill_ops emits promote_skill ONLY for domain="operational" incubating skills
      that meet the floor; trading skills yield NO op even with great task episodes.
  (b) forge_task_skills stamps every applied EditRecord with evidence_kind="task".
  (c) PINNING — the proposer ALWAYS stamps evidence_kind="task" (verdict 5 weakest-link guard).
  (d) operational skills below the sample/confirmed/success-rate floor yield no op.
"""
from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.task_forge import propose_task_skill_ops, forge_task_skills

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _skill(sid: str, status: str, domain: str = "trading") -> Skill:
    return Skill(skill_id=sid, name=sid, type="pattern", family="runner", phases=["trend"],
                 status=status, domain=domain)


def _h(*skills: Skill) -> HarnessState:
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills(list(skills)),
                        memory=MemoryStore.from_lessons([]))


def _store(*eps: Episode) -> EpisodeStore:
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s


_ep_counter = 0


def _task_ep(skill_id: str, outcome: str, exit_d: date = date(2026, 6, 3)) -> Episode:
    """Build a task episode with a unique episode_id so INSERT OR IGNORE keeps every row."""
    global _ep_counter
    _ep_counter += 1
    eid = f"task:{skill_id}:{outcome}:{exit_d.isoformat()}:{_ep_counter}"
    return Episode(
        episode_id=eid,
        symbol="",          # tasks have no symbol
        skill_id=skill_id,
        kind="task",
        entry_date=exit_d,
        exit_date=exit_d,
        outcome=outcome,
        advantage=0.0,
    )


def _confirmed(*eps: Episode) -> frozenset[str]:
    return frozenset(e.episode_id for e in eps)


_ASOF = date(2026, 6, 20)

# ---------------------------------------------------------------------------
# (a) domain guard — operational gets proposal, trading never does
# ---------------------------------------------------------------------------

def test_proposes_promote_for_operational_not_trading():
    """(a) promote_skill only for domain='operational'; trading domain ⇒ no op."""
    op_skill = _skill("op1", "incubating", domain="operational")
    tr_skill = _skill("tr1", "incubating", domain="trading")
    h = _h(op_skill, tr_skill)

    op_eps = [_task_ep("op1", "succeeded") for _ in range(3)]
    tr_eps = [_task_ep("tr1", "succeeded") for _ in range(3)]
    store = _store(*op_eps, *tr_eps)

    # both skills have identical confirmed floor coverage
    confirmed = _confirmed(*op_eps, *tr_eps)

    pairs = propose_task_skill_ops(store, h, asof=_ASOF, confirmed_ids=confirmed,
                                   promote_min_samples=3, promote_min_confirmed=3,
                                   promote_min_success_rate=0.5)

    proposed_ids = {op.args["skill_id"] for op, _ in pairs}
    assert "op1" in proposed_ids, "operational incubating skill must be proposed"
    assert "tr1" not in proposed_ids, "trading skill must NEVER be proposed"


def test_trading_skill_great_episodes_yields_zero_ops():
    """Explicit zero-op guard: a trading skill with n=10 confirmed successes ⇒ no op."""
    tr_skill = _skill("tr_great", "incubating", domain="trading")
    h = _h(tr_skill)

    eps = [_task_ep("tr_great", "succeeded") for _ in range(10)]
    store = _store(*eps)
    confirmed = _confirmed(*eps)

    pairs = propose_task_skill_ops(store, h, asof=_ASOF, confirmed_ids=confirmed)
    assert pairs == [], "trading skill must produce no proposals regardless of task episode quality"


# ---------------------------------------------------------------------------
# (b) evidence_kind="task" stamped on every EditRecord
# ---------------------------------------------------------------------------

def test_applied_records_stamped_evidence_kind_task():
    """(b) forge_task_skills stamps evidence_kind='task' on every applied EditRecord."""
    op_skill = _skill("op2", "incubating", domain="operational")
    h = _h(op_skill)

    eps = [_task_ep("op2", "succeeded") for _ in range(3)]
    store = _store(*eps)
    confirmed = _confirmed(*eps)

    log = EditLog()
    meta = MetaTools(h, log)
    rep = forge_task_skills(h, store, meta, asof=_ASOF, confirmed_ids=confirmed,
                             min_task_samples=3, min_task_confirmed_samples=3,
                             min_task_success_rate=0.5)

    assert rep.applied == ["op2"], f"expected op2 applied, got {rep}"
    # The promoted skill should now be active
    assert h.skills.get("op2").status == "active"

    # Every record in the log that has a provenance must carry evidence_kind="task"
    records = log.records()
    assert records, "at least one EditRecord expected"
    for rec in records:
        if rec.provenance is not None:
            assert rec.provenance.evidence_kind == "task", (
                f"record seq={rec.seq} has evidence_kind={rec.provenance.evidence_kind!r}, expected 'task'")


# ---------------------------------------------------------------------------
# (c) PINNING — proposer ALWAYS stamps evidence_kind="task" (verdict 5)
# ---------------------------------------------------------------------------

def test_pinning_always_stamps_evidence_kind_task():
    """(c) Pinning: forge_task_skills ALWAYS stamps evidence_kind='task' across multiple skills."""
    skills = [_skill(f"ops{i}", "incubating", domain="operational") for i in range(3)]
    h = _h(*skills)

    all_eps: list[Episode] = []
    for sk in skills:
        all_eps.extend(_task_ep(sk.skill_id, "succeeded") for _ in range(3))

    store = _store(*all_eps)
    confirmed = _confirmed(*all_eps)

    log = EditLog()
    meta = MetaTools(h, log)
    forge_task_skills(h, store, meta, asof=_ASOF, confirmed_ids=confirmed,
                      min_task_samples=3, min_task_confirmed_samples=3,
                      min_task_success_rate=0.5)

    # Every record that carries a provenance MUST have evidence_kind="task".
    # A trade-evidenced op from this proposer is architecturally impossible.
    for rec in log.records():
        if rec.provenance is not None:
            assert rec.provenance.evidence_kind == "task", (
                f"PINNING FAILED: record seq={rec.seq} skill={rec.target_id!r} "
                f"has evidence_kind={rec.provenance.evidence_kind!r}")


# ---------------------------------------------------------------------------
# (d) below the floor ⇒ no op
# ---------------------------------------------------------------------------

def test_below_sample_floor_no_op():
    """(d) proposer: n < promote_min_samples ⇒ no proposal."""
    op_skill = _skill("op_low_n", "incubating", domain="operational")
    h = _h(op_skill)

    # Only 2 episodes (below promote_min_samples=3)
    eps = [_task_ep("op_low_n", "succeeded") for _ in range(2)]
    store = _store(*eps)
    confirmed = _confirmed(*eps)

    pairs = propose_task_skill_ops(store, h, asof=_ASOF, confirmed_ids=confirmed,
                                   promote_min_samples=3, promote_min_confirmed=3,
                                   promote_min_success_rate=0.5)
    assert pairs == [], "below sample floor: no proposal"


def test_below_confirmed_floor_no_op():
    """(d) proposer: confirmed_n < promote_min_confirmed ⇒ no proposal."""
    op_skill = _skill("op_no_confirm", "incubating", domain="operational")
    h = _h(op_skill)

    # 5 episodes but none confirmed (confirmed_ids empty)
    eps = [_task_ep("op_no_confirm", "succeeded") for _ in range(5)]
    store = _store(*eps)

    pairs = propose_task_skill_ops(store, h, asof=_ASOF, confirmed_ids=frozenset(),
                                   promote_min_samples=3, promote_min_confirmed=3,
                                   promote_min_success_rate=0.5)
    assert pairs == [], "no confirmed episodes: no proposal"


def test_below_success_rate_floor_no_op():
    """(d) proposer: confirmed_success_rate < promote_min_success_rate ⇒ no proposal."""
    op_skill = _skill("op_low_rate", "incubating", domain="operational")
    h = _h(op_skill)

    # 3 failed episodes, all confirmed → confirmed_success_rate = 0.0 < 0.5
    eps = [_task_ep("op_low_rate", "failed") for _ in range(3)]
    store = _store(*eps)
    confirmed = _confirmed(*eps)

    pairs = propose_task_skill_ops(store, h, asof=_ASOF, confirmed_ids=confirmed,
                                   promote_min_samples=3, promote_min_confirmed=3,
                                   promote_min_success_rate=0.5)
    assert pairs == [], "low confirmed success rate: no proposal"


def test_gate_rejects_when_confirmed_n_below_gate_floor():
    """(d) gate-side: proposer passes but gate's min_task_confirmed_samples blocks apply."""
    op_skill = _skill("op_gate", "incubating", domain="operational")
    h = _h(op_skill)

    # 5 episodes, only 1 confirmed → proposer passes (promote_min_confirmed=1) but gate blocks (min=3)
    eps = [_task_ep("op_gate", "succeeded") for _ in range(5)]
    store = _store(*eps)
    confirmed = frozenset({eps[0].episode_id})   # only 1 confirmed

    log = EditLog()
    meta = MetaTools(h, log)
    rep = forge_task_skills(h, store, meta, asof=_ASOF, confirmed_ids=confirmed,
                             promote_min_samples=3,
                             promote_min_confirmed=1,     # proposer lets it through
                             promote_min_success_rate=0.0,
                             min_task_samples=3,
                             min_task_confirmed_samples=3,   # gate blocks
                             min_task_success_rate=0.0)

    assert rep.applied == [], "gate should block when confirmed_n < gate floor"
    assert any("op_gate" in sid for sid, _ in rep.rejected), "op_gate should appear in rejected"


# ---------------------------------------------------------------------------
# status guard — only incubating gets promote; active with great episodes stays unchanged
# ---------------------------------------------------------------------------

def test_active_operational_not_promoted():
    """An ACTIVE operational skill is never proposed for promote (promote is incubating-only)."""
    op_skill = _skill("op_active", "active", domain="operational")
    h = _h(op_skill)

    eps = [_task_ep("op_active", "succeeded") for _ in range(5)]
    store = _store(*eps)
    confirmed = _confirmed(*eps)

    pairs = propose_task_skill_ops(store, h, asof=_ASOF, confirmed_ids=confirmed)
    promote_ops = [op for op, _ in pairs if op.tool == "promote_skill"]
    assert promote_ops == [], "active skill must not be proposed for promote"
