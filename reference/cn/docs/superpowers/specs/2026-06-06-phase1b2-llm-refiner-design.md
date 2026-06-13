# Phase-1b-2 设计:LLM Refiner(读证据 → 经 meta-tool 编辑 H)= 真正的自进化

> 日期:2026-06-06 · 分支 `phase-1b2-llm-refiner`(待建)· 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans` 出逐任务执行计划。
>
> 先读:`PROJECT_STATE.md`(状态)· `后续开发文档.md`(§2 不变量、§4 路线图与 1b-2 设计分叉、§5 债务)· `自进化游资系统-架构蓝图-v1.0.md`(权威设计)· `docs/superpowers/specs/2026-06-01-phase1b1-...md`(1b-1 观测层 spec)。

---

## 0. 一句话

1b-1 已让系统能"看见自己哪条技能在亏"(`CreditReport`/已填 `SkillStats`)、"踩了哪类入场坑"(`FailureSignature`)。**本 spec 做 1b-2:让 LLM Refiner 读这些证据 + 当前 H,经 9 个 meta-tool 把教训结构性地写回 H(进 `EditLog`),系统开始自进化。** 论文式 **4-pass CRUD**(Δp→ΔG→ΔK→ΔM),其中 ΔG 因 G 子 Agent 群未建作**占位 no-op**(保留骨架、不发 LLM 调用)。1b-3(内环编排 + HCH/Hexpert/Hmin 度量 + 能力地板熔断)在其之上。

## 1. 已锁定决策(brainstorming,用户确认)

1. **范围 = Refiner + 相邻三项全做**(用户确认 ①②③ 全选):
   - **② 信用注入 agent 提示**:把 `SkillStats`(胜率/nukes/expectancy)+ `win` 类记忆渲进 agent 系统提示——闭合 1b-1→agent 的缺口(否则信用只 Refiner 可见、agent 仍用亏的技能)。
   - **③ 鲁棒共享 JSON 提取器**:贪婪/配平括号扫描,容忍 prose/thinking 前缀;Refiner 用 + 重构 `agent/parse._extract_json`(升级其 TODO,守既有等价性)。
   - **① `DeepSeekClient` retry/backoff**:实盘多日 eval 前必需;纯离线 1b-2 用 MockLLM 不依赖它,但顺手清掉这条 P0 债务。
2. **编辑面 = 全 9 个 meta-tool + 上限/校验**(用户确认):暴露 `write/patch/retire/revive/promote_skill` + `process/update/demote_memory` + `rewrite_doctrine`;风险靠 per-pass/per-refine 编辑数上限 + 强 schema 校验压,不靠砍 op。immutable 红线底座已挡死(`DoctrineEntry.__setattr__` + `Doctrine.rewrite/remove`)。
3. **结构 = 论文式 4-pass CRUD**(用户确认,非单次调用):Δp→ΔG→ΔK→ΔM 顺序、reset-free,后 pass 看得到前 pass 的编辑(同一个 `HarnessState`)。
4. **ΔG = 占位 no-op(方案 A,用户确认)**:G 子 Agent 群未建 → 无 meta-tool 可调 → ΔG pass **不发 LLM 调用**,直接返回空并在 `RefineReport` 记一条 "G-pass reserved(G 子 Agent 未建)" 说明。实际现在是 **3 次 live LLM 调用**(p/K/M),骨架忠于论文、G 落地即插。
5. **Refiner 是组件,不绑"每日"**:`refine(traj, credit, signatures) -> RefineReport`,就地编辑传入的 `HarnessState`(reset-free,agent 立即可见)。**checkpoint-before / 能力地板回滚 / 每日触发编排 = 1b-3,本 spec 不做。**
6. **每条编辑带 `rationale` 且全进 `EditLog`**:给 `EditRecord`/`EditLog.append`/9 个 meta-tool 加可选 `rationale=""`(默认空,向后兼容),让 Refiner 的理由进审计账本。

## 2. 不变量(必须守,沿用 `后续开发文档.md` §2)

1. **未来函数防火墙**:Refiner 在回放走完后、对已实现结果(`Trajectory`/`CreditReport`/`FailureSignature`)做事后分析,产出对 H 的编辑。编辑次日对 agent 可见,但 agent 决策仍只用 ≤t 信息;Refiner 的证据全是 ≤ t−horizon 的过去结果,无前视。**Refiner 永不取 source、永不进 ≤t 决策推理路径。**
2. **H 只经 9 个 meta-tool 做结构性编辑且入 `EditLog`**:Refiner 不直接改 `self.h`,一律走 `MetaTools`。**观测 vs 编辑边界(1b-1 确立)不变**:`SkillStats` 由 `apply_credit` 直写(观测,不入 EditLog);Refiner 的结构性 Δ 入 EditLog。
3. **immutable-core 写保护**:`rewrite_doctrine` 改 immutable 红线 → `ImmutableDoctrineError` → Refiner 捕获 → 该 op 拒绝、不应用、不计入 applied。Refiner 永远改不动红线。
4. **LLM 输出一律不可信**:op 列表经白名单 + schema 校验 + caps + rationale 必填过滤;malformed/越权/幻觉 target/非法转移 → 拒绝(带原因),绝不崩、绝不半应用。
5. **frozen 快照**:`RefineReport`/`AppliedEdit`/`RejectedEdit`/`RefineOp` 全 frozen pydantic;`HarnessState` 仍可变(被编辑)。
6. **离线可测**:测试用 `MockLLMClient`(脚本化 op 列表 JSON)+ 真实种子 H,永不触网。真实 DeepSeek 仅 `scripts/smoke_*.py`。
7. **代码约定**:照抄现有风格——frozen pydantic 快照、容器 `__bool__=True`、缺失值诚实 `None`、新建 `Skill`/`Lesson` 经 `from_seed` 归一 regime。

## 3. 模块布局与依赖方向

层级自底向上:`...→eval→harness→llm/agent→refine`。`refine/refiner.py` 依赖 `eval`(Trajectory)+ `harness`(MetaTools/HarnessState/Skill/Lesson/errors)+ `llm`(LLMClient + 共享 JSON 提取器)。

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/llm/extract.py` | **新增** | `extract_json_object(raw) -> str | None`:贪婪配平括号扫描(③) |
| `youzi/llm/client.py` | 改 | `DeepSeekClient.complete` 加 retry/backoff(①);可注入 `sleep`/`max_retries`/`backoff` 便于测试 |
| `youzi/agent/parse.py` | 重构 | `_extract_json` 改为调用 `extract_json_object`(守既有等价性测试) |
| `youzi/agent/prompt.py` | 改 | `build_system_prompt`:active 技能行追加 `[战绩 …]`(`stats.n>0` 才渲染);补渲染 `win` 类记忆(②) |
| `youzi/harness/edit_log.py` | 加字段/参数 | `EditRecord.rationale: str = ""`;`EditLog.append(..., rationale="")` |
| `youzi/harness/metatools.py` | 改 | 9 个方法各加 `rationale: str = ""` 透传进 `log.append` |
| `youzi/refine/ops.py` | **新增** | `RefineOp`(op schema)· `PASS_TOOLS`(pass→允许 tool 白名单)· `parse_ops(raw) -> list[RefineOp]` |
| `youzi/refine/refiner_prompt.py` | **新增** | `build_refiner_system_prompt(h, pass_kind)` · `build_refiner_user_prompt(traj, credit, signatures)` |
| `youzi/refine/refiner.py` | **新增** | `RefinerConfig` · `AppliedEdit`/`RejectedEdit`/`RefineReport` · `Refiner` |
| `tests/test_llm_extract.py`、`test_refine_ops.py`、`test_refiner.py`、`test_refiner_prompt.py`、`test_agent_prompt_stats.py`、`test_deepseek_retry.py`、`test_edit_log_rationale.py` | **新增** | 全离线 |

## 4. 数据模型与接口(精确)

### 4.1 `llm/extract.py`:鲁棒 JSON 提取器(③)

```python
def extract_json_object(raw: str) -> str | None:
    """从含 prose/markdown 围栏/thinking 前缀的文本里取第一个**配平**的 JSON 对象子串。
    扫描:跳到第一个 '{',按括号深度配平(尊重字符串字面量与转义,'{'/'}' 在字符串内不计深度),
    深度归零处截断返回。找不到配平对象 → None。"""
```

- 替代 `agent/parse._extract_json` 的 "first-`{`-to-last-`}`"(thinking-blob 前缀会失败)。重构后 `parse_decision` 行为对既有用例**不变**(等价性测试守),且新增容忍前缀/多对象取第一个的能力。
- 返回 `None` 时调用方按各自兜底(`parse_decision`→空仓;Refiner→该 pass 0 编辑)。

### 4.2 `llm/client.py`:`DeepSeekClient` retry/backoff(①)

```python
class DeepSeekClient:
    def __init__(self, ..., max_retries: int = 3, backoff: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep) -> None: ...
    def complete(self, system, user) -> str:
        # 第 k 次失败(k<max_retries):sleep(backoff * 2**k) 后重试;耗尽 → 抛最后一次异常
```

- 仅 `DeepSeekClient`;`MockLLMClient`/`LLMClient` 协议不变。`sleep` 可注入(测试传 `lambda _: None`,`delay` 不真睡)。
- 重试范围:网络/限流/5xx(`openai` 抛的异常);耗尽仍失败则向上抛(由 1b-3 编排或 `LLMAgentPolicy` 决定空仓兜底,本 spec 不在此加 try/except)。

### 4.3 `agent/prompt.py`:信用 + win 记忆注入(②)

`build_system_prompt`:
- **技能行加战绩**:对每条 `by_status("active")` 技能,若 `s.stats.n > 0`,行尾追加 `[战绩 n={n} 胜率={ewma_winrate:.2f} nukes={nukes} exp={expectancy:+.2f}]`(`None` 字段省略对应项)。让 agent 看到"这技能最近在亏/被砸"。
- **补渲染 win 记忆**:现仅渲 `principle`/`loss`;增 `for l in h.memory.all(): if l.outcome == "win": out.append(f"- [成功] {tag}{l.lesson}")`(`tag` 同 loss 用 `named_analog`)。
- `build_user_prompt` 不变。**等价性**:`stats.n==0` 且无 win 记忆时,系统提示与改动前**逐字符相等**(回归测试守)。

### 4.4 `harness/edit_log.py` + `metatools.py`:`rationale` 进审计

```python
class EditRecord(BaseModel):
    ...
    rationale: str = ""          # 新增:Refiner 给出的编辑理由(默认空,向后兼容)

# EditLog.append(tool, target_kind, target_id, op, summary="", payload=None, rationale="")
# 9 个 MetaTools 方法签名各加 rationale: str = "" 末参,透传进 log.append
```

- 默认空 → 既有 0b-2/0b-3 测试与序列化往返不破(`model_validate` 旧记录无 `rationale` → 取默认;新记录往返 byte-identical 仍成立——需补一条"旧 EditLog dict 无 rationale 可载入"回归)。

### 4.5 `refine/ops.py`:编辑 op schema + 解析

```python
PassKind = Literal["p", "G", "K", "M"]

# pass → 允许的 meta-tool 白名单(ΔG 为空集:占位 no-op)
PASS_TOOLS: dict[PassKind, frozenset[str]] = {
    "p": frozenset({"rewrite_doctrine"}),
    "G": frozenset(),                                  # G 子 Agent 未建
    "K": frozenset({"write_skill", "patch_skill", "retire_skill",
                    "revive_skill", "promote_skill"}),
    "M": frozenset({"process_memory", "update_memory", "demote_memory"}),
}

class RefineOp(BaseModel):           # frozen:一条待应用编辑
    model_config = ConfigDict(frozen=True)
    tool: str                        # meta-tool 名(必填;缺 → parse 阶段跳过该条)
    args: dict = {}                  # 该 tool 的参数(见下表)
    rationale: str = ""              # 默认空;**apply 阶段强制非空**(空/缺 → rejected,reason="缺 rationale")

def parse_ops(raw: str) -> list[RefineOp]:
    """LLM 文本 → list[RefineOp]:extract_json_object → json.loads → 取 "ops":[...];
    非对象/无 ops/条目缺 tool 或 malformed → 跳过该条(不崩);整体失败 → 返回 []。
    rationale 缺失不在此跳过(默认 ""),留到 apply 阶段作为 rejected 上报——所有 rationale 问题统一可见。"""
```

**op → meta-tool 参数映射(应用阶段构造)**:

| tool | args | 构造/校验 |
|---|---|---|
| `write_skill` | 完整 skill dict | `Skill.from_seed(args)`(`extra="forbid"` 抓拼写错 + regime 归一);`skill_id` 已存在 → **拒绝**(reason="skill_id 已存在,改用 patch_skill",防 Refiner 覆盖既有技能 stats/定义) |
| `patch_skill` | `{skill_id, ...fields}` | target 存在校验;`fields` 为 `Skill` 合法字段子集 |
| `retire_skill` | `{skill_id, permanent?}` | target 存在 |
| `revive_skill` | `{skill_id}` | target 存在;非 dormant → `InvalidTransitionError`→拒绝 |
| `promote_skill` | `{skill_id}` | target 存在 |
| `process_memory` | 完整 lesson dict | `Lesson.from_seed(args)`(`extra="forbid"` + regime 归一) |
| `update_memory` | `{lesson_id, ...fields}` | target 存在;`fields` 为 `Lesson` 合法字段子集 |
| `demote_memory` | `{lesson_id, factor}` | `0<factor<=1`(越界 `Importance.demote` 抛 ValueError→拒绝) |
| `rewrite_doctrine` | `{section, new_guidance}` | immutable → `ImmutableDoctrineError`→拒绝;section 不存在 → 拒绝 |

### 4.6 `refine/refiner_prompt.py`:Refiner 提示

```python
def build_refiner_system_prompt(h: HarnessState, pass_kind: PassKind) -> str:
    """复盘官系统提示:说明本 pass 只改哪个容器(p/K/M)、可用 meta-tool 及参数 schema、
    immutable 红线改不动、每条 op 必带 rationale、编辑数上限;输出严格 JSON {"ops":[...]}。
    渲染当前 H 的相关切片(p-pass 渲 mutable doctrine;K-pass 渲技能+stats;M-pass 渲记忆)。"""

def build_refiner_user_prompt(traj: Trajectory, credit: CreditReport,
                              signatures: list[FailureSignature], window: int) -> str:
    """渲染证据:最近 window 步决策摘要 + CreditReport(谁在亏:hit_rate/nuke_rate/expectancy)
    + FailureSignature 列表(kind/evidence/pattern/skill_id)。"""
```

- p/G/K/M 各有针对性系统提示(ΔG 不调用 → 无需提示)。**reset-free**:K-pass 提示渲染的是 p-pass 编辑后的 H 切片(同一对象,顺序执行天然可见)。
- 提示注入暂**全量**(按 regime 选择性注入被卡在缺 `G_cycle` 分类器 → 推迟,见债务)。

### 4.7 `refine/refiner.py`:Refiner 主体

```python
class RefinerConfig(BaseModel):
    max_edits_per_pass: int = 5
    max_edits_per_refine: int = 12
    window: int = 10                 # user prompt 渲染最近几步
    decay: float = 0.1               # 预留(信用已在 apply_credit 阶段算)

class AppliedEdit(BaseModel):        # frozen
    model_config = ConfigDict(frozen=True)
    pass_kind: PassKind; tool: str; target_id: str; seq: int; rationale: str

class RejectedEdit(BaseModel):       # frozen
    model_config = ConfigDict(frozen=True)
    pass_kind: PassKind; tool: str; target_id: str | None; reason: str

class RefineReport(BaseModel):       # frozen
    model_config = ConfigDict(frozen=True)
    applied: list[AppliedEdit] = []
    rejected: list[RejectedEdit] = []
    notes: list[str] = []            # 如 "G-pass reserved(G 子 Agent 未建)"
    def __bool__(self) -> bool: return True

class Refiner:
    def __init__(self, harness: HarnessState, llm: LLMClient,
                 meta: MetaTools, config: RefinerConfig = RefinerConfig()) -> None: ...
    def refine(self, traj: Trajectory, credit: CreditReport,
               signatures: list[FailureSignature]) -> RefineReport: ...
```

`refine` 流程(reset-free,4-pass 顺序 p→G→K→M):
1. 对每个 `pass_kind in ("p","G","K","M")`:
   - 若 `PASS_TOOLS[pass_kind]` 为空(G)→ 不发 LLM 调用,`notes` 记 "G-pass reserved",跳过。
   - 否则:`system = build_refiner_system_prompt(h, pass_kind)`;`user = build_refiner_user_prompt(traj, credit, signatures, window)`;`raw = llm.complete(system, user)`;`ops = parse_ops(raw)`。
   - 逐条应用 `_apply_op(op, pass_kind)`(见下),累计 applied/rejected,**尊重 per-pass 与 per-refine 上限**(超上限的 op → rejected,reason="超出编辑上限")。
2. 返回 `RefineReport`。

`_apply_op(op, pass_kind)`:
- `op.tool not in PASS_TOOLS[pass_kind]` → 拒绝(reason="tool 不属于本 pass" / "未知 tool")。
- `not op.rationale.strip()` → 拒绝(reason="缺 rationale")。
- 按 §4.5 表构造/校验参数 → 调对应 `MetaTools` 方法(透传 `rationale=op.rationale`)。
- 捕获 `ImmutableDoctrineError`/`InvalidTransitionError`/`ValidationError`/`ValueError`/target 不存在 → 拒绝(reason=异常信息);**绝不半应用、绝不崩**。
- 成功 → `AppliedEdit`(从返回的 `EditRecord` 取 `seq`)。

## 5. 关键边界(沿用 §2,登记于此)

- **观测 vs 编辑**:`apply_credit`/`extract_signatures`(1b-1,观测)在 `refine()` **之前**由调用方执行,产出 `credit`/`signatures` 传入;Refiner 只做"读证据→结构性编辑"。Refiner 不重算信用、不改 stats。
- **Refiner 不 checkpoint/不回滚**:就地编辑传入的 `HarnessState`。何时 checkpoint(编辑前/每周期)、能力地板熔断 = 1b-3。
- **ΔG 占位**:保留 4-pass 骨架与 `PASS_TOOLS["G"]=∅`;G 子 Agent 落地后填白名单 + 提示即转 live,无需改 `refine()` 主循环。

## 6. 防火墙论证(终审会查)

- Refiner 输入 = 走完的 `Trajectory` + 其派生 `CreditReport`/`FailureSignature`,皆 ≤ t−horizon 的已实现事后标签。Refiner **不持 source 句柄、不取数**。
- Refiner 产出 = 对 H 的结构性编辑,次日对 agent 可见;但 agent 决策仍只用 ≤t 信息(`build_user_prompt` 只渲当日盘面+候选),编辑本身不含未来标签。
- immutable 红线、幻觉 op、越权 tool、非法转移均被拒绝管线挡住,无侧信道。

## 7. 测试(全离线,MockLLM 脚本 + 真实种子 H)

- `test_llm_extract.py`:配平扫描——纯 JSON、prose 前缀、thinking-blob 前缀、markdown 围栏、嵌套对象、字符串内含 `{`/`}`/转义、多对象取第一个、无对象→None。
- `test_agent_prompt_stats.py`:`stats.n>0` 渲染战绩串;`n==0` 与改前逐字符相等(等价性);win 记忆渲染为 `[成功]`。
- `test_deepseek_retry.py`:注入"前 k 次抛异常后成功"的假 client + `sleep=lambda _: None` → 验重试次数/退避序列/耗尽抛出(**不触网**,mock openai 层)。
- `test_edit_log_rationale.py`:`rationale` 透传进 `EditRecord`;旧 dict(无 rationale)`from_dict` 可载入;新 EditLog 往返 byte-identical。
- `test_refine_ops.py`:`parse_ops` 取 `ops`、跳 malformed 条、整体失败→`[]`;`PASS_TOOLS` 白名单正确。
- `test_refiner.py`(核心):真实种子 H + MockLLM 脚本化各 pass 的 op 列表 →
  - **happy path**:`write_skill`(新 failure_detector)/`patch_skill`/`process_memory`/`rewrite_doctrine`(mutable) 应用成功,进 `EditLog`(带 rationale),`RefineReport.applied` 正确;
  - **immutable 拒绝**:`rewrite_doctrine` 改红线 → rejected(reason 含 immutable),H 未变,EditLog 未记;
  - **非法转移拒绝**:`revive_skill` 一个 active 技能 → rejected;
  - **越权/未知 tool**:K-pass 出 `rewrite_doctrine` → rejected;
  - **缺 rationale**:rejected;
  - **caps**:超 per-pass/per-refine 上限的 op → rejected(reason 含上限);
  - **幻觉 target**:`patch_skill` 不存在 id → rejected,不崩;
  - **malformed args**:`write_skill` 缺必填/拼错字段 → `ValidationError` 捕获→rejected;
  - **ΔG**:`RefineReport.notes` 含 "G-pass reserved";G-pass 不调用 LLM(MockLLM `calls` 计数 = 3 次)。
- `test_refiner_prompt.py`:各 pass 系统提示含对应容器切片 + meta-tool schema + immutable 警告 + rationale 要求;user 提示含证据(credit/signatures/最近 window 步)。
- 回归:既有 163 测试全绿;`HarnessState`/`EditLog` 序列化往返仍 byte-identical;`parse_decision` 等价性守。

## 8. 验收标准(Definition of Done)

1. 上述模块/字段/函数按签名实现;`Refiner.refine` 跑通 4-pass(ΔG no-op),真实种子 H + MockLLM 端到端产 `RefineReport` 且编辑进 `EditLog`。
2. 拒绝管线对 immutable/非法转移/越权/缺 rationale/超上限/幻觉 target/malformed 全部正确拒绝,**绝不半应用、绝不崩**。
3. 相邻三项:`extract_json_object` 鲁棒且 `parse_decision` 等价;agent 提示注入 stats+win 记忆且 `n==0` 等价;`DeepSeekClient` retry 可测(不触网)。
4. 防火墙 §6 论证在代码中成立(Refiner 无 source 句柄、无未来标签进决策路径)。
5. 新测试 + 全量回归绿;离线、不触网。
6. subagent-driven 两段评审(spec 合规 + 对抗质量)+ opus 终审通过。
7. 文档:更新 `PROJECT_STATE.md`(1b-2 完成 + 残留债务)、`后续开发文档.md`、memory。

## 9. 显式 out-of-scope(1b-3 及以后)

- 内环编排(`act → 收盘 → refine(每日) → 次日`);**何时触发 refine**。
- **checkpoint-before / 能力地板熔断 / 回滚策略**(底座 `HarnessManager` 已有,编排是 1b-3)。
- HCH(自精炼)vs Hexpert(种子静态)vs Hmin(裸 baseline)度量;bootstrap-updating 不退化的防护。
- **在线/流式增量信用**(1b-1/1b-2 只批处理 `apply_credit`)。
- **按 regime 选择性提示注入**(卡在缺 `G_cycle` 相位分类器)。
- **ΔG live pass**(待 G 子 Agent 群建成)。
- **涌现技能审计闸**(防 reward-hack 的作弊技能;蓝图 §6.3/§8)——登记为债务。
- OHLCV/相位驱动的失败签名(1b-1 推迟项)。
- `LLMAgentPolicy.decide`/Refiner 调用方的 API 异常→空仓兜底(1b-3 编排层)。
