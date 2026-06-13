# 架构评审与改进方案(2026-06-09)

> 方法:30-agent 多阶段评审 workflow——7 个子系统读者并行精读(harness/refine+loop/eval/data/agent/设计文档/web+测试)→ 5 个视角独立提案(自进化方法论/A股游资量化/软件架构/数据工程/评测有效性)36 条 → 合并 24 条 → 16 条 P0/P1 逐条对抗核实(读代码三关:问题真实?非旧债换皮?技术成立?)→ 综合。**0 条整案否决,12 条修正后存活**;6 个最关键论断已由主会话独立抽查坐实(孵化死锁/demote no-op/熔断永不上膛/frozen 不真冻/裸符号裁决/horizon=1 违反 T+1)。
> 提案明细(含每条的核实理由与修正版设计,实施时照此):`2026-06-09-arch-review-proposals.json`

# 自进化游资系统架构评审与改进方案

## 1. 总体评价

这套系统把"安全地改"做到了高水准:观测/编辑双层隔离、immutable 红线双保险、append-only 审计、PIT 防前视双保险、299 个离线确定性测试、四臂同窗同 oracle 的对照仪器——蓝图 §6.9 预言的 bootstrap 退化第一跑就 3/3 复现,证明这套科学仪器是真的。但系统当前卡在三个互锁的断点上:**Refiner 的编辑大多落在对决策不可见或零敏感的通道**(findings §9 两窗 HCH≡Hexpert,Δ 精确=0)、**评测尺既测不出也测不真**(裸符号裁决 + 虚构交易结算)、**进化无后验选择压**(熔断从未上膛、EditGate/锦标赛零代码)。离北极星的距离可以量化:Phase-1 验收门是"OOS 稳定优于 Hexpert",而当前 Δ=+0.003 的"打平"在 MDE≈0.26 的噪声水平下结构上不可证伪——不是"尚未有益",而是**目前还没有能力回答"是否有益"**。

## 2. 架构现状图

| 层 | 一句话 | 成熟度 |
|---|---|---|
| 数据(source/cache/capture) | akshare 四池+OHLCV、原子写 PIT、离线快照源;但单点依赖+空帧语义污染+OHLCV 端点硬拒连 | 中 |
| 回放(engine/firewall) | AsOfGuard 单调游标+history 截断,防前视纪律全链一致 | 高 |
| 特征(builder/sentiment) | 池级计数聚合;sentiment_norm 需 60 样本近乎不可用,席位/题材/晋级率等打板核心信号缺位,已采微观字段(封单/首封)弃用 | 低 |
| Agent(prompt/parse/client) | 每次 decide 重渲染 H 零延迟生效(关键耦合点做对了);但 24K 全量注入、检索索引全闲置、regime_read 被丢弃 | 中 |
| 评测(walk_forward/scorer) | PIT 延迟打分机制干净;尺=三值池成员制,无成交/成本/显著性 | 机制高、效度低 |
| 信用(credit/signatures) | pattern 精确匹配归因+确定性失败签名;无 advantage、无相位分桶、只有负向签名 | 中低 |
| Refiner(refiner/metatools) | 拒绝管线+多层防伪+退役证据门扎实;编辑触达断裂 | 防护高、效用低 |
| 内环(inner_loop) | checkpoint→refine→熔断闭环成形;熔断从未上膛、frozen 不真冻 | 中 |
| 对比+持久化(compare/run_store) | 四臂公平性到位;裁决是裸均值差符号 | 中 |
| web(youzi_web) | 领域零侵入的只读观测台;默认 run 排序与种子 H join 会误导诊断 | 中高 |

## 3. 核心诊断:为什么自进化"无害但无益"

**根因一:编辑→决策的触达链路结构性断裂。** 扩张算子死锁:write_skill 强制 incubating(refiner.py:116)而 prompt 只渲染 active(prompt.py:33)→新技能对 agent 不可见→pattern 永不命中→n 永远=0→永无证据晋升;promote 又无任何证据门(registry.py:97-103),两头都坏。收缩算子 no-op:demote_memory 只动 importance,而 weight() 全库零消费、prompt 全量渲染 memory.all()——实测 demote 到 0.01 后提示逐字不变。K-pass 盲改:Refiner 看不见 trigger/taboo 现值,patch 不可能增量。三条加起来,"refine 编辑不改变决策"不是 LLM 不行,是管道没接上。

**根因二:学习信号在三处失真,Refiner 拿到的证据又稀又脏。** ① 归因损耗:自由文本 pattern 仅 skill_id/name_cn 精确匹配(credit.py:35-45),变体写法落 unattributed,连锁压低 stats.n 使退役门更难触发;② β污染:expectancy 记原始分,裸追高 +0.185 vs HCH +0.222 说明 mean_score 大头是涨停池基准晋级率,Refiner 无法区分"技能好"与"上周市场好";③ 无相位分桶:"主升赢退潮亏"的技能在全局 stats 里搅成一个数,最有价值的结论类型(仅某相位失效→缩 regime)结构上学不到。结果只能保守收缩——1b-3d 后行为上移到 patch/rewrite 正是收缩偏置的表现。

**根因三:裁决层不可证伪。** d_mean>0 即判胜(compare.py:87),无方差无 CI;同日候选强相关、高产日主导池化均值,有效 n 远小于 n_candidates;冻结臂零代码改动被 LLM 重采样从 +0.267 抖到 +0.000(findings §8)。80% 功效下 5 窗约 30 日的 MDE≈0.26,检出 Δ=0.003 需约 20 万交易日。且 DeepSeek 纯 live 无响应缓存,每轮验证重复支付采样噪声与 API 费。

**根因四:尺子结算的是虚构交易。** horizon=1 时 ReturnScorer 同日开买收卖违反 T+1(walk_forward.py:71);一字板按 open 假设全额成交——hit 最高的恰是最买不到的;零成本滑点;缺数候选静默丢弃(scorer.py:49-50),停牌核查这类最差尾部被剔除,幸存者偏差直通信用链;三值 SCORE 把单日信息再压一层。即便自进化真产了 alpha,这把尺既测不出(分辨率)也测不真(可实现性)。

**根因五:进化无后验选择压。** 编辑=单次采样单批 CRUD 就地提交,开环;唯一安全网熔断从未上膛——breaker_min_samples=40 按候选计数,真实窗每窗仅 3~20 候选,len(scores)>=40 恒假,三窗"未触发"是算术必然(这也修正了 findings §4 自己的归因:不是地板没破,是地板检查从未执行)。1b-3d 用先验规则换来无害,同时压死了有益编辑的试错空间;没有后验闸,先验门只能越收越紧。

## 4. 改进方案

### A. 自进化机制

**A1(P0,M)孵化→晋升通路 + 预算化检索注入。** 问题:根因一的三个断点。方案:新建 agent/retrieval.py,select_for_prompt 按 phase_prior(前日 regime_read,parse 顺带补字段)∪applies_all 截 top-B1 技能、按 weight() 降序截 top-B2 记忆且 weight<0.15 不渲染(demote 即时生效);渲染至多 3 条 incubating 试验位标[试验]并指示 pattern 填 skill_id——孵化技能积累归因样本的唯一通道;promote 加证据门(n≥3 且均值>0,镜像 retire 门);resolve_skill 加 strip+casefold 归一;injection='full'|'retrieval' 开关留消融臂。影响:扩张与收缩两个算子同时接通,新技能"提出→小注→攒证据→过门"首次走通;token 不再随 H 生长单调膨胀。这是唯一直接打在"编辑不改变决策"病灶上的 P0。

**A2(P0,M)EditGate 编辑验收闸(修正版:前向影子为主通道)。** 问题:编辑就地生效,"编辑→决策→结果"开环。方案:Refiner 在 sandbox 克隆(from_dict 通路现成)上产出编辑;**主通道=前向影子验收**——H_candidate 作 challenger 与 live champion 并行前向 k 日虚拟打分,Δ≥0 才 adopt(同时把 1b-3c 影子机制落地到编辑级);后向回放降级为快速冒烟闸,且其 Δ≥0 **不得**作为放宽 min_retire_samples 的依据——对抗核实证明同窗回放是 in-sample,会放行恰被 1b-3d 治住的那类退化(砍掉 0 分候选→回放均分必涨)。收缩型编辑附加参与度不塌约束;GateRejectedEvent 回流作下轮证据;adopt=原子替换+重放窗内 credit。影响:从"无害"走向"有益"的前提——有后验闸才敢放宽先验约束。

**A3(P1,S)Refiner 证据重构。** last_refined_idx 水位线非重叠窗+evidence_min≥6 触发(保留 refine_every 作上限门);user prompt 增最近 2 次编辑史(applied rationale+rejected 拒因——现状渲染已有 lesson_id 仍挡不住重复,真因是重叠窗+拒因不可见);涉案技能(信用∪签名命中)渲染全文,其余单行。注意:patch 是整字段 setattr 替换,盲发 taboo 会静默丢失既有项,比重复更糟。最便宜的收敛性修复。

**A4(P1,M)赢家/错过者挖掘(修正版)。** SuccessSignature(continued 且 score>0)+ MissedWinner(池内未选、exit 日仍 continued);DayMembership 扩 boards 字段(录制点 universe 在作用域,真零额外取数);**必须**用 first_seal_time/blowup_count 给一字/秒板标 fill_doubt,否则把买不进的票挖成"错过的赢家"会让技能库系统性学歪;write_skill 引用实例的硬指令改条件式。给扩张算子第一次数据 grounding——当前系统只有防亏通道,没有产 alpha 通道。

**A5(P1,L)best-of-N 编辑锦标赛(修正版)。** N=3 候选批次+零臂,**窗内 holdout 验证+前向影子确认**(对齐蓝图 OOS-promote,治 winner's curse);adopt 语义=ops 重放而非状态移植(反事实 credit 绝不入 live stats);仅 YOUZI_SNAPSHOT+ReturnScorer+horizon≥2 时启用——PoolScorer 下编辑常不改决策,N+1 臂会日日全 tie,白烧调用。依赖 A2+C1 先落地。

### B. 交易策略与信号

**B1(P1,L)相位分类器 G-0(修正版)。** classify_phase 首版只出冰点/主升/退潮三相+None(中间相位 5 个标量特征弱可分,"余相类推"过于乐观);SkillStats 增 per_phase 分桶,apply_credit 双写;**桶级证据门必须复用 1b-3d 纪律**(建议缩 regime 需该桶 n≥K)——分桶让每桶 n 更小,不设门就是把治过的"小样本过度收缩"病在桶级重演;注入先软过滤(命中排前、未命中折叠)后硬过滤,被缩 regime 的技能保留小比例注入作翻案通道,杜绝"缩错→不注入→无样本→不可逆"死环;regime_read 与分类器逐日对账攒金标;signatures 增 relay_in_ebb——playbook 头号禁忌首次可检测。G 子系统 0→1,也是 Refiner 最有价值证据类型的使能件。

**B2(P1,M)熔断器重设计(修正版)。** 武装单位换"已评分决策日"(breaker_min_days=3,删按候选计数的 40 门);主地板=影子配对差(Hexpert daily 作 shadow),触发条件加双门 mean<−max(λ·std, ε_abs)+方向一致性副门——temp=0 下配对差恒 0 是常态,无 ε_abs 兜底会被微小负差误触发;fallback=advantage 口径 rolling<m−k·MAD,scorer 无关,"重标定常数"债务整体作废;**apply_credit 包进 if not frozen**(现 frozen 态提示仍在漂移);回滚至退化窗起点前 checkpoint+可再武装。六道闸中唯一"已实现"的一道从形同虚设变真保护。

**B3(P2)** confidence 校准报告+置信加权期望分(仓位 v0);另两项未核实但方向重要:持仓状态机(把超短 alpha 大头"卖点"纳入可学习面)、已采微观字段进提示。

### C. 评测与统计严谨性

**C1(P0,M)统一统计裁决层(修正版)。** 新建 eval/stats.py:日级等权聚合(空仓日记 0 保两臂日历对齐)、配对日差(免费方差缩减)、移动块 bootstrap(块长 2-5,B≥10000,seed 可控)+符号置换+MDE;verdict∈{win,loss,flat,insufficient}(配对日<8→insufficient)替换 compare.py:87 裸符号,保留旧 bool 兼容;蓝图 Phase-1 验收门改 ci_low>0。修正两处:aggregate_runs 只对含 daily 字段的新 run 做配对聚合——**§8/§9 历史 run 从未入 RunStore 且窗口已掉出 akshare 30 日限,不可回溯复算**,"打平"的程序化版本须用新管线重跑;verdict 函数本期只接 compare 与 web 视图,EditGate/锦标赛以接口约定形式预留(库内无 EditGate,现有熔断非臂对臂)。影响:北极星从单次采样的符号变成带置信度的可证伪命题;日级聚合+配对把所需窗口数降一个量级。

**C2(P0,M)优势化信用/截面超额。** day_baseline=决策日池全体按同口径打分的均值(PoolRecord 已录两日成员、capture 已抓全池 OHLCV,零额外取数);advantage=score−day_baseline 全面替换消费面:apply_credit 的 expectancy(保留 raw 第二字段)、refiner 信用行、compare 与北极星检验;新增 PoolAveragePolicy+RandomFromPoolPolicy 基线臂。影响:把"行情给的"与"技能挣的"分开——Refiner 第一次拿到选股信号而非市场方向;advantage 自带零点使熔断地板天然 scorer 无关;跨窗可比是聚合的前提。已核实零阻塞,数据全部现成。

**C3(P0,M)可成交收益尺(修正版)。** T+1:ReturnScorer 内部守门 entry==exit 即 raise(下沉到 scorer 才能同时罩住 WalkForward 与 InnerLoop 两条调用路径),ReturnScorer 须显式 horizon≥2;fill.py 比值阈值判一字板,**先板块后 ST**(仅主板 ST 降 5%,创业板 ST 仍 20%,否则系统性错杀游资常见的 ST 连板);CostModel 可配(印花税卖侧 5bp 现行);unfillable/missing 一等公民绝不静默丢弃,fill_rate 进 EvalReport 报双口径;path_outcome 扫 entry..exit 逐日成员 stop-on-nuke(Scorer 协议改传 mems 序列;首 nuked 日==entry 日时 exit 顺延一日,别在修 T+1 的提案里违反 T+1)。影响:不做这条,后续一切自进化结论建立在虚构结算上;代码可全离线先行,真实数据待 D1。

**C4(P1,S)Hcredit 消融臂(修正版)。** enable_refine 开关得到"只有战绩回注、无结构编辑"的第三通道;新写(非复用——现库无配对函数)~30 行按日对齐配对差;落地前可先用 refine_every>窗长零代码预跑一次探效应量级。把北极星拆成"在线反馈是否有益"与"结构编辑是否有益"两个可独立回答的问题。注意:§9 残差不能断言只来自 stats 通道——两个分叉窗里双通道均活跃,这正是需要消融的理由。

**C5(P1,M)实验预注册+ExperimentConfig(修正版)。** ExperimentConfig 定位为**声明式配置单源+全量入 run meta**,compare_harnesses 保留工厂注入(否则 294 个离线测试被破坏);删 RefinerConfig.window(与 credit_window 双旋钮静默漂移,prompt 内步列表与信用统计口径可不一致);decay 升入 LoopConfig(消费者是 InnerLoop,放 RefinerConfig 重演异处病);run_protocol.py 先注册窗口后执行,崩溃窗回写 status;aggregate 对完成率<80% 拒绝池化。"打平"宣称从此第三方可审计。

### D. 数据底座

**D1(P1,L)PIT 数据完整性闭环(修正版)。** sidecar manifest 五态(ok/empty_ok/unavailable/fetch_failed/contract_violation)+fetched_at;SnapshotSource 读 manifest 语义分型 raise——限流不再伪装"今日无炸板",炸板池>30 日标 unavailable 而非空帧(现状:历史窗 blowup_rate 恒 0、情绪分系统性偏正);covers(code,start,end) 范围语义,覆盖不足时**整段重抓原子重写**而非增量 merge——qfq 复权价随抓取时点漂移,merge 会把两个复权基准拼进同一文件,以完整性为名引入新污染;不可变语义分两类:pool 帧真 PIT 加 hash guard,OHLCV 豁免但记 fetched_at 审计;契约分级:结构性违约硬拒写,值域越界(北交所 30cm 会触发)只 warning 不卡 capture;snapshot_doctor 作收益对比前强制门。这是离线收益路线(C3 的数据地基)的硬前置,届时升 P0。

**D2(P2)** derive_zt_pool 从原价 OHLCV 重建历史池(解锁周期级长窗——蓝图 episode=完整轮回在 30 日数据下根本不可检验,这是选 Continual Harness 路线的全部理由);未核实:OHLCV 多源 fallback(当前最硬的外部阻塞)、每日前向 capture 调度。

### E. 工程架构

**E1(P0,M)LLM record/replay 缓存。** CachedLLMClient 实现 LLMClient Protocol,content-addressed key=sha256(model+temperature+system+user)——提示是 H 状态+当日数据的纯函数(已逐文件核实无 now/random),key 天然区分 H 演化每个状态,弃 seq 盒带方案(臂顺序脆);read_only 模式 miss 即 raise 决不静默回落 live;temp=0 录一次真实 smoke 固化为 tests/fixtures/golden_run,全链路离线回归断言 ComparisonReport 逐位复现;提示版本指纹防误用旧响应。影响:一次付费无限次确定性复跑;"verdict 翻转无法归因"类成本彻底消除;改 prompt/parse/credit 的验证从"花钱+人眼"降为一次 pytest。

**E2(P1,M)确定性规则策略中层(修正版)。** Skill 增 GateSpec(强类型,裸 dict 会被 typo 静默吞掉)机器可读门,仅测试种子填充;HarnessRulePolicy 真读 H 零 LLM;InnerLoop 加 agent_factory 注入并经 _rebind 重建(固定实例会在熔断回滚后静默读废弃 H——manager.py:25-30 已警告此坑);断言按 horizon 滞后对齐("退役次日起不再选 X",in-flight 候选仍归因是既有正确语义)。补上测试金字塔最大断层:"编辑→决策改变→分数改变"首次进 CI,顺带是 A1 的验收器。

**E3(P1,L)RunJournal+断点续跑(修正版)。** append-only JSONL 逐事件落盘+logging;resume 改"双 checkpoint+credit 重放"——原案"重放 refine 编辑"不可实现(EditRecord payload 对 write_skill 不含完整内容),refine 后补一次 post-refine checkpoint,resume 时 load 之+按 journal 重放其后 credit_applied;增量持久化走 journal 目录每臂独立文件,不动 frozen 的 ComparisonReport schema;smoke 的 SnapshotStore 从 tempfile 移到 run 专属目录(现状崩溃连 checkpoint 都在丢弃目录)。E1 落地后经济论据减弱,价值收敛为可观测性+长 episode 工程性。

**E4(P2)** DayStream/Arm 多臂共驱(臂数真实增长时再上,近期均有低成本替代);HarnessManager epoch 句柄+EditLog WAL+rollback 审计记录。

## 5. 实施顺序

```
第一波(全并行、纯离线、零数据依赖):
  E1 LLM缓存 ─┐
  C2 优势化   ─┼─→ C1 统计裁决(检验建在 advantage 口径上,C2 先合或同批)
  A3 证据重构 ─┘(S,独立夹带)

第二波(自进化杠杆):
  A1 孵化+注入(晋升门先用 expectancy,C2 落地后切 advantage)
  E2 规则策略中层(与 A1 同批——互为验收器)
  C4 Hcredit(依赖 C1 配对函数)

第三波(闭环与防线):
  A2 EditGate(依赖 C1 verdict + E1 降成本)
  B2 熔断重设计(依赖 C1/C2)
  C5 预注册(下次真实跑之前必须就位)

数据线(与上全程并行,受 akshare off-peak 制约):
  D1 PIT完整性 → 建库 → C3 真实数据接通(C3 代码离线先行)→ B1 相位分类器(快照窗校准)

第四波:A4 赢家挖掘 → A5 锦标赛(依赖 A2+C1+快照+ReturnScorer);E3 RunJournal
```

**下一个最值得做的 3 件事:** ① **E1 LLM 缓存+黄金 run**——一次付费换永久确定性回归层,所有后续改动的验证成本归零,且是 A2/A5 的成本前提;② **C2+C1 优势化+统计裁决**——先把尺修直:β剥掉、verdict 可证伪,否则后面每一条改进做完都无法证明有效;③ **A1 孵化→晋升+检索注入**——唯一直接打在"编辑不改变决策"结构病灶上的改动,配 E2 即可在 CI 里验收。这三件互不阻塞,可三线并行。

## 6. 附录:考虑过但否决的方案

对抗核实 13 项 P0/P1 提案,**0 项整案否决**(4 项 valid、9 项修正后存活),但以下子设计在核实中被砍,记录否决理由防止回潮:

- **EditGate 以同窗反事实回放作主验收**:in-sample 选择——窗内砍掉 0 分候选必使回放均分非负,闸会放行并奖励恰被 1b-3d 治住的小样本过度收缩;危害在窗外前向。改为前向影子主通道,后向降级冒烟闸。
- **"同窗回放 Δ≥0 即可放宽 min_retire_samples"**:同上,有把"无害"修回"有害"的风险,只有前向影子证据可作放宽依据。
- **LLM 缓存按 seq 序盒带做主键**:臂执行顺序/分支稍变即失配,四臂需手工分带;改 content-addressed key,盒带价值保留在黄金 run 资产。
- **OHLCV 跨窗增量 merge**:qfq 前复权基准随抓取时点漂移,merge 拼接两个基准产生跨缝错误收益——以完整性为名引入新静默污染;改整段重抓原子重写。
- **"aggregate_runs 可程序化复跑 §9 池化结论"**:不可兑现——历史 run 从未入 RunStore 且窗口已掉出 akshare 30 日限;承诺已从 C1 删除。
- **ExperimentConfig 作 compare_harnesses 唯一参数入口**:内部构造 DeepSeekClient 会破坏 294 个依赖工厂注入的离线测试;改声明式配置+保留注入。
- **MissedWinner 不过滤可买性**:会把一字/秒板延续票挖成"错过的赢家",将已登记的 fill-feasibility 债务从"收益高估"放大成"技能库系统性学歪";必须标 fill_doubt。
- **熔断主路径裸用 mean<−λ·std**:temp=0 下配对差恒 0 是常态,std≈0 时微小负差即误触发;必须加 ε_abs 与方向一致性双门。