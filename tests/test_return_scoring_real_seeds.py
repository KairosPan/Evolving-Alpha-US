# tests/test_return_scoring_real_seeds.py
"""真实种子(seeds/)上的收益打分端到端:act→ReturnScorer 延迟打分→在线信用。

与 test_inner_loop_real_seeds.py 同骨架(load_seeds + HarnessManager + FakeSource),
但把 scorer 换成 ReturnScorer,证明收益打分在真实 H 上闭环:
- 被选真实技能(一进二/relay_1to2)的候选 A 每日涨停(outcome 仍池类别 continued)
  且带覆盖 entry/exit 日的 OHLCV → sc.score = 前向收益(非 {1,0,−1});
- 同被选的候选 Z 也每日涨停但**无 OHLCV** → ReturnScorer 丢弃(不入 outcomes);
- 从轨迹派生的 EvalReport:mean_score = 平均收益、hit_rate = 池 continued 率;
- apply_credit 后真实技能 SkillStats.expectancy_raw = 平均收益(score 走收益,非 SCORE);
  expectancy(C2 起=advantage)= 0,因池收益基线恰=A 自身收益。
全离线(FakeSource + MockLLMClient,refiner 空 ops)。
"""
from datetime import date, timedelta

import pandas as pd

from youzi.eval.scorer import ReturnScorer
from youzi.eval.walk_forward import report_from_trajectory
from youzi.harness.loader import load_seeds
from youzi.harness.manager import HarnessManager
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import MockLLMClient
from youzi.loop.inner_loop import InnerLoop, LoopConfig
from tests.conftest import FakeSource

# ── 真实种子里确实存在的技能(见 seeds/skills.json) ──
SEED_SKILL_NAME = "一进二"          # relay_1to2.name_cn,agent 决策 pattern 用它(走 name_cn 解析归因)
SEED_SKILL_ID = "relay_1to2"

SCORED_CODE = "A"                   # 每日涨停 + 有 OHLCV → ReturnScorer 打分
DROPPED_CODE = "Z"                  # 每日涨停但无 OHLCV → ReturnScorer 丢弃

_DAYS = [date(2024, 6, 26) + timedelta(days=k) for k in range(4)]   # n=4 交易日

# 决策日 t(horizon=1)→ entry_day == exit_day == 次日;收益 = 该日 (close−open)/open。
# 仅给 SCORED_CODE 的 OHLCV(覆盖每个会被当作 exit 的日:_DAYS[1..3]),刻意取
# 非 {1,0,−1} 的整洁收益,使断言显式区分"收益打分"与"池 SCORE 打分"。
_RETURN_BY_EXIT = {
    _DAYS[1]: (10.0, 10.5),   # +0.05
    _DAYS[2]: (10.0, 11.0),   # +0.10
    _DAYS[3]: (10.0, 12.0),   # +0.20
}
_EXPECTED_RETURNS = [0.05, 0.10, 0.20]               # 被打分的三步(决策日 _DAYS[0..2])
_MEAN_RETURN = sum(_EXPECTED_RETURNS) / len(_EXPECTED_RETURNS)   # = 0.35/3


def _src() -> FakeSource:
    """A、Z 每日同时涨停(均 continued);只有 A 带 OHLCV。"""
    frames = {("zt", d): pd.DataFrame({"code": [SCORED_CODE, DROPPED_CODE],
                                       "name": ["甲", "乙"], "boards": [2, 2]})
              for d in _DAYS}
    ohlcv = {SCORED_CODE: pd.DataFrame(
        [(d, o, o + 1, o - 1, c, 100) for d, (o, c) in _RETURN_BY_EXIT.items()],
        columns=["date", "open", "high", "low", "close", "volume"])}
    return FakeSource(frames, _DAYS, ohlcv=ohlcv)


def _decision() -> str:
    """同时选 A、Z,pattern 用真实种子技能 name_cn(使在线信用归因到 relay_1to2)。"""
    return ('{"candidates": ['
            '{"code": "%s", "pattern": "%s", "confidence": 0.7},'
            '{"code": "%s", "pattern": "%s", "confidence": 0.7}],'
            ' "no_trade_reason": ""}') % (
        SCORED_CODE, SEED_SKILL_NAME, DROPPED_CODE, SEED_SKILL_NAME)


def test_real_seeds_return_scoring_end_to_end(tmp_path):
    n = len(_DAYS)
    src = _src()
    h = load_seeds("seeds/")
    mgr = HarnessManager(h, SnapshotStore(tmp_path))
    # sanity:被引用的真实技能存在、初态干净(expectancy 尚未被任何信用写过)
    sk = mgr.harness.skills.get(SEED_SKILL_ID)
    assert sk is not None and sk.name_cn == SEED_SKILL_NAME
    assert sk.stats.n == 0 and sk.stats.expectancy is None

    loop = InnerLoop(
        mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        MockLLMClient([_decision()]), MockLLMClient(['{"ops": []}']),
        config=LoopConfig(breaker_min_days=10_000),   # 不熔断,聚焦打分
        scorer=ReturnScorer(),
    )
    rep = loop.run()

    # ── ① 轨迹:n 步,horizon=1 → 前 n−1 步已打分,尾步未打分 ──
    assert rep.trajectory.n_decisions() == n
    scored = rep.trajectory.scored_steps()
    assert len(scored) == n - 1
    assert rep.trajectory.steps[-1].scored is False

    # ── ① sc.score = 前向收益(非池 SCORE {1,0,−1});outcome 仍池类别 continued ──
    got_scores = [s.outcomes[SCORED_CODE].score for s in scored]
    assert got_scores == _EXPECTED_RETURNS                       # 按决策日序的逐日收益
    for s in scored:
        sc = s.outcomes[SCORED_CODE]
        assert sc.outcome == "continued"                          # 池成员制不变
        assert sc.score not in (1.0, 0.0, -1.0)                   # 确是收益,不是 SCORE[outcome]

    # ── ② 无 OHLCV 的候选 Z 被丢弃:从不进任何步的 outcomes(尽管池里也是 continued)──
    assert all(DROPPED_CODE not in s.outcomes for s in scored)
    assert all(set(s.outcomes) == {SCORED_CODE} for s in scored)   # 每步只剩 A

    # ── ③ EvalReport:mean_score = 平均收益、hit_rate = 池 continued 率(全 continued=1.0)──
    er = report_from_trajectory(rep.trajectory)
    assert er.n_candidates == n - 1                                # Z 不计入(被丢弃)
    assert abs(er.mean_score - _MEAN_RETURN) < 1e-9               # 平均前向收益
    assert er.hit_rate == 1.0                                      # outcome 仍池 continued
    assert er.nuke_rate == 0.0

    # ── ④ apply_credit 后真实技能 SkillStats:expectancy_raw = 平均收益(score 走收益)──
    # C2 语义变更:expectancy=advantage(score−当日池收益基线)。池 {A, Z} 里只有 A 有
    # OHLCV(与"缺收益丢弃"一致)→ 基线=A 自身收益 → A 的超额=0;原始口径在 expectancy_raw。
    st = mgr.harness.skills.get(SEED_SKILL_ID).stats
    assert st.n == n - 1 and st.wins == n - 1                      # 仅 A 计入(Z 被丢弃,不归因)
    assert st.expectancy is not None and abs(st.expectancy) < 1e-9  # 超额=0(基线=自身收益)
    assert st.expectancy_raw is not None
    assert abs(st.expectancy_raw - _MEAN_RETURN) < 1e-9            # 收益均值,非 SCORE 均值(后者=1.0)
    assert st.expectancy_raw != 1.0                                # 反证:池 SCORE 打分会给 1.0
