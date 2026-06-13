# Findings:首次真实数据自进化对比 —— HCH 持续退化于 frozen(论文 §6.9 复现)

> 日期:2026-06-06 · 数据:真实 akshare(A股)+ 真实 DeepSeek(`deepseek-chat`,temperature=0.3)· 工具:`scripts/smoke_compare.py`(`compare_harnesses`)
>
> **一句话**:系统第一次在真实数据上端到端自进化,**三个独立窗口一致显示 HCH(每日自精炼)跑输 Hexpert(冻结种子 H)**。这是论文《Continual Harness》§6.9 最重要的负面发现(bootstrap 自更新可退化到比 frozen 还差)在 A 股真实数据上的复现。introspection 看清了退化机制。

---

## 1. 实验设置

- `compare_harnesses` 四路同 source/区间/horizon=1/同 oracle(池成员制 continued/faded/nuked):
  - **HCH** = `InnerLoop` 自精炼内环(每日 act→延迟打分→在线信用→能力地板熔断→每日 refine,真实 DeepSeek 既驱动 agent 又驱动 Refiner)。
  - **Hexpert** = 冻结种子 H + 同款 agent,**无 Refiner**(H 全程不变)。
  - **Hmin_highest** = 无脑追最高连板;**Hmin_notrade** = 永远空仓。
- 每路独立 fresh 种子 H + 独立 DeepSeek client(`_MemoizedSource` 让四路共享完全相同的真实行情,公平性硬保证)。
- 三个窗口(均在 akshare 池数据可取的最近 ~30 交易日内):`2026-05-12~19`、`05-20~28`、`05-29~06-05`。

## 2. 结果:3/3 窗 HCH < Hexpert

| 窗口 | HCH exp | Hexpert exp | Δexp | HCH 命中率 | Hexpert 命中率 | HCH 被砸率 | Hexpert 被砸率 | verdict | HCH refine |
|---|---|---|---|---|---|---|---|---|---|
| 05-12~19 | +0.333 | +0.500 | **−0.167** | 0.667 | 0.750 | 0.333 | 0.250 | ❌ | 1 |
| 05-20~28 | +0.188 | +0.211 | **−0.023** | 0.312 | 0.368 | 0.125 | 0.158 | ❌ | 5 |
| 05-29~06-05 | +0.050 | +0.267 | **−0.217** | 0.250 | 0.333 | 0.200 | 0.067 | ❌ | 4 |

- **方向 3/3 一致**:HCH 期望分始终低于 Hexpert(Δ −0.02 ~ −0.22)。
- **样本小**(每窗 3~20 候选),**magnitude 是噪声量级,但方向一致性已超出单窗噪声**。
- 参考:Hmin_highest 在个别窗口(05-12~19 的 +1.0、单候选)因小样本偶然居首——同样别过度解读。

## 3. 退化机制(由 `hch_loop_report` introspection 看清)

读 HCH 每次 refine 的 applied 编辑(`smoke_compare` 现会打印),病因清晰:**Refiner 在极小样本上过度收缩(over-restriction)**。

1. **几乎每次 refine 都在"砍"**:基于 1-2 次 `faded` 就 `patch_skill` 加禁忌 / `retire_skill` 退役。例:
   - 05-20~28 到第 4 次 refine 已退役 `w2s_strong_stronger`、`relay_1to2`、`kht_emo_extreme_open_first_board` 三个核心技能 → HCH 后段可用工具锐减、越来越胆小 → 错过 Hexpert(满技能)抓到的 continued 赢家。
   - rationale 原话:"relay_2to3_w2s n=2 胜率0.00 … 暂时退休"、"w2s_weak_to_strong n=2 胜率0.00 … 退休"。
2. **把 `faded`(空耗,SCORE 0)当亏损(−1)惩罚**:faded 只是"没续上"、非真亏,但 Refiner 拿它当强证据退役/收紧 → 过度规避 → 漏掉 continued。
3. **n=2/n=4 就做结构性编辑**:典型小样本过拟合噪声;Refiner **无"结构性编辑最小样本门槛"**。
4. **能力地板熔断 3 窗全程未触发**:HCH 期望分始终 >0(只是 < Hexpert),自相对地板/绝对地板都没破 → **自相对地板抓不到"比 frozen 差"**。

## 4. 真实 DeepSeek 暴露的 meta-tool / 提示摩擦(被 rejected 的编辑)

- `update_memory(..., regime="…")` → `ValidationError: Lesson Object has no attribute 'regime'`:LLM 很自然想更新教训的 regime,但 `Lesson` 的 regime 只在 `from_seed` 创建时解析,`update_memory` 直接 setattr `regime` 不被允许。
- `update_memory` 漏 `lesson_id` → `KeyError: 'lesson_id'`(LLM 偶尔不带 id)。
- `process_memory` 跨 refine **重复同一 lesson_id** → 多次 `重复 lesson_id` 拒绝(提示未显式列出已有记忆,LLM 重复提同一条新教训)。

这些不影响正确性(拒绝管线如实挡下、不半应用),但浪费编辑额度、降低自精炼效率。

## 5. 价值与结论

- **正面**:论文两环自进化在 A 股真实数据上**第一次完整转起来**——真实取数→agent(live H)选股→oracle 打分→在线信用→真实 DeepSeek Refiner 改 H→次日生效,全程不崩、防火墙守住、对比机器输出可信。
- **关键结论**:**当前朴素的"每日 refine + 小样本即编辑"会让系统退化到比 frozen 还差**——这是预期中的、有价值的负面结果,恰恰证明能力地板/纪律机制不是可选项而是必需。
- **不是 tradeable 结论**:无成本/滑点、horizon=1 单日池成员 oracle、单次 LLM 采样、小样本;只说明"机制需要纪律",不说明"打法本身好坏"。

## 6. 由本结果驱动的行动方向(优先级)

1. **Refiner 纪律化(治本,最高优先)**:
   - 结构性编辑(`retire_skill`/加禁忌)加**最小样本门槛**(如 n≥K 才允许退役);
   - **`faded` 权重 < `nuked`**(faded=漏、nuked=亏,不应同等触发收缩);
   - 提示里**列出已有记忆**(避免重复 lesson_id)+ 修 `update_memory` 的 regime/lesson_id 摩擦(或提供"更新 regime"的合法路径)。
2. **1b-3c 影子 Hexpert 严格地板**(安全网):环内并行跑冻结 agent,HCH 滚动跌破 Hexpert margin 即熔断冻结——自相对地板抓不到的"比 frozen 差",影子地板能抓。
3. **多窗口/多 episode 聚合 + 统计显著性**:当前 3 窗是定性方向,需更多窗口 + 跨 regime 才能下定量结论(1b-3b 债务)。
4. **P0 `_RENAME`**:dt 池 `封单资金→seal_amount`(本对比不受影响,但补全)。

## 7. 复现命令

```bash
# 单窗口(需 DEEPSEEK_API_KEY + 网络 + akshare;窗口须在最近 ~30 交易日内)
DEEPSEEK_API_KEY=... python scripts/smoke_compare.py 20260529 20260605 1
```
输出含四路对比表 + `HCH−Hexpert` delta + verdict + **HCH 每次 refine 改了什么**(applied/rejected 明细)。

---

## 8. 复测(2026-06-07,post-1b-3d Refiner 纪律化)

1b-3d 落地后(退役证据门 n≥5 + faded≠nuked 提示纪律),**同三窗复跑**:

| 窗口 | 改前 Δexp / verdict | 改后 Δexp / verdict |
|---|---|---|
| 05-29~06-05 | −0.217 ❌ | **+0.333 ✅**(HCH +0.333,被砸率 0%) |
| 05-20~05-28 | −0.023 ❌ | −0.033 ❌ |
| 05-12~05-19 | −0.167 ❌ | −0.167 ❌ |

**0/3 胜 → 1/3 胜。** 但 **verdict 被 LLM 重采样污染**:Hexpert(冻结、无代码改动)窗口 1 期望分 +0.267→+0.000 纯属随机,故 verdict 翻转**不能干净归因于 1b-3d**。

**真正的硬证据(噪声小)= 退役门改变了行为**:
- **改前**:HCH 大量小样本退役(`retire relay_2to3_w2s` n=2、`w2s_weak_to_strong` n=2、`w2s_strong_stronger` n=4、`relay_1to2` n=2 …),技能被逐个砍掉 → 后段胆小、漏赢家。
- **改后(三窗)**:applied 里**几乎无 `retire_skill`**——Refiner 改用 `patch_skill`(加禁忌)+ `rewrite_doctrine` + `process/demote_memory`,**技能库不再流失**。(唯一一条 retire 因幻觉技能名被 KeyError 拒,非样本门。)说明**提示纪律把行为上移到了"少而精地 patch",硬门作 backstop。**

**结论(诚实分级)**:
- **机制层(高置信)**:1b-3d **确实治住了退化根因**——HCH 不再小样本退役,改温和 patch/doctrine 调整,保住技能库。设计意图直接兑现,噪声小。
- **结果层(噪声大)**:verdict 0/3→1/3、窗口 1 强翻正,**方向乐观但非定论**(3 窗小样本 + LLM 重采样混淆)。定量证明"HCH ≥ Hexpert"需**多窗口/多 episode 聚合**(+ 控温/多次重采样去噪)。

**残留 friction(债务,复测中仍见)**:`update_memory` 漏 `lesson_id`→KeyError、`process_memory` 重复 `lesson_id`→拒(LLM 跨 refine 重提同一新教训)。不影响正确性(干净拒绝),浪费编辑额度。

**下一步**:① 多窗口聚合 + 控噪(定量证明,见 §9);② friction 修复;③ 1b-3c 影子 Hexpert 严格地板(安全网);④ 1c 协同学习外环。

---

## 9. 多窗口聚合 + 控噪(2026-06-07,temp=0,post-1b-3d)

为去掉 LLM 重采样混淆,用 **temperature=0**(贪婪近确定性)跑 **5 个不重叠窗口**覆盖 akshare 可取的全部最近交易日,**池化所有候选**算聚合期望分。
- 窗口 04-30~05-08 因 **akshare 炸板池"只能取最近 30 个交易日"**(04-30 当日已掉出)崩溃丢弃(见债务);余 4 窗(3 有候选 + 1 全空仓)。

**池化结果(temp=0):**

| 路 | 池化候选数 | 池化期望分 |
|---|---|---|
| Hmin_notrade(空仓) | 0 | 0.000 |
| Hmin_highest(裸追高) | 27 | +0.185 |
| **Hexpert(种子专家,冻结)** | 32 | **+0.219** |
| **HCH(自精炼)** | 36 | **+0.222** |

逐窗(temp=0):05-11~15 两路全空仓(平);05-18~22 **HCH≡Hexpert 完全相同**(Δ=0);05-25~29 HCH −0.048;06-01~05 HCH +0.063 → **2 平 / 1 微负 / 1 微正**。

**结论(对比改进前 temp0.3 的 HCH 3/3 退化、Δ −0.02~−0.22):**
1. **1b-3d 治住了退化(高置信)**:去噪后 HCH 从"持续 < frozen(−0.2)"→ **与 frozen 打平**(池化 Δ≈0)。退役纪律止住了流血。
2. **自精炼目前"中性"非"增益"**:HCH **没跑赢** frozen,只是不再拖后腿。temp=0 下两窗 HCH 编辑**未改变 agent 选股**(Δ 精确=0)→ 短窗/horizon=1 下 patch/doctrine 微调很少翻转决策,自精炼边际作用小。
3. **专家打法有 alpha**:Hexpert/HCH(+0.22)> 裸追高(+0.185)> 空仓(0)。

**一句话**:**1b-3d 把自进化从"有害"修成"无害(与 frozen 持平);让它"有益(超过 frozen)"是下一个更难的前沿**(需编辑真正改善决策、更长 horizon、更强信号)。

**新增债务**:akshare 炸板池(`stock_zt_pool_zbgc_em`)**只覆盖最近 ~30 交易日**,超范围日**抛 ValueError 直接崩**(非优雅退化)——回测窗口受此硬约束;应在 `AkshareSource.zt_pool_blowup` 捕获"超范围"→ 返回空(或运行前校验窗口在范围内)。这也意味着**真正的历史回测需自建 PIT 数据(边跑边快照),不能依赖 akshare 拉历史池**(早已登记的 PIT 债务在此具象化)。

---

## 10. 收益打分真实跑:被 akshare 限流挡住(2026-06-08,1b-3e-2 后)

收益打分链路并入 main(片1 oracle + 片2 接入,262 测试绿)后,尝试真实跑 `smoke_compare --scorer return`(horizon=2、temp=0、3 窗)。**结果:被 akshare 限流挡住,未取得可用收益对比。**

**现象**:
- 跑前发现并修了**两个真 gap**(运行才暴露):① `smoke_compare._MemoizedSource` 漏代理 `daily_ohlcv`(1b-3b 时还没这方法)→ ReturnScorer 取 OHLCV 必崩;② `AkshareSource` 取数**全程无 retry**(只有 DeepSeekClient 有)→ 单次网络抖动崩整轮。补:`_MemoizedSource.daily_ohlcv` memoize 代理 + `_retry_ak` 指数退避(ValueError 如 30 日限制不重试)。
- 加 retry 后重跑:**窗口 1(05-12~19)跑完未崩,但四路全 0 候选**(同窗池成员制打分本有候选)——数据被**限流返空**(空池/空 OHLCV → 全 no-trade/被丢弃);**窗口 2、3 仍硬崩 `RemoteDisconnected`**(retry 4 次耗尽)。单发探针(`zt_pool` 单次)却正常。

**诊断(高置信)**:收益打分对**每个候选每个评分步**都要 `daily_ohlcv`,叠加池取数,**调用量远大于池成员制** → 把 akshare/eastmoney **打到限流**(先软限流返空、再硬断连)。retry 救瞬时抖动,救不了**持续限流**。**非代码 bug——是 live-akshare 逐候选取数的吞吐撞墙。**

**结论 / 这具象化了 PIT 债务**:**真实收益回测不能靠 live akshare 逐候选取数**。须做**数据治理**——窗口内一次性预取/快照所有需要的池 + OHLCV(PIT 存储),再**离线**对快照打分。这正是早登记的 PIT 债务,现有硬证据:**收益打分的吞吐需求让"边跑边 live 取数"不可行**。

**已验证仍成立**:收益打分**机器本身没问题**——265 离线测试(含真实种子收益打分端到端 + 变异校验)全绿,窗口 1 也**跑完未崩**(只是数据被限流)。挡路的是数据供给,不是逻辑。

**下一步候选**:① **PIT 数据治理**(预取/快照 + 离线打分)——解锁收益回测的真正前置;② 继续用**池成员制**(调用量小、能跑)做更多窗口聚合;③ 待 akshare 空闲时段小窗重试(治标)。

---

## 11. 1c-PIT 已完成,但建库被 akshare OHLCV 端点硬拒连挡住(2026-06-08)

§10 的 PIT 数据治理已实现并入 main(Phase-1c-PIT,277 测试绿,opus 终审 0 blocking):`PITStore`(扩展 OHLCV/calendar/原子写)+ `SnapshotSource`(离线读)+ `capture_window`(节流幂等续跑)+ `capture_window.py` + smoke `YOUZI_SNAPSHOT` 离线分支。**离线链路全验证**(端到端 capture→SnapshotSource→compare 测试 + 真实 zt 池形状往返✅)。

**尝试建库失败**:真实 OHLCV 探针 **0/5**——`stock_zh_a_hist`(eastmoney 端点)5 个 code 全 `RemoteDisconnected`(每个 ~8 次尝试全败),而 zt 池(另一端点)能取。即 **akshare OHLCV 端点此刻硬性拒连**(非间歇限流)→ 现在建库无意义(每个 OHLCV fetch 都失败,幂等续跑也 0% 推进)。**纯外部阻塞,非代码问题。**

**地基全齐,只差端点恢复**。等 akshare OHLCV 恢复(off-peak/改日)跑:
```
python scripts/capture_window.py <s> <e> snap          # 建库一次(幂等可续跑)
YOUZI_SNAPSHOT=snap DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <s> <e> 2 0.0 return  # 离线跑
```

**新债务:OHLCV 多源 fallback。** capture 只依赖单一 OHLCV 端点(eastmoney `stock_zh_a_hist`),它挂则全挂。`AkshareSource.daily_ohlcv` 应做**多源 fallback**(eastmoney→sina `stock_zh_a_daily`→tencent `stock_zh_a_hist_tx`,各自列归一),抗单端点故障——纯离线小切片,不依赖 akshare 当下可用即可开发。
