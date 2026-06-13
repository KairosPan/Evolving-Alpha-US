# Phase-1b-3a 设计:内环编排(交错 act→打分→在线信用→refine,reset-free)+ 能力地板熔断

> 日期:2026-06-06 · 分支 `phase-1b3a-inner-loop`(待建)· 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans` 出逐任务执行计划。
>
> 先读:`PROJECT_STATE.md`(状态)· `后续开发文档.md`(§2 不变量、§4 路线图)· `自进化游资系统-架构蓝图-v1.0.md`(§6.9 bootstrap 退化负面发现、§8 六道闸)· `docs/superpowers/specs/2026-06-{01,06}-phase1b{1,2}-...md`(观测层 + LLM Refiner)。

---

## 0. 一句话

1b-2 已让 Refiner 能"读一段证据→编辑 H"。**本 spec 做 1b-3a:把它编排成一个交错内环**——每个交易日 agent 用 **live H**(在变)决策、延迟打分、**在线信用**就地回填 SkillStats、**每日 refine** 编辑 live H(次日 agent 立即可见),reset-free;并加 **能力地板熔断**(自相对地板,防论文最重要的负面发现:bootstrap 自更新退化到比 frozen 还差)。HCH/Hexpert/Hmin 三方度量对比 = **1b-3b**(本 spec 不做)。

## 1. 已锁定决策(brainstorming,用户确认)

1. **切片**:1b-3 拆 **1b-3a(本 spec:编排环 + 在线信用 + 能力地板熔断)** 与 1b-3b(度量对比 + 影子 Hexpert 严格地板)。先做 3a(自包含、便宜、可独立测)。
2. **refine 节奏 = 每日**(`refine_every=1`;暴露 knob 但默认每日):未冻结且当日有新评分证据时触发。
3. **能力地板熔断 = 自相对 + 绝对地板**(3a 内,不需并行影子 Hexpert):滚动 expectancy 跌破"早期基线窗口 − margin"或绝对地板 → 熔断。严格 HCH-vs-Hexpert 影子对照留 3b。
4. **熔断动作 = rollback 上个 checkpoint + 冻结后续 refine**(双保险);rollback 后 **rebind agent+refiner 到还原态**(解 0b-3 "rollback 旧引用失效"债务);无 checkpoint 时只冻结。

## 2. 不变量(必须守,沿用 `后续开发文档.md` §2)

1. **未来函数防火墙**:决策日 t 只用 ≤t(经 `GuardedSource` 的 frozen 快照);延迟打分用 t+horizon 已录成员;**在线信用/签名/refine 只用已实现的 ≤t−horizon 结果**;refine 编辑**次日才对 agent 生效**。轨迹/报告不持 source 句柄。
2. **观测 vs 编辑边界**:`SkillStats` 由 `apply_credit` 直写(观测,不入 EditLog);refine 的结构性 Δ 入 EditLog(经 `MetaTools`)。**1b-2 的 LLM-不可信边界硬化(stats/importance 写保护、regime 类型安全、status 钳制)继续有效**。
3. **reset-free**:全程单条游标推进、单个 live H;refine 就地编辑同一 H,agent 立即可见。
4. **熔断 = 安全网,不是优化**:熔断只在 rolling expectancy 跌破地板时触发;触发后 rollback + 冻结,系统退回能力地板以上的最近 good 态。
5. **frozen 快照**:`LoopReport`/`RefineEvent`/`BreakerEvent` 全 frozen pydantic;`Trajectory`/`TrajectoryStep` 复用 1b-1。
6. **离线可测**:`FakeSource` + 两个 `MockLLMClient`(agent 脚本决策 / refiner 脚本 ops),永不触网。

## 3. 模块布局与依赖方向

`youzi/loop/` 是顶层整合包(依赖 eval + refine + harness + universe + replay)。

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/refine/credit.py` | 加函数 | `merge_credit_reports(reports: list[CreditReport]) -> CreditReport`(纯只读合并,**不碰 stats**) |
| `youzi/loop/__init__.py` | **新增** | 包初始化 |
| `youzi/loop/inner_loop.py` | **新增** | `LoopConfig` · `RefineEvent`/`BreakerEvent`/`LoopReport` · `InnerLoop` |
| `tests/test_merge_credit.py` | **新增** | merge 合并语义 |
| `tests/test_inner_loop.py` | **新增** | 交错环 + 在线信用 + reset-free 可见 + 熔断,全离线 |

**复用(不改)**:`WalkForwardEval` 的延迟打分机制(本环复刻其打分循环,但交错 refine——不 fork `walk()`,逻辑同源但环内内联)· `ReplayEngine` · `build_universe` · `PoolRecord`/`outcome`/`SCORE` · `apply_credit`/`extract_signatures` · `Refiner`/`LLMAgentPolicy` · `HarnessManager`/`SnapshotStore` · `report_from_trajectory`。

## 4. 数据模型与接口(精确)

### 4.1 `refine/credit.py`:`merge_credit_reports`

```python
def merge_credit_reports(reports: list[CreditReport]) -> CreditReport:
    """把多份增量 CreditReport 合并为一份(纯只读,不触 SkillStats)。
    per_skill 按 skill_id 累加 n/wins/losses/nukes 与 score_sum(=expectancy*n),重算 hit_rate/nuke_rate/expectancy;
    unattributed 同法合并;n_scored 累加。空列表 → 空 CreditReport(n_scored=0)。"""
```

- 实现复用 `_Acc`(或等价累加器):对每份 report 的每个 `SkillCredit`,累加 `n/wins/losses/nukes` 和 `expectancy*n`(还原 score_sum),末尾构造 `SkillCredit`(n≥1 才构造,无除零)。
- 语义:给 refiner 的"本窗口谁在亏"——是**最近窗口增量之和**,区别于 H 内的**累计** stats(K-pass 系统提示渲染累计;user 提示渲染本窗口增量)。

### 4.2 `loop/inner_loop.py`:配置与报告模型

```python
class LoopConfig(BaseModel):
    horizon: int = 1                  # 延迟打分窗口(同 WalkForwardEval)
    refine_every: int = 1             # 每 N 个交易日 refine 一次(默认每日)
    credit_window: int = 10           # 给 refiner 的证据窗口(最近 N 个已评分步)
    # 能力地板熔断(自相对 + 绝对;SCORE∈{1,0,−1},expectancy∈[−1,1])
    breaker_window: int = 20          # 滚动 expectancy 窗口(最近 N 个已评分候选)
    baseline_window: int = 20         # 基线 = 前 N 个已评分候选的均值
    floor_abs: float = -0.2           # 绝对地板:rolling < floor_abs → 熔断
    floor_rel_margin: float = 0.15    # 相对地板:rolling < baseline − margin → 熔断
    breaker_min_samples: int = 40     # 已评分候选数 ≥ 此值才可能熔断(默认 baseline+breaker)

class RefineEvent(BaseModel):         # frozen:一次 refine 的记录
    model_config = ConfigDict(frozen=True)
    date: Date
    checkpoint_version: int | None    # checkpoint-before 的版本(无则 None)
    report: RefineReport

class BreakerEvent(BaseModel):        # frozen:一次熔断的记录
    model_config = ConfigDict(frozen=True)
    date: Date
    rolling: float
    baseline: float | None
    reason: str                       # "rolling<floor_abs" / "rolling<baseline-margin"
    rolled_back_to: int | None        # rollback 到的版本(无 checkpoint 则 None=只冻结)

class LoopReport(BaseModel):          # frozen
    model_config = ConfigDict(frozen=True)
    trajectory: Trajectory            # HCH 轨迹(供 1b-3b report_from_trajectory)
    refine_events: list[RefineEvent] = Field(default_factory=list)
    breaker_events: list[BreakerEvent] = Field(default_factory=list)
    frozen_from: Date | None = None   # 熔断冻结起始日(None=全程未熔断)
    n_edits: int = 0                  # EditLog 累计编辑数(applied)
    def __bool__(self) -> bool: return True
```

### 4.3 `loop/inner_loop.py`:`InnerLoop`

```python
class InnerLoop:
    """内环编排:交错 act→延迟打分→在线信用→(每日)refine,reset-free + 能力地板熔断。

    持有 HarnessManager(live H + EditLog + MetaTools + SnapshotStore);
    agent/refiner 由 manager.harness/manager.tools 构造,rollback 后重建(rebind)。
    """
    def __init__(self, manager: HarnessManager, source, start: Date, end: Date,
                 agent_llm: LLMClient, refiner_llm: LLMClient,
                 config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None) -> None: ...

    def run(self) -> LoopReport: ...
```

`run()` 主循环(reset-free,游标推进;`_rebind()` 在启动与每次 rollback 后调,用 `manager.harness`/`manager.tools` 重建 `self._agent=LLMAgentPolicy(manager.harness, agent_llm)` 与 `self._refiner=Refiner(manager.harness, refiner_llm, manager.tools, refiner_config)`):

```
engine = ReplayEngine(source, start, end); record = PoolRecord()
days_seen=[]; drafts=[]; pending=[]; scored_steps=[]      # frozen 已评分步,按序
per_step_credits=[]                                        # (cursor, CreditReport) 滚动
scores=[]                                                  # 已实现 per-候选 SCORE,按序(熔断用)
last_ckpt=None; frozen=False; frozen_from=None
refine_events=[]; breaker_events=[]
idx=0
loop:
  cursor=engine.cursor; days_seen.append(cursor)
  state=engine.observe(); universe=build_universe(engine.guarded_source, cursor); record.record(cursor, universe)
  decision=self._agent.decide(state, universe)            # live H
  entries=去重入选→EntrySnap(同 walk)
  drafts.append({date,market,decision,entries,scored:False,outcomes:{}}); pending.append(idx)
  # 延迟打分(复用 walk 机制):到 horizon 的决策打分 → 构造 frozen TrajectoryStep
  newly=[]; remaining=[]
  for j in pending:
    if idx>=j+horizon:
      mem=record.get(days_seen[j+horizon]); 打分填 drafts[j].outcomes/scored=True
      step_j=TrajectoryStep(**drafts[j]); scored_steps.append(step_j); newly.append(step_j)
    else: remaining.append(j)
  pending=remaining
  # 在线信用 + 熔断分数序列(每个刚评分步调一次 apply_credit,就地改 stats、不重复)
  for step in newly:
    cr=apply_credit(Trajectory(steps=[step], horizon=horizon), manager.harness)   # mutate stats
    per_step_credits.append((cursor, cr))
    for sc in step.outcomes.values(): scores.append(sc.score)
  # 熔断检查(自相对 + 绝对;只触发一次)
  if not frozen and len(scores)>=breaker_min_samples:
    baseline=mean(scores[:baseline_window]); rolling=mean(scores[-breaker_window:])
    reason = "rolling<floor_abs" if rolling<floor_abs else ("rolling<baseline-margin" if rolling<baseline-floor_rel_margin else None)
    if reason:
      rolled=None
      if last_ckpt is not None: manager.rollback_to(last_ckpt); self._rebind(); rolled=last_ckpt
      frozen=True; frozen_from=cursor
      breaker_events.append(BreakerEvent(date=cursor, rolling=rolling, baseline=baseline, reason=reason, rolled_back_to=rolled))
  # refine(每日;未冻结、到节奏、有新证据)
  if not frozen and newly and (idx % refine_every == 0):
    ver=manager.checkpoint(label=f"pre-refine {cursor}"); last_ckpt=ver           # checkpoint-before
    win=scored_steps[-credit_window:]
    win_traj=Trajectory(steps=win, horizon=horizon)
    credit=merge_credit_reports([cr for (d,cr) in per_step_credits[-credit_window:]])
    sigs=extract_signatures(win_traj, manager.harness)
    rep=self._refiner.refine(win_traj, credit, sigs)                              # 编辑 live H(经 manager.tools→EditLog)
    refine_events.append(RefineEvent(date=cursor, checkpoint_version=ver, report=rep))
  idx+=1
  if not engine.step(): break
traj=Trajectory(steps=[TrajectoryStep(**d) for d in drafts], horizon=horizon)     # 全步(尾部 scored=False 保留)
return LoopReport(trajectory=traj, refine_events=..., breaker_events=..., frozen_from=frozen_from, n_edits=len(manager.log))
```

- **rollback 后 rebind**:`manager.rollback_to` 把 `manager.harness/log/tools` 换成还原态新对象;`_rebind()` 据此重建 `self._agent/self._refiner`,使后续 act 读还原态、(虽已冻结)refiner 也指向还原态。**这是 0b-3 债务①的解法落点。**
- **熔断分数粒度**:per-**候选** SCORE(与 `EvalReport.mean_score`/expectancy 同口径);no-trade 日不贡献分数。
- **rollback 后 scored_steps/scores 不回溯**:熔断后冻结、不再 refine,这些累计仅用于报告与(已停用的)判定,不影响正确性(防火墙不破)。

## 5. 关键边界

- **在线信用(mutate)vs refiner 证据(只读)**:`apply_credit` 每候选恰好计一次(评分时);refiner 的窗口 CreditReport 由 `merge_credit_reports` 只读合并,**绝不二次 mutate stats**。`extract_signatures` 本就只读。
- **checkpoint-before / rollback / 冻结 = 本切片**;**HCH/Hexpert/Hmin 三方对比 + 影子 Hexpert 严格地板 = 1b-3b**。
- **熔断自相对地板**:用 HCH 自身早期基线 + 绝对地板,不需并行冻结 H(成本低);严格"是否比 frozen 强"是 3b 的离线度量。

## 6. 防火墙论证(终审会查)

- 决策(`self._agent.decide`)只拿当日 `state`/`universe`(≤t、frozen、无 source 句柄);打分用 `record` 在 t+horizon 游标已录的成员(届时已实现);在线信用/签名/refine 只消费已评分(≤t−horizon)的 frozen 步。refine 编辑 live H,但**次日**决策才用到——当日决策已先于 refine 完成。
- `LoopReport.trajectory` 不持 source;`apply_credit` 输入是单步 frozen Trajectory(已实现 outcomes)。
- rollback 只加载过去快照,不引入未来。

## 7. 测试(全离线,FakeSource + 两个 MockLLMClient)

- `test_merge_credit.py`:两份增量 CreditReport 合并 → per_skill n/wins/losses/nukes 累加、expectancy 加权重算、unattributed 合并、n_scored 累加;空列表→空报告。
- `test_inner_loop.py`:
  - **交错延迟打分**:短回放(如 6 日,horizon=1),`LoopReport.trajectory` 步数/延迟 outcomes/尾部 `scored=False` 正确(与等价 `walk()` 同源不冲突)。
  - **在线信用 mid-loop**:某技能被引用且评分后,其 `SkillStats.n/nukes` 在循环**中途**已增(非循环结束才更新)——可在 refiner 的 MockLLM 收到的 user 提示里断言含该技能的信用,或直接断言 `manager.harness` 内 stats 中途态。
  - **reset-free 可见**:refiner MockLLM 脚本一条 `retire_skill`(真实/构造技能)→ 断言**次日** agent 的系统提示(由 loop 内 `LLMAgentPolicy` 重建)不再含该技能;EditLog 记该编辑。
  - **每日 refine 节奏**:horizon=1 时,首个有新评分证据的日起每日触发;`refine_events` 日期/数量符合 `refine_every`;refiner MockLLM 调用次数符合(每 refine 3 次 live:p/K/M)。
  - **熔断 + rollback + 冻结**:构造 FakeSource 使评分多为 nuked(scores 偏负)→ rolling 跌破地板 → `breaker_events` 记一条(reason/rolling/baseline/rolled_back_to)、`frozen_from` 置位、**其后无新 `refine_events`**、`manager.harness` 已回到 checkpoint 态(某编辑被撤销)。
  - **无 checkpoint 熔断**:若熔断早于任何 refine(无 checkpoint)→ `rolled_back_to=None`、只冻结、不崩。
  - **防火墙**:由构造保证(策略只拿 frozen 快照);可加一条"决策日请求未来日经 GuardedSource 抛 LookaheadError"的既有保证复用说明。
- 回归:既有 217 测试全绿;`apply_credit`/`Refiner`/`walk()` 行为不变。

## 8. 验收标准(Definition of Done)

1. `merge_credit_reports` 正确(只读、加权重算、空安全)。
2. `InnerLoop.run()` 跑通交错环:延迟打分 + 在线信用就地更新 stats + 每日 refine 编辑 live H + 次日可见;`LoopReport` 结构完整。
3. 能力地板熔断:自相对 + 绝对触发、一次性、rollback 上个 checkpoint + rebind + 冻结后续 refine;无 checkpoint 时只冻结、不崩。
4. 防火墙 §6 论证在代码中成立(无 source 句柄泄漏、refine 编辑次日才生效、rollback 只引入过去)。
5. 新测试 + 全量回归绿;离线、不触网。
6. subagent-driven 两段评审(spec 合规 + 对抗质量)+ opus 终审通过。
7. 文档:更新 `PROJECT_STATE.md`/`后续开发文档.md`(1b-3a 完成 + 债务)与 memory。

## 9. 显式 out-of-scope(1b-3b 及以后)

- **HCH vs Hexpert vs Hmin 三方度量对比**(同窗口同 oracle 跑 self-refining / frozen seed / bare baseline,出对比报告)。
- **影子 Hexpert 严格地板**(环内并行冻结 H 实时比对,论文式"不退化到比 frozen 还差"的严格判定)。
- **rollback-to-last-good(多 refine)**:本切片熔断 rollback 到**上个** checkpoint;"回退到退化窗口之前的 good 态"是增强。
- **checkpoint 成本治理**:每日 checkpoint = N 个磁盘快照(~68KB/个);keep-last-K / 内存 ring 是增强。
- **在线 EWMA decay 加权信用**(本切片在线信用沿用 `apply_credit` 既有 decay;regime 双衰减待六道闸)。
- **bootstrap 退化的严格证伪**(论文 §6.9 的核心负面发现验证)需 3b 的三方对比数据。
