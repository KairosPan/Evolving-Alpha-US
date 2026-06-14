from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.data.calendar import trading_days_between
from alpha.eval.decision import DecisionPolicy
from alpha.eval.metrics import EvalReport, ScoredCandidate, build_report
from alpha.eval.oracle import PoolRecord, classify_day
from alpha.eval.return_oracle import ReturnOracle
from alpha.eval.scorer import PoolScorer
from alpha.eval.trajectory import Trajectory, TrajectoryStep, report_from_trajectory
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe


class WalkForwardEval:
    """Forward-replay eval: policy decides on <=t snapshots; scored at t+horizon with realized data.
    The firewall holds by construction (per-day GuardedSource; scoring guard at the current cursor).

    HORIZON SEMANTICS: `horizon` = trading-day steps from the DECISION day to the EXIT day. A decision
    at day t enters at t+1 OPEN and exits at t+horizon CLOSE. horizon>=2 therefore means the position
    is held at least overnight (t+1 open -> t+2 close) and is NEVER opened-and-closed in the same
    session — the US analog of the A-share T+1 no-same-day-round-trip constraint. (horizon=2 = the
    shortest legal hold.) The last `horizon` decisions in the window have no t+horizon day yet and are
    left unscored (the full per-step Trajectory is US-2).
    """

    def __init__(self, source, start: Date, end: Date, horizon: int = 2, scorer=None) -> None:
        if horizon < 2:
            raise ValueError(f"horizon must be >=2 (no same-day round-trip), got {horizon}")
        self._source = source
        self._start = start
        self._end = end
        self._horizon = horizon
        self._scorer = scorer or PoolScorer()

    def walk(self, policy: DecisionPolicy) -> Trajectory:
        """Forward-replay capturing the full per-day record (the Refiner's evidence). Same scoring as
        run(): decision j enters days[j+1] open, exits days[j+horizon] close; last `horizon` unscored."""
        days = trading_days_between(self._source.trading_calendar(), self._start, self._end)
        record = PoolRecord()
        decisions: list = []
        markets: list = []
        universes: list = []
        scored_by_day: dict = {}
        for i, cursor in enumerate(days):
            guarded = GuardedSource(self._source, AsOfGuard(cursor))
            universe = build_universe(guarded, cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0))
            record.record(cursor, classify_day(guarded.daily_snapshot(cursor)))
            decision = policy.decide(state, universe)
            decisions.append(decision); markets.append(state); universes.append(universe)
            j = i - self._horizon
            if j >= 0:
                sc_list = self._score(decisions[j], days, j, cursor, record)
                scored_by_day[days[j]] = {sc.symbol: sc for sc in sc_list}
        n = len(days)
        steps: list[TrajectoryStep] = []
        for i, cursor in enumerate(days):
            uni = universes[i]
            entries = {c.symbol: snap for c in decisions[i].candidates
                       if (snap := uni.get(c.symbol)) is not None}
            steps.append(TrajectoryStep(date=cursor, market=markets[i], decision=decisions[i],
                                        entries=entries, outcomes=scored_by_day.get(cursor, {}),
                                        scored=(i <= n - 1 - self._horizon)))
        return Trajectory(steps=steps)

    def run(self, policy: DecisionPolicy) -> EvalReport:
        return report_from_trajectory(self.walk(policy), horizon=self._horizon)

    def _score(self, decision, days: list[Date], j: int, cursor: Date,
               record: PoolRecord) -> list[ScoredCandidate]:
        # invariant: j == i - horizon, so j+horizon == i (the current cursor index) — always a valid
        # index whose membership was recorded THIS iteration; days[j+1]/days[j+horizon] never go OOB.
        entry_day = days[j + 1]                       # buy next open (t+1)
        exit_day = days[j + self._horizon]            # sell t+horizon close
        decision_mem = record.get(days[j])
        exit_mem = record.get(exit_day)
        oracle = ReturnOracle(GuardedSource(self._source, AsOfGuard(cursor)))   # as_of>=exit, firewall ok
        out = self._scorer.score_step(decision, decision_mem, exit_mem, entry_day, exit_day, oracle)
        return list(out.values())
