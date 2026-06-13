# Phase-1b-3e-2:收益打分接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把片 1 的前向收益接进打分链路——可插拔 `Scorer`(`PoolScorer` 默认/回归安全 + `ReturnScorer`)注入 `WalkForwardEval`/`InnerLoop`/`compare_harnesses`,`apply_credit` 改用 `sc.score`,使配 `ReturnScorer` 时 `mean_score`/`SkillStats.expectancy`=平均收益(更细信号到 Refiner 与对比),`outcome` 仍是池成员制类别。

**Architecture:** 把"每候选去重打分"从 walk/InnerLoop 抽成 `Scorer.score_step(decision, mem, entry_day, exit_day, source)`,两循环共用;默认 `PoolScorer`(= 现行为)保回归;`ReturnScorer` 用 `ReturnOracle` 算收益、收益 None 丢弃候选。`apply_credit` 用 `sc.score`(池下 `sc.score==SCORE[outcome]` 故零回归)。

**Tech Stack:** Python · pandas · pytest(全离线:`FakeSource`(含 OHLCV)+ MockLLM,不触网)。

**分支:** `phase-1b3e2-return-scoring`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-08-phase1b3e2-return-scoring-design.md`。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **254 passed**。

**Bundle 分组:** A=Task 1-2(scorer + credit)· B=Task 3-4(walk + inner_loop)· C=Task 5-6(compare + smoke)。

---

## Bundle A

### Task 1: `eval/scorer.py`(Scorer 协议 + PoolScorer + ReturnScorer)

**Files:**
- Create: `youzi/eval/scorer.py`
- Test: `tests/test_scorer.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_scorer.py
from datetime import date

import pandas as pd

from youzi.eval.scorer import PoolScorer, ReturnScorer
from youzi.eval.oracle import DayMembership
from youzi.eval.decision import DecisionPackage, Candidate
from tests.conftest import FakeSource


def _decision(*codes):
    return DecisionPackage(date=date(2026, 6, 1),
                           candidates=[Candidate(code=c, name=c, pattern="p") for c in codes])


def _ohlcv(rows):
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def test_pool_scorer_matches_pool_membership():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset({"B"}))
    out = PoolScorer().score_step(_decision("A", "B", "A"), mem,
                                  date(2026, 6, 2), date(2026, 6, 2), None)
    assert set(out) == {"A", "B"}                       # 去重
    assert out["A"].outcome == "continued" and out["A"].score == 1.0
    assert out["B"].outcome == "nuked" and out["B"].score == -1.0


def test_return_scorer_uses_return_and_drops_missing():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset())
    # A 有 OHLCV:entry open@6/2=10 → exit close@6/3=12 → +0.20;B 无 OHLCV → 丢弃
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100),
                 (date(2026, 6, 3), 10.6, 12.5, 10, 12.0, 200)])
    src = FakeSource({}, [], ohlcv={"A": df})
    out = ReturnScorer().score_step(_decision("A", "B"), mem,
                                    date(2026, 6, 2), date(2026, 6, 3), src)
    assert set(out) == {"A"}                             # B 缺收益被丢弃
    assert out["A"].outcome == "continued"               # outcome 仍池类别
    assert out["A"].score == 0.20                        # score = 收益
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.eval.scorer`)

- [ ] **Step 3: 实现 `youzi/eval/scorer.py`**

```python
# youzi/eval/scorer.py
from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from youzi.eval.decision import DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.oracle import SCORE, DayMembership, outcome
from youzi.eval.return_oracle import ReturnOracle


class Scorer(Protocol):
    """把一步成熟决策打分成 code→ScoredCandidate(去重;可丢弃缺数候选)。"""
    def score_step(self, decision: DecisionPackage, mem: DayMembership,
                   entry_day: Date, exit_day: Date, source) -> dict[str, ScoredCandidate]: ...


class PoolScorer:
    """默认:池成员制 outcome + SCORE[outcome](= 现行为)。entry/exit/source 忽略。"""

    def score_step(self, decision: DecisionPackage, mem: DayMembership,
                   entry_day: Date, exit_day: Date, source) -> dict[str, ScoredCandidate]:
        seen: set[str] = set()
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.code in seen:
                continue
            seen.add(c.code)
            oc = outcome(c.code, mem)
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=SCORE[oc])
        return out


class ReturnScorer:
    """收益打分:outcome 仍池成员制;score=前向收益;收益 None → 丢弃该候选。"""

    def score_step(self, decision: DecisionPackage, mem: DayMembership,
                   entry_day: Date, exit_day: Date, source) -> dict[str, ScoredCandidate]:
        oracle = ReturnOracle(source)
        seen: set[str] = set()
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.code in seen:
                continue
            seen.add(c.code)
            ret = oracle.score(c.code, entry_day, exit_day)
            if ret is None:
                continue                                  # 丢弃缺收益候选
            oc = outcome(c.code, mem)
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=ret)
        return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_scorer.py -q`
Expected: PASS(2 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/eval/scorer.py tests/test_scorer.py
git commit -m "feat(eval): 可插拔 Scorer(PoolScorer 默认 + ReturnScorer 收益打分,缺收益丢弃)"
```

---

### Task 2: `apply_credit` 改用 `sc.score`

**Files:**
- Modify: `youzi/refine/credit.py:49-104`
- Test: `tests/test_credit.py`(追加回归+收益用例)

- [ ] **Step 1: 追加失败测试(到 `tests/test_credit.py`)**

```python
def test_apply_credit_uses_sc_score_for_expectancy():
    # 直接用 sc.score(收益)算 expectancy,而非 SCORE[outcome]
    from datetime import date
    from youzi.eval.trajectory import Trajectory, TrajectoryStep
    from youzi.eval.decision import DecisionPackage, Candidate
    from youzi.eval.metrics import ScoredCandidate
    from youzi.schemas.market import MarketState
    from datetime import datetime
    from youzi.refine.credit import apply_credit
    from tests.test_metatools import _harness

    h = _harness()                       # 技能 "a"(active),pattern 用 name_cn 解析
    mkt = MarketState(date=date(2026, 6, 1), max_board_height=3, limit_up_count=5,
                      blowup_count=1, blowup_rate=0.2, limit_down_count=0, echelon=[],
                      money_effect_raw=1.0, sentiment_raw=0.0, as_of=datetime(2026, 6, 1, 15))
    # outcome=continued(win)但 score=收益 +0.08(非 SCORE=1.0)
    sc = ScoredCandidate(decision_date=date(2026, 6, 1), code="X", pattern="甲",
                         outcome="continued", score=0.08)
    step = TrajectoryStep(date=date(2026, 6, 1), market=mkt,
                          decision=DecisionPackage(date=date(2026, 6, 1),
                                                   candidates=[Candidate(code="X", pattern="甲")]),
                          scored=True, outcomes={"X": sc})
    rep = apply_credit(Trajectory(steps=[step], horizon=1), h)
    assert h.skills.get("a").stats.expectancy == 0.08     # 用 sc.score,不是 1.0
    assert h.skills.get("a").stats.wins == 1              # win 仍由 outcome=continued
    assert rep.per_skill["a"].expectancy == 0.08
```

> 注:`_harness` 技能 "a" 的 `name_cn="甲"`;`pattern="甲"` 经 `resolve_skill` 的 name_cn 匹配命中。若不符,改用真实 `skill_id`/`name_cn`。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_credit.py::test_apply_credit_uses_sc_score_for_expectancy -q`
Expected: FAIL(expectancy==1.0,因现用 SCORE[outcome])

- [ ] **Step 3: 改 `credit.py`(第 49-104 行)**

`_classify`(第 49-51 行)→ 去掉 SCORE:

```python
def _classify(outcome: str) -> tuple[bool, bool]:
    """oracle outcome → (是否 win, 是否 nuked)。score 改由 ScoredCandidate.score 提供(支持收益 oracle)。"""
    return outcome == "continued", outcome == "nuked"
```

`_Acc.add`(第 64-73 行)→ 收 score 入参:

```python
    def add(self, oc: str, score: float) -> None:
        win, nuked = _classify(oc)
        self.n += 1
        self.score_sum += score
        if win:
            self.wins += 1
        else:
            self.losses += 1
        if nuked:
            self.nukes += 1
```

`apply_credit` 内(第 96、98-104 行)→ 用 `sc.score`:

```python
            if skill is None:
                unattr.add(sc.outcome, sc.score)          # 未匹配:进 unattributed
                continue
            win, nuked = _classify(sc.outcome)
            skill.stats.record(win, decay)
            m = skill.stats.expectancy if skill.stats.expectancy is not None else 0.0
            skill.stats.expectancy = m + (sc.score - m) / skill.stats.n   # 用 sc.score(支持收益)
            if nuked:
                skill.stats.nukes += 1
            per.setdefault(skill.skill_id, _Acc()).add(sc.outcome, sc.score)
```

> `from youzi.eval.oracle import SCORE` 在 credit.py 顶部若已不再使用,删除该 import(`_classify` 不再用 SCORE)。

- [ ] **Step 4: 跑测试确认通过 + 回归 credit/signatures/inner_loop**

Run: `.venv/bin/python -m pytest tests/test_credit.py tests/test_signatures.py tests/test_merge_credit.py tests/test_refine_integration.py tests/test_inner_loop.py -q`
Expected: PASS(新例 + 既有全绿;PoolScorer 下 `sc.score==SCORE[outcome]` 故回归值不变)

- [ ] **Step 5: 提交**

```bash
git add youzi/refine/credit.py tests/test_credit.py
git commit -m "feat(refine): apply_credit 用 sc.score 算 expectancy(oracle-agnostic,池下零回归)"
```

---

## Bundle B

### Task 3: `WalkForwardEval` 接 `scorer`

**Files:**
- Modify: `youzi/eval/walk_forward.py`
- Test: `tests/test_walk_forward_scorer.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_walk_forward_scorer.py
from datetime import date

import pandas as pd

from youzi.eval.walk_forward import WalkForwardEval
from youzi.eval.scorer import ReturnScorer
from youzi.eval.baselines import HighestBoardPolicy
from tests.conftest import FakeSource


def _src_with_ohlcv():
    """A 连续涨停(continued);带 A 的 OHLCV 使 ReturnScorer 可算收益。"""
    days = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    frames = {("zt", d): pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]}) for d in days}
    ohlcv = {"A": pd.DataFrame([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100),
                                (date(2026, 6, 3), 10.6, 12.5, 10, 12.0, 200)],
                               columns=["date", "open", "high", "low", "close", "volume"])}
    return FakeSource(frames, days, ohlcv=ohlcv)


def test_default_pool_scorer_unchanged():
    # 默认 PoolScorer:mean_score = SCORE 均值(continued=1.0)
    rep = WalkForwardEval(_src_with_ohlcv(), date(2026, 6, 1), date(2026, 6, 3),
                          horizon=1).run(HighestBoardPolicy())
    assert rep.mean_score == 1.0 and rep.hit_rate == 1.0


def test_return_scorer_mean_is_avg_return():
    # ReturnScorer + horizon=1:决策 6/1 → entry 6/2 open=10、exit 6/2 close=10.5 → +0.05
    rep = WalkForwardEval(_src_with_ohlcv(), date(2026, 6, 1), date(2026, 6, 3),
                          horizon=1, scorer=ReturnScorer()).run(HighestBoardPolicy())
    # 6/1 决策(A)entry=exit=6/2:(10.5−10)/10=+0.05;6/2 决策 entry=exit=6/3:(12−10.6)/10.6≈+0.132
    assert rep.n_candidates == 2
    assert abs(rep.mean_score - (0.05 + (12.0 - 10.6) / 10.6) / 2) < 1e-9
    assert rep.hit_rate == 1.0          # outcome 仍池类别(continued)
```

> 注:horizon=1 时 entry_day=days_seen[j+1]、exit_day=days_seen[j+1](同日),即 entry open→同日 close(日内)。N=2 由调用方设 horizon=2。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_walk_forward_scorer.py -q`
Expected: FAIL(`WalkForwardEval.__init__` 不接受 `scorer`)

- [ ] **Step 3: 改 `walk_forward.py`**

顶部 import 加:`from youzi.eval.scorer import PoolScorer`。

`__init__`(现 `def __init__(self, source, start, end, horizon=1)`)加 `scorer`:

```python
    def __init__(self, source, start: Date, end: Date, horizon: int = 1, scorer=None) -> None:
        if horizon < 1:
            raise ValueError(f"horizon 必须 >=1, got {horizon}")
        self._source = source
        self._start = start
        self._end = end
        self._horizon = horizon
        self._scorer = scorer or PoolScorer()
```

`walk()` 的打分块——把"决策 j 成熟"分支里**构造 outcomes 的内层 for 循环**整体替换为调 `score_step`。即把

```python
                    dp = drafts[j]["decision"]
                    seen: set[str] = set()
                    outcomes: dict[str, ScoredCandidate] = {}
                    for c in dp.candidates:
                        if c.code in seen:
                            continue
                        seen.add(c.code)
                        oc = outcome(c.code, mem)
                        outcomes[c.code] = ScoredCandidate(
                            decision_date=dp.date, code=c.code, pattern=c.pattern,
                            outcome=oc, score=SCORE[oc])
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
```

替换为:

```python
                    outcomes = self._scorer.score_step(
                        drafts[j]["decision"], mem,
                        days_seen[j + 1], days_seen[j + self._horizon], engine.guarded_source)
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
```

> 替换后 `walk_forward.py` 不再直接用 `SCORE`/`outcome`/`ScoredCandidate` 构造(scorer 内做);若顶部 `from youzi.eval.oracle import SCORE, PoolRecord, outcome` 的 `SCORE`/`outcome` 与 `ScoredCandidate` import 变为仅 `report_from_trajectory`/类型用途未用,删除未用项(`PoolRecord` 仍用,保留;`report_from_trajectory` 用 `ScoredCandidate` 注解则保留 `ScoredCandidate`)。**保留所有仍被引用的 import**。

- [ ] **Step 4: 跑测试确认通过 + 回归 walk 等价性**

Run: `.venv/bin/python -m pytest tests/test_walk_forward_scorer.py tests/test_walk_forward.py tests/test_walk_forward_trajectory.py -q`
Expected: PASS(新 2 例 + 既有 walk 等价性全绿)

- [ ] **Step 5: 提交**

```bash
git add youzi/eval/walk_forward.py tests/test_walk_forward_scorer.py
git commit -m "feat(eval): WalkForwardEval 接 scorer(默认 PoolScorer,可传 ReturnScorer)"
```

---

### Task 4: `InnerLoop` 接 `scorer`

**Files:**
- Modify: `youzi/loop/inner_loop.py`
- Test: `tests/test_inner_loop.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
def test_inner_loop_accepts_return_scorer(tmp_path):
    from youzi.eval.scorer import ReturnScorer
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame({"code": ["W"], "name": ["赢家"], "boards": [2]}) for d in days}
    ohlcv = {"W": pd.DataFrame([(date(2024, 6, 27), 10.0, 11, 9, 10.5, 100),
                                (date(2024, 6, 28), 10.6, 12, 10, 11.0, 200)],
                               columns=["date", "open", "high", "low", "close", "volume"])}
    src = FakeSource(frames, days, ohlcv=ohlcv)
    mgr = _mgr(tmp_path)
    loop = InnerLoop(mgr, src, days[0], days[-1], MockLLMClient(_decision("W")),
                     MockLLMClient('{"ops": []}'),
                     config=LoopConfig(horizon=1, breaker_min_samples=10_000),
                     scorer=ReturnScorer())
    rep = loop.run()
    # 决策 6/26 → entry=exit=6/27:(10.5−10)/10=+0.05;score 为收益
    sc = rep.trajectory.scored_steps()[0].outcomes["W"]
    assert sc.outcome == "continued" and abs(sc.score - 0.05) < 1e-9
```

> 复用 `tests/test_inner_loop.py` 既有的 `_mgr`、`_decision`、`InnerLoop`、`LoopConfig`、`MockLLMClient`、`FakeSource` import。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py::test_inner_loop_accepts_return_scorer -q`
Expected: FAIL(`InnerLoop.__init__` 不接受 `scorer`)

- [ ] **Step 3: 改 `inner_loop.py`**

顶部 import 加:`from youzi.eval.scorer import PoolScorer`。

`InnerLoop.__init__` 末尾加 `scorer` 入参并存:把签名加 `scorer=None`,在 `self._refiner_cfg = ...` 之后加 `self._scorer = scorer or PoolScorer()`(在 `self._rebind()` **之前**)。

`run()` 打分块(现 inner_loop.py:128-136 的内层 for)整体替换:把

```python
                    dp = drafts[j]["decision"]
                    seen: set[str] = set()
                    outcomes: dict[str, ScoredCandidate] = {}
                    for c in dp.candidates:
                        if c.code in seen:
                            continue
                        seen.add(c.code)
                        oc = outcome(c.code, mem)
                        outcomes[c.code] = ScoredCandidate(decision_date=dp.date, code=c.code,
                                                           pattern=c.pattern, outcome=oc, score=SCORE[oc])
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
```

替换为:

```python
                    outcomes = self._scorer.score_step(
                        drafts[j]["decision"], mem,
                        days_seen[j + 1], days_seen[j + cfg.horizon], engine.guarded_source)
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
```

> 替换后 inner_loop.py 不再直接构造 `ScoredCandidate`/用 `SCORE`/`outcome`;删除变为未用的 import(若 `ScoredCandidate`/`SCORE`/`outcome` 别处未再用)。**保留仍被引用的**(如 `apply_credit`、`Trajectory`、`TrajectoryStep`)。

- [ ] **Step 4: 跑测试确认通过 + 回归 inner_loop**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py tests/test_inner_loop_real_seeds.py -q`
Expected: PASS(新例 + 既有全绿,默认 PoolScorer 行为不变)

- [ ] **Step 5: 提交**

```bash
git add youzi/loop/inner_loop.py tests/test_inner_loop.py
git commit -m "feat(loop): InnerLoop 接 scorer(默认 PoolScorer,可传 ReturnScorer)"
```

---

## Bundle C

### Task 5: `compare_harnesses` 接 `scorer`

**Files:**
- Modify: `youzi/loop/compare.py`
- Test: `tests/test_compare.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
def test_compare_accepts_scorer(tmp_path):
    from youzi.eval.scorer import ReturnScorer
    rep, *_ = _compare(tmp_path, [_PICK_W], scorer=ReturnScorer())
    # 四路齐全;HCH 的 EvalReport 存在(收益打分)
    assert set(rep.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
```

> 需把 `tests/test_compare.py` 的 `_compare` 辅助加一个 `scorer=None` 入参并透传给 `compare_harnesses`;`_w_src()` 改为带 W 的 OHLCV(否则 ReturnScorer 全丢弃→无候选)。在 `_w_src` 里加 `ohlcv={"W": <两日 OHLCV df>}`,W 每日涨停;OHLCV 覆盖窗口内交易日。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_compare.py::test_compare_accepts_scorer -q`
Expected: FAIL(`compare_harnesses` 不接受 `scorer`)

- [ ] **Step 3: 改 `compare.py`**

`compare_harnesses` 签名加 `scorer=None`;HCH 的 `InnerLoop(...)` 传 `scorer=scorer`;Hexpert/Hmin 的 `WalkForwardEval(source, start, end, horizon=cfg.horizon)` 改为 `WalkForwardEval(source, start, end, horizon=cfg.horizon, scorer=scorer)`。(scorer=None 时各自默认 PoolScorer,行为不变。)

```python
def compare_harnesses(
    harness_factory, source, start, end, *,
    agent_llm_factory, refiner_llm_factory, store_factory,
    loop_config=None, refiner_config=None, scorer=None,
) -> ComparisonReport:
    cfg = loop_config or LoopConfig()
    mgr = HarnessManager(harness_factory(), store_factory())
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(),
                     refiner_llm_factory(), cfg, refiner_config, scorer=scorer)
    ...
    wf = WalkForwardEval(source, start, end, horizon=cfg.horizon, scorer=scorer)
    ...
```

> `InnerLoop` 的 scorer 是位置在 refiner_config 之后的关键字参(Task 4 已加 `scorer=None`),此处 `scorer=scorer` 关键字传。

- [ ] **Step 4: 跑测试确认通过 + 回归 compare**

Run: `.venv/bin/python -m pytest tests/test_compare.py tests/test_compare_real_seeds.py -q`
Expected: PASS(新例 + 既有全绿,默认 PoolScorer 不变)

- [ ] **Step 5: 提交**

```bash
git add youzi/loop/compare.py tests/test_compare.py
git commit -m "feat(loop): compare_harnesses 接 scorer(四路同 scorer,收益对比)"
```

---

### Task 6: `smoke_compare.py` 加 `--scorer`

**Files:**
- Modify: `scripts/smoke_compare.py`

- [ ] **Step 1: 改 `main` + CLI(无离线测试;手动 smoke)**

`main` 签名加 `scorer_kind: str = "pool"`;构造 scorer 并传:

```python
def main(start_ymd, end_ymd, horizon=1, temperature=0.3, scorer_kind="pool"):
    ...
    from youzi.eval.scorer import PoolScorer, ReturnScorer
    scorer = ReturnScorer() if scorer_kind == "return" else PoolScorer()
    print(f"... scorer={scorer_kind} ...")     # 并入现有 print
    rep = compare_harnesses(
        lambda: load_seeds(seeds), src, start, end,
        agent_llm_factory=lambda: DeepSeekClient(temperature=temperature),
        refiner_llm_factory=lambda: DeepSeekClient(temperature=temperature),
        store_factory=lambda: SnapshotStore(Path(tmp)),
        loop_config=LoopConfig(horizon=horizon),
        scorer=scorer,
    )
```

CLI(`__main__`)加第 5 位参 scorer:

```python
    main(sys.argv[1], sys.argv[2],
         int(sys.argv[3]) if len(sys.argv) > 3 else 1,
         float(sys.argv[4]) if len(sys.argv) > 4 else 0.3,
         sys.argv[5] if len(sys.argv) > 5 else "pool")
```

并把表头"期望分"在 return 模式下读作"平均收益"(可在 print 注明,非必须)。

- [ ] **Step 2: 语法检查 + 全量回归**

Run: `.venv/bin/python -m py_compile scripts/smoke_compare.py && .venv/bin/python -m pytest -q`
Expected: `syntax ok`;全量 PASS(254 + 本阶段新增,目标 ≈262)

- [ ] **Step 3: 提交**

```bash
git add scripts/smoke_compare.py
git commit -m "feat(smoke): smoke_compare 加 --scorer pool|return(真实收益对比)"
```

---

## 收尾(Task 6 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`/`后续开发文档.md`(1b-3e-2 完成,收益打分全链路接通)+ memory。
- [ ] **(人工)** `DEEPSEEK_API_KEY=... python scripts/smoke_compare.py <start> <end> 2 0.0 return` 跑真实**收益**对比(horizon=2),记进 `docs/findings/`(更细信号是否让 HCH 产 alpha)。

**本阶段债务**:fill-feasibility(一字涨停次日买不进)、成本/滑点、OHLCV 历史范围、N 日池成员类别变体、regime 分层、1b-3c 影子地板、1c 协同学习。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage:** §4.1 Scorer/PoolScorer/ReturnScorer → Task 1 ✅;§4.2 apply_credit 用 sc.score → Task 2 ✅;§4.3 WalkForwardEval/InnerLoop 接 scorer → Task 3/4 ✅;§4.4 compare + smoke → Task 5/6 ✅;§6 防火墙(ReturnScorer 经 Guarded、entry=t+1/exit=t+N)→ Task 3/4 用 engine.guarded_source + days_seen[j+1]/[j+horizon] ✅;§7 测试(PoolScorer 等价/ReturnScorer 收益+丢弃/credit 回归+收益/walk·loop·compare 接 scorer)→ Task 1-5 全覆盖;§8 DoD + 全量回归 → Task 6 Step 2;§7 人工真实跑 → 收尾。

**2. Placeholder scan:** 无 TBD/TODO;每步完整代码 + 确切命令/预期。替换块给了 before→after 完整代码。

**3. Type consistency:** `Scorer.score_step(decision, mem, entry_day, exit_day, source)`、`PoolScorer`/`ReturnScorer`、`_classify(outcome)->(win,nuked)`、`_Acc.add(oc, score)`、`apply_credit` 用 `sc.score`、`WalkForwardEval(..., scorer=None)`/`InnerLoop(..., scorer=None)`/`compare_harnesses(..., scorer=None)` 跨 Task 一致;`entry_day=days_seen[j+1]`/`exit_day=days_seen[j+horizon]`、`engine.guarded_source` 与既有循环一致;复用 `ReturnOracle`/`forward_return`(片1)、`ScoredCandidate(decision_date/code/pattern/outcome/score)`、`DayMembership`、`outcome`/`SCORE`、`FakeSource(frames,calendar,ohlcv=)` 均与既有源一致。
