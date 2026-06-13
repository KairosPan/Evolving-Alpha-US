# ROADMAP — 自进化游资系统(youzi)

> 总图:我们在造什么、走到哪、下一步去哪。详细交接见 `PROJECT_STATE.md`;实验记录见 `docs/findings/`;每阶段 spec/plan 见 `docs/superpowers/`。
> 截至 2026-06-09 · `codex/roadmap-b2` · **420 测试全绿(离线)** · 🔎 **全架构评审已做**(`docs/findings/2026-06-09-arch-review.md`,本图据此重排)。✅ **第一波+第二波+B2 已完成**(E1/C2/C1/A3/A1/E2/C4/B2,共 121 测试新增)。

---

## 北极星

把论文《Continual Harness》的 `H=(p,G,K,M)` 两环自进化机制,落到 A 股**游资/超短**交易(《轮回.docx》playbook),做一个**决策支持 Co-pilot**(系统排候选 + 计划 + 理由,**人确认下单,绝不自动交易**)。

**中心问题(尚未回答):自进化(每日精炼 H)能否产生 alpha —— 即 `HCH`(自精炼)能否跑赢 `Hexpert`(冻结种子)?**

当前诚实答案(2026-06-09 评审后修正):**不仅"还不能",而且当前评测体系还没有能力回答这个问题。**
- 1b-3d 后池化 HCH +0.222 ≈ Hexpert +0.219"打平">裸追高 +0.185>空仓 0(findings §8/§9)。
- 但裁决是裸符号(`d_mean>0`,compare.py:87),无 CI/显著性;Δ=+0.003 远小于该样本量下的最小可检测效应(MDE≈0.26)——**"打平"结构上不可证伪**。
- 因此路线重排:**先修尺(C1/C2/C3),再修编辑触达(A1/A2),再问北极星。** 就算 akshare 明天恢复,现在这把尺也测不出结论。

---

## 不可动摇的边界(贯穿所有阶段)

1. **决策支持,非自动交易** —— 系统给候选/计划/理由,人确认。
2. **未来函数防火墙** —— 决策只用 ≤t 信息(GuardedSource/AsOfGuard);打分在 t+horizon;已实现未来只作事后 oracle 标签,绝不回灌 ≤t 推理。
3. **观测 vs 编辑边界** —— SkillStats 由 `apply_credit` 直接写(观测);结构性编辑走 9 个 MetaTool 入 EditLog。
4. **领域/web 分层** —— `youzi/`(领域)零依赖 web;`youzi_web/`(web)单向依赖领域。
5. **离线优先** —— 全部逻辑离线可测(FakeSource/MockLLM/TestClient);live(akshare/DeepSeek)是末端可换适配器。

---

## 🔎 架构评审五根因(2026-06-09,全部带 file:line 实证,已独立抽查坐实)

1. **编辑→决策触达断裂**:`write_skill` 强制 incubating(refiner.py)而提示只渲染 `by_status("active")`(prompt.py)→ 孵化技能永不可见、n 永远=0、永无证据晋升,promote 又无证据门——**孵化死锁,扩张算子整条废掉**;`demote_memory` 只动 importance 而 `weight()` 全库零消费、提示全量渲染 `memory.all()`——**demote 是 no-op**;K-pass 看不见 trigger/taboo 现值——**盲改**(patch 整字段替换还会静默丢既有 taboo)。
2. **信用信号脏**:expectancy 含市场β(裸追高 +0.185 说明大头是行情);pattern 自由文本仅精确匹配,变体落 unattributed;无相位分桶("主升赢退潮亏"学不到)。
3. **裁决不可证伪**:`hch_beats_hexpert=d_mean>0` 裸符号,无方差/CI/MDE;冻结臂被 LLM 重采样 +0.267→0.000。
4. **尺子结算虚构交易**:horizon=1 时 ReturnScorer 同日开买收卖**违反 T+1**(walk_forward 把 `days_seen[j+1]` 同时作 entry/exit);一字板假设按 open 全额成交;缺收益候选静默丢弃(幸存者偏差直通信用链)。
5. **进化无后验选择压**:熔断 `breaker_min_samples=40` 按**候选**计数,真实窗每窗仅 3~20 候选 → **从未上膛**(三窗"未触发"是算术必然);frozen 后 `apply_credit` 仍写 stats(冻结的提示还在漂移);编辑就地生效无验收闸。

16 条改进方案(P0×6/P1×10,经逐条对抗核实,0 整案否决):报告 `docs/findings/2026-06-09-arch-review.md`,**逐条核实理由+修正版实施设计** `docs/findings/2026-06-09-arch-review-proposals.json`(实施照 revision)。

---

## 已完成(并入 main)

### 地基(Phase-0)
- **0a–0d**:数据回放 + 未来函数防火墙 + universe + 评测尺 + 种子 H(57 技能/21 记忆/doctrine,从《轮回》抽取)。

### 自进化内环(Phase-1a–1c)
- **1a** Agent(act)· **1b-1** 观测层(Trajectory/credit/签名)· **1b-2** LLM Refiner(4-pass CRUD)· **1b-3a** InnerLoop 编排 · **1b-3b** compare_harnesses 四臂对比 · **🔬 真实数据验**(HCH 3/3 退化,§6.9 复现)· **1b-3d** Refiner 纪律化(退役证据门,复测打平)· **1b-3e** 收益 oracle+可插拔 Scorer · **1c-PIT** 快照+离线打分。

### 前端平台(FE)
- **FE-0** 外壳+注册表+research/H 查看器 · **FE-B** 研究驾驶舱(run_store+3 视图) · **FE-A** 决策驾驶舱(离线渲染已存决策)。
- 看成品:`python scripts/sample_run.py` → `python scripts/serve_web.py` → http://127.0.0.1:8000

### 评审(2026-06-09)
- 30-agent 全架构评审:7 子系统精读 → 5 视角 36 提案 → 合并 24 → 16 条 P0/P1 对抗核实全存活(12 修正)。

### 架构修复 第一波 — 修尺(2026-06-09,299→409 测试)
- **E1 LLM record/replay 缓存**:`youzi/llm/cache.py` — `CachedLLMClient` 三模式(read_write/read_only/off),content-addressed key=sha256(model+temp+system+user+fingerprint);read_only miss 即 raise `CacheMissError`,决不静默回落 live;原子写;17 测试。
- **C2 优势化信用**:`youzi/eval/scorer.py` + `metrics.py` + `harness/skill.py` + `refine/credit.py` + `loop/compare.py` + `eval/baselines.py` — `day_baseline`=决策日池均分;`advantage=score−day_baseline` 替换 apply_credit expectancy(保留 raw);compare 北极星切 mean_excess;新增 `PoolAveragePolicy`/`RandomFromPoolPolicy` 基线臂;17 测试。
- **C1 统计裁决层**:`youzi/eval/stats.py` — `daily_series()`/`paired_daily_diff()`/`moving_block_bootstrap()`/`sign_permutation_pvalue()`/`mde()`/`verdict()`→`StatVerdict∈{win,loss,flat,insufficient}`;配对日<8→insufficient;compare 视图加 stat_verdict 卡;18 测试。
- **A3 Refiner 证据重构**:`youzi/loop/inner_loop.py` — `last_refined_idx` 水位线非重叠窗+`evidence_min` 触发(保留 refine_every 上限);`youzi/refine/refiner.py` — `deque(maxlen=2)` 保留最近 2 次报告;`refiner_prompt.py` — 近期编辑史段+涉案技能全文渲染+patch 纪律注;11 测试。

### 架构修复 第二波 — 修编辑触达(2026-06-09)
- **A1 孵化→晋升+预算化检索注入**:`youzi/agent/retrieval.py` — `select_for_prompt(phase_prior ∪ applies_all, top-B1 技能/top-B2 记忆, weight<0.15 过滤)`;至多 3 条 incubating[试验]渲染;promote 证据门(n≥3 且均值>0);`resolve_skill` strip+casefold 归一;`agent/prompt.py` injection='full'|'retrieval';12 测试。
- **E2 规则策略中层**:`youzi/eval/rule_policy.py` — `GateSpec`(强类型门)+`HarnessRulePolicy` 真读 H 零 LLM;`inner_loop.py` `agent_factory`+`_rebind`(防熔断后废弃 H);断言按 horizon 滞后对齐;17 测试(含 3 集成)。
- **C4 Hcredit 消融臂**:`loop/compare.py` `ablate` 参数+`Hcredit` 臂(`enable_refine=False`);按日对齐配对差复用 C1;compare.html Hcredit 行+消融裁决;6 测试。

### 架构修复 第三波 — 闭环与防线(部分,2026-06-09,409→420 测试)
- **B2 熔断重设计**:`youzi/loop/inner_loop.py` — 熔断武装单位改为已评分决策日(`breaker_min_days`),日级 advantage-MAD fallback(`_fallback_trip`),影子配对双门(`_shadow_trip` + ε_abs + 方向门),`BreakerEvent.mode∈{rollback,frozen}`,冻结后停 `apply_credit`,退化窗起点前 checkpoint 整段回滚并可再武装;旧 `breaker_min_samples/window/baseline/floor_rel_margin` 仅保留兼容不再消费。`youzi/loop/compare.py` — `shadow=True` 时先跑 Hexpert,提取日级 advantage 序列注入 HCH/Hcredit 熔断,内部按 ≤当前已评分日过滤防前视;11 测试。

---

## 路线图(评审后重排,按波次;字母编号对应评审报告 §4)

### 第一波 — 修尺(纯离线、零数据依赖、三线并行)✅ 已完成
1. **E1 LLM record/replay 缓存(P0,M)**:`CachedLLMClient` 实现 LLMClient 协议,content-addressed key=sha256(model+temperature+system+user);record/replay/read_only 三模式,read_only miss 即 raise 决不静默回落 live;黄金 run 固化为离线回归(录制需一次真实 smoke,待 akshare/DeepSeek)。一次付费换永久确定性复跑;A2/A5 的成本前提。
2. **C2 优势化信用(P0,M)**:`day_baseline`=决策日池全体同口径打分均值(PoolRecord 已录两日成员,零额外取数);`advantage=score−day_baseline` 替换消费面——apply_credit 的 expectancy(保留 raw)、refiner 信用行、compare 北极星检验;新增 PoolAverage/RandomFromPool 基线臂。把"行情给的"与"技能挣的"分开;advantage 自带零点使熔断地板天然 scorer 无关。
3. **C1 统计裁决层(P0,M)**:`eval/stats.py`——日级等权聚合(空仓日记 0)、配对日差、移动块 bootstrap CI(块长 2-5,B≥10000,seed 可控)+符号置换+MDE;`verdict∈{win,loss,flat,insufficient}`(配对日<8→insufficient)替换裸符号,保留旧 bool 兼容;Phase-1 验收门改 `ci_low>0`。检验建在 advantage 口径上(C2 先合或同批)。
4. **A3 Refiner 证据重构(P1,S)**:`last_refined_idx` 水位线非重叠证据窗+`evidence_min` 触发(保留 refine_every 作上限门);提示注入最近 2 次编辑史(applied rationale+rejected 拒因);涉案技能(信用∪签名命中)渲染全文。最便宜的收敛性修复。

### 第二波 — 修编辑触达(自进化杠杆)✅ 已完成
5. **A1 孵化→晋升+预算化检索注入(P0,M)**:`agent/retrieval.py` select_for_prompt(phase_prior∪applies_all 截 top-B1 技能、weight() 降序截 top-B2 记忆且 weight<0.15 不渲染);渲染至多 3 条 incubating 试验位[试验];promote 加证据门(n≥3 且均值>0,镜像退役门);resolve_skill strip+casefold 归一;injection='full'|'retrieval' 开关。唯一直接打在"编辑不改变决策"病灶上的 P0。
6. **E2 规则策略中层(P1,M)**:Skill 增 GateSpec(强类型机器可读门,仅测试种子填充);HarnessRulePolicy 真读 H 零 LLM;InnerLoop 加 agent_factory 注入(经 _rebind 重建,防熔断回滚后读废弃 H);断言按 horizon 滞后对齐。"编辑→决策改变→分数改变"首次进 CI;与 A1 互为验收器。
7. **C4 Hcredit 消融臂(P1,S)**:`enable_refine` 开关得到"只有战绩回注、无结构编辑"第三臂;按日对齐配对差(复用 C1);把北极星拆成"在线反馈是否有益"与"结构编辑是否有益"。

### 第三波 — 闭环与防线⏭ 当前(A2/C5 待做,B2 已完成)
8. **A2 EditGate 编辑验收闸(P0,M)**:Refiner 在 sandbox 克隆上产出编辑;**主通道=前向影子验收**(H_candidate 与 live champion 并行前向 k 日虚拟打分,Δ≥0 才 adopt);后向回放只作冒烟闸、**不得**作为放宽退役门依据(in-sample 会放行恰被 1b-3d 治住的退化);GateRejectedEvent 回流作证据。依赖 C1 verdict+E1 降成本。
9. ✅ **B2 熔断重设计(P1,M)**:武装单位换"已评分决策日"(breaker_min_days=3,删 40 候选门);主地板=影子配对差(双门 mean<−max(λ·std,ε_abs)+方向一致性副门);fallback=advantage-MAD 自标定;**apply_credit 包进 if not frozen**;回滚至退化窗起点+可再武装。作废"熔断 scorer-aware 重标定"债务。
10. **C5 实验预注册+ExperimentConfig(P1,M)**:声明式配置单源全量入 run meta(保留工厂注入);删 RefinerConfig.window 双旋钮;decay 升入 LoopConfig;run_protocol.py 先注册窗口后执行;完成率<80% 拒绝池化。下次真实跑之前必须就位。

### 数据线(与上并行,受 akshare off-peak 制约)
- **D1 PIT 完整性闭环(P1,L;建库时升 P0)**:sidecar manifest 五态语义分型(限流不再伪装"今日无炸板")+covers 范围语义+整段重抓原子重写(qfq 复权基准不可 merge)+契约分级+snapshot_doctor 强制门 → 建库 → **C3 可成交收益尺(P0,M,代码离线先行)**:T+1 守门(entry==exit raise,ReturnScorer 须 horizon≥2)+一字板成交判定(先板块后 ST)+CostModel+缺数一等公民+path stop-on-nuke → **B1 相位分类器 G-0(P1,L)**:三相+None 起步、SkillStats 相位分桶(桶级证据门复用 1b-3d 纪律)、软过滤注入+翻案通道、relay_in_ebb 签名。
- **OHLCV 多源 fallback**(eastmoney→sina→tencent,纯离线小切片,当下就能做)。

### 第四波 / 后备
- **A4 赢家/MissedWinner 挖掘(P1,M)**(必须标 fill_doubt)→ **A5 best-of-N 编辑锦标赛(P1,L)**(依赖 A2+C1+快照+ReturnScorer;=蓝图育种场最小版)。
- **E3 RunJournal+断点续跑(P1,L)**(resume=双 checkpoint+credit 重放;E1 落地后价值收敛为可观测性)。
- P2:DayStream/Arm 多臂共驱、confidence 校准(仓位 v0)、derive_zt_pool 历史池重建(解锁周期级长窗)、HarnessManager epoch 句柄+EditLog WAL。
- **1c 协同学习外环**(PRM+oracle relabel+LoRA,需 GPU)。

### C. 前端平台(成长型 · 加功能=加模块)
1. live 按需跑决策/从 UI 触发跑批(需异步任务+akshare 恢复)。
2. news 分类模块、agents 编排模块。
3. 研究侧深钻:trajectory 单步详情/多 run 对比/run-store 清理分页;C1 落地后 verdict/CI 进对比视图。

---

## 债务清单(评审后更新)

| 债务 | 处置 |
|---|---|
| LLM 响应缓存 | **升级为第一波 E1** |
| 熔断 scorer-aware 重标定 | **由 B2 作废**(advantage-MAD/影子配对自标定) |
| 选择性提示注入(按 regime) | **升级为第二波 A1**(检索注入) |
| friction:update_memory lesson_id / 重复 lesson_id | **由 A3 治本**(编辑史注入+非重叠窗) |
| fill-feasibility / 成本滑点 | **升级为 C3**(可成交收益尺) |
| OHLCV 多源 fallback | 数据线,当下可做 |
| 真历史回测 / PIT 自建 / 幸存者偏差 | D1(闭环)+ D2 derive_zt_pool(P2) |
| FE live 接线 / 触发跑批 / news / agents | 轨道 C |

---

## 怎么读这张图

- **想知道"自进化行不行"** → 先看"五根因":当前尺子测不出答案;第一波修尺 + 第二波修触达之后,北极星才可证伪。
- **想现在能稳定推进、不依赖外部** → 第一波全部纯离线(E1/C2/C1/A3),C3 代码也可离线先行。
- **每个阶段都走** brainstorm → spec → plan → subagent 实现 + 两段评审 + opus 终审 → FF 合并。spec/plan 在 `docs/superpowers/`;评审实施细节直接用 `2026-06-09-arch-review-proposals.json` 里的 revision。
