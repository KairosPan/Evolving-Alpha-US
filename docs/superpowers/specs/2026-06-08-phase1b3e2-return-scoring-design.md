# Phase-1b-3e-2 设计:收益打分接入(可插拔 Scorer + apply_credit 用 sc.score,片 2/2)

> 日期:2026-06-08 · 分支 `phase-1b3e2-return-scoring`(待建)· 本文是 brainstorming 产出的设计冻结(spec),下一步交 `writing-plans`。
>
> 先读:`docs/superpowers/specs/2026-06-08-phase1b3e1-return-oracle-design.md`(片 1)· `docs/findings/2026-06-06-real-data-hch-vs-hexpert.md`(为何要更细信号)· `youzi/eval/{oracle,metrics,walk_forward}.py` · `youzi/refine/credit.py` · `youzi/loop/{inner_loop,compare}.py`。

---

## 0. 一句话

片 1 给了 `forward_return`/`ReturnOracle`(纯计算+取数)。**片 2 把收益接进打分链路**:定义可插拔 `Scorer`(`PoolScorer` 默认/回归安全 + `ReturnScorer`),接进 `WalkForwardEval`/`InnerLoop`/`compare_harnesses`;`apply_credit` 改用 `sc.score`(而非重算 `SCORE[outcome]`)使信用 oracle-agnostic。配 `ReturnScorer` 时 `mean_score`/`SkillStats.expectancy` = 平均收益(更细信号到 Refiner 与对比),`outcome` 仍是池成员制类别(喂签名/命中率/被砸率)。

## 1. 已锁定决策(brainstorming,用户确认)

1. **一个切片全做**(Scorer 抽象 + apply_credit + WalkForwardEval + InnerLoop + compare + smoke)。
2. **收益缺失(停牌/退市/无 OHLCV → `forward_return` None)→ 丢弃该候选**(不进 outcomes/EvalReport/credit)。
3. **`outcome` 保留池成员制**(continued/faded/nuked),`score` 变前向收益(配 ReturnScorer 时);`apply_credit` 改用 `sc.score`;`build_report` 不改(已用 `sc.score` 算 `mean_score`、用 outcome 算命中/被砸率)。
4. **默认 `PoolScorer`** → 既有 254 测试零回归。

## 2. 不变量(沿用 §2)

1. **未来函数防火墙**:`ReturnScorer` 在打分时刻(cursor=exit_day、as_of=exit_day)经 `engine.guarded_source` 取 OHLCV[entry..exit];`guard.check(exit_day)` 合法、越界 `LookaheadError`。决策日 t 不打分。`outcome`/`score` 仅聚合 ≤ t+N 已实现结果。
2. **观测 vs 编辑边界不变**:`apply_credit` 仍只写 `SkillStats`(观测);改的是它**用哪个数**算 expectancy(sc.score 而非 SCORE[outcome]),不动边界。
3. **回归安全**:`PoolScorer` 下 `sc.score == SCORE[sc.outcome]` → `apply_credit` 用 sc.score 等价于原 SCORE[outcome];`WalkForwardEval.run`/`walk` 默认 PoolScorer 行为不变。
4. **缺失诚实 None / 丢弃**:`ReturnScorer` 对 `forward_return` None 的候选**跳过**(不构造 ScoredCandidate)。
5. **离线可测**:`FakeSource`(含 OHLCV)+ MockLLM,永不触网。

## 3. 模块布局

| 文件 | 动作 | 内容 |
|---|---|---|
| `youzi/eval/scorer.py` | **新增** | `Scorer` 协议 · `PoolScorer`(默认)· `ReturnScorer` |
| `youzi/refine/credit.py` | 改 | `_classify`→`(win, nuked)`;`_Acc.add(oc, score)`;`apply_credit` 用 `sc.score`(移除 SCORE 重算) |
| `youzi/eval/walk_forward.py` | 改 | `WalkForwardEval.__init__(... scorer=None)`(None→PoolScorer);`walk()` 打分块调 `scorer.score_step` |
| `youzi/loop/inner_loop.py` | 改 | `InnerLoop.__init__(... scorer=None)`;`run()` 打分块调 `scorer.score_step` |
| `youzi/loop/compare.py` | 改 | `compare_harnesses(... scorer=None)` 透传给 InnerLoop + WalkForwardEval(四路同 scorer) |
| `scripts/smoke_compare.py` | 改 | `--scorer pool|return`(return→ReturnScorer + horizon=N) |
| `tests/test_scorer.py`、`test_credit.py`、`test_walk_forward*.py`、`test_inner_loop.py`、`test_compare.py` | 加/改 | scorer 注入 + 回归 + 收益打分,全离线 |

## 4. 数据模型与接口(精确)

### 4.1 `eval/scorer.py`

```python
from typing import Protocol
from datetime import date as Date

class Scorer(Protocol):
    def score_step(self, decision: DecisionPackage, mem: DayMembership,
                   entry_day: Date, exit_day: Date, source) -> dict[str, ScoredCandidate]:
        """对一步成熟决策打分:code→ScoredCandidate(去重;可丢弃缺数候选)。"""

class PoolScorer:
    """默认:池成员制 outcome + SCORE[outcome](= 现行为)。entry/exit/source 忽略。"""
    def score_step(self, decision, mem, entry_day, exit_day, source):
        seen, out = set(), {}
        for c in decision.candidates:
            if c.code in seen: continue
            seen.add(c.code)
            oc = outcome(c.code, mem)
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=SCORE[oc])
        return out

class ReturnScorer:
    """收益打分:outcome 仍池成员制;score=前向收益;收益 None → 丢弃该候选。"""
    def score_step(self, decision, mem, entry_day, exit_day, source):
        oracle = ReturnOracle(source)
        seen, out = set(), {}
        for c in decision.candidates:
            if c.code in seen: continue
            seen.add(c.code)
            ret = oracle.score(c.code, entry_day, exit_day)
            if ret is None: continue                     # 丢弃缺收益候选
            oc = outcome(c.code, mem)
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=ret)
        return out
```

### 4.2 `refine/credit.py`:`apply_credit` 用 `sc.score`

```python
def _classify(outcome: str) -> tuple[bool, bool]:
    return outcome == "continued", outcome == "nuked"     # 去掉 SCORE;win/nuked 仍由 outcome 类别

class _Acc:
    def add(self, oc: str, score: float) -> None:
        win, nuked = _classify(oc)
        self.n += 1; self.score_sum += score
        self.wins += int(win); self.losses += int(not win); self.nukes += int(nuked)

# apply_credit 内:
win, nuked = _classify(sc.outcome)
skill.stats.record(win, decay)
m = skill.stats.expectancy if skill.stats.expectancy is not None else 0.0
skill.stats.expectancy = m + (sc.score - m) / skill.stats.n   # 用 sc.score(非 SCORE[outcome])
if nuked: skill.stats.nukes += 1
per.setdefault(skill.skill_id, _Acc()).add(sc.outcome, sc.score)
# 未匹配:unattr.add(sc.outcome, sc.score)
```
- `build_report`/`merge_credit_reports`/`extract_signatures` **不用改**(已用 `sc.score`/不重算 SCORE)。
- credit.py 不再 import `SCORE`(移到 scorer.py 用)。

### 4.3 打分循环接入(walk + InnerLoop 同形)

`WalkForwardEval.__init__(source, start, end, horizon=1, scorer=None)` → `self._scorer = scorer or PoolScorer()`。`walk()` 打分块:决策 j 成熟(idx≥j+horizon)时
```python
mem = record.get(days_seen[j + self._horizon])
entry_day = days_seen[j + 1]                 # 决策次日
exit_day = days_seen[j + self._horizon]      # t+N
outcomes = self._scorer.score_step(drafts[j]["decision"], mem, entry_day, exit_day, engine.guarded_source)
drafts[j]["outcomes"] = outcomes; drafts[j]["scored"] = True
```
`InnerLoop.__init__(..., scorer=None)` 同;`run()` 打分块同上(用 `self._scorer`、`engine.guarded_source`)。**用 ReturnScorer 时 horizon=N(=2)** → entry=t+1、exit=t+N。

### 4.4 `compare_harnesses` + smoke

`compare_harnesses(..., scorer=None)` → 四路(HCH InnerLoop / Hexpert·Hmin walk)**同一 scorer**(收益对比时全用 ReturnScorer,公平)。`smoke_compare.py` 加 `--scorer pool|return`(return → ReturnScorer + LoopConfig/WalkForwardEval horizon=N)。

## 5. 关键边界

- **outcome 与 score 解耦**:outcome=池类别(签名/命中率/被砸率),score=收益(配 ReturnScorer)。`apply_credit` expectancy 跟 score(收益),win/nuke 跟 outcome。
- **回归靠默认 PoolScorer + sc.score==SCORE[outcome]**;改 apply_credit 不改既有数值。
- **scorer 注入点**:WalkForwardEval/InnerLoop/compare 构造期;smoke CLI 选。

## 6. 防火墙论证(终审会查)

- ReturnScorer 打分时刻 as_of=exit_day=t+N;取 OHLCV[entry..exit] 全 ≤ exit_day=as_of → `guard.check` 通过;越界抛 `LookaheadError`。entry=t+1、exit=t+N 都 ≤ t+N。决策日 t 不调 score_step。
- 收益与 outcome 都是 ≤ t+N 已实现事后标签,永不回灌 ≤t 决策。

## 7. 测试(全离线,FakeSource+OHLCV / MockLLM)

- `test_scorer.py`:① `PoolScorer.score_step` 与现 walk 打分逐字段等价(outcome+SCORE);② `ReturnScorer.score_step` 用 FakeSource OHLCV → score=收益、outcome=池类别;收益 None 的候选被丢弃(不在返回 dict);去重。
- `test_credit.py`(回归+扩展):① 既有用例(score=SCORE[outcome])expectancy 不变;② 新:ScoredCandidate score=收益 → `SkillStats.expectancy`/`SkillCredit.expectancy` = 平均收益。
- `test_walk_forward*.py`:默认 PoolScorer `run()`/`walk()` 行为不变(等价性守);传 ReturnScorer + FakeSource OHLCV → mean_score=平均收益、缺收益候选不计入。
- `test_inner_loop.py`:默认 PoolScorer 行为不变;传 ReturnScorer 端到端跑通。
- `test_compare.py`:`compare_harnesses(..., scorer=ReturnScorer())` 四路同 scorer、mean_score=收益。
- 回归:既有 254 全绿。
- **人工(终审/收尾)**:`smoke_compare --scorer return` 真实跑收益对比,记 findings。

## 8. 验收标准(DoD)

1. `Scorer`/`PoolScorer`/`ReturnScorer` 实现;丢弃缺收益候选。
2. `apply_credit` 用 `sc.score`;PoolScorer 下零回归。
3. `WalkForwardEval`/`InnerLoop`/`compare_harnesses` 接 scorer(默认 PoolScorer);ReturnScorer 端到端 mean_score=收益。
4. 防火墙 §6 成立(ReturnScorer 经 Guarded 守界、不取未来)。
5. 新测试 + 全量回归绿;离线。
6. subagent-driven 两段评审 + opus 终审通过。
7. 文档:更新 PROJECT_STATE/后续开发文档/memory;**改进后真实跑收益对比记 findings**。

## 9. 显式 out-of-scope(债务)

- **fill-feasibility**(一字涨停次日开盘买不进——进场假设 t+1 open 成交);**成本/滑点**;OHLCV 历史范围(~30 交易日);**N 日池成员类别变体**;**regime 分层对比**;1b-3c 影子地板;1c 协同学习。
