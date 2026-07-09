# Kairos → Evolving-Alpha-US：可迁移设计挖掘

> **命名注（2026-07-09）：** 本文中的 "Kairos" 指同级 CN 法律智能体仓库
> `~/Desktop/self-evolve/kairos`——不是 Sonia-Kairos-US-Stock（本仓库，2026-07-09 由
> Evolving-Alpha-US 更名）中的 Kairos 工作者主体。以下正文为冻结记录。

**日期：** 2026-07-01 · **方法：** 47-agent 工作流：8 个领域深读 agent 阅读
`~/Desktop/self-evolve/kairos` → 将每个模式映射到本仓库代码 + ROADMAP →
对每个 adopt/adapt 候选做对抗式验证 → 覆盖率批评 + 一轮跟进。

**规模：** 挖掘 100 个模式 · **40 个 already-have**（alpha 已有等价实现）· 24 个 adopt/adapt
候选完成对抗式验证（**8 个确认、16 个经修正后削弱、0 个被反驳**）·
批评轮产出 21 个未验证补充 · 17 个不适用（多租户/法律/web 产品）。

---

## 0. 元发现：趋同演化验证了两套架构

100 个 kairos 模式中有 40 个已经以不同名称存在于 alpha 中，属于独立趋同：
kairos `RunExecutor.execute` 单一入口 ≈ alpha 的 `try_apply_op` 写入腰部 + 装饰器栈；
kairos D12 状态变更前审计的晋升门 ≈ `try_apply_op` floors + 追加式 EditLog；
kairos L1-L6 优化器阶梯 ≈ alpha R1-R6 修改阶梯；kairos 候选资格与授权拆分
≈ `StagedEdit.valid` vs `status=='approved'`；kairos MatterScopedSession（把租户隔离编译进 SDK）
≈ `GuardedSource(AsOfGuard)`（同一招应用到*时间*）；kairos dormant-flag shipping
≈ alpha 默认关闭/字节一致的家风。应把这视为对 alpha 核心宝物的强交叉验证，而不是“没什么可学”。

---

## 1. 现在采用：低成本、命中已命名 backlog

### 1.1 ROADMAP.md 中的 Activation Ledger  *(CONFIRMED，价值 5，成本低)*

Kairos 的 `docs/ROADMAP.md` 以一张表开头：Capability | Built | **Live in prod** |
Remaining activation step，把“完成”重新定义为 *flag ON 且承载真实流量*，并带有 WIP 规则
（已完成但仍处于暗态时，不开启新 track）以及 ROADMAP 作为唯一状态权威。
**Alpha 缺口（已验证，且是真实 live drift）：** ROADMAP.md 仍写着“555 tests / P-A `[ ]`”，
而 PROJECT_STATE 记录 P-A + live-face + P-B/P-C 已合并并推送，在 882 tests（@`23e0dbc`）；
P-B/P-C 耦合是 dormant-by-design，其 4 项激活清单只作为一句话存在于 PROJECT_STATE 头部段落中。
**做法：** 在 ROADMAP.md 顶部加入三列表。今天可清理的行：**P-B/P-C operational-K coupling**
（已构建、暗态、4 个已知激活步骤）以及 **§6 live daily production loop**
（producer 已存在，loop 未构建）。*已折入修正：* GCycle recalibration 是普通 backlog
（未构建调参），不是 ledger 行。“Prod”⇒“接入 live driver（save_decisions / refine_live /
workbench）并承载真实运行”。

### 1.2 Flag-flip rollout runbooks（`docs/superpowers/runbooks/`） *(价值 5，成本低)*

Kairos 为每个暗态发布的能力提供专用 runbook，这是唯一被认可的开启路径：§0 开启后会发生什么 +
被命名的验证 E2E 测试；§1 完整 flag 集合，按 Flag | Role | Without-it 表呈现，并明确警告
**“headline flags 并不足够”** + 两级 kill switch；§2 pre-flip checklist；§3 staged rollout。
Fail-closed 成本边界（超预算 = 终止 defer，绝不静默降级）。
**Alpha 缺口：** `docs/superpowers/` 只有 specs/ + plans/；episode read-side flip 是从一个 plan +
PROJECT_STATE 的散落叙述中协调出来的；P-B/P-C flip 明显更难。
**做法：** 创建 `runbooks/`；第一份 runbook = **P-B/P-C activation**
（接线 `experience_writer` / `task_forge` / `confirmed_ids` / pinned-asof + conflict_queue routing；
pre-flip checklist 重新确认 verdict read/write symmetry + default-off-when-dark；kill switch =
断开 `experience_writer` / `for_asof(kind=)` fence；验证测试 = verdict-neutrality regression）。
*修正：* runbook 是 implementation plan 的**运维伴侣**（alpha 的 activation 是代码接线，
参照 episode-readside 先例），不是替代品。

### 1.3 解析一次并固定的 SSRF egress guard  *(adopt，价值 4，成本低)*

Kairos `ingestion.py::is_safe_public_url` + A2A egress guard：仅 https、无 userinfo，
host **只解析一次**，要求每个解析出的 IP 都是 `is_global`（阻断 loopback/private/
link-local/reserved/multicast/CGNAT 以及 metadata `169.254.169.254`），然后连接到
*固定后的* IP。
**Alpha 缺口：** ROADMAP §6 逐字命名这是任何非 localhost serving 前的 **BLOCKING precondition**；
`alpha/meta/ingest.py` 只有 scheme allowlist。
**做法：** 在 `alpha/meta/` 中添加仅依赖 stdlib（`ipaddress` + `socket`）的 validator
（例如 `netguard.py`），由 `fetch_url` 调用，之后可被任何 arena network tool 复用。
*验证修正：* 要符合 ROADMAP 中的 DNS-rebinding-safe 表述，需要 resolve once → validate every
returned IP → **connect by pinned IP**（保留 Host header），并在 `_urllib_fetcher` 中禁用/重新验证
redirect；裸 validator 本身无法关闭 redirect bypass。保留 kairos 的 byte cap。

### 1.4 新增 trade-proposing skills 必须有 negative guards  *(CONFIRMED，价值 3，成本低)*

Kairos `TriggerContract{fire_when, do_not_fire_when}`：声明某个风险类别的 skill 必须声明至少一个
negative guard（`model_validator` 基于 `model_fields_set`，避免 legacy seeds 被 brick）。
**Alpha 缺口（已验证）：** `Skill.taboo` 默认空，且没有任何 enforcement；`GateSpec` 可机器读取但
**未被消费**（其 docstring 中的 `eval/rule_policy` consumer 不存在）。
**做法：** 在 `try_apply_op` 的 `write_skill` 分支做 gate-side 检查：新的 `type='pattern'`、
`domain='trading'` skill 必须带有 ≥1 个 taboo entry，否则以清晰原因拒绝（形状与 missing-rationale
guard 一致）。作为 ROADMAP §6 post-apply red-line lint 的**第 1 步**发布。放在 gate
（覆盖 refiner/Sonia/converse provenance），不要放进 pydantic validator。

### 1.5 persistence waists 上 redact-before-emit  *(CONFIRMED，价值 3，成本低)*

Kairos 有一个递归 `redact()`（敏感 key + value pattern → `<REDACTED>`）应用于每个 egress，
并保持 *redact before hash* 的顺序不变式。
**Alpha 缺口（已验证泄漏向量）：** `LocalEnv.run` 继承父进程 env；T2 shell 执行 `env`
会把 `DEEPSEEK_API_KEY`/APCA keys 放入 tool results，并被**原样**持久化到
`ProjectTurn.tool_calls`（converse sqlite store）和 SessionStore JSON。*（Task episodes 没问题，
`experience.py` 只持久化压缩摘要。）*
**做法：** 一个 dependency-free `redact()`，应用于 converse sqlite store 和
`meta/store.SessionStore`（experience_writer 作为廉价第三处）。仅限定 key/credential 范围，
绝不要清洗 rollback replay 所需的 market/PIT data 或 edit payload。

### 1.6 Assembled-prompt audit record：“drops are recorded, never silent”  *(adopt，价值 4，成本低；未验证补充)*

Kairos 的 prompt assembler 接收可选 `collect` callback，记录每一层：ref、order、bytes、
`included|dropped` + reason。
**Alpha 缺口：** `build_system_prompt` 会静默丢弃 `depends_on` 失败的 skills、
低于 `MIN_MEMORY_WEIGHT`/budget 的 lessons、超预算 episodes；没有任何持久化记录说明一个
decision 的 prompt 实际包含了什么。
**做法：** 在 `alpha/agent/prompt.py` 加入可选 collect hook（默认 None ⇒ 字节一致），
由 producers 与 DecisionPackage 并列持久化。直接服务于诊断 **ROADMAP §1 GCycle recalibration**
（证明 suppressed agent 实际被展示了什么）。配套廉价收益：一个 `scripts/render_prompt.py`
离线 prompt-layout viewer。

---

## 2. 变形后采用：中等成本、与 backlog 对齐

### 2.1 TCB lockfile：spec 自己声明的 NOW deliverable  *(CONFIRMED，价值 4)*

Kairos：`scripts/gen_skills_lock.py` + `kairos-skills.lock` 固定 governed capability dirs 的内容哈希；
`--check` 枚举 typed drift 并失败；接入 CI/pre-commit。
**Alpha：** 全仓没有任何 hashing（grep 已验证），但 modification-ladder spec §3
*声明 TCB manifest 是 NOW deliverable*（spec 中已有 13 行表格，直接提取，不要重新推导；
注意它刻意列出 floor_breaker/conflict/snapshot，而不是 `guard/`）。
**做法：** 基于 spec §3 文件集合实现 `scripts/gen_tcb_lock.py` + `tcb.lock`，并加一个
`--check` pytest。可选跟进：在每个 EditRecord 中打入 post-state brain content hash
（增量可选字段，eval 永不读取）。这是 deferred R3+ `try_promote_body` byte-hash pin 的种子。

### 2.2 guard 边界上的三态数据可用性  *(CONFIRMED，价值 4)*

Kairos connector adapters 让 `exists()` 变成三态：found / not-found /
**backend-unavailable**（抛出 `LookupUnavailable`），因此 outage 绝不会被误标为“已验证不存在”。
**Alpha 漏洞（逐行验证）：** 缺失 `corp_actions.parquet` → `pit_store` 返回 None → empty frame →
`has_dilution`/reverse-split flags 计算为 **False**，“没有数据”和“已检查且没有公告”无法区分；
dilution veto 静默盲跑。
**做法：** 在 corp-actions 路径上提供可区分的 unavailable 状态（typed wrapper 或
`has_corp_actions()` probe），由 `screen_decision` 暴露到 `DecisionPackage.key_risks`
（“dilution/SSR guard ran blind”）——符合 co-pilot 取向：*警告人类*，不是新增 veto。
默认关闭，关闭时字节一致，并**对称**穿入 verdict 两臂。*（这吸收了单独的“per-gate fail posture”
候选：真正静默的边界只有 snapshot-store corp-actions read 以及 `ssr_active`/`halt_then_dump`
把缺失行映射成 False；live Alpaca 路径已经 loud fail。）*

### 2.3 task evidence 的 gate-side 重新推导：P-C activation 前加固  *(价值 4)*

Kairos 双重 gate promotion：pure gate 对自动 driver 硬编码 `approved=False`，
而 `promote` 会基于**调用方无法伪造的持久化 eval records**重新检查 floors。
**Alpha 不对称（已验证）：** trade floors 读取不可伪造的 harness-held `sk.stats`
（`_PATCH_FORBIDDEN`），但 P-C task 分支信任**调用方提供的** `task_stats`
（`apply.py:129` “the caller MUST supply precomputed task evidence”）以及 `confirmed_ids`。
**做法（P-C live 前）：** 将一个**只读、PIT-pinned** episode-store handle
（`for_asof(asof, kind="task")`，lazy import 以尊重 refine↔memory cycle）传入
`try_apply_op` task 分支，并在 gate 内部重新计算 `summarize_task`；从 durable records
（EditLog provenance / persisted verifier verdicts）推导 `confirmed_ids`，而不是从 producer
输入读取。镜像 verdict 的 read-only `recall_store` 拆分，确保 gate 永远不会变成 self-write channel。
把它加入 P-B/P-C runbook checklist（§1.2）。

### 2.4 写入腰部的 safety-only-tightens 偏序  *(价值 4，两步)*

Kairos `safety_only_tightens(baseline, candidate)`：一个纯非 LLM gate，只允许 self-evolved
changes 让安全姿态单调变严格，并从 pydantic model **枚举 safety fields**，确保新字段自动覆盖。
**Alpha 缺口：** 只有 red-line *文本*不可变；没有东西阻止 `patch_skill` 缩小 `Skill.taboo`
或 retire 支持 guard 的 lesson。但 alpha 目前还没有可枚举的 typed safety surface。
**做法：** (1) 增加一个小的 safety-posture surface（例如 `safety_critical` tag /
Skill/Lesson 上的 designated-field registry）；(2) 在 **`try_apply_op` 内部**实现 monotonic check，
仅限 safety-tagged fields（Refiner 本来就应该能放松普通交易知识，过度扩大范围会僵化 harness）；
将 violation 路由到现有 `conflict_queue` → USER adjudication，而不是 hard-reject。
服务 ROADMAP §6 red-line lint。

### 2.5 对抗性 trap-day battery  *(CONFIRMED，价值 3)*

Kairos 保留 candidate-only adversarial eval rows，其中 SAFE 行为得分 1.0，并绑定一个独立的
`ADVERSARIAL_FLOOR=1.0`，任一失败都会阻塞，无视 aggregate。
**Alpha：** anti-Goodhart 组件已存在（Hmin_chase arm、confirmed-positive、episode-taboo），
但还没有固定的 trap battery survives-recalibration test。
**做法：** 仿照 PIT firewall 四件套，在 `tests/` 中加入 battery：用 synthetic FakeSource
构造 blowoff-top/backside days，任何 new long = fail，并跑完整的
`SizingPolicy(GuardedPolicy(...))` 栈。**这是让 ROADMAP §1 GCycle threshold loosening
可以安全推进的护栏。** 如果加载到 0 个 trap days 必须失败（禁止 vacuous pass）。
Trap days 不进入 live eval/verdict scoring，只作为 regression/promotion preconditions，绝不作为 training signal。

### 2.6 captured PIT windows 的 CHECKSUMS manifest  *(价值 3)*

Kairos 在读取 golden eval corpus **之前**验证 sha256 manifest，fail-closed。
**Alpha：** `snap/` parquet windows 这一“评分试卷”没有 integrity pin。
**做法：** `capture_window.py` 写 CHECKSUMS manifest；**把 manifest 提交到 git**
（parquet 仍保持 gitignored），这样篡改需要一个可审查的 git change；`run_verdict.py`
fail-closed 验证，ad-hoc exploration 只警告。丢弃 kairos 的 K_MAX 一半（alpha 已经有成本边界）；
不要给增长中的 `brain.db` 做 manifest。

### 2.7 App entry points 上的 frozen Settings model  *(价值 4，来自两个候选)*

Kairos policy models：在已验证 YAML 边界使用 `extra='forbid'` + `frozen` + Field bounds；
flags 在 boot 时**解析一次**成一个 frozenset，并传给每个耦合边界，避免组件在运行中意见不一致。
**Alpha：** 已命名的 config-centralization backlog（约 32 处 inline `ALPHA_*`/`APCA_*` 读取；
`./state/brain` 在 4 个文件中重复；alpha_web 在 route handler 内按请求读取 env）。
**做法：** 在每个 app/script entry point（alpha_web/sonia/workbench/producers）构造 frozen、
bounds-validated Settings object，并作为 constructor args 传下去——采用 kairos 的 `from_yaml`
姿态（允许 coercion，在适用处拒绝 unknown-key），**不是** `strict=True`。不要让它进入
`alpha/harness`，也不要放到 4 条 lazy-import cycle 边上；offline defaults 必须保持字节一致。
在每个 flag 旁边记录 co-flip couplings（P-B/P-C flag set）。*（为拼错的 env vars 做
`ALPHA_*` prefix audit 是新机制，不是 kairos 借鉴，可选。）*

### 2.8 Purged & embargoed CV：原生实现，仅借 kairos 的报告风格  *(价值 3)*

kairos 的 “holdout retest” 文件是一个约 50 行 stub（claimed-vs-observed tolerance check）；
其 marketplace framing 只是 docstring prose。Alpha 的 promotion evidence 已经是 ground-truth
（oracle-scored realized returns）。
**做法：** 在 `walk_forward.py` + `compare.py` 中原生实现 ROADMAP §4：在 `multi_window`
window 边缘 embargo horizon-h overlap；可选保留从未在 refiner prompt/config 迭代期间使用的
held-out windows（真正残余的 Goodhart surface 是*人类* meta-iteration）。只借 kairos 的
per-metric tolerance-with-reasons reporting shape 给 `StatVerdict`。两臂必须看到相同 holdout windows
（verdict symmetry）。

### 2.9 Hash-chained EditLog：缩小范围  *(价值 2-3，原为 4)*

Kairos audit rows 带 `prev_chain_hash`/`chain_hash`（对 canonical JSON 做 sha256）+
一个 `verify_chain()` 重新推导。
**Verify 修正：** 没有**外部锚点**时，chain 只能做 corruption-detection，不能在已接受的 T2-shell
operator-trust 姿态下提供 tamper-evidence（能编辑 `brain.json` 的 shell 也能重新推导 chain）。
采用方式：chain + `verify_chain()` 在 persist time（`stamp_last` 之后）最终确定，legacy snapshots =
unchained prefix，**再加**一个外部 chain-head anchor（每个 session 把 head hash 追加到一个 git-committed
file，或在 `/evolution` 上展示）。这是 deferred BodyLog 的基础。如果 §1.5 与它都落地，
强制 redact-before-hash。

---

## 3. 给后续 brainstorm→spec 轮次的设计输入（暂不构建）

| Kairos 模式 | 输入到哪个 alpha 项 | 要保留的关键细节 |
|---|---|---|
| **Content-addressed frozen `WorkflowSpec` + deterministic compile**（CONFIRMED） | `workflow` brain-component model（ROADMAP §6 brain-drawer） | 对 canonical JSON 计算 `spec_hash`；compile-time cycle rejection（Kahn + lexicographic）；编辑只能通过经过 `try_apply_op` 的新 MetaTools verbs；新增 `edit_log` target_kind |
| **Governed connector manifest**（side_effect_class / risk_class → central authorize） | `connector` brain-component model | 默认取**最严格**类别（kairos 自身 model 默认 `pure_read`，应复制它的 frontmatter default）；manifest-derived tier 相比 code-assigned tier 只能**收窄** |
| **Core-skill schema split**（把 harness roles 作为 shape-discriminated data） | `workflow`/`subagent` models + “Sonia edits the three new components” + “general meta-agent core” | 按 role 使用 `extra='forbid'` discriminated schemas（refiner config 不能获得 coordinator powers）；`PASS_TOOLS`/gate params 保持为 CODE（TCB）；role prompt-body edits 是 **R5 surfaces** → 仅 teaching-path + human confirm |
| **Epoch-based fork/rollback sessions**（CONFIRMED） | “Branchable named brains” + “keep-last-K pruning” | fork-at-snapshot-version 并记录 `parent_id` lineage；rollback = epoch bump，绝不 delete；**只 prune leaf lineages**；任何分支上的 edits 仍经过写入腰部 |
| **Sub-run scope narrowing + depth ceiling** | ROADMAP §5 “Master-dispatch G sub-agents” | child tool map ⊆ parent；per-tool tier 只能朝**更严格 oversight**移动（在 alpha 中是 T0→T4 方向，verify pass 修正了 inherited-direction bug）；同一个 ActivityPolicy choke point；现在记录为 arena-spec constraint |
| **Off-hot-path improvement detectors** | ROADMAP §6 “Self-learning channel”（已命名的 headline next step） | 基于 `kind='task'` episodes 的 deterministic forge-style detectors（PIT `for_asof` reads）→ 通过 `try_apply_op` 进入 Sonia review queue；human-rejection mining 是单独 follow-on，被消费为**负约束**，绝不重新作为 proposals 浮现 |
| **`harness_digest` decision attribution** | observability polish；之后的 body-axis joint rollback | 在 `snapshot.py` 中对 HarnessState 做 canonical-JSON sha256（stdlib，harness 保持 dependency-free）；DecisionPackage/producers 上可选 `h_digest`；eval 永不读取 |
| **Teaching funnel state machine** | 进行中的 teach-crystallize build | 验证 `ProposedEdit`/session status transitions（表驱动，不允许自由赋值）；crystallize 强制 `{ops}|{no_edit,reason}` 输出已经修复了 kairos 的 honest-empty concern |
| **Context management trio**（保留 provenance 的 pruning / content-addressed offload + recall tool / 4-phase compaction with protected bookends） | Sonia/workbench long-session usability；self-learning channel 的前置条件 | prune 丢 bytes 不丢 handles（`[...elided - recall hash=X]`）；offload store 根植在 Workspace 内部；recall tool 以 T0 通过 choke point 注册；保护 turn-0 task + last-N；offline suite 用 FakeSummarizer |
| **Egress posture ladder + sandbox resource manifest** | activity-space spec 中开放的 “network allowlist shape” 问题；R6 kernel sandbox | M1 = monitor-everything（在 choke point 记录 typed `sandbox_egress` audit records），M2 = deny-by-default allowlist；resource ceilings 在 image manifest 中声明，policy 只能 tighten |
| **Operator CLI over agent-written memory** | observability polish | 在 `EpisodeStore.for_asof` 上提供只读 `scripts/inspect_episodes.py`（或 `/episodes` page），展示 veto 使用的同一组 `summarize`/`is_episode_taboo` 数字；write path 仍只允许 Sonia |
| **Dilution lifecycle as typed update events** | ROADMAP §3 EDGAR feed + withdrawal/expiry lifecycle | `updates_since` 形态的 checker；保留今天“永久 veto”作为显式 fail-closed no-connector default；每个 lifecycle event 以自己的 announce/process date（PIT）为 key |
| **Offered-vs-cited evidence lineage** | self-learning channel + credit precision | 持久化 `Selection` ids + recalled episode ids + asof 作为可选 DecisionStore sidecar；支持 offered-vs-cited attribution |
| **Day-0 launch ledger rows bound to tests** | P-B/P-C activation checklist | 每个 checklist row → 命名 proving test → blocker type（code / design / human）；合入 §1.2 runbook，而不是单独 artifact |

验证后降级：kairos “protected-modules” 模式中唯一净新增构建是 **red-line lint**
（alpha 的 spec §3 已包含完整 TCB 表）；lint 的 semantic contradiction check 需要自己的设计
（kairos 的 module-reference scan 无法映射）。

---

## 4. 顺手发现的 bug / drift（已验证，独立于任何采用项）

1. **ROADMAP.md 状态漂移**——头部写 555 tests，§1 仍列 P-A unchecked；实际为
   882 tests，且 P-A/P-B/P-C 已推送（@`23e0dbc`）。无论是否做 §1.1 都应修。
2. **缺失 artifact 时 corp-actions guard 盲跑**——没有 `corp_actions.parquet` ⇒ flags
   计算为 False（§2.2）。这在 snapshot-store 路径中真实存在（pre-fix 或 hand-built captures）。
3. **Secret 泄漏到持久化 transcripts**——`LocalEnv` 继承父进程 env；`env` 输出原样落入
   `ProjectTurn.tool_calls` + SessionStore JSON（§1.5）。
4. **`GateSpec` 未被消费**——其 docstring 指向一个不存在的 consumer（`eval/rule_policy`）。
   要么接线它，要么修 docstring（§1.4 是自然接线时机）。
5. **GCycle thresholds 对 Refiner 不可达**——`classifier.py` 说“the LLM Refiner calibrates these
   thresholds”，但它们是 hardcoded literals，没有任何 edit path 能触达。如果未来确实需要
   Refiner-calibration path（而不是人工 US prior），thresholds 必须进入 H 内一个声明式 params object，
   并通过经过 `try_apply_op` 的新 metatool 编辑，同时把 RISK_OFF veto floor 固定在可调 surface 之外。
6. **`session.py` 的 `experience_writer` 调用未加保护**——writer exception 会杀掉 live turn；
   一行 try/except-log。应放进 P-B/P-C pre-activation checklist。

## 5. 明确不适用（已检查，跳过）

Ed25519 signed envelopes / Merkle batch roots（单进程信任域；仅在 deferred body axis 时再考虑）、
multi-tenant RLS / IDOR / idempotency-key middleware、A2A dual-signed tasks、SSE fan-out/resume
clients、PII-free metric flowback、meet-semilattice policy compile、alpha 当前规模下的 perf-budget CI gates。

## 6. 建议顺序

1. **Docs day（§1.1 + §1.2 + §4.1）：** 修 ROADMAP drift，加入 Activation Ledger，
   创建 `runbooks/` 和 P-B/P-C activation runbook（把 §2.3 的 gate-side hardening + §4.6
   折入 checklist）。
2. **廉价加固批次（§1.3-§1.6）：** SSRF pin、taboo-required gate check、redact()、
   prompt-audit hook + `render_prompt.py`。
3. **完整性批次（§2.1 + §2.6，一个 hashing utility）：** `tcb.lock` + PIT-window CHECKSUMS。
4. **GCycle recalibration 前（§2.5）：** trap-day battery，然后借 §1.6 的 audit record
   做诊断来重新校准。
5. **P-C activation 前（§2.3）：** gate-side task-evidence re-derivation。
6. **对应 spec 轮次开启时：** 将 §3 各行输入 workflow/connector/subagent models、
   branchable brains、G sub-agents、self-learning channel、context management。
