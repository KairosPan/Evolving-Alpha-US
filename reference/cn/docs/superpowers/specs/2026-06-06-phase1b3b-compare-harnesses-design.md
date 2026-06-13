# Phase-1b-3b 设计:HCH/Hexpert/Hmin 三方度量对比

> 日期:2026-06-06 · 分支 `phase-1b3b-compare`(待建)· 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans` 出逐任务执行计划。
>
> 先读:`PROJECT_STATE.md`(状态)· `后续开发文档.md`(§2 不变量、§4 路线图)· `自进化游资系统-架构蓝图-v1.0.md`(§6.9 bootstrap 退化负面发现)· `docs/superpowers/specs/2026-06-06-phase1b3a-...md`(内环编排)。

---

## 0. 一句话

1b-3a 已让内环能端到端自进化(`InnerLoop.run()`)。**本 spec 做 1b-3b:把它放到同窗同 oracle 的尺子上量**——跑 `HCH`(自精炼内环)vs `Hexpert`(冻结种子 H + agent,无 Refiner)vs `Hmin`(裸 baseline:HighestBoard 主 + NoTrade 附)三/四路,出 `ComparisonReport`,直接回答论文核心问题:**自进化到底有没有比 frozen 强、有没有退化到比 frozen 还差**(蓝图 §6.9 最重要的负面发现)。影子 Hexpert 环内严格地板 = 1b-3c(本 spec 不做)。

## 1. 已锁定决策(brainstorming,用户确认)

1. **范围 = 仅三方对比**(HCH/Hexpert/Hmin);**影子 Hexpert 环内严格地板留 1b-3c**(改 InnerLoop、LLM agent 成本翻倍,按对比结果再决定是否急需)。
2. **Hmin = HighestBoard 主 + NoTrade 附**(两条平凡基线都报:能看出"主动追高 vs 不交易"的下界)。
3. **factory 注入**(非实例):每路 `harness_factory()` 拿独立 fresh 种子 H(HCH 改自己的/Hexpert 冻结自己的,互不污染);每路 `agent_llm_factory()` 拿独立 LLM client(防测试 MockLLM 调用计数跨路串台;真实 DeepSeek 无状态)。

## 2. 不变量(必须守,沿用 `后续开发文档.md` §2)

1. **未来函数防火墙**:HCH 复用 `InnerLoop` 的防火墙(决策 ≤t、延迟打分、refine 次日生效);Hexpert/Hmin 复用 `WalkForwardEval.walk` 的(≤t 决策、t+horizon 延迟打分)。`compare_harnesses` 只编排,**不取数、不持 source 句柄、不进 ≤t 推理路径**。
2. **同尺可比**:四路同 `source`/`start`/`end`/`horizon`/同 oracle(`WalkForwardEval` 与 `report_from_trajectory` 共用 `build_report`,口径一致)。
3. **同起点**:HCH 与 Hexpert 各自 `harness_factory()` 独立 fresh 种子 H —— 同一起点、互不污染;差异只来自"自精炼 vs 冻结 vs 裸基线"。
4. **H 真冻结**:Hexpert 用 `LLMAgentPolicy(frozen_H, agent_llm)`,**不配 Refiner/MetaTools** → H 在整段回放中不变。
5. **frozen 快照**:`ArmReport`/`ComparisonReport` frozen pydantic。
6. **离线可测**:每路独立 `MockLLMClient`(via factory)+ `FakeSource` + `SnapshotStore(tmp_path)`(via store_factory),永不触网。

## 3. 模块布局与依赖方向

`youzi/loop/compare.py` 与 `inner_loop.py` 同包(顶层整合:依赖 `loop`(InnerLoop)+ `eval`(WalkForwardEval/report_from_trajectory/EvalReport)+ `agent`(LLMAgentPolicy)+ `harness`(HarnessManager)+ `baselines`)。

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/loop/compare.py` | **新增** | `ArmReport` · `ComparisonReport` · `compare_harnesses(...)` |
| `tests/test_compare.py` | **新增** | 四路对比 + delta/verdict + HCH 环信息,全离线 |

**复用(不改)**:`InnerLoop`/`LoopReport`(HCH)· `WalkForwardEval.run`(Hexpert/Hmin)· `report_from_trajectory`(HCH 轨迹→EvalReport)· `LLMAgentPolicy`(Hexpert agent)· `HarnessManager`/`SnapshotStore`(HCH)· `baselines.HighestBoardPolicy`/`NoTradePolicy`(Hmin)· `EvalReport`(metrics)。

## 4. 数据模型与接口(精确)

### 4.1 `loop/compare.py`:报告模型

```python
class ArmReport(BaseModel):           # frozen:一路结果
    model_config = ConfigDict(frozen=True)
    name: str                         # "HCH" / "Hexpert" / "Hmin_highest" / "Hmin_notrade"
    report: EvalReport
    n_refines: int | None = None         # 仅 HCH:LoopReport.refine_events 数
    n_breaker_trips: int | None = None   # 仅 HCH:LoopReport.breaker_events 数
    frozen_from: Date | None = None      # 仅 HCH:LoopReport.frozen_from

class ComparisonReport(BaseModel):    # frozen
    model_config = ConfigDict(frozen=True)
    arms: dict[str, ArmReport] = Field(default_factory=dict)   # name → ArmReport
    hch_minus_hexpert_mean_score: float
    hch_minus_hexpert_hit_rate: float
    hch_minus_hexpert_nuke_rate: float
    hch_beats_hexpert: bool           # (HCH.mean_score - Hexpert.mean_score) > 0
    def __bool__(self) -> bool: return True
```

### 4.2 `loop/compare.py`:`compare_harnesses`

```python
def compare_harnesses(
    harness_factory: Callable[[], HarnessState],
    source, start: Date, end: Date, *,
    agent_llm_factory: Callable[[], LLMClient],
    refiner_llm_factory: Callable[[], LLMClient],
    store_factory: Callable[[], SnapshotStore],
    loop_config: LoopConfig | None = None,
    refiner_config: RefinerConfig | None = None,
) -> ComparisonReport:
    """四路同窗同 oracle 对比:HCH(自精炼内环)vs Hexpert(冻结种子+agent)vs Hmin(HighestBoard/NoTrade)。"""
```

流程:
1. `cfg = loop_config or LoopConfig()`;`horizon = cfg.horizon`。
2. **HCH**:`mgr = HarnessManager(harness_factory(), store_factory())`;`loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(), cfg, refiner_config)`;`lr = loop.run()`;`hch_eval = report_from_trajectory(lr.trajectory)`;extras 取自 `lr`(`len(refine_events)`/`len(breaker_events)`/`frozen_from`)。
3. **Hexpert**:`wf = WalkForwardEval(source, start, end, horizon=horizon)`;`hexpert_eval = wf.run(LLMAgentPolicy(harness_factory(), agent_llm_factory()))`(**无 Refiner → H 冻结**)。
4. **Hmin**:`hmin_hb = wf.run(HighestBoardPolicy())`;`hmin_nt = wf.run(NoTradePolicy())`(可复用同一 `wf` 实例:`run()` 内部每次 new `ReplayEngine`,无状态残留 —— 见 `walk_forward.py`)。
5. 组装 `arms`(4 个 `ArmReport`);算 delta:`hch.mean_score - hexpert.mean_score` 等;`hch_beats_hexpert = delta_mean_score > 0`。
6. 返回 `ComparisonReport`。

- **factory 调用次数**:`harness_factory` 调 2 次(HCH、Hexpert 各一份 fresh H);`agent_llm_factory` 调 2 次(HCH agent、Hexpert agent);`refiner_llm_factory` 调 1 次(HCH refiner);`store_factory` 调 1 次(HCH)。Hmin 不用 LLM/H/store。
- **EvalReport 字段**(复用,见 `eval/metrics.py`):`n_decisions/n_no_trade/n_candidates/horizon/hit_rate/nuke_rate/mean_score/by_pattern`。delta 用 `mean_score`(=expectancy)、`hit_rate`、`nuke_rate`。

## 5. 关键边界

- **本切片 = 离线三方对比**(回答"自进化是否优于/退化于 frozen")。**影子 Hexpert 环内严格地板**(并行冻结 agent 实时熔断)= 1b-3c。
- **公平性**:HCH 与 Hexpert 同起点(各自 fresh 种子 H)、同数据、同尺;唯一差异是 HCH 自精炼、Hexpert 冻结。
- compare 不改 InnerLoop/WalkForwardEval,纯组合。

## 6. 防火墙论证(终审会查)

- 四路决策均经各自 ≤t 路径(InnerLoop / walk 都经 `GuardedSource` 的 frozen 快照);打分均 t+horizon 延迟、用已实现成员。`compare_harnesses` 不持 source 句柄、不调取数、不在路径间泄漏未来。
- HCH 的 H 演化只受其自身 ≤t−horizon 已实现证据驱动(InnerLoop 已证);Hexpert 的 H 全程不变;两者输出的 EvalReport 仅聚合各自已实现结果。

## 7. 测试(全离线,每路独立 MockLLM via factory + FakeSource)

**测试可行性约束(重要)**:`MockLLMClient` **忽略提示、返回脚本化响应** → refine 改了 H 也不会改变 agent 的脚本化选股。因此**用 MockLLM 无法演示"refine 让 HCH 选股变好"**(那是真实 DeepSeek 的实效问题)。本切片测的是**对比机器本身**(四路编排、delta/verdict 计算、factory 隔离、HCH 环信息透传)。用**有状态 factory** 给各路不同脚本来制造已知的路间差异:

```python
class _SeqFactory:                 # 第 k 次调用返回第 k 个脚本对应的 client
    def __init__(self, scripts): self._scripts = scripts; self._i = 0
    def __call__(self): c = MockLLMClient(self._scripts[self._i]); self._i += 1; return c
```

- `test_compare.py`:
  - **四路齐全**:`ComparisonReport.arms` 含 "HCH"/"Hexpert"/"Hmin_highest"/"Hmin_notrade",各有 `EvalReport`。
  - **delta/verdict 机器**:`agent_llm_factory=_SeqFactory([HCH脚本选赢家(continued), Hexpert脚本选输家(nuked)])`(call1=HCH、call2=Hexpert)→ HCH.mean_score > Hexpert → `hch_beats_hexpert=True`、`hch_minus_hexpert_mean_score>0`(逐字段对账);**互换脚本**(HCH 选输家、Hexpert 选赢家)→ `hch_beats_hexpert=False`、delta<0(证明退化可如实报出)。
  - **MockLLM 同脚本基线**:HCH 与 Hexpert 用**同一脚本**(选同一赢家)→ 两路 `EvalReport` 相等、delta=0、`hch_beats_hexpert=False`,但 `n_refines>0`(说明 refine 跑了但 MockLLM 下不改脚本化决策——记录此为 MockLLM 局限,真实实效见真实 DeepSeek)。
  - **factory 隔离**:断言 `harness_factory`/`agent_llm_factory`/`refiner_llm_factory`/`store_factory` 各被调用预期次数(2/2/1/1);HCH 改了它的 H 而 Hexpert 的 H 是**不同实例**、不受影响。
  - **HCH 环信息**:`n_refines`/`n_breaker_trips`/`frozen_from` 来自 `LoopReport`,熔断场景下被正确填充。
- 真实种子端到端(终审):`compare_harnesses(lambda: load_seeds("seeds/"), FakeSource(...), …)` 跑通,四路出报告、不崩。
- 回归:既有 230 测试全绿;`InnerLoop`/`WalkForwardEval`/`report_from_trajectory` 行为不变。

## 8. 验收标准(Definition of Done)

1. `compare_harnesses` 跑通四路、同窗同 oracle、各产 `EvalReport`;`ComparisonReport` 含 arms + delta + verdict + HCH 环信息。
2. factory 注入正确(独立 fresh H / 独立 LLM client / HCH 独立 store);Hexpert H 真冻结(无 Refiner)。
3. `hch_beats_hexpert` 两种取值均可如实产出(优于 & 退化于 frozen 都能观测)。
4. 防火墙 §6 论证在代码中成立(compare 无 source 句柄、无跨路未来泄漏)。
5. 新测试 + 全量回归绿;离线、不触网。
6. subagent-driven 两段评审(spec 合规 + 对抗质量)+ opus 终审通过。
7. 文档:更新 `PROJECT_STATE.md`/`后续开发文档.md`(1b-3b 完成 + 债务)与 memory。

## 9. 显式 out-of-scope(1b-3c 及以后)

- **影子 Hexpert 环内严格地板**(InnerLoop 并行跑冻结 agent + 影子相对熔断,论文式实时保护)。
- **按 regime 分层对比**(需校准的 `G_cycle` 相位分类器)。
- **N 日窗口 / 收益幅度 oracle**(需 OHLCV 扩展);成本/滑点折算后的 tradeable edge。
- **多 episode / 多窗口聚合对比**(本切片单窗口三方对比)。
