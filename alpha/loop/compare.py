from __future__ import annotations

from datetime import date as Date
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.baselines import ChaseBiggestGainerPolicy, NoTradePolicy
from alpha.eval.metrics import EvalReport
from alpha.eval.ablation import ablate_credit
from alpha.eval.contribution import ContributionReport, contribution_split
from alpha.eval.purged_cv import embargo_trajectory
from alpha.eval.scorer import ReturnScorer
from alpha.eval.stats import StatVerdict, daily_series, paired_daily_diff, verdict
from alpha.eval.stratify import regime_key_for, stratified_verdicts
from alpha.eval.trajectory import Trajectory, report_from_trajectory
from alpha.eval.walk_forward import WalkForwardEval
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.state import HarnessState
from alpha.guard.screen import GuardedPolicy
from alpha.sizing.policy import SizingPolicy
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
    de-market-beta (spec §7). `stat_verdict` (paired day-level CI/p/MDE) and `contribution`
    (offense/defense + per-family) are additive-Optional fields (US-2e) computed inline in compare_harnesses."""
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
    # P6 additive-Optional (default None -> byte-identical): per-regime paired HCH-Hexpert verdicts
    # (stratify=True) and the Hcredit ABLATION delta HCH - HCH_nocredit (credit_ablation=True; a
    # diagnostic, NOT the North-Star verdict). HCH_nocredit rides in `arms` when present.
    stratified: dict[str, StatVerdict] | None = None
    hch_minus_nocredit_mean_excess: float | None = None


def compare_harnesses(harness_factory: Callable[[], HarnessState], source, start: Date, end: Date, *,
                      agent_llm_factory: Callable[[], LLMClient],
                      refiner_llm_factory: Callable[[], LLMClient],
                      store_factory: Callable[[], SnapshotStore],
                      loop_config: LoopConfig | None = None,
                      refiner_config: RefinerConfig | None = None,
                      scorer_factory: Callable[[], object] | None = None,
                      shadow: bool = False, recall_store=None,
                      embargo: int = 0, credit_ablation: bool = False,
                      stratify: bool = False) -> ComparisonReport:
    """Run HCH (self-refining InnerLoop) vs Hexpert (frozen seed H + agent, NO Refiner) vs Hmin
    (chase-biggest-gainer + no-trade) on the SAME source/window/horizon/scorer. All inputs are FACTORIES
    so each arm gets a fresh H / LLM client / store (no cross-arm pollution; MockLLMClient is stateful).
    When shadow=True, Hexpert runs FIRST and its daily_advantage seeds HCH's paired breaker.
    scorer_factory MUST return a STATELESS scorer (the wf instance's scorer is shared across Hexpert +
    both Hmin arms); ReturnScorer (the default) is stateless.

    P6 (all additive/default-off -> byte-identical when unset): `embargo` drops `embargo` trailing
    scored decisions from EVERY arm's reporting view (symmetric right-edge purged-CV; the loop still
    refines internally over its full set — a measurement fence, not a live-decision change);
    `credit_ablation` adds an `HCH_nocredit` arm (credit seam removed) + the ablation delta;
    `stratify` attaches per-regime paired HCH-Hexpert verdicts under the run's vocabulary."""
    cfg = loop_config or LoopConfig()
    scorer_factory = scorer_factory or (lambda: ReturnScorer())
    wf = WalkForwardEval(source, start, end, horizon=cfg.horizon, scorer=scorer_factory())

    # HCH (InnerLoop) auto-wraps its agent in GuardedPolicy (L4) + SizingPolicy (L3) via _rebind when
    # cfg.screen / cfg.size. WalkForwardEval has no loop_config hook, so to put the Hexpert/Hmin arms under
    # the SAME guard+sizing (a fair, symmetric comparison), wrap each policy here before wf.walk/run — in the
    # SAME order as _rebind: L4 guard inner, L3 sizing outer (size the post-veto survivors). Sizing is
    # verdict-neutral, so wrapping the non-HCH arms does not change their numbers; it keeps the chain uniform.
    # recall_store is READ-only for EVERY arm: GuardedPolicy taboo + Hexpert recall (episode_store=), HCH via
    # the loop's recall_store= (NOT episode_store= — the verdict must not self-write mid-run). Default None ->
    # byte-identical to the no-memory verdict. The §6 read is applied SYMMETRICALLY (like the screen flag).
    # P2: vocabulary rides WITH the seed H under test (never the env); a growth H reads the growth market
    # clock, a momo H reads GCycle. track_history=True gives EVERY arm its own accumulator, so HCH and
    # Hexpert (fed the same source/window) build IDENTICAL strictly-prior histories -> the panic veto +
    # growth clock see the same backdrop symmetrically (the screen-flag / recall_store symmetry pattern).
    # vocab is read off a seed H the run ALREADY builds (the shadow pre-run's / mgr's), never an extra
    # harness_factory() call, so factory-isolation is unchanged.
    vocab = "momo"

    def _wrap(policy):
        # clock_authority (§1.4) rides on cfg -> threaded to EVERY arm's GuardedPolicy identically, so both
        # arms compose the SAME theme+stock cascade over the SAME source/window (verdict-symmetric, the
        # screen-flag / recall_store pattern). Default OFF -> byte-identical.
        p = GuardedPolicy(policy, source, episode_store=recall_store, vocabulary=vocab,
                          track_history=True, clock_authority=cfg.clock_authority) if cfg.screen else policy
        return SizingPolicy(p) if cfg.size else p

    # Hexpert FIRST when shadow (its series seeds HCH); frozen H = bare agent walk, no Refiner/manager.
    hexpert_traj = None
    if shadow:
        hexpert_h = harness_factory()
        vocab = hexpert_h.vocabulary
        hexpert_traj = wf.walk(_wrap(LLMAgentPolicy(hexpert_h, agent_llm_factory(),
                                                    episode_store=recall_store)))

    # HCH = self-refining InnerLoop (optionally shadow-gated against the Hexpert reference series)
    mgr = HarnessManager(harness_factory(), store_factory())
    vocab = mgr.harness.vocabulary          # non-shadow: set before the first _wrap call below
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                     config=cfg, refiner_config=refiner_config, scorer=scorer_factory(),
                     shadow_daily=(daily_advantage(hexpert_traj) if shadow else None),
                     recall_store=recall_store)   # READ-only into the loop (never episode_store=): no self-write
    lr = loop.run()
    # P6 PURGED-CV EMBARGO (spec §1): the embargo is a MEASUREMENT fence applied at the reporting layer
    # ONLY — the loop already refined internally over its full matured set (HCH's live behavior). Both
    # arms are re-scored through the SAME embargo_trajectory (symmetric right-edge purge); the shadow
    # reference fed to HCH's breaker above stays RAW (hexpert_traj), so no live decision changes.
    # embargo=0 -> the views ARE the raw trajectories (byte-identical).
    hch_view = embargo_trajectory(lr.trajectory, embargo)
    hch_eval = report_from_trajectory(hch_view, horizon=cfg.horizon)

    # Hexpert (reuse the shadow pre-run trajectory, else run it now); embargo the REPORTING view.
    if hexpert_traj is None:
        hexpert_traj = wf.walk(_wrap(LLMAgentPolicy(harness_factory(), agent_llm_factory(),
                                                    episode_store=recall_store)))
    hexpert_view = embargo_trajectory(hexpert_traj, embargo)
    hexpert_eval = report_from_trajectory(hexpert_view, horizon=cfg.horizon)

    # Hmin floor baselines (deterministic, no LLM/H/store); embargo each walk's REPORTING view.
    hmin_chase = report_from_trajectory(embargo_trajectory(wf.walk(_wrap(ChaseBiggestGainerPolicy())),
                                                           embargo), horizon=cfg.horizon)
    hmin_notrade = report_from_trajectory(embargo_trajectory(wf.walk(_wrap(NoTradePolicy())),
                                                             embargo), horizon=cfg.horizon)

    arms = {
        "HCH": ArmReport(name="HCH", report=hch_eval, n_refines=len(lr.refine_events),
                         n_breaker_trips=len(lr.breaker_events), frozen_from=lr.frozen_from),
        "Hexpert": ArmReport(name="Hexpert", report=hexpert_eval),
        "Hmin_chase": ArmReport(name="Hmin_chase", report=hmin_chase),
        "Hmin_notrade": ArmReport(name="Hmin_notrade", report=hmin_notrade),
    }

    # P6 Hcredit (C4) ABLATION arm (spec §3): a second HCH identical in every input but with the
    # credit-assignment seam removed (credit_fn=ablate_credit -> no SkillStats mutation, empty
    # CreditReport to the Refiner). Isolates how much of HCH's edge is the credit seam. Default off ->
    # no extra arm / no extra factory calls. Same shadow reference (raw hexpert) keeps it comparable.
    d_nocredit: float | None = None
    if credit_ablation:
        mgr_nc = HarnessManager(harness_factory(), store_factory())
        loop_nc = InnerLoop(mgr_nc, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                            config=cfg, refiner_config=refiner_config, scorer=scorer_factory(),
                            shadow_daily=(daily_advantage(hexpert_traj) if shadow else None),
                            recall_store=recall_store, credit_fn=ablate_credit)
        lr_nc = loop_nc.run()
        nocredit_eval = report_from_trajectory(embargo_trajectory(lr_nc.trajectory, embargo),
                                               horizon=cfg.horizon)
        arms["HCH_nocredit"] = ArmReport(name="HCH_nocredit", report=nocredit_eval,
                                         n_refines=len(lr_nc.refine_events),
                                         n_breaker_trips=len(lr_nc.breaker_events),
                                         frozen_from=lr_nc.frozen_from)
        d_nocredit = hch_eval.mean_excess - nocredit_eval.mean_excess

    # §9/§10 acceptance procedure: paired day-level verdict (HCH - Hexpert) + offense/defense split, on
    # the embargoed views (symmetric). P6 stratify: per-regime paired verdicts under the run's vocab.
    diffs = paired_daily_diff(daily_series(hch_view), daily_series(hexpert_view))
    stat = verdict(diffs)
    contribution = contribution_split(hch_view, mgr.harness)   # resolve against the evolved HCH H
    stratified = stratified_verdicts(hch_view, hexpert_view, regime_key_for(vocab)) if stratify else None

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
        stratified=stratified,
        hch_minus_nocredit_mean_excess=d_nocredit,
    )


class MultiWindowReport(BaseModel):
    """Honest-bar DIAGNOSTIC across N (start, end) windows. NOTE: few/short-window excess deltas are
    NOISE (MDE ~0.26 at ~30 trading days, spec §12) — this surfaces the direction/distribution
    (win-rate, sign-consistency), it is NOT a pooled significance test. P6 un-defers purged-CV: `embargo`
    is applied inside every window (symmetric right-edge purge) and the last `reserved` windows are a
    held-out set surfaced via the `reserved_*` view (never looked at while iterating — the residual
    Goodhart surface is HUMAN meta-iteration)."""
    model_config = ConfigDict(frozen=True)
    n_windows: int
    deltas: list[float] = Field(default_factory=list)   # hch_minus_hexpert_mean_excess per window (ALL)
    mean_delta: float = 0.0                              # over ALL windows (byte-identical semantics)
    win_rate: float = 0.0                                # fraction of windows with delta > 0 (ALL)
    sign_consistent: bool = False                       # all deltas strictly same sign (ALL)
    # A ROLLUP of per-window single-window verdicts (each a within-window CI), NOT a pooled cross-window
    # significance test — cohort-level inference stays the win_rate / sign-consistency direction diagnostic.
    verdicts: list[str] = Field(default_factory=list)             # per-window stat-verdict labels (ALL)
    verdict_tally: dict[str, int] = Field(default_factory=dict)   # counts by label across windows (ALL)
    # P6 additive holdout view (default reserved=0 -> iterate == ALL, reserved empty -> byte-identical).
    embargo: int = 0
    n_reserved: int = 0
    iterate_mean_delta: float = 0.0                      # mean delta over the ITERATE (non-held-out) folds
    iterate_win_rate: float = 0.0
    reserved_deltas: list[float] = Field(default_factory=list)   # deltas over the held-out tail folds
    reserved_mean_delta: float = 0.0
    reserved_win_rate: float = 0.0


def multi_window(harness_factory: Callable[[], HarnessState], source,
                 windows: list[tuple[Date, Date]], *,
                 agent_llm_factory: Callable[[], LLMClient],
                 refiner_llm_factory: Callable[[], LLMClient],
                 store_factory: Callable[[], SnapshotStore],
                 loop_config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None,
                 scorer_factory: Callable[[], object] | None = None,
                 shadow: bool = False, recall_store=None,
                 embargo: int = 0, reserved: int = 0) -> MultiWindowReport:
    """Run compare_harnesses over each window; aggregate the excess deltas. A direction diagnostic, not
    a significance test (see MultiWindowReport). P6: `embargo` is threaded into EVERY window (both arms,
    identical holdout windows preserved) and the last `reserved` windows form the held-out set — every
    window is still RUN (verdict symmetry) but the `reserved_*` view is separated so a human iterating on
    refiner prompts/config watches only `iterate_*`."""
    deltas: list[float] = []
    verdicts: list[str] = []
    for (start, end) in windows:
        cr = compare_harnesses(harness_factory, source, start, end, agent_llm_factory=agent_llm_factory,
                               refiner_llm_factory=refiner_llm_factory, store_factory=store_factory,
                               loop_config=loop_config, refiner_config=refiner_config,
                               scorer_factory=scorer_factory, shadow=shadow, recall_store=recall_store,
                               embargo=embargo)
        deltas.append(cr.hch_minus_hexpert_mean_excess)
        verdicts.append(cr.stat_verdict.verdict if cr.stat_verdict is not None else "insufficient")
    n = len(deltas)
    mean_delta = sum(deltas) / n if n else 0.0
    win_rate = sum(1 for d in deltas if d > 0.0) / n if n else 0.0
    sign_consistent = n > 0 and (all(d > 0.0 for d in deltas) or all(d < 0.0 for d in deltas))
    tally: dict[str, int] = {}
    for v in verdicts:
        tally[v] = tally.get(v, 0) + 1
    split = n - reserved                                          # last `reserved` windows = held-out
    it, res = deltas[:split], deltas[split:]
    _mean = lambda xs: sum(xs) / len(xs) if xs else 0.0
    _wr = lambda xs: sum(1 for d in xs if d > 0.0) / len(xs) if xs else 0.0
    return MultiWindowReport(n_windows=n, deltas=deltas, mean_delta=mean_delta, win_rate=win_rate,
                             sign_consistent=sign_consistent, verdicts=verdicts, verdict_tally=tally,
                             embargo=embargo, n_reserved=reserved,
                             iterate_mean_delta=_mean(it), iterate_win_rate=_wr(it),
                             reserved_deltas=res, reserved_mean_delta=_mean(res), reserved_win_rate=_wr(res))
