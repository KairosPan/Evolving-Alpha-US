# youzi/loop/compare.py
from __future__ import annotations

from datetime import date as Date
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.baselines import HighestBoardPolicy, NoTradePolicy
from youzi.eval.metrics import EvalReport
from youzi.eval.stats import StatVerdict, daily_series, paired_daily_diff, verdict
from youzi.eval.walk_forward import WalkForwardEval, report_from_trajectory
from youzi.harness.harness import HarnessState
from youzi.harness.manager import HarnessManager
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import LLMClient
from youzi.loop.inner_loop import InnerLoop, LoopConfig, LoopReport
from youzi.refine.refiner import RefinerConfig


class ArmReport(BaseModel):
    """一路对比的结果(frozen)。HCH 额外带环信息。"""
    model_config = ConfigDict(frozen=True)
    name: str
    report: EvalReport
    n_refines: int | None = None         # 仅 HCH:refine 次数
    n_breaker_trips: int | None = None   # 仅 HCH:熔断次数
    frozen_from: Date | None = None      # 仅 HCH:熔断冻结起始日


class ComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    arms: dict[str, ArmReport] = Field(default_factory=dict)
    hch_minus_hexpert_mean_score: float              # 原始分差(保留旧口径)
    hch_minus_hexpert_mean_excess: float = 0.0       # 截面超额差(advantage 口径;旧 JSON 缺省 → 0.0)
    hch_minus_hexpert_hit_rate: float
    hch_minus_hexpert_nuke_rate: float
    hch_beats_hexpert: bool                          # 北极星裁决:mean_excess>0(C2 起超额口径;旧 bool 保留)
    stat_verdict: StatVerdict | None = None     # C1 统计裁决:日级配对差→CI/p/MDE 四值 verdict(旧 JSON 缺省 → None)
    hch_loop_report: LoopReport | None = None   # HCH 完整环报告(refine_events/breaker_events 明细;诊断"自进化改了啥")
    # ── C4 消融(ablate=True 才填;旧 JSON / 默认四臂缺省 → None)──
    # Hcredit = enable_refine=False 的内环:只有 apply_credit 战绩回注、无 Refiner 结构编辑。
    # 两组配对日差把 HCH−Hexpert 合效应拆成:编辑通道(HCH−Hcredit)+ stats 通道(Hcredit−Hexpert)。
    # ⚠ 解读注意:长窗熔断时 HCH rollback_to 连 skill.stats 一起回滚,而 Hcredit 无 refine
    #   无 checkpoint、熔断只冻结不回滚——两臂 stats 历史不再对称。解读 hch_minus_hcredit
    #   前先核对 arms["HCH"].n_breaker_trips / arms["Hcredit"].n_breaker_trips(>0 时归因失真);
    #   未武装的短窗(已评分日 < breaker_min_days=3,B2 日级武装)不受影响。
    hch_minus_hcredit_verdict: StatVerdict | None = None       # 编辑通道净效应(同窗日级配对)
    hcredit_minus_hexpert_verdict: StatVerdict | None = None   # 战绩回注通道净效应(同上)
    hcredit_loop_report: LoopReport | None = None  # Hcredit 完整环报告(照 HCH 做法;refine_events 应为空)

    def __bool__(self) -> bool:
        return True


def compare_harnesses(
    harness_factory: Callable[[], HarnessState],
    source, start: Date, end: Date, *,
    agent_llm_factory: Callable[[], LLMClient],
    refiner_llm_factory: Callable[[], LLMClient],
    store_factory: Callable[[], SnapshotStore],
    loop_config: LoopConfig | None = None,
    refiner_config: RefinerConfig | None = None,
    scorer=None,
    ablate: bool = False,
    shadow: bool = False,
) -> ComparisonReport:
    """四路同窗同 oracle 对比:HCH(自精炼内环)vs Hexpert(冻结种子 H + agent,无 Refiner)
    vs Hmin(HighestBoard / NoTrade)。每路独立 fresh 种子 H + 独立 LLM client(防交叉污染)。

    C4:ablate=True 时多跑第五臂 Hcredit(enable_refine=False 的内环:apply_credit
    在线战绩回注照常、无 Refiner 结构编辑),并产出两组配对日差裁决,把 HCH−Hexpert
    合效应拆成编辑通道(HCH−Hcredit)与 stats 通道(Hcredit−Hexpert)。

    B2 ⑥:shadow=True 时**先跑 Hexpert** 臂,从其 trajectory 提取日级 advantage 序列
    (eval.stats.daily_series 口径)作 shadow_daily 传入 HCH(与 Hcredit)的 InnerLoop
    熔断(影子配对地板)——整窗序列含未来日,InnerLoop 内部按当前已评分日严格过滤
    防前视。默认 False 行为不变。

    factory 调用顺序(测试脚本按此对位):
      shadow=False:HCH → Hcredit(仅 ablate)→ Hexpert;
      shadow=True :Hexpert → HCH → Hcredit(仅 ablate)。"""
    cfg = loop_config or LoopConfig()

    # Hexpert 评测器(C1:走 walk()+report_from_trajectory,留住 Trajectory 供日级统计)
    wf = WalkForwardEval(source, start, end, horizon=cfg.horizon, scorer=scorer)
    hexpert_traj = None
    shadow_daily: dict[Date, float] | None = None
    if shadow:
        # B2 ⑥:先跑 Hexpert,日级 advantage 序列作影子地板喂给内环熔断
        hexpert_traj = wf.walk(LLMAgentPolicy(harness_factory(), agent_llm_factory()))
        shadow_daily = dict(daily_series(hexpert_traj))

    # HCH:自精炼内环
    mgr = HarnessManager(harness_factory(), store_factory())
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(),
                     refiner_llm_factory(), cfg, refiner_config, scorer=scorer,
                     shadow_daily=shadow_daily)
    lr = loop.run()
    hch_eval = report_from_trajectory(lr.trajectory)
    hch_arm = ArmReport(name="HCH", report=hch_eval,
                        n_refines=len(lr.refine_events),
                        n_breaker_trips=len(lr.breaker_events),
                        frozen_from=lr.frozen_from)

    # C4 Hcredit:消融臂(只有战绩回注、无结构编辑)。独立 fresh 种子 H + 独立 LLM
    # client(经现有 factory,防交叉污染);refiner client 仅满足构造签名,enable_refine=False
    # 下永不被调。无 refine → 无 checkpoint → 共享 store 目录也零写入、熔断只冻结不回滚。
    hcredit_lr: LoopReport | None = None
    hcredit_arm: ArmReport | None = None
    if ablate:
        mgr_c = HarnessManager(harness_factory(), store_factory())
        cfg_c = cfg.model_copy(update={"enable_refine": False})
        loop_c = InnerLoop(mgr_c, source, start, end, agent_llm_factory(),
                           refiner_llm_factory(), cfg_c, refiner_config, scorer=scorer,
                           shadow_daily=shadow_daily)   # B2 ⑥:影子地板同样喂给消融臂
        hcredit_lr = loop_c.run()
        hcredit_arm = ArmReport(name="Hcredit",
                                report=report_from_trajectory(hcredit_lr.trajectory),
                                n_refines=len(hcredit_lr.refine_events),   # 恒 0(门控挡死)
                                n_breaker_trips=len(hcredit_lr.breaker_events),
                                frozen_from=hcredit_lr.frozen_from)

    # Hexpert:冻结种子 H + agent(无 Refiner → H 全程不变)
    # C1:走 walk()+report_from_trajectory(与 run() 等价,有等价性测试守着),
    # 留住 Trajectory 供日级统计裁决——不重复跑 LLM。
    # B2 ⑥:shadow=True 时 Hexpert 已先跑(轨迹复用,同样不重复跑 LLM)。
    if hexpert_traj is None:
        hexpert_traj = wf.walk(LLMAgentPolicy(harness_factory(), agent_llm_factory()))
    hexpert_eval = report_from_trajectory(hexpert_traj)
    hexpert_arm = ArmReport(name="Hexpert", report=hexpert_eval)

    # Hmin:裸基线(同一 wf 实例可复用:run() 内部每次 new ReplayEngine,无状态残留)
    hmin_hb = ArmReport(name="Hmin_highest", report=wf.run(HighestBoardPolicy()))
    hmin_nt = ArmReport(name="Hmin_notrade", report=wf.run(NoTradePolicy()))

    d_mean = hch_eval.mean_score - hexpert_eval.mean_score
    d_excess = hch_eval.mean_excess - hexpert_eval.mean_excess   # 截面 demean 砍掉日间共同β
    d_hit = hch_eval.hit_rate - hexpert_eval.hit_rate
    d_nuke = hch_eval.nuke_rate - hexpert_eval.nuke_rate
    # C1 统计裁决:两臂日级等权 advantage 序列 → 按日配对差 → bootstrap CI/置换 p/MDE
    diffs = paired_daily_diff(daily_series(lr.trajectory), daily_series(hexpert_traj))
    stat = verdict(diffs)

    arms = {"HCH": hch_arm, "Hexpert": hexpert_arm,
            "Hmin_highest": hmin_hb, "Hmin_notrade": hmin_nt}
    # C4 消融裁决:复用 C1 统计裁决层(daily_series/paired_daily_diff/verdict),
    # 编辑通道 = HCH−Hcredit,stats 通道 = Hcredit−Hexpert(同窗同日历配对)。
    hch_vs_hcredit: StatVerdict | None = None
    hcredit_vs_hexpert: StatVerdict | None = None
    if hcredit_arm is not None and hcredit_lr is not None:
        arms["Hcredit"] = hcredit_arm
        ds_hcredit = daily_series(hcredit_lr.trajectory)
        hch_vs_hcredit = verdict(paired_daily_diff(daily_series(lr.trajectory), ds_hcredit))
        hcredit_vs_hexpert = verdict(paired_daily_diff(ds_hcredit, daily_series(hexpert_traj)))
    return ComparisonReport(
        arms=arms,
        hch_minus_hexpert_mean_score=d_mean,
        hch_minus_hexpert_mean_excess=d_excess,
        hch_minus_hexpert_hit_rate=d_hit,
        hch_minus_hexpert_nuke_rate=d_nuke,
        hch_beats_hexpert=d_excess > 0,   # C2:北极星裁决改超额口径(去市场β后才算真胜)
        stat_verdict=stat,                # C1:带 CI/p/MDE 的可证伪裁决(旧 bool 保留向后兼容)
        hch_loop_report=lr,
        hch_minus_hcredit_verdict=hch_vs_hcredit,           # C4:编辑通道净效应(None=未消融)
        hcredit_minus_hexpert_verdict=hcredit_vs_hexpert,   # C4:战绩回注通道净效应
        hcredit_loop_report=hcredit_lr,
    )
