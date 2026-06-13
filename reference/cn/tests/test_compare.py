# tests/test_compare.py
import pytest

from youzi.loop.compare import ArmReport, ComparisonReport
from youzi.eval.metrics import EvalReport


def _empty_eval():
    return EvalReport(n_decisions=0, n_no_trade=0, n_candidates=0,
                      hit_rate=0.0, nuke_rate=0.0, mean_score=0.0)


def test_models_frozen_and_truthy():
    arm = ArmReport(name="HCH", report=_empty_eval(), n_refines=3,
                    n_breaker_trips=0, frozen_from=None)
    cr = ComparisonReport(arms={"HCH": arm},
                          hch_minus_hexpert_mean_score=0.0,
                          hch_minus_hexpert_hit_rate=0.0,
                          hch_minus_hexpert_nuke_rate=0.0,
                          hch_beats_hexpert=False)
    assert bool(cr) is True
    assert cr.arms["HCH"].n_refines == 3
    with pytest.raises(Exception):
        cr.hch_beats_hexpert = True            # frozen
    with pytest.raises(Exception):
        arm.name = "X"                          # frozen


from datetime import date

import pandas as pd

from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import MockLLMClient
from tests.conftest import FakeSource
from tests.test_inner_loop import _seed_h, _decision

_PICK_W = _decision("W")
_NO_TRADE = '{"candidates": [], "no_trade_reason": "空仓"}'


def _w_src():
    """W 每日涨停(continued)+ 每日一只只上一天榜的 L{i}(次日掉出全部池 → faded);3 日。

    C2 起池里需要输家:决策日涨停池 {W, L_i} → day_baseline=(1+0)/2=0.5,选 W 的
    advantage=+0.5(单码池里选 W=闭眼买全池,超额恒 0,verdict 永远判不胜)。
    带 W 的 OHLCV(覆盖 6/27、6/28),使 ReturnScorer 可算收益。
    """
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame({"code": ["W", f"L{i}"], "name": ["赢家", f"输{i}"],
                                       "boards": [2, 1]}) for i, d in enumerate(days)}
    ohlcv = {"W": pd.DataFrame([(date(2024, 6, 27), 10.0, 11, 9, 10.5, 100),
                               (date(2024, 6, 28), 10.6, 12, 10, 11.0, 200)],
                              columns=["date", "open", "high", "low", "close", "volume"])}
    return FakeSource(frames, days, ohlcv=ohlcv)


class _SeqFactory:
    """第 k 次调用返回第 k 个脚本对应的 client(超出则用最后一个);记 calls。"""
    def __init__(self, scripts):
        self._scripts = scripts
        self._i = 0
        self.calls = 0

    def __call__(self):
        self.calls += 1
        c = MockLLMClient(self._scripts[min(self._i, len(self._scripts) - 1)])
        self._i += 1
        return c


class _CountFactory:
    def __init__(self, fn):
        self._fn = fn
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._fn()


def _compare(tmp_path, agent_scripts, refiner_script='{"ops": []}', cfg=None, scorer=None,
             ablate=False):
    src = _w_src()
    agent_f = _SeqFactory(agent_scripts)
    refiner_f = _SeqFactory([refiner_script])
    store_f = _CountFactory(lambda: SnapshotStore(tmp_path))
    harness_f = _CountFactory(_seed_h)
    rep = compare_harnesses(
        harness_f, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=agent_f, refiner_llm_factory=refiner_f,
        # A3:evidence_min=1 保持原意(3 日窗每日 ≤1 候选,默认 6 永不 refine,
        # n_refines>=1 类断言会失真)
        store_factory=store_f, loop_config=cfg or LoopConfig(evidence_min=1), scorer=scorer,
        ablate=ablate)   # C4:agent 脚本对位 factory 调用顺序 HCH→Hcredit→Hexpert
    return rep, agent_f, refiner_f, store_f, harness_f


def test_four_arms_and_verdict_true(tmp_path):
    # HCH 选 W(continued, mean=1.0);Hexpert 空仓(mean=0.0)→ HCH 胜。
    # C2 语义变更:verdict 改基于 mean_excess(>0)。池 {W, L_i} 基线=0.5 → HCH 超额=+0.5。
    rep, *_ = _compare(tmp_path, [_PICK_W, _NO_TRADE])
    assert set(rep.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    assert rep.arms["HCH"].report.mean_score == 1.0
    assert rep.arms["HCH"].report.mean_excess == 0.5            # 1.0 − 池基线 0.5
    assert rep.arms["Hexpert"].report.mean_score == 0.0
    assert rep.arms["Hexpert"].report.mean_excess == 0.0        # 空仓:无已评分候选
    assert rep.arms["Hmin_highest"].report.mean_score == 1.0   # HighestBoard 也追 W(2板>1板)
    assert rep.arms["Hmin_notrade"].report.mean_score == 0.0
    assert rep.hch_minus_hexpert_mean_score == 1.0              # 旧口径字段保留
    assert rep.hch_minus_hexpert_mean_excess == 0.5             # 新:截面超额差
    assert rep.hch_beats_hexpert is True                        # 基于超额 > 0
    assert rep.arms["HCH"].n_refines >= 1                       # W 续板有证据 → refine 触发
    assert rep.arms["HCH"].n_breaker_trips == 0


def test_verdict_false_when_hch_worse(tmp_path):
    # HCH 空仓(excess=0);Hexpert 选 W(excess=+0.5)→ HCH 退化于 frozen
    rep, *_ = _compare(tmp_path, [_NO_TRADE, _PICK_W])
    assert rep.hch_minus_hexpert_mean_score == -1.0
    assert rep.hch_minus_hexpert_mean_excess == -0.5            # C2:超额口径同向
    assert rep.hch_beats_hexpert is False
    assert rep.arms["HCH"].n_refines == 0                       # 全空仓无评分证据 → 不 refine


def test_same_script_delta_zero(tmp_path):
    # HCH 与 Hexpert 同脚本(都选 W)→ delta=0、verdict False,但 HCH 仍 refine(MockLLM 局限:refine 不改脚本化决策)
    rep, *_ = _compare(tmp_path, [_PICK_W])     # 两路都拿到 _PICK_W(SeqFactory 超出用末元素)
    assert rep.arms["HCH"].report.mean_score == rep.arms["Hexpert"].report.mean_score == 1.0
    assert rep.hch_minus_hexpert_mean_score == 0.0
    assert rep.hch_minus_hexpert_mean_excess == 0.0             # 同脚本 → 超额差也为 0
    assert rep.hch_beats_hexpert is False
    assert rep.arms["HCH"].n_refines >= 1


def test_factory_call_counts_and_isolation(tmp_path):
    rep, agent_f, refiner_f, store_f, harness_f = _compare(tmp_path, [_PICK_W, _NO_TRADE])
    assert harness_f.calls == 2      # HCH + Hexpert 各一份 fresh H
    assert agent_f.calls == 2        # HCH agent + Hexpert agent
    assert refiner_f.calls == 1      # 仅 HCH refiner
    assert store_f.calls == 1        # 仅 HCH 用 store


def test_hch_loop_report_exposed_for_introspection(tmp_path):
    # ComparisonReport 暴露 HCH 完整 LoopReport,供诊断"自进化改了啥"
    rep, *_ = _compare(tmp_path, [_PICK_W])
    assert rep.hch_loop_report is not None
    assert len(rep.hch_loop_report.refine_events) == rep.arms["HCH"].n_refines
    assert len(rep.hch_loop_report.breaker_events) == rep.arms["HCH"].n_breaker_trips


def test_compare_accepts_scorer(tmp_path):
    from youzi.eval.scorer import ReturnScorer
    rep, *_ = _compare(tmp_path, [_PICK_W], scorer=ReturnScorer())
    # 四路齐全;HCH 的 EvalReport 存在(收益打分)
    assert set(rep.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}


# ── C4:Hcredit 消融臂(编辑通道 vs 战绩回注通道拆开归因)──

def test_ablate_adds_hcredit_arm_and_two_verdicts(tmp_path):
    # 脚本对位 factory 调用顺序 HCH→Hcredit→Hexpert:HCH 选 W、Hcredit 选 W、Hexpert 空仓。
    rep, agent_f, refiner_f, store_f, harness_f = _compare(
        tmp_path, [_PICK_W, _PICK_W, _NO_TRADE], ablate=True)
    assert set(rep.arms) == {"HCH", "Hcredit", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    # Hcredit:门控挡死结构编辑(refine=0、零编辑),但臂报告齐全(照 HCH 做法)
    assert rep.arms["Hcredit"].n_refines == 0
    assert rep.arms["Hcredit"].n_breaker_trips == 0
    assert rep.hcredit_loop_report is not None
    assert rep.hcredit_loop_report.n_edits == 0
    assert rep.arms["Hcredit"].report.mean_excess == 0.5     # 选 W:1.0 − 池基线 0.5
    # 两组消融 verdict(复用 C1 统计裁决层):
    # 编辑通道 HCH−Hcredit 同脚本 → 日均差 0;战绩通道 Hcredit−Hexpert → +0.5
    sv_edit, sv_credit = rep.hch_minus_hcredit_verdict, rep.hcredit_minus_hexpert_verdict
    assert sv_edit is not None and sv_credit is not None
    assert sv_edit.n_days == sv_credit.n_days == 2           # 3 日窗 horizon=1 → 2 已评分日
    assert sv_edit.mean_diff == pytest.approx(0.0)
    assert sv_credit.mean_diff == pytest.approx(0.5)
    # 隔离:Hcredit 独立 fresh H + 独立 agent client;refiner client 仅满足构造、永不被调
    assert harness_f.calls == 3 and agent_f.calls == 3
    assert refiner_f.calls == 2 and store_f.calls == 2


def test_ablate_false_default_no_hcredit_zero_regression(tmp_path):
    # 默认 ablate=False:四臂照旧,C4 新字段全 None(零回归)
    rep, *_ = _compare(tmp_path, [_PICK_W, _NO_TRADE])
    assert "Hcredit" not in rep.arms
    assert rep.hch_minus_hcredit_verdict is None
    assert rep.hcredit_minus_hexpert_verdict is None
    assert rep.hcredit_loop_report is None


def test_stat_verdict_wired_end_to_end(tmp_path):
    # C1 接线:HCH(lr.trajectory)与 Hexpert(wf.walk 的 Trajectory)日级配对 → StatVerdict。
    # 3 日窗 horizon=1 → 2 个已评分日(尾日不入列);HCH 选 W 日级 adv=+0.5,Hexpert 空仓=0。
    rep, *_ = _compare(tmp_path, [_PICK_W, _NO_TRADE])
    sv = rep.stat_verdict
    assert sv is not None
    assert sv.n_days == 2
    assert sv.mean_diff == pytest.approx(0.5)        # 日级配对差均值 = +0.5
    assert sv.verdict == "insufficient"              # 2 < 8:小窗保守不下结论
    assert sv.ci_low is not None and sv.p_value is not None   # n≥2 仍附信息
    # 旧 bool 北极星裁决保留且不受影响
    assert rep.hch_beats_hexpert is True
    # Hexpert 改 walk()+report_from_trajectory 后行为等价(指标与旧 run() 路径一致)
    assert rep.arms["Hexpert"].report.mean_score == 0.0
    assert rep.arms["Hexpert"].report.n_decisions == 3
