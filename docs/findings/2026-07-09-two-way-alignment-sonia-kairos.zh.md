# 双向对照：Sonia-Kairos 设计宪章 ↔ 本代码库

**日期：** 2026-07-09 · **方法：** 31-agent 工作流——5 个穷尽式读取器（宪章、后端设计、设计台账、
代码命名审计、代码架构现实审计）→ 正向/反向双综合 → 对每条承重事实做对抗验证（24 条已验证：
**21 CONFIRMED、3 CORRECTED、0 REFUTED**）。来源锚定：设计仓库 `../Sonia-Kairos/`（截至
2026-07-09）；本仓库 `main` @ `a1a8acd`（919 测试）。

> **命名注：** 自 2026-07-09 起本仓库更名 **Sonia-Kairos-US-Stock**（原 Evolving-Alpha-US）。
> **Sonia** = 教师（`alpha/meta/` + `sonia/`）；**Kairos** = 工作者（`converse/` + `arena/` +
> `workbench/`）。下文小写 `kairos` = 同级 CN 法律智能体 donor 仓库。设计宪章的 "harness" =
> Kernel ∪ Body；本仓库（及论文）的 "harness" = 可进化剧本 `H` = 宪章的 **Body**。

---

## A 部分——正向：本仓库今日落地的修改（2026-07-09）

均已本次落地；此处仅记录，细节见 diff：

1. **更名** 为 Sonia-Kairos-US-Stock，覆盖 CLAUDE.md §1（含对宪章 2026-07-06 pivot 的诚实分歧
   声明）、README、pyproject 描述、文档头（blueprint/PROJECT_STATE/ROADMAP）、web 控制台标题 +
   品牌标记、workbench 标题、Kairos 实时系统提示词（`converse/agent.py`）、verdict 运行横幅、
   ingest User-Agent。Kairos 命名选择 **方案 (A)**：工作者面孔按现状承名；其分歧点
   （T3 `propose_memory_edit`；`write_mode="apply"` 经门把自己的编辑落地）是被记录的，不是被
   掩盖的。
2. **CLAUDE.md 漂移修复：** freshness `dce2a0a`/704 → `a1a8acd`/919 + 负责人/审阅日期；整个
   `alpha/arena/` 包补进层脊/包图（此前完全缺失！）；补 6 个新模块（`extractor.py`、
   `approve.py`、`task_forge.py`、`refiner_prompt.py`、`baselines.py`、`errors.py`）；新增术语桥
   （harness 陷阱、Sonia/Kairos 角色、小写 kairos）；blueprint 的 "Authoritative" 声明限定为
   感知/评估层 v1.0。
3. **README 事实修复：** US-1/US-2/US-3 仍标 "Planned"——实际全部建成；过期的
   `docs/ROADMAP.md` 链接改指根部 backlog；`docs/ROADMAP.md` 缩为指针存根；新增 Kairos
   workbench 小节；License 行改为诚实表述。
4. **打包：** `pyproject` `packages.find` 补 `workbench*`（此前 wheel 构建会静默丢掉该服务）。
5. **推迟项（记录于 `ROADMAP.md` §7 Naming）：** GitHub 仓库改名 + 设计仓库指针同步；
   EditProvenance 迁移（`'hermes'`→`'kairos'`、加 `'user'`、填充 `human_approver`）；子目录
   CLAUDE.md + 提交式 settings 屏蔽列表。import 包保持 `alpha`、env 前缀保持 `ALPHA_*`
   （约 1,340 条 import 行 / 约 296 文件；改名成本 ≫ 收益）。

更名后全量测试通过（919 tests，exit 0）。

---

## B 部分——反向：本代码库对设计仓库的建议

**落地纪律（务必遵守）：** 架构/治理类 = 提议的**宪章修正案**（带日期标记，然后向下同步）；
精度/呈现类 = **后端同步更正**（直接落 `Backend-Design-SoniaKairos.md`）；流程类 = **ROADMAP
追加**。绝不编辑冻结的 `docs/research/` 记录。本文件自身也是冻结记录——以下每条是供设计仓库
自身流程处理的建议，不是已在那里做出的编辑。

验证状态：rev-01…rev-12 本次经对抗验证（11 CONFIRMED，rev-08 CORRECTED 且结论被加强）；
rev-13…rev-19 有证据引用但未独立复验。

### B1. 事实性更正——设计文档今天就是错的

- **rev-01（critical）· 宪章内部矛盾：memory 失败语义。** 宪章第 33 行（Memory Stores 条目，
  2026-07-07 句）仍说无法 reconcile 的 store *隔离整个会话*，而第 383 行（2026-07-09 随 Mem0
  修订）宣布 memory 是*刻意的例外*——由 journal 重建自愈。奠基性组件枚举与它指向的机制章节
  互相矛盾。修正第 33 行以声明 memory 例外（新日期标记与旧标记并存）。*(CONFIRMED)*

- **rev-02（critical）· anti-donor 指针无法解析。** 后端 §4（368/379 行）写 "α
  `floor_breaker.py` … 其 auto-`rollback_to` 已删除"——但 `floor_breaker.py` 是纯检测数学，
  grep `rollback_to` 零命中；机器回滚实际在 `loop/inner_loop.py`（trip →
  `self._mgr.rollback_to(target)`）+ `harness/manager.py::rollback_to`。更正引用，让"拆除图"
  可被 grep 验证。*(CONFIRMED)*

- **rev-16（medium）· Sonia "零出口" vs 她自己的厂商 LLM 调用。** `sonia/propose` 与 dreaming
  由 LLM 驱动；厂商托管模型调用本身就是一个向外的 socket（本仓库的 Sonia 直连 DeepSeek——
  `sonia/app.py:92,133`）。明确模型推理出口物理上从哪里出去（内核中介调度），并把它从 SP2
  零出口 socket 测试的断言中豁免——否则该测试写成即败于任何厂商模型 Sonia。

### B2. Donor 器官图刷新——后端 §5 vs `main` @ `a1a8acd`

- **rev-03（high）· 五个新器官未入图**（该图的 alpha 快照晚于 P-A、早于 teach-crystallize
  v5）：(1) `meta/extractor.py::extract_ops` + `refine/ops.py::parse_extraction` →
  `sonia/propose` 先例；(2) `converse/approve.py`（`StagedEdit`/`assert_approvable`）→
  `kernel/approvals` 先例（现只引 κ）；(3) `meta/conflict_store.py::ConflictQueue` +
  `refine/conflict.py::is_conflict` → `sonia/triage` 先例；(4) `arena/experience.py` +
  `experience_writer` 注入缝 + `Episode.kind∈{trade,task}` → "episodes 是追加式会话事件"行的
  已定位实现；(5) P-C 的 domain 标签运营-K 门机制 → 作用域标签 Body 内容先例。*(CONFIRMED)*

- **rev-04（high）· 缺失的 anti-donor：工作者面孔的大脑编辑通道。** `arena/builder.py` 在
  `write_mode∈{apply,stage}` 时注册 T3 `propose_memory_edit`，且
  `converse/tools.py::make_gated_write_tool` 在 `apply` 模式经 `try_apply_op` 无人工环节地把
  工作者自己的编辑落地——这是对"Kairos 不提议、不自改"最直接的违背，而 does-not-survive
  列表却漏掉它。补上。*(CONFIRMED)*

- **rev-14（medium）· §3 布局树里 faces 无家可归**，尽管该文档自 2026-07-09 frontend-design
  拆除后全权拥有 faces、SP4 要建三个。补一个 `faces/`（或 `apps/`）顶级条目，引本仓库已被
  验证的三应用-over-HTTP 模式（:8100/:8810/:8820，HTTP 而非 import，mock 模型离线可测）——
  并编码那个实战踩到的打包陷阱：把打包清单钉到 face 名册上（workbench 在本仓库曾被 wheel
  静默丢弃直至 2026-07-09）。

### B3. 提议的宪章修正案——宪章缺失的实战教训

- **rev-05（high）· 永不静默的提案结晶。** 散文→提案的转换必须是显式的、schema 强制的动作，
  返回 ops **或** `{no_edit, reason}`——静默的空提取是契约违规，须呈报用户。这是
  teach-crystallize v5 的核心教训：有门写路径从来不是缺口；教学是在门的*上游*蒸发的——聊天
  模型自愿输出的 ops 被静默解析为 `[]`。Donor：`extract_ops`/`parse_extraction`。*(CONFIRMED)*

- **rev-06（high）· 试验臂对称：读/写句柄分离。** 进化臂对冻结臂比较时，比较期间进化臂被剥夺
  共享习得状态的**写**句柄；所有臂读同一固定池。今天这条只存在于后端 donor 单元格备注——
  按设计仓库自己的纪律，评估公平性规则应先落宪章。同时给推迟的 counterfactual 盲比较决定加注
  "donor 已定位：`loop/compare.py::compare_harnesses`"。*(CONFIRMED)*

- **rev-07（high）· PIT / knowable-as-of 纪律。** 宪章通篇**零** PIT/前视概念，而后端已在
  `learned_asof` 上承重（§5、Fitness Protocol、SP3/SP5、§8 不变量）——下游文档领跑宪章，
  违反自身纪律。具体：宪章 430 行的试验 fork 只读**当前 tip** 的 memory，于是重放上个月的
  会话能查到上周才学到的事实——不诚实的证据。修正：习得工件携带 knowable-as-of 键；一切
  重放/试验/反事实把检索掩码到该键。*(CONFIRMED——宪章唯一的 "point-in-time" 字符串是 244 行
  无关的审计恢复义。)*

- **rev-08（high）· 批准 episodes-as-session-events 框架 + 定义饱和度指标。**
  (a) 内核观测的逐决策结果事实是内核写入的会话事件，**不是** memory 内容提案——永不过审批
  队列；只有从中提炼的解释/lessons 才过（后端 §5 已如此断言；其 §10 风险行自认宪章从未言明）。
  (b) 把定性的队列饱和/饥饿 revisit 触发器换成可测量指标。*(CORRECTED 且被加强：本仓库每个
  被计分的 **pick** 写一条 PIT 键 episode——每决策日数条而非一条——事实走审批队列会更快
  饱和。)*

- **rev-09（high）· revert 必须 reconcile 全部派生状态。** reconcile 集合包括每一条断言某已
  落地编辑存在的派生记录（会话侧 applied 标志、队列/终态、UI 处置），不只是声明的 stores。
  活体标本：本仓库 `/rollback` 恢复大脑但留下会话上的 `applied_seqs` → `/propose` 返回 409，
  该教学轮次永久死锁（已记录于我们的 ROADMAP）。*(CONFIRMED)*

- **rev-10（high）· Sonia 提案触碰用户落地编辑时的争议/搁置机制。** 2026-07-08 第二触发器
  造出双写入者来源的世界，宪章只写了一半：Sonia "可提议更正"——但没说她的更正与用户已落地
  编辑冲突时怎么办。Donor 恰好解决过这条缝：按最新来源判定所有权（内核计算、绝不由提案者
  自述）、争议包裹搁置待用户显式裁决、create 类动词永不争议
  （`refine/conflict.py::is_conflict` + `ConflictQueue` + `apply.py` held-for-review）。*(CONFIRMED)*

- **rev-11（high）· 回滚后证据隔离。** 因坏结果触发 revert 之后，在被 revert 的 Body 版本下
  产生的证据窗口，对下一轮提案要排除（或显式标记）——否则同一编辑会从同一批劣化证据再次
  落地。Donor：`inner_loop.py:215-229` 把 `last_refined_idx` 推过被丢弃窗口，注释写明正是
  此因。与落地权限无关，普适。*(CONFIRMED)*

- **rev-12（high）· confirmed-positive 反 Goodhart 规范。** 只有外部确认的正例可计入提案包裹
  的晋升级主张；agent 自报成功至多是参考。Donor：`TaskStats` 只数确认正例 + fail-toward-strict
  任务地板（"不在 confirmed_ids 里的 'succeeded' episode 是中性的"）。宪章有邻近概念，但提案
  证据内部无此规范——这正是 Goodhart 经 Sonia 包裹重新进场的通道。*(CONFIRMED)*

- **rev-17（medium）· 顾问型垂直领域的建议完整性残余风险。** "会话的爆炸半径随会话消亡"
  对"被采纳的建议"这一伤害通道是盲的：一个被注入的会话使某日排名偏倚，按宪章记账"随会话
  消亡"，但其金融伤害不会。命名该残余风险；注明领域输出侧缓解（确定性 veto/guard + sizing
  包装器作为钉死的机制插件、策略内容在 Body）是垂直领域的责任——本仓库的
  `SizingPolicy(GuardedPolicy(·))` + 人工确认教义即是成形范例。

### B4. 流程 / roadmap 项

- **rev-13（high）· 更名引用计划**（GitHub 改名落地时执行）：更新两个非冻结指针（后端第 5 行
  donor 路径；设计 CLAUDE.md 的 "`../evolving-alpha-us/` literally implements a Sonia" 行），
  加 "(ex evolving-alpha-us)" 注释；旧→新映射记入 ROADMAP 追加条目而非动冻结研究文档；§4
  donor 图例加一行消歧 "κ/kairos = CN 法律智能体 donor 仓库，非 Kairos 工作者"；在设计的
  "finance vertical" 与本仓库的 "US-stock" 措辞间做一次自觉决定。

- **rev-15（medium）· 强制力等级标注。** §8 常设规则：每个防护机制声明其等级（内核边界 /
  访问控制 / 参考性黑名单 / 惯例），参考级防护必须在代码里指名真正守线的结构不变量（能加
  boot 断言就加）。Donor：arena `LocalEnv` 的 "NOT a security boundary … TOCTOU-bypassable"
  诚实注释 + workbench 的大脑目录在工作区外 fail-fast 断言。

- **rev-18（low）· SP2 分解纪律。** SP2 捆绑七个新内核包 + 两个 sonia 包；同等规模在本仓库
  只以每弧 7–20 个经评审的 TDD 子任务的方式交付过。给 SP2 分段，或记录预定的分解纪律。

- **rev-19（low）· 组合顺序钉进单一工厂。** 包装器堆叠顺序即语义
  （`SizingPolicy(GuardedPolicy(·))`——guard 在内、sizing 在外），且装配必须住在**一个**
  工厂里，实盘路径与每个试验臂都调它——否则试验测的是接线不同的 agent。Donor：
  `compare_harnesses` 用一个共享闭包串起所有臂。

---

## 元观察

2026-07-01 的挖掘发现 kairos 100 个模式中 40 个已在本仓库趋同存在。本次反方向同样：设计仓库
已吸收本仓库的治理器官（写腰 → Applier、verdict harness → kernel/trial、arena → sandbox）——
尚未吸收的集中在两类：**时间纪律**（PIT、证据隔离、臂对称——rev-06/07/11）与**缝隙处的失败
诚实**（永不静默提取、revert 清算派生状态、争议搁置、confirmed-positive——rev-05/09/10/12）。
两类都是本仓库用真实 bug 换来的；在 SP1 代码存在之前导入它们，是设计所能买到的最便宜的教训。
