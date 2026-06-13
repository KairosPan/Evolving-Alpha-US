from __future__ import annotations

from datetime import date as Date

from youzi.eval.decision import DecisionPolicy
from youzi.eval.metrics import EvalReport, ScoredCandidate, build_report
from youzi.eval.oracle import PoolRecord
from youzi.eval.scorer import PoolScorer
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.replay.engine import ReplayEngine
from youzi.universe.universe import build_universe


def report_from_trajectory(traj: Trajectory) -> EvalReport:
    """从已走轨迹派生 EvalReport(展平已打分步的 outcomes)。"""
    scored: list[ScoredCandidate] = []
    for step in traj.steps:
        if step.scored:
            scored.extend(step.outcomes.values())
    return build_report(scored, n_decisions=traj.n_decisions(),
                        n_no_trade=traj.n_no_trade(), horizon=traj.horizon)


class WalkForwardEval:
    """前向回放评测:策略每日决策(≤t 快照),horizon 天后用已实现 pool 成员延迟打分。"""

    def __init__(self, source, start: Date, end: Date, horizon: int = 1, scorer=None) -> None:
        if horizon < 1:
            raise ValueError(f"horizon 必须 >=1, got {horizon}")
        self._source = source
        self._start = start
        self._end = end
        self._horizon = horizon
        self._scorer = scorer or PoolScorer()

    def walk(self, policy: DecisionPolicy) -> Trajectory:
        """走完区间,产出 Trajectory(每步含 market/decision/entries,horizon 日回填 outcomes)。"""
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        drafts: list[dict] = []          # 可变草稿,末尾封 frozen TrajectoryStep
        pending: list[int] = []          # 待打分的 draft 索引
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()                                  # ≤t 聚合状态
            universe = build_universe(engine.guarded_source, cursor)  # ≤t 候选(经防火墙)
            record.record(cursor, universe)
            decision = policy.decide(state, universe)
            # 入场上下文:去重入选 code → EntrySnap(从当日 universe 查;查不到则不记)
            entries: dict[str, EntrySnap] = {}
            for c in decision.candidates:
                if c.code in entries:
                    continue
                snap = universe.get(c.code)
                if snap is not None:
                    entries[c.code] = EntrySnap(code=c.code, status=snap.status,
                                                boards=snap.boards)
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "scored": False, "outcomes": {}})
            pending.append(idx)
            # 延迟打分:决策 j 在 idx >= j+horizon 时,用 days_seen[j+horizon] 的已录成员打分
            remaining: list[int] = []
            for j in pending:
                if idx >= j + self._horizon:
                    # 持有路径 entry..exit 逐日成员(days_seen[j+1 .. j+horizon];均已录制)
                    mems = [record.get(days_seen[j + h]) for h in range(1, self._horizon + 1)]
                    assert all(m is not None for m in mems), \
                        f"BUG: 决策 {days_seen[j]} 的持有路径有交易日未录制成员"
                    outcomes = self._scorer.score_step(
                        drafts[j]["decision"], mems,
                        days_seen[j + 1], days_seen[j + self._horizon], engine.guarded_source,
                        decision_mem=record.get(days_seen[j]))   # 决策日(≤t)池成员 → day_baseline
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
                else:
                    remaining.append(j)
            pending = remaining
            idx += 1
            if not engine.step():
                break
        # 尾部不足 horizon 的步保留(scored=False),显式化原"静默丢弃"
        steps = [TrajectoryStep(**d) for d in drafts]
        return Trajectory(steps=steps, horizon=self._horizon)

    def run(self, policy: DecisionPolicy) -> EvalReport:
        return report_from_trajectory(self.walk(policy))
