# Phase-0d 评测脚手架 + 已实现未来 oracle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一套**与 Agent 无关**的评测脚手架:决策/候选 schema + **已实现未来 oracle**(用 pool-membership 类别结果)+ 多维指标 + walk-forward 评测协议 + 平凡基线策略。这是量化"任何选股策略好不好"的验收尺——现在先量平凡基线(floor),Phase-1 的 LLM Agent 落地后用同一把尺量它,与"已实现的未来"对照(交易版 Dijkstra)。

**Architecture:** 新 `youzi/eval/` 层,架在回放引擎(Phase-0a)+ 候选 universe(Phase-0c)之上。`DecisionPolicy` 协议(`decide(state, universe) -> DecisionPackage`)→ `RealizedFutureOracle`(类别结果 continued/faded/nuked + 分值)→ `WalkForwardEval`(**延迟打分** delayed scoring:决策在 t 用 ≤t 数据做出,挂起;游标自然推进到 t+horizon 后才用已录制的 pool 成员结果打分——保证未来函数防火墙不破)→ `metrics`(hit/nuke/expectancy + by_pattern)。纯 Python + pydantic,**全程离线可测**(多日 FakeSource fixtures)。

**Tech Stack:** Python 3.11+ · pydantic v2 · pytest。无新依赖。

**范围边界(v1):** oracle = **horizon 天后的 pool-membership 类别结果**(不依赖 `封单资金` 等待 smoke 核对的个股字段,故不被列名债务阻塞);horizon 默认 1(次日,超短核心)。**不做**:精确收益/OHLCV oracle(需日线数据扩展)、regime 分层(需 G_cycle 分类器,Phase-1)、成本/滑点 Pareto(后续)、LLM 策略(Phase-1)、Hexpert 静态 playbook 策略(需 LLM 或形式化触发器,Phase-1)。

**关键设计点:**
- **未来函数防火墙(延迟打分)**:策略 `decide(state_t, universe_t)` 只拿 ≤t 的快照(universe 经 GuardedSource 在游标 t 构建)。oracle 用 day[t+horizon] 的 pool 成员打分,而该天成员只在游标**自然推进到** t+horizon 时才录制(≤当时游标)——决策时不可见未来,打分时用的是"相对打分时点已是过去"的数据。**无泄漏**。
- **oracle = 已实现未来(交易版 Dijkstra)**:对每个被选 code,看其 horizon 天后在哪个池:涨停池→continued(+1)、跌停/炸板池→nuked(−1)、掉出→faded(0)。这是不依赖 LLM 的客观结果标签。
- **杀 falsy-trap**(沿用):容器/报告若有 `__len__` 一律配 `__bool__=True`。

---

## File Structure

```
youzi/eval/
  __init__.py
  decision.py        # Candidate + DecisionPackage(frozen) + DecisionPolicy(Protocol)
  oracle.py          # DayMembership + Outcome + PoolRecord + outcome() + SCORE
  metrics.py         # ScoredCandidate + PatternStat + EvalReport + build_report()
  baselines.py       # NoTradePolicy + HighestBoardPolicy
  walk_forward.py    # WalkForwardEval(回放+universe+延迟打分+指标)
tests/
  test_decision.py
  test_oracle.py
  test_metrics.py
  test_baselines.py
  test_walk_forward.py
  test_eval_integration.py    # 多日场景: continued/nuked/faded + no-lookahead
```

**全局类型契约:**
- `Candidate`(frozen):`code/name/pattern/reason/confidence`。`DecisionPackage`(frozen):`date/candidates/no_trade_reason`。`DecisionPolicy`:`decide(state: MarketState, universe: CandidateUniverse) -> DecisionPackage`。
- `DayMembership`(frozen):`limit_up/blowup/limit_down: frozenset[str]`。`PoolRecord`:`record(day, universe)`、`get(day) -> DayMembership|None`。`outcome(code, mem) -> Outcome`;`SCORE: dict[Outcome,float]`。
- `ScoredCandidate`:`decision_date/code/pattern/outcome/score`。`EvalReport`:`n_decisions/n_no_trade/n_candidates/hit_rate/nuke_rate/mean_score/by_pattern`。`build_report(scored, n_decisions, n_no_trade) -> EvalReport`。
- `WalkForwardEval(source, start, end, horizon=1)`:`run(policy) -> EvalReport`。

---

## Task 1: 决策/候选 schema + 策略协议

**Files:** Create `youzi/eval/__init__.py`, `youzi/eval/decision.py`; Test `tests/test_decision.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_decision.py
from datetime import date
from youzi.eval.decision import Candidate, DecisionPackage


def test_candidate_and_package_frozen():
    c = Candidate(code="000001", name="甲", pattern="highest_board", confidence=0.7)
    assert c.code == "000001" and c.confidence == 0.7
    pkg = DecisionPackage(date=date(2024, 6, 27), candidates=[c])
    assert pkg.candidates[0].code == "000001" and pkg.no_trade_reason == ""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.code = "x"                 # frozen


def test_no_trade_package():
    pkg = DecisionPackage(date=date(2024, 6, 27), no_trade_reason="退潮空仓")
    assert pkg.candidates == [] and pkg.no_trade_reason == "退潮空仓"
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd "/Volumes/kairos/引力场量化/youzi-自进化版" && source .venv/bin/activate && pytest tests/test_decision.py -v`
Expected: FAIL（`ModuleNotFoundError: youzi.eval.decision`）

- [ ] **Step 3: 实现 `youzi/eval/__init__.py` 与 `youzi/eval/decision.py`**

`youzi/eval/__init__.py`:
```python
"""评测脚手架:决策 schema / 已实现未来 oracle / 指标 / walk-forward。"""
```

`youzi/eval/decision.py`:
```python
from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class Candidate(BaseModel):
    """策略选出的一个候选标的(v1 评测只看选了哪些 code + 声明的模式)。"""
    model_config = ConfigDict(frozen=True)
    code: str
    name: str = ""
    pattern: str = ""              # 命中的模式/skill_id(策略声明,用于 by_pattern 归因)
    reason: str = ""
    confidence: float = 0.5


class DecisionPackage(BaseModel):
    """某交易日的决策包(co-pilot 输出的 v1 子集:候选池 + 不参与理由)。"""
    model_config = ConfigDict(frozen=True)
    date: Date
    candidates: list[Candidate] = Field(default_factory=list)
    no_trade_reason: str = ""


class DecisionPolicy(Protocol):
    """策略接口:读当日聚合状态 + 候选 universe,产决策包。

    LLM Agent(Phase-1)在构造期持有 HarnessState/LLM,decide 仍只吃 (state, universe)。
    """
    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage: ...
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_decision.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/eval/__init__.py youzi/eval/decision.py tests/test_decision.py
git commit -m "feat(eval): 决策/候选 schema + DecisionPolicy 协议"
```

---

## Task 2: 已实现未来 oracle(pool-membership 类别结果)

**Files:** Create `youzi/eval/oracle.py`; Test `tests/test_oracle.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_oracle.py
from datetime import date
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.eval.oracle import PoolRecord, DayMembership, outcome, SCORE


def _uni(limit_up, blowup, limit_down):
    stocks = [StockSnapshot(code=c, name=c, status="limit_up") for c in limit_up]
    stocks += [StockSnapshot(code=c, name=c, status="blowup") for c in blowup]
    stocks += [StockSnapshot(code=c, name=c, status="limit_down") for c in limit_down]
    return CandidateUniverse.from_stocks(stocks)


def test_pool_record_and_get():
    rec = PoolRecord()
    d = date(2024, 6, 28)
    rec.record(d, _uni(["A", "B"], ["C"], ["D"]))
    mem = rec.get(d)
    assert isinstance(mem, DayMembership)
    assert mem.limit_up == frozenset({"A", "B"}) and mem.limit_down == frozenset({"D"})
    assert rec.get(date(2024, 6, 29)) is None


def test_outcome_categories():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset({"C"}),
                        limit_down=frozenset({"D"}))
    assert outcome("A", mem) == "continued"      # 次日仍涨停
    assert outcome("D", mem) == "nuked"          # 次日跌停
    assert outcome("C", mem) == "nuked"          # 次日炸板
    assert outcome("Z", mem) == "faded"          # 掉出
    assert SCORE["continued"] == 1.0 and SCORE["nuked"] == -1.0 and SCORE["faded"] == 0.0
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_oracle.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/eval/oracle.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Literal

from youzi.universe.universe import CandidateUniverse

Outcome = Literal["continued", "faded", "nuked"]

SCORE: dict[str, float] = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


@dataclass(frozen=True)
class DayMembership:
    """某交易日三池的 code 成员(用于事后判定被选标的的结果)。"""
    limit_up: frozenset[str]
    blowup: frozenset[str]
    limit_down: frozenset[str]


class PoolRecord:
    """按交易日录制 pool 成员;walk-forward 每到一个游标录一天(只录 ≤ 游标)。"""

    def __init__(self) -> None:
        self._by_day: dict[Date, DayMembership] = {}

    def record(self, day: Date, universe: CandidateUniverse) -> None:
        self._by_day[day] = DayMembership(
            limit_up=frozenset(s.code for s in universe.by_status("limit_up")),
            blowup=frozenset(s.code for s in universe.by_status("blowup")),
            limit_down=frozenset(s.code for s in universe.by_status("limit_down")),
        )

    def get(self, day: Date) -> DayMembership | None:
        return self._by_day.get(day)


def outcome(code: str, mem: DayMembership) -> Outcome:
    """已实现未来类别:horizon 天后该 code 在哪个池。跌停/炸板优先判 nuked。"""
    if code in mem.limit_down or code in mem.blowup:
        return "nuked"
    if code in mem.limit_up:
        return "continued"
    return "faded"
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_oracle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/eval/oracle.py tests/test_oracle.py
git commit -m "feat(eval): 已实现未来 oracle(pool-membership 类别结果)+ PoolRecord"
```

---

## Task 3: 指标 + 报告

**Files:** Create `youzi/eval/metrics.py`; Test `tests/test_metrics.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_metrics.py
from datetime import date
from youzi.eval.metrics import ScoredCandidate, EvalReport, build_report


def _sc(code, pattern, oc, score):
    return ScoredCandidate(decision_date=date(2024, 6, 27), code=code,
                           pattern=pattern, outcome=oc, score=score)


def test_build_report_aggregates():
    scored = [
        _sc("A", "highest_board", "continued", 1.0),
        _sc("B", "highest_board", "nuked", -1.0),
        _sc("C", "w2s", "continued", 1.0),
        _sc("D", "w2s", "faded", 0.0),
    ]
    rep = build_report(scored, n_decisions=4, n_no_trade=1)
    assert rep.n_candidates == 4 and rep.n_decisions == 4 and rep.n_no_trade == 1
    assert rep.hit_rate == 0.5            # 2 continued / 4
    assert rep.nuke_rate == 0.25          # 1 nuked / 4
    assert abs(rep.mean_score - (1 - 1 + 1 + 0) / 4) < 1e-9   # 0.25
    hb = rep.by_pattern["highest_board"]
    assert hb.n == 2 and hb.hit_rate == 0.5 and hb.mean_score == 0.0
    w2s = rep.by_pattern["w2s"]
    assert w2s.n == 2 and w2s.hit_rate == 0.5 and w2s.mean_score == 0.5


def test_build_report_empty():
    rep = build_report([], n_decisions=3, n_no_trade=3)
    assert rep.n_candidates == 0 and rep.hit_rate == 0.0 and rep.mean_score == 0.0
    assert rep.by_pattern == {}
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_metrics.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/eval/metrics.py`**

```python
from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field


class ScoredCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_date: Date
    code: str
    pattern: str
    outcome: str
    score: float


class PatternStat(BaseModel):
    model_config = ConfigDict(frozen=True)
    n: int
    hit_rate: float
    mean_score: float


class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    n_decisions: int
    n_no_trade: int
    n_candidates: int
    hit_rate: float          # continued / n_candidates
    nuke_rate: float         # nuked / n_candidates
    mean_score: float        # 期望分(expectancy)
    by_pattern: dict[str, PatternStat] = Field(default_factory=dict)


def _agg(items: list[ScoredCandidate]) -> tuple[float, float, float]:
    """返回 (hit_rate, nuke_rate, mean_score);空列表全 0。"""
    n = len(items)
    if n == 0:
        return (0.0, 0.0, 0.0)
    hits = sum(1 for s in items if s.outcome == "continued")
    nukes = sum(1 for s in items if s.outcome == "nuked")
    mean = sum(s.score for s in items) / n
    return (hits / n, nukes / n, mean)


def build_report(scored: list[ScoredCandidate], n_decisions: int,
                 n_no_trade: int) -> EvalReport:
    hit, nuke, mean = _agg(scored)
    patterns: dict[str, list[ScoredCandidate]] = {}
    for s in scored:
        patterns.setdefault(s.pattern, []).append(s)
    by_pattern: dict[str, PatternStat] = {}
    for pat, items in patterns.items():
        h, _, m = _agg(items)
        by_pattern[pat] = PatternStat(n=len(items), hit_rate=h, mean_score=m)
    return EvalReport(n_decisions=n_decisions, n_no_trade=n_no_trade,
                      n_candidates=len(scored), hit_rate=hit, nuke_rate=nuke,
                      mean_score=mean, by_pattern=by_pattern)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/eval/metrics.py tests/test_metrics.py
git commit -m "feat(eval): EvalReport 指标(hit/nuke/expectancy + by_pattern)"
```

---

## Task 4: 平凡基线策略(Hmin-class floor)

**Files:** Create `youzi/eval/baselines.py`; Test `tests/test_baselines.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_baselines.py
from datetime import date, datetime
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.eval.baselines import NoTradePolicy, HighestBoardPolicy


def _state(d=date(2024, 6, 27)):
    return MarketState(date=d, max_board_height=7, limit_up_count=3, blowup_count=1,
                       blowup_rate=0.25, limit_down_count=1, echelon=[],
                       money_effect_raw=0.0, sentiment_raw=0.0, sentiment_norm=None,
                       as_of=datetime(2024, 6, 27, 15, 0))


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(code="A", name="龙", status="limit_up", boards=7),
        StockSnapshot(code="B", name="中", status="limit_up", boards=3),
        StockSnapshot(code="C", name="炸", status="blowup", boards=None),
    ])


def test_no_trade_policy():
    pkg = NoTradePolicy().decide(_state(), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_highest_board_policy_picks_top_boards():
    pkg = HighestBoardPolicy().decide(_state(), _uni())
    assert {c.code for c in pkg.candidates} == {"A"}          # 7板最高
    assert pkg.candidates[0].pattern == "highest_board"


def test_highest_board_policy_no_limit_up():
    empty = CandidateUniverse.from_stocks([
        StockSnapshot(code="C", name="炸", status="blowup")])
    pkg = HighestBoardPolicy().decide(_state(), empty)
    assert pkg.candidates == [] and pkg.no_trade_reason
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_baselines.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/eval/baselines.py`**

```python
from __future__ import annotations

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class NoTradePolicy:
    """floor 基线:永远空仓。"""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return DecisionPackage(date=state.date, no_trade_reason="baseline:no-trade")


class HighestBoardPolicy:
    """floor 基线:无脑追当日最高连板(超短最朴素的追高)。"""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        ups = universe.by_status("limit_up")
        if not ups:
            return DecisionPackage(date=state.date, no_trade_reason="无涨停")
        top = max((s.boards or 0) for s in ups)
        picks = [s for s in ups if (s.boards or 0) == top]
        cands = [Candidate(code=s.code, name=s.name, pattern="highest_board",
                           reason=f"{s.boards}板最高") for s in picks]
        return DecisionPackage(date=state.date, candidates=cands)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_baselines.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/eval/baselines.py tests/test_baselines.py
git commit -m "feat(eval): 平凡基线策略 NoTrade / HighestBoard(floor)"
```

---

## Task 5: `WalkForwardEval`(回放 + 延迟打分)

**Files:** Create `youzi/eval/walk_forward.py`; Test `tests/test_walk_forward.py`

> 核心:决策在游标 t 用 ≤t 快照做出并挂起;游标推进到 t+horizon 后,用那天**已录制**的 pool 成员打分。决策从不见未来。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_walk_forward.py
from datetime import date
import pandas as pd
from youzi.eval.walk_forward import WalkForwardEval
from youzi.eval.baselines import HighestBoardPolicy, NoTradePolicy
from tests.conftest import FakeSource


def _src():
    """3 天:A 连续涨停(continued);B day0 涨停 day1 跌停(nuked,但 HighestBoard 不选 B)。"""
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    frames = {}
    # day0: A(2板,最高), B(1板)
    frames[("zt", d0)] = pd.DataFrame({"code": ["A", "B"], "name": ["A", "B"], "boards": [2, 1]})
    frames[("blowup", d0)] = pd.DataFrame(); frames[("dt", d0)] = pd.DataFrame()
    # day1: A(3板,最高); B 跌停
    frames[("zt", d1)] = pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [3]})
    frames[("blowup", d1)] = pd.DataFrame()
    frames[("dt", d1)] = pd.DataFrame({"code": ["B"], "name": ["B"]})
    # day2: A(4板)
    frames[("zt", d2)] = pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [4]})
    frames[("blowup", d2)] = pd.DataFrame(); frames[("dt", d2)] = pd.DataFrame()
    return FakeSource(frames, [d0, d1, d2])


def test_walk_forward_scores_highest_board():
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(
        HighestBoardPolicy())
    # day0 选A(2板)→day1 A涨停=continued; day1 选A(3板)→day2 A涨停=continued; day2 选A 但无次日→不打分
    assert rep.n_decisions == 3
    assert rep.n_candidates == 2          # 只有 day0、day1 的决策被打分
    assert rep.hit_rate == 1.0 and rep.mean_score == 1.0
    assert rep.by_pattern["highest_board"].n == 2


def test_walk_forward_no_trade_yields_empty_report():
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(
        NoTradePolicy())
    assert rep.n_decisions == 3 and rep.n_no_trade == 3 and rep.n_candidates == 0
    assert rep.hit_rate == 0.0
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_walk_forward.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/eval/walk_forward.py`**

```python
from __future__ import annotations

from datetime import date as Date

from youzi.eval.decision import DecisionPolicy
from youzi.eval.metrics import EvalReport, ScoredCandidate, build_report
from youzi.eval.oracle import SCORE, PoolRecord, outcome
from youzi.replay.engine import ReplayEngine
from youzi.universe.universe import build_universe


class WalkForwardEval:
    """前向回放评测:策略每日决策(≤t 快照),horizon 天后用已实现 pool 成员延迟打分。"""

    def __init__(self, source, start: Date, end: Date, horizon: int = 1) -> None:
        if horizon < 1:
            raise ValueError(f"horizon 必须 >=1, got {horizon}")
        self._source = source
        self._start = start
        self._end = end
        self._horizon = horizon

    def run(self, policy: DecisionPolicy) -> EvalReport:
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        pending: list[tuple[int, object]] = []     # (decision_index, DecisionPackage)
        scored: list[ScoredCandidate] = []
        n_no_trade = 0
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()                                  # ≤t 聚合状态
            universe = build_universe(engine.guarded_source, cursor)  # ≤t 候选(经防火墙)
            record.record(cursor, universe)
            decision = policy.decide(state, universe)
            if not decision.candidates:
                n_no_trade += 1
            pending.append((idx, decision))
            # 延迟打分:决策 j 在 idx >= j+horizon 时,用 days_seen[j+horizon] 的已录成员打分
            still: list[tuple[int, object]] = []
            for j, dp in pending:
                if idx >= j + self._horizon:
                    mem = record.get(days_seen[j + self._horizon])
                    for c in dp.candidates:
                        oc = outcome(c.code, mem)
                        scored.append(ScoredCandidate(
                            decision_date=dp.date, code=c.code, pattern=c.pattern,
                            outcome=oc, score=SCORE[oc]))
                else:
                    still.append((j, dp))
            pending = still
            idx += 1
            if not engine.step():
                break
        # 余下不足 horizon 的决策不打分(丢弃,未来不足)
        return build_report(scored, n_decisions=idx, n_no_trade=n_no_trade)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_walk_forward.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/eval/walk_forward.py tests/test_walk_forward.py
git commit -m "feat(eval): WalkForwardEval 前向回放 + 延迟打分(防火墙保持)"
```

---

## Task 6: 集成 — continued/nuked/faded + 无前视审计

**Files:** Create `tests/test_eval_integration.py`

- [ ] **Step 1: 写集成测试(多日场景 + spy 策略验证无前视)**

```python
# tests/test_eval_integration.py
from datetime import date
import pandas as pd
from youzi.eval.walk_forward import WalkForwardEval
from youzi.eval.decision import Candidate, DecisionPackage
from tests.conftest import FakeSource


def _src():
    """day0 三标的: X(将continued), Y(将nuked), Z(将faded)。"""
    d0, d1 = date(2024, 6, 27), date(2024, 6, 28)
    frames = {
        ("zt", d0): pd.DataFrame({"code": ["X", "Y", "Z"], "name": ["X", "Y", "Z"], "boards": [1, 1, 1]}),
        ("blowup", d0): pd.DataFrame(), ("dt", d0): pd.DataFrame(),
        # day1: X 仍涨停(continued), Y 跌停(nuked), Z 掉出(faded)
        ("zt", d1): pd.DataFrame({"code": ["X"], "name": ["X"], "boards": [2]}),
        ("blowup", d1): pd.DataFrame(),
        ("dt", d1): pd.DataFrame({"code": ["Y"], "name": ["Y"]}),
    }
    return FakeSource(frames, [d0, d1])


class PickAllPolicy:
    """day0 选 X/Y/Z 各一(pattern=test);仅 day0 被打分。"""
    def __init__(self):
        self.seen = []      # 记录每次 decide 看到的 (date, universe codes)
    def decide(self, state, universe):
        self.seen.append((state.date, frozenset(s.code for s in universe.all())))
        cands = [Candidate(code=c, name=c, pattern="test")
                 for c in sorted(s.code for s in universe.by_status("limit_up"))]
        return DecisionPackage(date=state.date, candidates=cands)


def test_three_outcomes_and_no_lookahead():
    pol = PickAllPolicy()
    rep = WalkForwardEval(_src(), date(2024, 6, 27), date(2024, 6, 28), horizon=1).run(pol)
    # day0 选 X,Y,Z;day1 用次日成员打分:X continued, Y nuked, Z faded
    assert rep.n_candidates == 3
    assert abs(rep.hit_rate - 1 / 3) < 1e-9      # 仅 X continued
    assert abs(rep.nuke_rate - 1 / 3) < 1e-9     # 仅 Y nuked
    assert abs(rep.mean_score - (1 + (-1) + 0) / 3) < 1e-9   # 0.0
    # 无前视:day0 decide 只看到 day0 的成员(X,Y,Z),绝不含 day1 才出现的状态变化
    day0, codes0 = pol.seen[0]
    assert day0 == date(2024, 6, 27)
    assert codes0 == frozenset({"X", "Y", "Z"})   # day0 universe,非未来
    # day1 decide 只看到 day1 成员(X 涨停 + Y 跌停)
    day1, codes1 = pol.seen[1]
    assert codes1 == frozenset({"X", "Y"})
```

- [ ] **Step 2: 运行,确认通过**

Run: `pytest tests/test_eval_integration.py -v`
Expected: PASS

- [ ] **Step 3: 跑全量套件**

Run: `pytest -p no:cacheprovider`(`-q` 摘要经管道会空,看退出码;约 130+ 用例)
Expected: exit 0,全绿

- [ ] **Step 4: Commit**

```bash
git add tests/test_eval_integration.py
git commit -m "test(eval): 多日 continued/nuked/faded + 无前视端到端审计"
```

---

## Self-Review(已自检)

**1. Spec 覆盖(对照 Goal/范围):**
- 决策/候选 schema + DecisionPolicy 协议 → Task 1。✅
- 已实现未来 oracle(pool-membership 类别 + 分值)+ PoolRecord → Task 2。✅
- 多维指标(hit/nuke/expectancy + by_pattern)→ Task 3。✅
- 平凡基线(NoTrade/HighestBoard,floor)→ Task 4。✅
- walk-forward + **延迟打分(防火墙保持)** → Task 5。✅
- 端到端 continued/nuked/faded + 无前视审计 → Task 6。✅
- **明确不在 v1**:精确收益/OHLCV oracle、regime 分层(需 G_cycle)、成本 Pareto、LLM/Hexpert 策略(Phase-1)、N>1 horizon 的窗口聚合(horizon 参数已留,v1 用"恰好 horizon 天后单日")。

**2. Placeholder 扫描:** 无 TBD/TODO;每个改代码 step 均给完整代码 + 命令。✅

**3. 类型一致性:** `DecisionPolicy.decide(state, universe)` 在 Task 1 定义,Task 4 基线、Task 5/6 策略一致实现;`DecisionPackage`/`Candidate` 字段在 Task 1 定义、各处构造一致;`outcome/SCORE/PoolRecord/DayMembership` 在 Task 2 定义、Task 5 walk_forward 使用一致;`ScoredCandidate/EvalReport/build_report` 在 Task 3 定义、Task 5 使用一致;`build_universe`(Phase-0c)、`ReplayEngine`(Phase-0a,`.cursor/.observe()/.step()/.guarded_source`)在 Task 5 复用一致。✅

**4. 防火墙正确性(核心):** 策略 `decide` 只拿游标 t 的 `state`(engine.observe,≤t)+ `universe`(build_universe 经 engine.guarded_source,≤t),拿到的是**快照对象**(无 source,无法取任意日期)→ 结构上不可能见未来。oracle 用 `days_seen[j+horizon]` 的成员,该天成员只在游标推进到它时(`idx>=j+horizon`,即 cursor≥该天)才 record(≤cursor)→ 打分时该天已是过去。Task 6 spy 策略显式断言"decide 看到的 universe codes == 当日成员,非未来"。✅

**5. 回归风险:** 纯新增 `youzi/eval/` 包 + 复用 Phase-0a/0c 公共接口,不改已有模块 → 既有 111 测试不受影响。FakeSource(conftest)返回多日英文列帧,与 build_universe/observe 期望一致。✅
