# Phase-1b-3d 设计:Refiner 纪律化(退役证据门 + faded≠nuked 提示纪律)

> 日期:2026-06-07 · 分支 `phase-1b3d-refiner-discipline`(待建)· 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans`。
>
> 先读:`docs/findings/2026-06-06-real-data-hch-vs-hexpert.md`(退化根因)· `PROJECT_STATE.md` · `后续开发文档.md` §2 · `docs/superpowers/specs/2026-06-06-phase1b2-...`(Refiner)。

---

## 0. 一句话

真实数据三窗一致显示 HCH(自精炼)退化于 frozen(`docs/findings/2026-06-06-...`),**根因 = Refiner 在 n=2~4 极小样本上 `retire_skill`**(拿 1-2 次 `faded` 空耗就退役技能,后段工具锐减、过度胆小、漏掉赢家)。**本 spec 治本:给退役加硬证据门(n≥K)+ K-pass 提示纪律(faded≠nuked、能 patch 别 retire)**。friction(update_memory 改 regime / 重复 lesson_id)= 债务,本 spec 不做。

## 1. 已锁定决策(brainstorming,用户确认)

1. **范围 = 退役证据门 + 提示纪律**(治退化根因);friction(`update_memory(regime=…)` ValidationError、重复 `lesson_id`)留债务。
2. **门口径 = n≥K(默认 K=5,可调)**;`faded`(空耗 score 0)vs `nuked`(真亏 −1)的区别走**提示框架**,不另设数值机制(纯 faded 但 n≥K 仍可退役——连续多次空耗也是证据)。
3. **硬门只加在 `retire_skill`**(最具破坏性、最易机械判定);patch 加 taboo 的过度收缩靠提示软压(无法机械判定"限制性 patch")= 债务。

## 2. 不变量(沿用 `后续开发文档.md` §2)

1. **观测 vs 编辑边界不变**:门只读 `skill.stats.n`(观测),不改 stats;1b-2 的写保护/状态钳制/regime 类型安全仍有效。
2. **拒绝管线一致**:门触发 → `RejectedEdit`(带原因),绝不半应用、绝不崩;与既有 immutable/转移/越权/缺 rationale 拒绝同管线。
3. **Refiner = 策略,MetaTools/registry = 机制**:证据门是 **Refiner 策略**(人通过 MetaTools 仍可随时退役)→ 落在 `Refiner._apply_op`,不动 `MetaTools`/`registry`。
4. **离线可测**:MockLLM + 构造 H,永不触网。

## 3. 模块布局

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/refine/refiner.py` | 改 | `RefinerConfig` 加 `min_retire_samples`;`_apply_op` 加 retire 证据门;`refine()` 把 `min_retire_samples` 传给提示构造 |
| `youzi/refine/refiner_prompt.py` | 改 | `build_refiner_system_prompt(h, pass_kind, min_retire_samples=5)`:K-pass 加纪律段 |
| `tests/test_refiner.py` | 加 | 退役门用例(n<K 拒、n≥K 应用、permanent 同门、config 校验) |
| `tests/test_refiner_prompt.py` | 加 | K-pass 含 "n≥K" + faded≠nuked 框架 + 注入的 K 值 |

## 4. 数据模型与接口(精确)

### 4.1 `refiner.py`:`RefinerConfig` 加字段

```python
class RefinerConfig(BaseModel):
    max_edits_per_pass: int = 5
    max_edits_per_refine: int = 12
    window: int = 10
    decay: float = 0.1
    min_retire_samples: int = Field(default=5, ge=1)   # 新增:retire_skill 需 skill.stats.n >= 此值,防小样本过度退役
```
> 注:既有 `RefinerConfig` 字段若无 `Field` 约束,保持原样;仅新增 `min_retire_samples` 带 `ge=1`。需 `from pydantic import Field`(若未导入则补)。

### 4.2 `refiner.py`:`_apply_op` 加退役证据门

在 `_apply_op` 的 **rationale 检查之后、`_dispatch` 之前**插入:

```python
        # 退役证据门(治真实数据退化根因:小样本过度退役)。只读 stats.n,不改 stats。
        if op.tool == "retire_skill":
            sk = self._h.skills.get(str(tid)) if tid else None
            if sk is not None and sk.stats.n < self._cfg.min_retire_samples:
                return False, RejectedEdit(
                    pass_kind=pk, tool=op.tool, target_id=tid,
                    reason=(f"证据不足:n={sk.stats.n}<min_retire_samples="
                            f"{self._cfg.min_retire_samples},不退役(faded 是空耗非亏损,样本不足别退役)"))
```
- `tid = _target_id(op.tool, op.args)` 已在 `_apply_op` 开头算好(retire 的 tid 即 skill_id)。
- 技能不存在(`sk is None`)→ **不在此拦**,交给 `_dispatch` 抛 `KeyError` → 既有捕获 → rejected(保持"幻觉 target"行为不变)。
- permanent retire 同样过门(permanent 更具破坏性,n<K 同样拒绝)。
- 门读 `self._h`(Refiner 持有的 live HarnessState)与 `self._cfg.min_retire_samples`。

### 4.3 `refiner_prompt.py`:K-pass 提示纪律

```python
def build_refiner_system_prompt(h: HarnessState, pass_kind: PassKind,
                                min_retire_samples: int = 5) -> str:
    ...
    elif pass_kind == "K":
        out.append("\n## 当前技能(含战绩):")
        for s in h.skills.all():
            st = s.stats
            perf = f" [n={st.n} nukes={st.nukes}]" if st.n > 0 else ""
            out.append(f"- {s.skill_id}({s.name_cn})[{s.type}/{s.status}]{perf}")
        out.append(
            f"\n## 收缩纪律(重要):结构性收缩(retire / 加 taboo)要克制——"
            f"**retire 需 n≥{min_retire_samples}**(样本不足会被拒);"
            f"**faded 是空耗(没续上,score 0)不是亏损**,别只因 1-2 次 faded 就退役/加禁忌;"
            f"**nuked(跌停/炸板)才是真亏**,优先据 nuke 收缩;能 patch 微调就别 retire。")
```
- `Refiner.refine()` 调用处改为:`build_refiner_system_prompt(self._h, pk, self._cfg.min_retire_samples)`。
- 参数带默认 `=5` → 既有 `test_refiner_prompt` 的 2-参调用不破。

## 5. 关键边界

- **门是 Refiner 策略**:只挡 LLM Refiner 的小样本退役;人经 `MetaTools.retire_skill` 不受影响。
- **只挡 retire,不挡 patch**:限制性 patch(加 taboo)的过度收缩无法机械判定 → 提示软压 + 登记债务。
- **faded≠nuked 不设数值机制**:n≥K 门已挡住"1-2 次就退";多次空耗(n≥K 纯 faded)仍可退役(连续不续板也是证据)。faded 的"别 panic"靠提示。

## 6. 防火墙论证(终审会查)

- 门只读 `skill.stats.n`(已实现 oracle 聚合的过去结果,≤ t−horizon),不取 source、不引入未来。
- 不改 stats(观测边界守住),不半应用(拒绝在 dispatch 前,H 未变、EditLog 未记)。

## 7. 测试(全离线,MockLLM + 构造 H)

- `test_refiner.py`(加):
  - **n<K 拒**:构造技能 `a`(`stats.n=2`,e.g. 2 次 faded),`_apply_op(retire_skill a)` → not ok、reason 含 "证据不足"/"min_retire_samples"、`a.status` 未变(仍 active)、`meta.log` 未记。
  - **n≥K 应用**:技能 `a` `stats.n=5`(真亏)→ `_apply_op(retire_skill a)` → ok、`a.status=="dormant"`。
  - **permanent 同门**:`retire_skill a permanent=True` 对 n<K → 仍拒。
  - **幻觉 target 仍 KeyError 拒**:`retire_skill 不存在` → rejected(reason 含 KeyError),证明门不误吞。
  - **refine() 级**:MockLLM 脚本 K-pass 退役一个 n<K 技能 → `RefineReport.rejected` 含之、H 未变。
  - **config 校验**:`RefinerConfig(min_retire_samples=0)` → ValidationError。
- `test_refiner_prompt.py`(加):K-pass 提示含 `n≥{min_retire_samples}`(注入值)、"faded"、"nuked"、"空耗" 等纪律词;非 K pass 不含收缩纪律段(或不强求)。
- 回归:既有 237 测试全绿;`build_refiner_system_prompt` 2-参调用仍可用(默认 K=5)。

## 8. 验收标准(DoD)

1. `min_retire_samples` 字段(ge=1);`_apply_op` 退役证据门(n<K 拒、n≥K 过、permanent 同门、幻觉 target 仍 KeyError)。
2. K-pass 提示含具体收缩纪律(n≥K + faded≠nuked + 能 patch 别 retire),注入真实 K 值。
3. 防火墙/观测边界不破;拒绝管线一致(不半应用、不崩)。
4. 新测试 + 全量回归绿;离线。
5. subagent-driven 两段评审 + opus 终审通过。
6. 文档:更新 `PROJECT_STATE.md`/`后续开发文档.md`(1b-3d 完成)与 memory。
7. **(可选,人工)改进后再跑真实三窗**对照:HCH 退役是否被纪律纠正、Δ(HCH−Hexpert) 是否改善(记进 findings)。

## 9. 显式 out-of-scope(债务 / 后续)

- **friction 修复**:`update_memory(regime=…)` 合法路径(重解析)、提示列已有记忆避免重复 `lesson_id`、`update_memory` 漏 `lesson_id` 的友好报错。
- **限制性 patch 的机械门**(加 taboo 的过度收缩)。
- **1b-3c 影子 Hexpert 严格地板**(安全网,自相对地板抓不到"比 frozen 差")。
- **faded/nuked 的数值化加权信用**(EWMA/regime 双衰减;六道闸)。
- **多窗口/regime 聚合 + 统计显著性**。
