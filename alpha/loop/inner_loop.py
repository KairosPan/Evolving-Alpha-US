from __future__ import annotations

from datetime import date as Date, datetime as DateTime
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.calendar import trading_days_between
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.eval.decision import DecisionPolicy
from alpha.eval.oracle import PoolRecord, classify_day
from alpha.eval.scorer import ReturnScorer
from alpha.eval.trajectory import Trajectory, TrajectoryStep
from alpha.eval.walk_forward import score_decision
from alpha.harness.manager import HarnessManager
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.refine.credit import CreditReport, apply_credit, merge_credit_reports
from alpha.refine.refiner import RefineReport, Refiner, RefinerConfig
from alpha.refine.signatures import extract_signatures
from alpha.loop.floor_breaker import _fallback_trip, _shadow_eps_abs, _shadow_trip
from alpha.guard.screen import GuardedPolicy
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe


class LoopConfig(BaseModel):
    """Inner-loop knobs. Dropped from CN: 4 B2-deprecated fields (breaker_window / baseline_window /
    floor_rel_margin / breaker_min_samples) + credit_window (A3: superseded by the watermark). The 3
    shadow_* fields (the paired-arm breaker) are US-2d — they need the Hexpert reference arm."""
    horizon: int = Field(default=2, ge=2)          # US: no same-day round-trip (WalkForwardEval enforces >=2)
    refine_every: int = Field(default=1, ge=1)
    evidence_min: int = Field(default=6, ge=1)     # min FRESH candidates (not steps) before a refine
    credit_decay: float = Field(default=0.1, gt=0.0, le=1.0)
    breaker_min_days: int = Field(default=3, ge=1)
    breaker_k_max: int = Field(default=5, ge=1)
    breaker_mad_c: float = Field(default=2.0, ge=0.0)
    floor_abs: float = Field(default=-0.2, ge=-1.0, le=1.0)
    enable_refine: bool = True
    screen: bool = True         # L4 hard veto ON by default — the richer state builder now feeds GCycle
    #   follow_through/sentiment so the regime arm reads frontside on genuine uptrends (no longer over-fires);
    #   the SSR / reverse-split / dilution / halt-then-dump data-flag vetoes are exact. Set screen=False to
    #   run an unguarded baseline (compare_harnesses wraps all arms symmetrically when this is True).
    # shadow/paired breaker (US-2d): active only when an InnerLoop is given a shadow_daily reference series
    breaker_shadow_lambda: float = Field(default=1.0, ge=0.0)
    breaker_shadow_eps_c: float = Field(default=0.25, ge=0.0)
    breaker_shadow_eps_floor: float = Field(default=0.05, ge=0.0)


class RefineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    checkpoint_version: int | None
    report: RefineReport


class BreakerEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    rolling: float
    baseline: float | None
    reason: str
    rolled_back_to: int | None
    mode: Literal["rollback", "frozen"]


class LoopReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    trajectory: Trajectory
    refine_events: list[RefineEvent] = Field(default_factory=list)
    breaker_events: list[BreakerEvent] = Field(default_factory=list)
    frozen_from: Date | None = None
    n_edits: int = 0


class InnerLoop:
    """Interleaved self-evolution driver over one date range on a single LIVE H. Reset-free: the agent
    decides on the live H, edits become visible the next day. checkpoint/rollback + the capability-floor
    breaker live HERE (the Refiner only edits in place). After every rollback _rebind() re-fetches
    mgr.harness/mgr.tools and rebuilds the agent + refiner (the cached-handle-after-rollback hazard)."""

    def __init__(self, manager: HarnessManager, source, start: Date, end: Date,
                 agent_llm: LLMClient, refiner_llm: LLMClient, config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None, scorer=None,
                 agent_factory: Callable[[HarnessState], DecisionPolicy] | None = None,
                 shadow_daily: dict[Date, float] | None = None) -> None:
        self._mgr = manager
        self._source = source
        self._start = start
        self._end = end
        self._agent_llm = agent_llm
        self._refiner_llm = refiner_llm
        self._cfg = config or LoopConfig()
        self._refiner_cfg = refiner_config or RefinerConfig()
        self._scorer = scorer or ReturnScorer()   # spec §7: forward-return oracle is PRIMARY (CN defaulted PoolScorer)
        self._agent_factory = agent_factory
        self._shadow_daily = dict(shadow_daily) if shadow_daily is not None else None
        self._rebind()

    def _rebind(self) -> None:
        """(Re)build agent + refiner from the CURRENT mgr.harness/mgr.tools. Call at startup and after
        EVERY rollback (rollback_to rebinds mgr.harness/mgr.tools to the restored objects)."""
        h = self._mgr.harness
        base = self._agent_factory(h) if self._agent_factory is not None \
            else LLMAgentPolicy(h, self._agent_llm)
        self._agent = GuardedPolicy(base, self._source) if self._cfg.screen else base
        self._refiner = Refiner(h, self._refiner_llm, self._mgr.tools, self._refiner_cfg)

    def run(self) -> LoopReport:
        cfg = self._cfg
        days = trading_days_between(self._source.trading_calendar(), self._start, self._end)
        record = PoolRecord()
        drafts: list[dict] = []
        pending: list[int] = []
        scored_steps: list[TrajectoryStep] = []
        per_step_credits: list[CreditReport] = []
        refine_events: list[RefineEvent] = []
        breaker_events: list[BreakerEvent] = []
        breaker_days: list[tuple[Date, float]] = []
        ckpts: list[tuple[int, Date]] = []
        last_refined_idx = 0
        breaker_trips = 0
        frozen = False
        frozen_from: Date | None = None
        # regime context threaded forward across the run; a breaker rollback does NOT rewind these (the
        # regime read is a forward-only s_t-side input, not part of H — and sentiment_norm is None on the
        # short windows where rollbacks are exercised, so no normalized value can drift).
        history: list[float] = []                  # prior-day sentiment_raw
        prev_gainers: frozenset[str] = frozenset()

        for i, cursor in enumerate(days):
            guarded = GuardedSource(self._source, AsOfGuard(cursor))
            universe = build_universe(guarded, cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0),
                                       history=history, prev_gainers=prev_gainers)
            history.append(state.sentiment_raw)    # forward-only: feeds next day's sentiment_norm percentile
            prev_gainers = frozenset(s.symbol for s in universe.by_status("gainer"))
            record.record(cursor, classify_day(guarded.daily_snapshot(cursor)))
            decision = self._agent.decide(state, universe)
            entries = {c.symbol: snap for c in decision.candidates
                       if (snap := universe.get(c.symbol)) is not None}
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "outcomes": {}, "scored": False})
            pending.append(i)

            # delayed scoring: mature any decision j that has reached its t+horizon exit
            newly: list[TrajectoryStep] = []
            still: list[int] = []
            for j in pending:
                if i >= j + cfg.horizon:
                    outcomes = score_decision(self._source, self._scorer, drafts[j]["decision"],
                                              days, j, cfg.horizon, cursor, record)
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
                    step_j = TrajectoryStep(**drafts[j])
                    scored_steps.append(step_j)
                    newly.append(step_j)
                else:
                    still.append(j)
            pending = still

            # online credit (once per newly-scored step) + breaker evidence — gated on NOT frozen
            for step in newly:
                if frozen:
                    continue
                per_step_credits.append(apply_credit(Trajectory(steps=[step]), self._mgr.harness,
                                                     decay=cfg.credit_decay))
                advs = [c.advantage for c in step.outcomes.values()]
                # empty outcomes (no oracle data / all dropped) contribute 0.0 — a neutral day, not excluded
                breaker_days.append((step.date, sum(advs) / len(advs) if advs else 0.0))

            # capability-floor breaker (fallback path): judge the daily-advantage series; on a trip,
            # roll back to the latest checkpoint BEFORE the degraded window (1st trip) or freeze.
            if not frozen and len(breaker_days) >= cfg.breaker_min_days:
                trip = False
                rolling = thr = 0.0
                reason = ""
                window_start = None
                if self._shadow_daily is not None:
                    # SHADOW (paired) path: judge HCH's daily advantage against the frozen-expert reference.
                    cur_max = breaker_days[-1][0]
                    own = {d: v for d, v in breaker_days}
                    shadow = {d: s for d, s in self._shadow_daily.items() if d <= cur_max}   # anti-lookahead
                    common = sorted(own.keys() & shadow.keys())
                    if len(common) >= cfg.breaker_min_days:
                        k = min(len(common), cfg.breaker_k_max)
                        diffs = [own[d] - shadow[d] for d in common]
                        eps = _shadow_eps_abs(list(shadow.values()), cfg.breaker_shadow_eps_c,
                                              cfg.breaker_shadow_eps_floor)
                        trip, rolling, thr, reason = _shadow_trip(diffs, k, cfg.breaker_shadow_lambda, eps)
                        window_start = common[-k]
                else:
                    k = min(len(breaker_days), cfg.breaker_k_max)
                    adv_series = [v for _, v in breaker_days]   # NOT `history` — that name is the outer
                    #   sentiment_raw accumulator threaded to build_market_state; rebinding it here would
                    #   corrupt sentiment_norm once history reaches min_samples on a long run.
                    trip, rolling, thr, reason = _fallback_trip(adv_series, k, cfg.breaker_mad_c, cfg.floor_abs)
                    window_start = breaker_days[-k][0]
                if trip:
                    breaker_trips += 1
                    target = max((v for v, d in ckpts if d < window_start), default=None)
                    if breaker_trips == 1 and target is not None:
                        self._mgr.rollback_to(target)
                        self._rebind()
                        ckpts = [(v, d) for v, d in ckpts if v <= target]   # drop discarded-timeline ckpts
                        breaker_days.clear()                                # re-arm: need breaker_min_days again
                        last_refined_idx = len(scored_steps)                # drop the discarded window so the
                        #   next refine is NOT re-fed the degraded evidence that caused this rollback (also
                        #   makes the same-day refine's window empty, so no `continue` is needed). The final
                        #   LoopReport.trajectory still contains the pre-rollback steps by design.
                        breaker_events.append(BreakerEvent(date=cursor, rolling=rolling, baseline=thr,
                                                           reason=reason, rolled_back_to=target,
                                                           mode="rollback"))
                    else:
                        rolled = None
                        if target is not None:
                            self._mgr.rollback_to(target)
                            self._rebind()
                            rolled = target
                        frozen = True
                        frozen_from = cursor
                        breaker_events.append(BreakerEvent(date=cursor, rolling=rolling, baseline=thr,
                                                           reason=reason, rolled_back_to=rolled,
                                                           mode="frozen"))

            # periodic refine: checkpoint BEFORE editing H, over the non-overlapping watermark window
            fresh = scored_steps[last_refined_idx:]
            n_fresh = sum(len(s.outcomes) for s in fresh)        # count CANDIDATES (empty days add 0)
            if cfg.enable_refine and not frozen and n_fresh >= cfg.evidence_min and i % cfg.refine_every == 0:
                ver = self._mgr.checkpoint(label=f"pre-refine {cursor}")
                ckpts.append((ver, cursor))
                win_traj = Trajectory(steps=fresh)
                credit = merge_credit_reports(per_step_credits[last_refined_idx:])
                sigs = extract_signatures(win_traj, self._mgr.harness)
                report = self._refiner.refine(win_traj, credit, sigs)
                refine_events.append(RefineEvent(date=cursor, checkpoint_version=ver, report=report))
                last_refined_idx = len(scored_steps)             # advance watermark (non-overlapping)

        traj = Trajectory(steps=[TrajectoryStep(**d) for d in drafts])
        # n_edits = edits in the LIVE log (after any rollback rebinds mgr.log to the restored, shorter
        # log) — a current-state count, not a cumulative-across-rollbacks total.
        return LoopReport(trajectory=traj, refine_events=refine_events, breaker_events=breaker_events,
                          frozen_from=frozen_from, n_edits=len(self._mgr.log))
