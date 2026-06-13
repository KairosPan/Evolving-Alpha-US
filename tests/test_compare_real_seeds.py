# tests/test_compare_real_seeds.py
"""真实种子(seeds/)上的四路 compare_harnesses 端到端冒烟。

与 tests/test_compare.py 的区别:harness_factory 不再用合成 _seed_h,而是
load_seeds("seeds/") 装真实 57 技能 / 22 条 doctrine 的种子 H。证明对比机器
(编排/delta/verdict/隔离)在真实(大)系统提示下也能端到端跑通,不崩。

仍离线:MockLLMClient 忽略提示,按脚本作答。HCH 选续板赢家(mean=1.0)、
Hexpert 空仓(mean=0.0)→ HCH 应胜 frozen 种子。refiner 返回空 ops(不改 H,
但有评分证据 → refine 仍触发,验证内环真在跑)。
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from youzi.eval.metrics import EvalReport
from youzi.harness.loader import load_seeds
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import MockLLMClient
from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from tests.conftest import FakeSource

# 与 test_compare 同形:选续板赢家 W / 空仓
_PICK_W = ('{"candidates": [{"code": "W", "pattern": "龙头接力", "confidence": 0.7}],'
           ' "no_trade_reason": ""}')
_NO_TRADE = '{"candidates": [], "no_trade_reason": "空仓"}'


def _w_src():
    """W 每日涨停(continued)+ 每日一只只上一天榜的 L{i}(次日掉出 → faded);3 日。

    C2 起 verdict 基于 mean_excess:单码池里选 W=闭眼买全池(超额恒 0,判不胜),
    故池里放输家使基线=0.5、选 W 的 advantage=+0.5。W 在 universe 内 → 决策不被当幻觉丢弃。
    """
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame({"code": ["W", f"L{i}"], "name": ["赢家", f"输{i}"],
                                       "boards": [2, 1]})
              for i, d in enumerate(days)}
    return FakeSource(frames, days)


class _SeqFactory:
    """有状态 factory:第 k 次调用返回第 k 个脚本对应的 client(超出用最后一个)。

    给 HCH(第 1 次)与 Hexpert(第 2 次)不同脚本,使 HCH 胜 frozen 种子。
    """

    def __init__(self, scripts):
        self._scripts = scripts
        self._i = 0
        self.calls = 0

    def __call__(self):
        self.calls += 1
        c = MockLLMClient(self._scripts[min(self._i, len(self._scripts) - 1)])
        self._i += 1
        return c


def test_four_arms_end_to_end_on_real_seeds(tmp_path):
    src = _w_src()
    # HCH agent → 选 W(续板,mean=1.0);Hexpert agent → 空仓(mean=0.0)
    agent_f = _SeqFactory([_PICK_W, _NO_TRADE])
    refiner_f = _SeqFactory(['{"ops": []}'])
    store_f = lambda: SnapshotStore(tmp_path)  # noqa: E731
    harness_f = lambda: load_seeds("seeds/")    # noqa: E731  真实种子(57 技能)

    rep = compare_harnesses(
        harness_f, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=agent_f, refiner_llm_factory=refiner_f,
        # A3:evidence_min=1 保持原意(3 日窗每日 1 候选,默认 6 永不 refine → ③ 断言失真)
        store_factory=store_f, loop_config=LoopConfig(evidence_min=1))

    # ① 四路齐全,各有 EvalReport
    assert set(rep.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    for arm in rep.arms.values():
        assert isinstance(arm.report, EvalReport)

    # ② HCH(自精炼)在真实种子下选中续板赢家 → 胜 frozen 种子空仓的 Hexpert
    # C2:verdict 基于 mean_excess(去市场β);池 {W, L_i} 基线=0.5 → HCH 超额=+0.5
    assert rep.arms["HCH"].report.mean_score == 1.0
    assert rep.arms["HCH"].report.mean_excess == 0.5
    assert rep.arms["Hexpert"].report.mean_score == 0.0
    assert rep.hch_minus_hexpert_mean_score > 0
    assert rep.hch_minus_hexpert_mean_excess > 0
    assert rep.hch_beats_hexpert is True

    # ③ 内环真在跑:有评分证据 → 至少触发一次 refine,且未熔断
    assert rep.arms["HCH"].n_refines >= 1
    assert rep.arms["HCH"].n_breaker_trips == 0

    # ④ 两条裸基线都有报告(HighestBoard 也追 W → 1.0;NoTrade → 0.0)
    assert rep.arms["Hmin_highest"].report.mean_score == 1.0
    assert rep.arms["Hmin_notrade"].report.mean_score == 0.0

    # ⑤ 隔离:HCH+Hexpert 各取一份 fresh 种子 H + 各自 agent client;仅 HCH 用 refiner
    assert agent_f.calls == 2
    assert refiner_f.calls == 1
