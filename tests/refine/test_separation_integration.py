# tests/refine/test_separation_integration.py
"""PC-11 — composite separation + anti-gaming end-to-end integration test.

Pins the full invariants described in the PB/PC design spec (§3.1-§3.4 + verdict 5):

(a) Full path — task evidence cannot move ANY trading skill.
    forge_task_skills (the task proposer) emits no op for trading skills even with perfect
    task evidence; direct gate calls also reject (promote + retire).

(b) No relabel-then-promote laundering path.
    patch_skill(domain=...) is set-once-rejected for every provenance; the skill remains
    domain="trading", so a subsequent task-evidenced promote is also rejected.

(c) Anti-Goodhart (verdict 5).
    A stream of agent-authored default-pass "succeeded" episodes with ZERO external
    confirmations (confirmed_ids=frozenset()) yields confirmed_n=0 from summarize_task.
    The propose_task_skill_ops proposer emits no op; the gate also rejects directly.
    The operational skill is NOT promoted.

(d) Verdict-neutrality — composite filter hold.
    compare_harnesses numbers are bit-identical when the harness contains operational
    elements AND the recall brain.db contains kind="task" episodes, vs a baseline without
    them.  This pins the PC-6 read-side domain filter (operational skills excluded from
    the trading prompt) AND the for_asof(kind="trade") fence (task rows excluded from
    the verdict path) working TOGETHER.

If any sub-assertion fails, report which invariant leaked — do NOT loosen a guard.
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.data.source import FakeSource
from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.loader import load_seeds
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.state import HarnessState
from alpha.llm.client import MockLLMClient
from alpha.loop.compare import compare_harnesses
from alpha.loop.inner_loop import LoopConfig
from alpha.memory.aggregate import TaskStats, summarize_task
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import PASS_TOOLS, RefineOp
from alpha.refine.task_forge import forge_task_skills, propose_task_skill_ops

SEEDS = Path(__file__).resolve().parents[2] / "seeds"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _h(skills=None):
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills(skills or []),
        memory=MemoryStore.from_lessons([]),
    )


def _skill(sid: str, *, status: str = "incubating", n: int = 10,
           expectancy: float | None = 0.5, domain: str = "trading") -> Skill:
    return Skill(skill_id=sid, name=sid, type="pattern", status=status,
                 stats=SkillStats(n=n, expectancy=expectancy), domain=domain)


_ep_ctr = 0


def _task_ep(skill_id: str, outcome: str = "succeeded",
             asof: date = date(2026, 6, 1)) -> Episode:
    """Build a task episode with a unique ID so INSERT OR IGNORE keeps every row."""
    global _ep_ctr
    _ep_ctr += 1
    return Episode(
        episode_id=f"task:{skill_id}:{outcome}:{asof.isoformat()}:{_ep_ctr}",
        symbol="",
        skill_id=skill_id,
        kind="task",
        entry_date=asof,
        exit_date=asof,
        outcome=outcome,
        advantage=0.0,
        learned_asof=asof,
    )


def _store(*eps: Episode) -> EpisodeStore:
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s


_ASOF = date(2026, 6, 20)

_PASSING_TASK_STATS = TaskStats(
    n=5, succeeded=4, failed=0, incomplete=1,
    confirmed_success=3, confirmed_n=3,
)


# ===========================================================================
# (a) Full path — task evidence cannot move ANY trading skill
# ===========================================================================

def test_proposer_skips_trading_skill_entirely():
    """propose_task_skill_ops emits NO op for a trading skill, even with perfect confirmed evidence.
    This is the proposer-level domain gate — the first wall before the gate even sees the op."""
    tr = _skill("tr_a_prop", status="incubating", domain="trading")
    h = _h(skills=[tr])
    eps = [_task_ep("tr_a_prop", "succeeded") for _ in range(5)]
    store = _store(*eps)
    confirmed = frozenset(e.episode_id for e in eps)

    pairs = propose_task_skill_ops(
        store, h, asof=_ASOF, confirmed_ids=confirmed,
        promote_min_samples=3, promote_min_confirmed=3, promote_min_success_rate=0.5,
    )
    assert pairs == [], (
        "proposer must emit ZERO ops for domain='trading' skills — "
        f"got: {[(op.tool, op.args) for op, _ in pairs]}"
    )


def test_forge_applies_zero_ops_for_trading_skill():
    """forge_task_skills (full task proposer) applies nothing for a trading skill.
    Tests the full propose-gate-apply path end-to-end."""
    tr = _skill("tr_a_forge", status="incubating", domain="trading")
    h = _h(skills=[tr])
    eps = [_task_ep("tr_a_forge", "succeeded") for _ in range(5)]
    store = _store(*eps)
    confirmed = frozenset(e.episode_id for e in eps)

    log = EditLog(); meta = MetaTools(h, log)
    report = forge_task_skills(
        h, store, meta, asof=_ASOF, confirmed_ids=confirmed,
        promote_min_samples=3, promote_min_confirmed=3, promote_min_success_rate=0.5,
        min_task_samples=3, min_task_confirmed_samples=3, min_task_success_rate=0.5,
    )

    assert report.applied == [], f"trading skill must not be applied: {report.applied}"
    assert h.skills.get("tr_a_forge").status == "incubating"
    assert len(log) == 0


def test_direct_gate_rejects_task_promote_on_trading_skill():
    """Direct gate call: task-evidenced promote_skill on a trading skill → separation rejected.
    Even with passing task_stats the separation wall stands."""
    tr = _skill("tr_a_direct_promo", status="incubating", n=10, expectancy=0.5, domain="trading")
    h = _h(skills=[tr])
    log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="promote_skill", args={"skill_id": "tr_a_direct_promo"},
                  rationale="task evidence — promote")
    p = EditProvenance(path="self_study", proposer="forge", evidence_kind="task")

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=p, task_stats=_PASSING_TASK_STATS)

    assert rec is None
    assert reason is not None and "separation:" in reason and "trading" in reason, (
        f"expected separation rejection with 'trading' in message, got: {reason!r}"
    )
    assert h.skills.get("tr_a_direct_promo").status == "incubating"
    assert len(log) == 0


def test_direct_gate_rejects_task_retire_on_trading_skill():
    """Direct gate call: task-evidenced retire_skill on a trading skill → separation rejected.
    Retire (not just promote) is also blocked — the wall is not op-specific."""
    tr = _skill("tr_a_direct_retire", status="active", n=20, expectancy=0.5, domain="trading")
    h = _h(skills=[tr])
    log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="retire_skill", args={"skill_id": "tr_a_direct_retire"},
                  rationale="task evidence — retire")
    p = EditProvenance(path="self_study", proposer="forge", evidence_kind="task")
    retire_stats = TaskStats(n=10, succeeded=0, failed=8, incomplete=2,
                             confirmed_success=0, confirmed_n=5)

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=p, task_stats=retire_stats)

    assert rec is None
    assert reason is not None and "separation:" in reason
    assert h.skills.get("tr_a_direct_retire").status == "active"  # unchanged
    assert len(log) == 0


# ===========================================================================
# (b) No relabel-then-promote — set-once guard closes the laundering path
# ===========================================================================

def test_laundering_sequence_both_steps_rejected():
    """Full laundering sequence: attempt relabel then promote.
    Step 1 (relabel): patch_skill(domain='operational') → set-once rejected.
    Step 2 (promote): skill still domain='trading' → separation rejected.
    Nothing written; skill remains incubating and domain='trading' throughout."""
    tr = _skill("tr_b_launder", status="incubating", n=10, expectancy=0.5, domain="trading")
    h = _h(skills=[tr])
    log = EditLog(); meta = MetaTools(h, log)

    # Step 1: attempt relabel via task evidence
    relabel = RefineOp(tool="patch_skill",
                       args={"skill_id": "tr_b_launder", "domain": "operational"},
                       rationale="attempting to launder trading skill to operational")
    p_task = EditProvenance(path="self_study", proposer="forge", evidence_kind="task")
    rec1, reason1 = try_apply_op(meta, h, relabel, allowed=PASS_TOOLS["K"],
                                 min_retire_samples=5, min_promote_samples=3, provenance=p_task)

    assert rec1 is None
    assert reason1 == "domain is set-once; cannot be relabeled", (
        f"expected set-once rejection, got: {reason1!r}"
    )
    assert h.skills.get("tr_b_launder").domain == "trading", "domain must remain 'trading' after failed relabel"
    assert len(log) == 0

    # Step 2: attempt promote with passing task stats — skill still domain='trading'
    promote = RefineOp(tool="promote_skill", args={"skill_id": "tr_b_launder"},
                       rationale="task says promote after 'relabel'")
    rec2, reason2 = try_apply_op(meta, h, promote, allowed=PASS_TOOLS["K"],
                                 min_retire_samples=5, min_promote_samples=3,
                                 provenance=p_task, task_stats=_PASSING_TASK_STATS)

    assert rec2 is None
    assert reason2 is not None and "separation:" in reason2, (
        f"expected separation rejection after failed relabel, got: {reason2!r}"
    )
    assert h.skills.get("tr_b_launder").status == "incubating", "skill must NOT be promoted"
    assert len(log) == 0, "nothing must be written after the full laundering sequence"


def test_relabel_rejected_for_all_provenances():
    """patch_skill(domain=...) is blocked for trade provenance, task provenance, and no provenance.
    Belt-and-suspenders: the set-once guard is provenance-agnostic."""
    tr = _skill("tr_b_all_prov", domain="trading")
    provenances = [
        EditProvenance(path="self_study", proposer="refiner", evidence_kind="trade"),
        EditProvenance(path="self_study", proposer="forge", evidence_kind="task"),
        None,
    ]
    for prov in provenances:
        h = _h(skills=[tr])
        log = EditLog(); meta = MetaTools(h, log)
        op = RefineOp(tool="patch_skill",
                      args={"skill_id": "tr_b_all_prov", "domain": "operational"},
                      rationale="relabel attempt")
        rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                                   min_retire_samples=5, min_promote_samples=3, provenance=prov)
        assert rec is None, f"relabel must be rejected for provenance={prov!r}"
        assert reason == "domain is set-once; cannot be relabeled", (
            f"wrong rejection for provenance={prov!r}: {reason!r}"
        )
        assert len(log) == 0


# ===========================================================================
# (c) Anti-Goodhart: zero confirmed_ids → confirmed_n=0 → gate rejects
# ===========================================================================

def test_summarize_task_zero_confirmed_ids_yields_confirmed_n_zero():
    """summarize_task with confirmed_ids=frozenset() yields confirmed_n=0 regardless of n.
    This is the aggregate-level proof: agent-authored successes without external confirmation
    are neutral — n/succeeded rise, confirmed_n stays zero."""
    eps = [_task_ep("op_c_sk", "succeeded") for _ in range(10)]
    store = _store(*eps)
    task_rows = store.for_asof(_ASOF, kind="task", limit=None)
    stats = summarize_task(task_rows, key=lambda e: e.skill_id, confirmed_ids=frozenset())
    s = stats.get("op_c_sk")

    assert s is not None
    assert s.n == 10, f"expected n=10, got {s.n}"
    assert s.succeeded == 10
    assert s.confirmed_n == 0, (
        f"expected confirmed_n=0 with empty confirmed_ids, got {s.confirmed_n}"
    )
    assert s.confirmed_success == 0
    assert s.confirmed_success_rate == 0.0


def test_proposer_emits_no_op_when_zero_confirmed():
    """propose_task_skill_ops emits no op for an operational skill with zero confirmed_ids.
    The proposer-side confirmed floor blocks the proposal before the gate is reached."""
    op_sk = _skill("op_c_prop", status="incubating", domain="operational", n=0, expectancy=None)
    h = _h(skills=[op_sk])
    eps = [_task_ep("op_c_prop", "succeeded") for _ in range(10)]
    store = _store(*eps)

    pairs = propose_task_skill_ops(
        store, h, asof=_ASOF,
        confirmed_ids=frozenset(),          # ← the anti-Goodhart key: empty
        promote_min_samples=3,
        promote_min_confirmed=3,            # floor: need >= 3 confirmed
        promote_min_success_rate=0.5,
    )
    assert pairs == [], (
        "proposer must emit NO op when confirmed_ids is empty (confirmed_n=0 < 3)"
    )


def test_forge_does_not_promote_operational_with_zero_confirmed():
    """forge_task_skills (full end-to-end) does not promote an operational skill when
    all task episodes are agent-authored with zero external confirmations."""
    op_sk = _skill("op_c_forge", status="incubating", domain="operational", n=0, expectancy=None)
    h = _h(skills=[op_sk])
    eps = [_task_ep("op_c_forge", "succeeded") for _ in range(10)]
    store = _store(*eps)

    log = EditLog(); meta = MetaTools(h, log)
    report = forge_task_skills(
        h, store, meta, asof=_ASOF,
        confirmed_ids=frozenset(),          # ← anti-Goodhart: no external confirmation
        promote_min_samples=3,
        promote_min_confirmed=3,
        promote_min_success_rate=0.5,
        min_task_samples=3,
        min_task_confirmed_samples=3,
        min_task_success_rate=0.5,
    )

    assert report.applied == [], (
        f"operational skill must NOT be promoted when confirmed_ids empty: {report}"
    )
    assert h.skills.get("op_c_forge").status == "incubating", "skill status must remain incubating"
    assert len(log) == 0


def test_gate_rejects_direct_task_promote_with_zero_confirmed_n():
    """Direct gate call: task-evidenced promote with TaskStats(confirmed_n=0) → task floor rejected.
    This is the gate-level proof — even if the proposer somehow bypassed, the waist holds."""
    op_sk = _skill("op_c_direct", status="incubating", domain="operational", n=0, expectancy=None)
    h = _h(skills=[op_sk])
    log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="promote_skill", args={"skill_id": "op_c_direct"},
                  rationale="10 agent-authored successes, zero external confirmations")
    p = EditProvenance(path="self_study", proposer="forge", evidence_kind="task")
    zero_conf = TaskStats(n=10, succeeded=10, failed=0, incomplete=0,
                          confirmed_success=0, confirmed_n=0)

    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["K"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=p, task_stats=zero_conf)

    assert rec is None, f"expected gate rejection, got a record: {rec}"
    assert reason is not None and "task floor" in reason and "confirmed_n" in reason, (
        f"expected task-floor/confirmed_n rejection, got: {reason!r}"
    )
    assert h.skills.get("op_c_direct").status == "incubating"
    assert len(log) == 0


# ===========================================================================
# (d) Verdict-neutrality: operational elements + task episodes → bit-identical
# ===========================================================================

def _verdict_source(n: int = 6, rate: float = 1.15) -> FakeSource:
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes: list[float] = []
    for d in cal:
        prev = px
        px = px * rate
        closes.append(px)
        snaps[d] = pd.DataFrame(
            {"symbol": ["RUN"], "name": ["RUN"],
             "open": [prev], "high": [px],
             "low": [prev], "close": [px],
             "volume": [1], "prev_close": [prev]},
        )
    bars = {
        "RUN": pd.DataFrame(
            {"date": cal,
             "open": [10.0] + closes[:-1], "high": closes,
             "low": [10.0] + closes[:-1], "close": closes,
             "volume": [1] * n},
        )
    }
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _harness_with_operational() -> HarnessState:
    """Load the real seeds then inject one operational skill.
    The operational skill must be excluded from the trading prompt by the PC-6 domain filter."""
    h = load_seeds(SEEDS)
    op_skill = Skill(
        skill_id="op_verdict_pin",
        name="Operational Verdict Pin",
        type="pattern",
        status="incubating",
        domain="operational",
        trigger="n/a",
        phases=["trend"],
    )
    h.skills.write(op_skill)
    return h


def _run_verdict(recall_store) -> object:
    src = _verdict_source()
    return compare_harnesses(
        _harness_with_operational,
        src,
        src.trading_calendar()[0],
        src.trading_calendar()[-1],
        agent_llm_factory=lambda: MockLLMClient(
            '{"regime_read": "trend", "candidates": '
            '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'
        ),
        refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
        store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
        loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1),
        recall_store=recall_store,
    )


def test_verdict_neutral_with_operational_skill_and_task_episodes():
    """compare_harnesses numbers are bit-identical when BOTH invariants are present:
    - harness has an operational skill (PC-6 read-side domain filter must exclude it), AND
    - recall brain.db has kind='task' episodes (for_asof(kind='trade') fence must exclude them).

    Run 1: operational harness + clean store (no task rows).
    Inject task episodes attributed to the operational skill.
    Run 2: same operational harness + same store (now has task rows).
    All headline + supporting numbers must be bit-identical.

    If this fails, either:
      - build_system_prompt is rendering an operational skill into the trading prompt, OR
      - a verdict-path consumer is calling for_asof(kind=None) and seeing task rows.
    Fix the call site; do NOT loosen either filter.
    """
    store = EpisodeStore.in_memory()

    # Run 1: operational harness + clean store (no task episodes)
    cr1 = _run_verdict(recall_store=store)

    # Inject task episodes for the operational skill (PIT-visible: learned_asof <= window start)
    for i in range(8):
        store.add(Episode(
            episode_id=f"task:op_verdict_pin:integration:{i}",
            symbol="",
            skill_id="op_verdict_pin",
            kind="task",
            entry_date=date(2026, 6, 1),
            exit_date=date(2026, 6, 1),
            outcome="succeeded",
            advantage=0.0,
            learned_asof=date(2026, 6, 1),
        ))

    # Run 2: same operational harness + store now has task rows
    cr2 = _run_verdict(recall_store=store)

    # All verdict numbers must be bit-identical (both PC-6 + kind="trade" fence hold together)
    assert cr1.hch_minus_hexpert_mean_excess == cr2.hch_minus_hexpert_mean_excess, (
        f"hch_minus_hexpert_mean_excess changed: "
        f"{cr1.hch_minus_hexpert_mean_excess!r} -> {cr2.hch_minus_hexpert_mean_excess!r}. "
        "PC-6 read-side domain filter OR for_asof(kind='trade') fence may have leaked."
    )
    assert cr1.hch_minus_hexpert_mean_score == cr2.hch_minus_hexpert_mean_score
    assert cr1.hch_minus_hexpert_hit_rate == cr2.hch_minus_hexpert_hit_rate
    assert cr1.hch_minus_hexpert_nuke_rate == cr2.hch_minus_hexpert_nuke_rate
    assert cr1.hch_beats_hexpert == cr2.hch_beats_hexpert

    # Per-arm candidate counts (taboo/recall must not see task rows)
    assert cr1.arms["HCH"].report.n_candidates == cr2.arms["HCH"].report.n_candidates
    assert cr1.arms["Hexpert"].report.n_candidates == cr2.arms["Hexpert"].report.n_candidates
