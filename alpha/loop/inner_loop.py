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
from alpha.loop.floor_breaker import _fallback_trip
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
                 agent_factory: Callable[[HarnessState], DecisionPolicy] | None = None) -> None:
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
        self._rebind()

    def _rebind(self) -> None:
        """(Re)build agent + refiner from the CURRENT mgr.harness/mgr.tools. Call at startup and after
        EVERY rollback (rollback_to rebinds mgr.harness/mgr.tools to the restored objects)."""
        h = self._mgr.harness
        self._agent = self._agent_factory(h) if self._agent_factory is not None \
            else LLMAgentPolicy(h, self._agent_llm)
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

        for i, cursor in enumerate(days):
            guarded = GuardedSource(self._source, AsOfGuard(cursor))
            universe = build_universe(guarded, cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0))
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
                breaker_days.append((step.date, sum(advs) / len(advs) if advs else 0.0))

            # [Task 5 inserts the BREAKER block here]

            # [Task 4 inserts the REFINE block here]

        traj = Trajectory(steps=[TrajectoryStep(**d) for d in drafts])
        # n_edits = edits in the LIVE log (after any rollback rebinds mgr.log to the restored, shorter
        # log) — a current-state count, not a cumulative-across-rollbacks total.
        return LoopReport(trajectory=traj, refine_events=refine_events, breaker_events=breaker_events,
                          frozen_from=frozen_from, n_edits=len(self._mgr.log))
