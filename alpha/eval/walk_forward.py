from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.data.calendar import trading_days_between
from alpha.eval.decision import DecisionPolicy
from alpha.eval.metrics import EvalReport, ScoredCandidate, build_report
from alpha.eval.oracle import PoolRecord, classify_day
from alpha.eval.purged_cv import embargo_trajectory
from alpha.eval.return_oracle import ReturnOracle
from alpha.eval.scorer import PoolScorer
from alpha.eval.trajectory import Trajectory, TrajectoryStep, report_from_trajectory
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe, tape_breadth


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

    def __init__(self, source, start: Date, end: Date, horizon: int = 2, scorer=None,
                 embargo: int = 0) -> None:
        if horizon < 2:
            raise ValueError(f"horizon must be >=2 (no same-day round-trip), got {horizon}")
        if embargo < 0:
            raise ValueError(f"embargo must be >=0, got {embargo}")
        self._source = source
        self._start = start
        self._end = end
        self._horizon = horizon
        self._scorer = scorer or PoolScorer()
        self._embargo = embargo   # P6: drop `embargo` MORE trailing scored decisions (purged-CV right edge)

    def walk(self, policy: DecisionPolicy) -> Trajectory:
        """Forward-replay capturing the full per-day record (the Refiner's evidence). Same scoring as
        run(): decision j enters days[j+1] open, exits days[j+horizon] close; last `horizon` unscored."""
        days = trading_days_between(self._source.trading_calendar(), self._start, self._end)
        record = PoolRecord()
        decisions: list = []
        markets: list = []
        universes: list = []
        scored_by_day: dict = {}
        history: list[float] = []                 # prior-day sentiment_raw (regime-relative context)
        prev_gainers: frozenset[str] = frozenset()
        for i, cursor in enumerate(days):
            guarded = GuardedSource(self._source, AsOfGuard(cursor))
            universe = build_universe(guarded, cursor)
            snap = guarded.daily_snapshot(cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0),
                                       history=history, prev_gainers=prev_gainers,
                                       market_counts=tape_breadth(snap))   # P2: full-tape breadth (screen-independent)
            history.append(state.sentiment_raw)   # forward-only: feeds next day's sentiment_norm percentile
            prev_gainers = frozenset(s.symbol for s in universe.by_status("gainer"))
            record.record(cursor, classify_day(snap))
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
            # SCORING FENCE (P0.6 spec §6 / P0.5 spec §8): these entries feed forward-return LONG scoring.
            # Every Candidate.action is "enter" today; the producer that FIRST emits a trim/exit (a derisk
            # on a HELD name, not a new long) MUST fence them out here — `... for c in decisions[i].candidates
            # if c.action == "enter"` — mirroring the verdict `for_asof(kind="trade")` fence. Pin only.
            entries = {c.symbol: snap for c in decisions[i].candidates
                       if (snap := uni.get(c.symbol)) is not None}
            steps.append(TrajectoryStep(date=cursor, market=markets[i], decision=decisions[i],
                                        entries=entries, outcomes=scored_by_day.get(cursor, {}),
                                        scored=(i <= n - 1 - self._horizon)))
        # P6: the embargo is the ONE shared purge implementation both arms call (compare_harnesses
        # applies the identical embargo_trajectory to the HCH loop trajectory) -> symmetric right-edge
        # purge; embargo=0 returns the trajectory unchanged (byte-identical).
        return embargo_trajectory(Trajectory(steps=steps), self._embargo)

    def run(self, policy: DecisionPolicy) -> EvalReport:
        return report_from_trajectory(self.walk(policy), horizon=self._horizon)

    def _score(self, decision, days: list[Date], j: int, cursor: Date,
               record: PoolRecord) -> list[ScoredCandidate]:
        return list(score_decision(self._source, self._scorer, decision, days, j, self._horizon,
                                   cursor, record).values())


def score_decision(source, scorer, decision, days: list[Date], j: int, horizon: int,
                   cursor: Date, record: PoolRecord) -> dict[str, ScoredCandidate]:
    """Score decision j (made on days[j]) at its t+horizon exit. Returns {symbol: ScoredCandidate}.
    Firewall: the oracle reads through GuardedSource(AsOfGuard(cursor)) where cursor == the exit day,
    so as_of >= exit_day (never future). Shared by WalkForwardEval._score and the US-2c InnerLoop.
    Invariant: the caller guarantees j+1 < j+horizon <= cursor's index, so days[j+1]/days[j+horizon]
    never go OOB and cursor >= exit_day keeps as_of >= exit (in walk() j == i-horizon exactly; in the
    InnerLoop a matured decision can be scored at i >= j+horizon, still with cursor >= exit_day)."""
    entry_day = days[j + 1]                       # buy next open (t+1)
    exit_day = days[j + horizon]                  # sell t+horizon close
    decision_mem = record.get(days[j])
    exit_mem = record.get(exit_day)
    oracle = ReturnOracle(GuardedSource(source, AsOfGuard(cursor)))   # as_of>=exit, firewall ok
    return scorer.score_step(decision, decision_mem, exit_mem, entry_day, exit_day, oracle)
