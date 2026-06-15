from __future__ import annotations

from datetime import date as Date
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.baselines import ChaseBiggestGainerPolicy, NoTradePolicy
from alpha.eval.metrics import EvalReport
from alpha.eval.contribution import ContributionReport, contribution_split
from alpha.eval.scorer import ReturnScorer
from alpha.eval.stats import StatVerdict, daily_series, paired_daily_diff, verdict
from alpha.eval.trajectory import Trajectory, report_from_trajectory
from alpha.eval.walk_forward import WalkForwardEval
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig, LoopReport
from alpha.refine.refiner import RefinerConfig


def daily_advantage(traj: Trajectory) -> dict[Date, float]:
    """Per-decision-day mean advantage from a Trajectory (empty/no-trade day -> 0.0, NOT excluded).
    Byte-identical to InnerLoop's internal breaker_days rule, so the Hexpert series and HCH's own
    series are the same lens — this is the shadow reference for HCH's paired breaker."""
    out: dict[Date, float] = {}
    for step in traj.scored_steps():
        advs = [c.advantage for c in step.outcomes.values()]
        out[step.date] = sum(advs) / len(advs) if advs else 0.0
    return out


class ArmReport(BaseModel):
    """One arm's result. n_refines/n_breaker_trips/frozen_from are HCH-only (None for frozen/baseline arms)."""
    model_config = ConfigDict(frozen=True)
    name: str
    report: EvalReport
    n_refines: int | None = None
    n_breaker_trips: int | None = None
    frozen_from: Date | None = None


class ComparisonReport(BaseModel):
    """Three-tier compare (four arms). The North-Star verdict is on the EXCESS (advantage) delta,
    de-market-beta (spec §7). A later `stat_verdict` can be added as an additive Optional field."""
    model_config = ConfigDict(frozen=True)
    arms: dict[str, ArmReport] = Field(default_factory=dict)
    hch_minus_hexpert_mean_excess: float
    hch_minus_hexpert_mean_score: float
    hch_minus_hexpert_hit_rate: float
    hch_minus_hexpert_nuke_rate: float
    hch_beats_hexpert: bool
    hch_loop_report: LoopReport | None = None
    stat_verdict: StatVerdict | None = None         # paired HCH-Hexpert day-level decision (CI/p/MDE)
    contribution: ContributionReport | None = None  # HCH offense/defense + per-family split


def compare_harnesses(harness_factory: Callable[[], HarnessState], source, start: Date, end: Date, *,
                      agent_llm_factory: Callable[[], LLMClient],
                      refiner_llm_factory: Callable[[], LLMClient],
                      store_factory: Callable[[], SnapshotStore],
                      loop_config: LoopConfig | None = None,
                      refiner_config: RefinerConfig | None = None,
                      scorer_factory: Callable[[], object] | None = None,
                      shadow: bool = False) -> ComparisonReport:
    """Run HCH (self-refining InnerLoop) vs Hexpert (frozen seed H + agent, NO Refiner) vs Hmin
    (chase-biggest-gainer + no-trade) on the SAME source/window/horizon/scorer. All inputs are FACTORIES
    so each arm gets a fresh H / LLM client / store (no cross-arm pollution; MockLLMClient is stateful).
    When shadow=True, Hexpert runs FIRST and its daily_advantage seeds HCH's paired breaker.
    scorer_factory MUST return a STATELESS scorer (the wf instance's scorer is shared across Hexpert +
    both Hmin arms); ReturnScorer (the default) is stateless."""
    cfg = loop_config or LoopConfig()
    scorer_factory = scorer_factory or (lambda: ReturnScorer())
    wf = WalkForwardEval(source, start, end, horizon=cfg.horizon, scorer=scorer_factory())

    # Hexpert FIRST when shadow (its series seeds HCH); frozen H = bare agent walk, no Refiner/manager.
    hexpert_traj = wf.walk(LLMAgentPolicy(harness_factory(), agent_llm_factory())) if shadow else None

    # HCH = self-refining InnerLoop (optionally shadow-gated against the Hexpert reference series)
    mgr = HarnessManager(harness_factory(), store_factory())
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                     config=cfg, refiner_config=refiner_config, scorer=scorer_factory(),
                     shadow_daily=(daily_advantage(hexpert_traj) if shadow else None))
    lr = loop.run()
    hch_eval = report_from_trajectory(lr.trajectory, horizon=cfg.horizon)

    # Hexpert (reuse the shadow pre-run trajectory, else run it now)
    if hexpert_traj is None:
        hexpert_traj = wf.walk(LLMAgentPolicy(harness_factory(), agent_llm_factory()))
    hexpert_eval = report_from_trajectory(hexpert_traj, horizon=cfg.horizon)

    # Hmin floor baselines (deterministic, no LLM/H/store)
    hmin_chase = wf.run(ChaseBiggestGainerPolicy())
    hmin_notrade = wf.run(NoTradePolicy())

    arms = {
        "HCH": ArmReport(name="HCH", report=hch_eval, n_refines=len(lr.refine_events),
                         n_breaker_trips=len(lr.breaker_events), frozen_from=lr.frozen_from),
        "Hexpert": ArmReport(name="Hexpert", report=hexpert_eval),
        "Hmin_chase": ArmReport(name="Hmin_chase", report=hmin_chase),
        "Hmin_notrade": ArmReport(name="Hmin_notrade", report=hmin_notrade),
    }
    # §9/§10 acceptance procedure: paired day-level verdict (HCH - Hexpert) + offense/defense split.
    diffs = paired_daily_diff(daily_series(lr.trajectory), daily_series(hexpert_traj))
    stat = verdict(diffs)
    contribution = contribution_split(lr.trajectory, mgr.harness)   # resolve against the evolved HCH H

    d_excess = hch_eval.mean_excess - hexpert_eval.mean_excess
    return ComparisonReport(
        arms=arms,
        hch_minus_hexpert_mean_excess=d_excess,
        hch_minus_hexpert_mean_score=hch_eval.mean_score - hexpert_eval.mean_score,
        hch_minus_hexpert_hit_rate=hch_eval.hit_rate - hexpert_eval.hit_rate,
        hch_minus_hexpert_nuke_rate=hch_eval.nuke_rate - hexpert_eval.nuke_rate,
        hch_beats_hexpert=(d_excess > 0.0),
        hch_loop_report=lr,
        stat_verdict=stat,
        contribution=contribution,
    )


class MultiWindowReport(BaseModel):
    """Honest-bar DIAGNOSTIC across N (start, end) windows. NOTE: few/short-window excess deltas are
    NOISE (MDE ~0.26 at ~30 trading days, spec §12) — this surfaces the direction/distribution
    (win-rate, sign-consistency), it is NOT a significance test. Formal CI/MDE/purged-CV are deferred."""
    model_config = ConfigDict(frozen=True)
    n_windows: int
    deltas: list[float] = Field(default_factory=list)   # hch_minus_hexpert_mean_excess per window
    mean_delta: float = 0.0
    win_rate: float = 0.0                                # fraction of windows with delta > 0
    sign_consistent: bool = False                       # all deltas strictly same sign
    # A ROLLUP of per-window single-window verdicts (each a within-window CI), NOT a pooled cross-window
    # significance test — cohort-level inference stays the win_rate / sign-consistency direction diagnostic.
    verdicts: list[str] = Field(default_factory=list)             # per-window stat-verdict labels
    verdict_tally: dict[str, int] = Field(default_factory=dict)   # counts by label across windows


def multi_window(harness_factory: Callable[[], HarnessState], source,
                 windows: list[tuple[Date, Date]], *,
                 agent_llm_factory: Callable[[], LLMClient],
                 refiner_llm_factory: Callable[[], LLMClient],
                 store_factory: Callable[[], SnapshotStore],
                 loop_config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None,
                 scorer_factory: Callable[[], object] | None = None,
                 shadow: bool = False) -> MultiWindowReport:
    """Run compare_harnesses over each window; aggregate the excess deltas. A direction diagnostic, not
    a significance test (see MultiWindowReport)."""
    deltas: list[float] = []
    verdicts: list[str] = []
    for (start, end) in windows:
        cr = compare_harnesses(harness_factory, source, start, end, agent_llm_factory=agent_llm_factory,
                               refiner_llm_factory=refiner_llm_factory, store_factory=store_factory,
                               loop_config=loop_config, refiner_config=refiner_config,
                               scorer_factory=scorer_factory, shadow=shadow)
        deltas.append(cr.hch_minus_hexpert_mean_excess)
        verdicts.append(cr.stat_verdict.verdict if cr.stat_verdict is not None else "insufficient")
    n = len(deltas)
    mean_delta = sum(deltas) / n if n else 0.0
    win_rate = sum(1 for d in deltas if d > 0.0) / n if n else 0.0
    sign_consistent = n > 0 and (all(d > 0.0 for d in deltas) or all(d < 0.0 for d in deltas))
    tally: dict[str, int] = {}
    for v in verdicts:
        tally[v] = tally.get(v, 0) + 1
    return MultiWindowReport(n_windows=n, deltas=deltas, mean_delta=mean_delta, win_rate=win_rate,
                             sign_consistent=sign_consistent, verdicts=verdicts, verdict_tally=tally)
