# Phase-1b-1 设计:轨迹 · 信用分配 · 失败签名(deterministic 观测层)

> 日期:2026-06-01 · 分支 `phase-1b1-trajectory-credit` · 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans` 出逐任务执行计划。
>
> 先读:`PROJECT_STATE.md`(状态)· `后续开发文档.md`(§2 不变量、§4 路线图)· `自进化游资系统-架构蓝图-v1.0.md`(权威设计)。

---

## 0. 一句话

Phase-1b(Refiner = 真正的自进化)拆 1b-1/1b-2/1b-3。**本 spec 只做 1b-1:确定性、无 LLM、纯离线可测的"观测层"**——把一次回放走出的 `Trajectory` 记下来,用**已实现 oracle 结果**给 agent 引用的技能做**信用分配**(终于把空着的 `SkillStats` 槽填上),并抽取**结构化失败签名**。1b-2(LLM Refiner + 四遍 CRUD)与 1b-3(内环编排 + HCH/Hexpert/Hmin 度量 + 能力地板)在其之上。

## 1. 已锁定决策(brainstorming,用户确认)

1. **切片**:Phase-1b 拆 1b-1/1b-2/1b-3,先做 1b-1(本 spec)。沿用 0b-1/2/3 节奏。
2. **失败证据来源**:**oracle 驱动(pool-membership:nuked/faded=亏),OHLCV 推迟**。13 个 K 线 `failure_detector` 仍只作为 1b-2 LLM 的提示知识;把它们当代码跑是后续 OHLCV 增强。
3. **1b-1 边界**:Trajectory + 信用分配 + **确定性失败签名**三者同属对"已打分轨迹"的确定性分析,内聚为一个切片;1b-2 因此变成"纯 LLM Refiner 消费这些结构化证据"。
4. **faded 信用**:`continued`=win;`faded` 与 `nuked` 同记为"非 win"(连续性打法没续上=miss),但在 `SkillStats.expectancy`(SCORE 滚动均值)里**保留 faded(0)/nuked(−1) 的区别**,并**单独**统计 nuke 次数。

### 1.1 brainstorming 后的事实修正(写 spec 时发现,需评审知晓)

- **`MarketState` 没有离散相位字段**(只有 `sentiment_norm`/`money_effect_raw` 等客观标量;校准过的 `G_cycle` 相位分类器是 Phase-1 项,尚未建)。项目铁律"弃绝对阈值",故 1b-1 **无法诚实地把某日打成"退潮"**。→ 原设计里的 `relay_in_ebb`(退潮接力)签名**移入推迟**,待 `G_cycle` 相位分类器就绪再做。
- **`Candidate` 不带连板/状态信息**(只有 code/name/pattern/reason/confidence)。个股板数/状态在 `CandidateUniverse`(`StockSnapshot.boards/status`)里。→ Trajectory 必须在**决策时点**把每个入选 code 的客观入场上下文(boards/status)快照进来,信用分配/签名才能纯函数化、且不再触 source(防火墙更稳)。
- 结论:1b-1 的失败签名改为 **board-rank(相对当日 `max_board_height`)× oracle outcome** 驱动——regime-relative、合规、且只用现有数据。

## 2. 不变量(必须守,沿用 §2)

1. **未来函数防火墙**:信用分配与签名抽取**在回放走完后、对已实现结果做事后分析**,永不进入 ≤t 决策路径。产出的 `SkillStats` 次日对 agent 可见,但它们只聚合 ≤ t−horizon(已成为过去)的结果,无前视。
2. **H 只经 9 个 meta-tool 做结构性编辑**——但见 §5 的"观测 vs 编辑"边界决策:**stats 是观测,由信用分配直接写,不入 EditLog**;结构性"改打法"是 1b-2 的活,走 meta-tool 且入 EditLog。
3. **frozen 快照**:`Trajectory`/`TrajectoryStep`/`EntrySnap`/`FailureSignature`/`CreditReport`/`SkillCredit` 全部 frozen pydantic;`SkillStats` 仍可变(运行期更新)。
4. **缺失值诚实 `None`**(boards 可为 None);**不臆造**。
5. **离线可测**:`FakeSource` + 脚本化 policy,永不触网。
6. **向后兼容**:`WalkForwardEval.run(policy) -> EvalReport` 签名与返回不变 → 既有 129+ eval 测试全绿。

## 3. 模块布局与依赖方向

层级自底向上:`data→features→replay→schemas→universe→eval→harness→llm/agent→refine`。`Trajectory` 放 `eval/`(它是任意 policy 走的记录,与 refiner 无关,使 `eval` 不依赖 `refine`);`refine/` 依赖 `eval`(Trajectory/Outcome/SCORE)+ `harness`(读写 SkillStats)。

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/eval/trajectory.py` | 新增 | `EntrySnap` · `TrajectoryStep` · `Trajectory` |
| `youzi/eval/walk_forward.py` | 重构 | 加 `walk(policy) -> Trajectory`;`run()` = `report_from_trajectory(self.walk(policy))` |
| `youzi/eval/metrics.py` | 加函数 | `report_from_trajectory(traj) -> EvalReport`(内部复用现有 `build_report`,**不改其签名**) |
| `youzi/harness/skill.py` | 加字段 | `SkillStats.nukes: int = 0`(默认 0,序列化前向兼容;`record()` 不变) |
| `youzi/refine/__init__.py` | 新增 | 包初始化 |
| `youzi/refine/credit.py` | 新增 | `CreditPolicy` 映射 · `SkillCredit` · `CreditReport` · `apply_credit(traj, harness) -> CreditReport` |
| `youzi/refine/signatures.py` | 新增 | `FailureKind` · `FailureSignature` · `extract_signatures(traj, harness) -> list[FailureSignature]` |
| `tests/test_trajectory.py`、`test_credit.py`、`test_signatures.py`、`test_walk_forward_trajectory.py` | 新增 | 全离线 |

## 4. 数据模型与接口(精确)

### 4.1 `eval/trajectory.py`

```python
class EntrySnap(BaseModel):       # frozen:入选 code 在决策日的客观入场上下文(≤t)
    model_config = ConfigDict(frozen=True)
    code: str
    status: StockStatus           # limit_up / blowup / limit_down(来自 universe)
    boards: int | None = None     # 连板数;源未给则 None(不臆造 0)

class TrajectoryStep(BaseModel):  # frozen:某决策日的一步
    model_config = ConfigDict(frozen=True)
    date: Date
    market: MarketState                         # ≤t 客观状态(带 max_board_height/echelon)
    decision: DecisionPackage                   # agent 当日选择(含 pattern)
    entries: dict[str, EntrySnap] = {}          # 去重后入选 code → 入场上下文(no-trade 为空)
    scored: bool = False                        # 是否已到 horizon 打分
    outcomes: dict[str, ScoredCandidate] = {}   # code → 已实现结果(打分前为空)

class Trajectory(BaseModel):      # frozen 容器
    model_config = ConfigDict(frozen=True)
    steps: list[TrajectoryStep] = []
    horizon: int = 1
    def scored_steps(self) -> list[TrajectoryStep]: ...   # scored=True 的步
    def n_decisions(self) -> int: ...                     # len(steps)
    def n_no_trade(self) -> int: ...                      # 无 candidates 的步数
    def __bool__(self) -> bool: return True               # 杀 falsy-empty 陷阱(项目约定)
```

- `entries` 的 code 取每步**去重后**的入选(与现有打分循环 `seen_codes` 去重一致)。因为 `parse_decision` 已保证入选 code ∈ universe,故每个入选 code 必能在当日 universe 查到 `StockSnapshot` → boards/status。
- `outcomes` 与 `scored` 在 `walk()` 内延迟回填:决策步 j 在游标推进到 j+horizon 时,用已录 `DayMembership` 打分并回写该步(`scored=True`)。
- **尾部不足 horizon 的步保留,`scored=False`**(把现有 eval 循环"静默丢弃尾部"显式化、可审计)。

### 4.2 `walk_forward.py` 重构

`walk(policy) -> Trajectory`:复刻现有 `run()` 的延迟打分循环(同一把防火墙逻辑,不再 fork),但把每步 `(date, market, decision, entries)` 记入 step,并在到达 horizon 时回写 `outcomes/scored`。`entries` 由当日 `universe.get(code)` 填充(同一个已构造的 universe,无额外取数)。

`run(policy) -> EvalReport`(签名不变)= `report_from_trajectory(self.walk(policy))`。

`report_from_trajectory(traj)`(`metrics.py`):把 `traj.scored_steps()` 的所有 `outcomes` 展平为 `list[ScoredCandidate]`,`n_decisions=traj.n_decisions()`、`n_no_trade=traj.n_no_trade()`、`horizon=traj.horizon`,调用现有 `build_report(...)`。**等价性测试**:对同一 source/policy,新 `run()` 的 `EvalReport` 与重构前**逐字段相等**。

### 4.3 `harness/skill.py`:`SkillStats` 加 `nukes`

```python
class SkillStats(BaseModel):
    n: int = 0
    wins: int = 0
    losses: int = 0
    nukes: int = 0            # 新增:被砸(nuked)次数;nuke_rate = nukes/n
    ewma_winrate: float | None = None
    pnl_ratio: float | None = None
    expectancy: float | None = None
    oracle_gap: float | None = None
    def record(self, win: bool, decay: float = 0.1) -> None: ...   # 不变
```

- `record()` 不动(仍 bool)。`nukes`/`expectancy` 由 `apply_credit` 维护(见 §4.4)。
- 序列化:默认 0,旧快照无 `nukes` 经 `model_validate` 取默认 → 前向兼容;新快照含之 → save→load→save 仍 byte-identical(Phase-0b-3 往返测试不破)。需补一条"旧快照(无 nukes)可载入"回归测试。

### 4.4 `refine/credit.py`:信用分配

```python
class SkillCredit(BaseModel):    # frozen:本次 trajectory 对某技能的信用汇总
    model_config = ConfigDict(frozen=True)
    skill_id: str
    n: int; wins: int; losses: int; nukes: int
    hit_rate: float              # wins/n
    nuke_rate: float             # nukes/n
    expectancy: float            # 本次贡献的 SCORE 均值

class CreditReport(BaseModel):   # frozen
    model_config = ConfigDict(frozen=True)
    per_skill: dict[str, SkillCredit] = {}
    unattributed: SkillCredit | None = None   # pattern 未匹配到技能的汇总(skill_id="__unattributed__")
    n_scored: int = 0
    def __bool__(self) -> bool: return True

def resolve_skill(pattern: str, harness: HarnessState) -> Skill | None:
    """pattern → Skill:先 skill_id 精确,再 name_cn 精确(name_cn 若多命中取第一个);都不中 → None。"""

def apply_credit(traj: Trajectory, harness: HarnessState, decay: float = 0.1) -> CreditReport:
    """对已打分轨迹做信用分配:就地更新 harness 内被引用技能的 SkillStats,返回汇总。"""
```

`apply_credit` 行为:
- 遍历 `traj.scored_steps()`,**按日期序**(忠实 ewma 衰减);对每步每个 `outcomes[code]`(已按 code 去重):
  1. `pattern = outcomes[code].pattern`;`skill = resolve_skill(pattern, harness)`。
  2. `win = (outcome == "continued")`;`skill.stats.record(win, decay)`(更新 n/wins/losses/ewma)。
  3. **expectancy 增量均值**(Welford,跨多次 apply 可累加):`m=stats.expectancy or 0.0; stats.expectancy = m + (SCORE[outcome]-m)/stats.n`。
  4. `if outcome == "nuked": stats.nukes += 1`。
  5. 未匹配技能(`skill is None`)→ 累入 `unattributed` 桶(**不静默丢弃证据**),不写任何技能 stats。
- 返回 `CreditReport`:`per_skill` 为本次受影响技能的增量汇总,`unattributed`,`n_scored`=本次打分的(code,step)总数。
- **`SkillCredit` 语义**:汇总的是**本次 trajectory 贡献的增量**(n/wins/losses/nukes/expectancy 仅计本次,不含历史),便于 1b-2/1b-3 读"这一轮谁在亏";技能的累计在 `skill.stats` 里。实现:apply 过程用 per-skill 局部累加器记本次增量,结束时一次性构造 `SkillCredit`(`hit_rate`/`nuke_rate`/`expectancy` 用该累加器的 n 作分母,故只对 n≥1 的技能/桶构造,无除零)。
- **幂等性**:`apply_credit` 对一条 trajectory **调用一次**(写在 docstring);重复调用会重复计入(stats 设计为累计)。1b-3 的在线/流式增量信用在其切片处理;1b-1 提供批处理原语 + 每步数据。

### 4.5 `refine/signatures.py`:确定性失败签名(board-rank × outcome)

```python
FailureKind = Literal[
    "chased_into_nuke",    # 追最高板被闷:boards == market.max_board_height 且 nuked
    "weed_over_dragon",    # 接非龙头被砸:boards 已知且 < max_board_height 且 nuked
    "generic_nuke",        # 被砸但板数未知(boards None)且 nuked
    "faded_miss",          # 空耗:faded
]

class FailureSignature(BaseModel):   # frozen
    model_config = ConfigDict(frozen=True)
    date: Date
    code: str
    pattern: str
    skill_id: str | None       # resolve_skill 命中则填,否则 None
    kind: FailureKind
    score: float               # SCORE[outcome]
    evidence: str              # 人读证据,如 "boards=5/max=5 → 追最高板被闷,次日跌停"

def extract_signatures(traj: Trajectory, harness: HarnessState) -> list[FailureSignature]:
    """对已打分轨迹抽取入场类失败签名(继续盈利 continued 不产签名)。"""
```

判定(每步每个已打分入选 code,仅 outcome ∈ {faded, nuked} 产签名):
- `continued` → 无签名(赢了)。
- `faded` → `faded_miss`。
- `nuked`:取 `b = entries[code].boards`,`mx = step.market.max_board_height`;
  - `b is not None and b == mx` → `chased_into_nuke`;
  - `b is not None and b < mx` → `weed_over_dragon`;
  - 否则(`b is None`,或异常 `b > mx`)→ `generic_nuke`。
- `skill_id = resolve_skill(pattern, harness)` 命中则填。
- 全部用 `entries`(入场快照)+ `outcomes`(oracle)+ `market.max_board_height`,**不触 source、不需 OHLCV、不需相位**。

**1b-1 明确不做(推迟)**的签名,并注明解锁条件:
- `relay_in_ebb`(退潮接力)、任何**相位依赖**签名 → 待 `G_cycle` 相位分类器(Phase-1)。
- K 线 detector(黄昏之星/三柱香/出货分时…)、**持有/退出**类(该走不走)→ 待 OHLCV oracle / 持仓模型。
- "比同板更高板的票续板了我却接了杂毛"(需对**全 universe**打分,而非仅决策集)→ 后续增强。

## 5. 关键边界决策:观测 vs 编辑(触及不变量 #2,已评审通过)

- **信用分配直接写 `SkillStats`,不经 meta-tool、不入 `EditLog`**。理由:stats 是**观测**(已实现结果的遥测),区别于**结构性编辑**(改打法)。EditLog 应是 Refiner 决策(1b-2)的账本,不被每候选的 stat tick 淹没。
- stats 仍被 `HarnessState.to_dict` 快照捕获 → rollback 覆盖之。
- 因此 1b-1 = **观测**(填 stats、抽签名);1b-2 = **决策**(读证据,经 meta-tool 编辑 H,入 EditLog)。

## 6. 防火墙论证(终审会查)

- `apply_credit`/`extract_signatures` 输入是**走完的** `Trajectory`,其 `outcomes` 是 t+horizon 的已实现 pool 成员——事后标签,永不回灌 ≤t 推理。
- `Trajectory` 内不持 source 句柄;`MarketState`/`EntrySnap`/`ScoredCandidate` 皆 frozen、≤t(market/entries 在决策日采;outcomes 在 horizon 日采,仅作打分)。
- 产出的 `SkillStats` 次日对 agent 可见,但聚合的是 ≤ t−horizon 的过去结果(决策时刻 t' 看到的 stats 只含 ≤ t'−horizon 已实现者)→ 无前视。在线交错(随结果实现增量更新)是 1b-3 的事。

## 7. 测试(全离线,FakeSource + 脚本 policy)

- `test_trajectory.py`:模型 frozen/`__bool__`/`scored_steps`/`n_no_trade` 计数。
- `test_walk_forward_trajectory.py`:① `walk()` 步数/`entries`/延迟 `outcomes` 回填正确;② **尾部步 `scored=False` 保留**;③ **等价性**:新 `run()` 的 `EvalReport` 与展平 `walk()` 一致(并与重构前同 source 的报告逐字段相等)。
- `test_credit.py`:构造已知结局的 trajectory + 种子技能 →
  - 断言 per-skill `n/wins/losses/nukes/ewma_winrate/expectancy`(数值对账);
  - `faded` 记非 win 但 expectancy 含 0、`nuked` 含 −1、`nukes++`;
  - `pattern` 未匹配 → 进 `unattributed`,技能 stats 不动;
  - `resolve_skill`:skill_id 命中、name_cn 命中、都不中三路;
  - 幂等性说明(调两次翻倍)。
- `test_signatures.py`:四类 kind 各一例(含 boards=None→generic、b==mx→chased、b<mx→weed、faded→miss),continued 不产签名;evidence 文案含 boards/max。
- `test_skill_stats.py`(扩展):`nukes` 默认 0;旧快照(无 nukes 字段)`model_validate` 可载入。
- 回归:既有 eval/harness 测试全绿;`HarnessState` 序列化往返仍 byte-identical。

## 8. 验收标准(Definition of Done)

1. 上述模块/字段/函数按签名实现;`walk()` 产出正确 `Trajectory`,`run()` 行为不变(等价性测试通过)。
2. `apply_credit` 正确填 `SkillStats`(含 `nukes`/`expectancy`),未匹配进 unattributed;`extract_signatures` 产四类入场签名。
3. 防火墙 §6 论证在代码中成立(无 source 句柄泄漏、无未来标签进决策路径)。
4. 新测试 + 全量回归绿;离线、不触网。
5. subagent-driven 两段评审(spec 合规 + 对抗质量)+ opus 终审通过。
6. 文档:更新 `PROJECT_STATE.md`(1b-1 完成 + 残留债务)与 memory。

## 9. 显式 out-of-scope(1b-2/1b-3)

LLM Refiner + 四遍 CRUD;按 regime 选择性提示注入 + 把 stats/win-memory 注入 agent 提示;`DeepSeekClient` retry/backoff;内环编排(act→收盘→refine→次日);HCH vs Hexpert vs Hmin 度量 + 能力地板熔断;在线/流式增量信用;OHLCV/相位驱动的签名。
