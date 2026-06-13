# Phase-1b-1 Implementation Plan:轨迹 · 信用分配 · 失败签名

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给自进化系统加一个确定性、无 LLM、纯离线可测的"观测层"——把一次回放走出的 `Trajectory` 记下来,用已实现 oracle 结果给 agent 引用的技能做信用分配(填 `SkillStats`),并抽取结构化失败签名。

**Architecture:** `Trajectory` 作为一次 policy 走的一等产物放 `eval/`;`WalkForwardEval` 复用唯一的延迟打分循环新增 `walk()→Trajectory`,`run()→EvalReport` 行为不变。`refine/` 新包消费 `Trajectory`:`apply_credit` 就地更新被引用技能的 `SkillStats`(观测,不入 EditLog),`extract_signatures` 产 board-rank×outcome 四类入场签名。1b-2(LLM Refiner)/1b-3(内环编排+度量)在其上。

**Tech Stack:** Python 3.13 · pydantic v2(frozen 快照)· pytest(全离线 FakeSource,不触网)。

**先读**:`docs/superpowers/specs/2026-06-01-phase1b1-trajectory-credit-signatures-design.md`(设计冻结)· `后续开发文档.md` §2 不变量。

**全局约定(每个 task 都守)**:
- 未来函数防火墙:信用/签名只对**走完的** trajectory 的已实现结果做事后分析,永不回灌 ≤t 推理。
- frozen 快照:`Trajectory`/`TrajectoryStep`/`EntrySnap`/`FailureSignature`/`CreditReport`/`SkillCredit` 全 frozen;容器类 `__bool__ = True`。
- 缺失值诚实 `None`;不臆造。
- 每 task 跑 `python -m pytest -q` 必须全绿(含既有 145 测试)。commit message 中文,按 feat/fix/test/docs 分类。

---

## File Structure

| 文件 | 动作 | 责任 |
|---|---|---|
| `youzi/eval/trajectory.py` | Create | `EntrySnap` · `TrajectoryStep` · `Trajectory`(模型 + 计数/scored_steps 助手) |
| `youzi/eval/walk_forward.py` | Modify | 加 `walk()→Trajectory` 与模块函数 `report_from_trajectory()`;`run()` 改为二者组合 |
| `youzi/harness/skill.py` | Modify | `SkillStats` 加 `nukes: int = 0` 字段(`record()` 不变) |
| `youzi/refine/__init__.py` | Create | 包初始化(空) |
| `youzi/refine/credit.py` | Create | `SkillCredit` · `CreditReport` · `resolve_skill` · `apply_credit` |
| `youzi/refine/signatures.py` | Create | `FailureKind` · `FailureSignature` · `extract_signatures` |
| `tests/test_trajectory.py` | Create | 模型 frozen/计数/scored_steps |
| `tests/test_walk_forward_trajectory.py` | Create | walk() 结构 + run() 等价性 |
| `tests/test_skill_stats_nukes.py` | Create | nukes 默认/序列化/旧快照前向兼容 |
| `tests/test_credit.py` | Create | resolve + 信用分配数值对账 + unattributed + 幂等 |
| `tests/test_signatures.py` | Create | 四类 kind + skip continued + unresolved |
| `tests/test_refine_integration.py` | Create | 真实种子端到端 walk→credit→signatures + H 序列化往返 |
| `PROJECT_STATE.md` | Modify | 标记 1b-1 完成 + 残留债务 |

> **实现注记(对 spec §4.2 的一处偏移)**:`report_from_trajectory` 放在 `walk_forward.py` 而非 `metrics.py`——否则 `metrics.py`(被 `trajectory.py` import `ScoredCandidate`)反过来 import `trajectory` 会成环。`walk_forward.py` 同时 import `build_report` 与 `Trajectory`,是它的自然落点。

---

## Bundle A —— Trajectory 模型 + WalkForwardEval 重构(eval 层)

### Task A1: `eval/trajectory.py` 三模型

**Files:**
- Create: `youzi/eval/trajectory.py`
- Test: `tests/test_trajectory.py`

- [ ] **Step 1: 写失败测试** `tests/test_trajectory.py`

```python
# tests/test_trajectory.py
from datetime import date, datetime, time

import pytest
from pydantic import ValidationError

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.schemas.market import MarketState


def _state(d, max_board=0):
    return MarketState(date=d, max_board_height=max_board, limit_up_count=0,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0,
                       echelon=[], money_effect_raw=0.0, sentiment_raw=0.0,
                       as_of=datetime.combine(d, time(15, 0)))


def _step(d, codes, scored=False, outcomes=None):
    cands = [Candidate(code=c, pattern="p") for c in codes]
    return TrajectoryStep(
        date=d, market=_state(d),
        decision=DecisionPackage(date=d, candidates=cands),
        entries={c: EntrySnap(code=c, status="limit_up", boards=1) for c in codes},
        scored=scored, outcomes=outcomes or {})


def test_trajectory_step_is_frozen():
    s = _step(date(2024, 6, 26), ["A"])
    with pytest.raises(ValidationError):
        s.scored = True


def test_entry_snap_boards_can_be_none():
    e = EntrySnap(code="A", status="limit_up")
    assert e.boards is None


def test_trajectory_counts_and_scored_steps():
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    sc = ScoredCandidate(decision_date=d0, code="A", pattern="p",
                         outcome="continued", score=1.0)
    steps = [
        _step(d0, ["A"], scored=True, outcomes={"A": sc}),
        _step(d1, [], scored=True),                     # no-trade
        _step(d2, ["B"], scored=False),                 # 尾部未打分
    ]
    traj = Trajectory(steps=steps, horizon=1)
    assert traj.n_decisions() == 3
    assert traj.n_no_trade() == 1
    assert [s.date for s in traj.scored_steps()] == [d0, d1]
    assert bool(traj) is True


def test_empty_trajectory_is_truthy():
    assert bool(Trajectory()) is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_trajectory.py -q`
Expected: FAIL（`ModuleNotFoundError: youzi.eval.trajectory`）

- [ ] **Step 3: 实现** `youzi/eval/trajectory.py`

```python
from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field

from youzi.eval.decision import DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockStatus


class EntrySnap(BaseModel):
    """入选 code 在决策日的客观入场上下文(≤t)。"""
    model_config = ConfigDict(frozen=True)
    code: str
    status: StockStatus
    boards: int | None = None      # 连板数;源未给则 None(不臆造 0)


class TrajectoryStep(BaseModel):
    """某决策日一步:决策日采 market/decision/entries;horizon 日回填 outcomes/scored。"""
    model_config = ConfigDict(frozen=True)
    date: Date
    market: MarketState
    decision: DecisionPackage
    entries: dict[str, EntrySnap] = Field(default_factory=dict)
    scored: bool = False
    outcomes: dict[str, ScoredCandidate] = Field(default_factory=dict)


class Trajectory(BaseModel):
    """一次回放走出的轨迹(frozen 容器)。"""
    model_config = ConfigDict(frozen=True)
    steps: list[TrajectoryStep] = Field(default_factory=list)
    horizon: int = 1

    def scored_steps(self) -> list[TrajectoryStep]:
        return [s for s in self.steps if s.scored]

    def n_decisions(self) -> int:
        return len(self.steps)

    def n_no_trade(self) -> int:
        return sum(1 for s in self.steps if not s.decision.candidates)

    def __bool__(self) -> bool:
        return True
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_trajectory.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: commit**

```bash
git add youzi/eval/trajectory.py tests/test_trajectory.py
git commit -m "feat(eval): Trajectory/TrajectoryStep/EntrySnap 模型(frozen,1b-1 观测层)"
```

---

### Task A2: `walk_forward.py` 加 `walk()` + `report_from_trajectory()`,`run()` 不变

**Files:**
- Modify: `youzi/eval/walk_forward.py`(整文件替换为下方实现)
- Test: `tests/test_walk_forward_trajectory.py`

- [ ] **Step 1: 写失败测试** `tests/test_walk_forward_trajectory.py`

```python
# tests/test_walk_forward_trajectory.py
from datetime import date

import pandas as pd

from youzi.eval.baselines import HighestBoardPolicy
from youzi.eval.walk_forward import WalkForwardEval, report_from_trajectory
from tests.conftest import FakeSource


def _src():
    """A 连续涨停;B day0 涨停 day1 跌停。复刻 test_walk_forward._src()。"""
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    frames = {}
    frames[("zt", d0)] = pd.DataFrame({"code": ["A", "B"], "name": ["A", "B"], "boards": [2, 1]})
    frames[("blowup", d0)] = pd.DataFrame(); frames[("dt", d0)] = pd.DataFrame()
    frames[("zt", d1)] = pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [3]})
    frames[("blowup", d1)] = pd.DataFrame()
    frames[("dt", d1)] = pd.DataFrame({"code": ["B"], "name": ["B"]})
    frames[("zt", d2)] = pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [4]})
    frames[("blowup", d2)] = pd.DataFrame(); frames[("dt", d2)] = pd.DataFrame()
    return FakeSource(frames, [d0, d1, d2])


def test_walk_records_steps_entries_and_delayed_outcomes():
    traj = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).walk(
        HighestBoardPolicy())
    assert traj.n_decisions() == 3
    assert [s.date for s in traj.scored_steps()] == [date(2024, 6, 26), date(2024, 6, 27)]
    s0 = traj.steps[0]
    assert s0.scored is True
    assert "A" in s0.entries and s0.entries["A"].boards == 2       # 入场上下文来自当日 universe
    assert s0.outcomes["A"].outcome == "continued"                # 次日 A 仍涨停
    assert traj.steps[2].scored is False                          # 尾部步保留但未打分


def test_run_equals_report_from_trajectory():
    ev = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1)
    rep = ev.run(HighestBoardPolicy())
    rep2 = report_from_trajectory(ev.walk(HighestBoardPolicy()))
    assert rep == rep2
    # 与既有 test_walk_forward 的断言一致(等价性回归)
    assert rep.n_decisions == 3 and rep.n_candidates == 2
    assert rep.hit_rate == 1.0 and rep.mean_score == 1.0
    assert rep.by_pattern["highest_board"].n == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_walk_forward_trajectory.py -q`
Expected: FAIL（`ImportError: cannot import name 'report_from_trajectory'`）

- [ ] **Step 3: 实现** —— 整体替换 `youzi/eval/walk_forward.py`

```python
from __future__ import annotations

from datetime import date as Date

from youzi.eval.decision import DecisionPolicy
from youzi.eval.metrics import EvalReport, ScoredCandidate, build_report
from youzi.eval.oracle import SCORE, PoolRecord, outcome
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.replay.engine import ReplayEngine
from youzi.universe.universe import build_universe


def report_from_trajectory(traj: Trajectory) -> EvalReport:
    """从已走轨迹派生 EvalReport(展平已打分步的 outcomes)。"""
    scored: list[ScoredCandidate] = []
    for step in traj.steps:
        if step.scored:
            scored.extend(step.outcomes.values())
    return build_report(scored, n_decisions=traj.n_decisions(),
                        n_no_trade=traj.n_no_trade(), horizon=traj.horizon)


class WalkForwardEval:
    """前向回放评测:策略每日决策(≤t 快照),horizon 天后用已实现 pool 成员延迟打分。"""

    def __init__(self, source, start: Date, end: Date, horizon: int = 1) -> None:
        if horizon < 1:
            raise ValueError(f"horizon 必须 >=1, got {horizon}")
        self._source = source
        self._start = start
        self._end = end
        self._horizon = horizon

    def walk(self, policy: DecisionPolicy) -> Trajectory:
        """走完区间,产出 Trajectory(每步含 market/decision/entries,horizon 日回填 outcomes)。"""
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        drafts: list[dict] = []          # 可变草稿,末尾封 frozen TrajectoryStep
        pending: list[int] = []          # 待打分的 draft 索引
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()                                  # ≤t 聚合状态
            universe = build_universe(engine.guarded_source, cursor)  # ≤t 候选(经防火墙)
            record.record(cursor, universe)
            decision = policy.decide(state, universe)
            # 入场上下文:去重入选 code → EntrySnap(从当日 universe 查;查不到则不记)
            entries: dict[str, EntrySnap] = {}
            for c in decision.candidates:
                if c.code in entries:
                    continue
                snap = universe.get(c.code)
                if snap is not None:
                    entries[c.code] = EntrySnap(code=c.code, status=snap.status,
                                                boards=snap.boards)
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "scored": False, "outcomes": {}})
            pending.append(idx)
            # 延迟打分:决策 j 在 idx >= j+horizon 时,用 days_seen[j+horizon] 的已录成员打分
            remaining: list[int] = []
            for j in pending:
                if idx >= j + self._horizon:
                    mem = record.get(days_seen[j + self._horizon])
                    assert mem is not None, f"BUG: 交易日 {days_seen[j + self._horizon]} 未录制成员"
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
                else:
                    remaining.append(j)
            pending = remaining
            idx += 1
            if not engine.step():
                break
        # 尾部不足 horizon 的步保留(scored=False),显式化原"静默丢弃"
        steps = [TrajectoryStep(**d) for d in drafts]
        return Trajectory(steps=steps, horizon=self._horizon)

    def run(self, policy: DecisionPolicy) -> EvalReport:
        return report_from_trajectory(self.walk(policy))
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `python -m pytest tests/test_walk_forward_trajectory.py tests/test_walk_forward.py tests/test_eval_integration.py -q`
Expected: PASS（新测试 + 既有 walk_forward/eval 测试全绿,证明 run() 行为不变）

- [ ] **Step 5: commit**

```bash
git add youzi/eval/walk_forward.py tests/test_walk_forward_trajectory.py
git commit -m "feat(eval): WalkForwardEval.walk()→Trajectory + report_from_trajectory;run() 行为不变(等价性测试守既有)"
```

---

## Bundle B —— SkillStats.nukes + 信用分配(refine 层)

### Task B1: `SkillStats` 加 `nukes` 字段

**Files:**
- Modify: `youzi/harness/skill.py`(`SkillStats` 加一字段,`record()` 不动)
- Test: `tests/test_skill_stats_nukes.py`

- [ ] **Step 1: 写失败测试** `tests/test_skill_stats_nukes.py`

```python
# tests/test_skill_stats_nukes.py
from youzi.harness.skill import Skill, SkillStats


def test_skillstats_nukes_defaults_zero():
    assert SkillStats().nukes == 0


def test_skillstats_roundtrip_includes_nukes():
    st = SkillStats(n=3, wins=1, losses=2, nukes=1, expectancy=-0.33)
    d = st.model_dump()
    assert d["nukes"] == 1
    assert SkillStats.model_validate(d).nukes == 1


def test_skillstats_loads_old_dict_without_nukes():
    # 旧快照(无 nukes 字段)前向兼容 → 默认 0
    old = {"n": 2, "wins": 1, "losses": 1, "ewma_winrate": 0.5}
    assert SkillStats.model_validate(old).nukes == 0


def test_skill_with_old_stats_dict_loads():
    sk = Skill.model_validate({
        "skill_id": "x", "name_cn": "x", "type": "pattern",
        "trigger": "t", "entry": "e", "exit_stop": "s",
        "stats": {"n": 1, "wins": 1, "losses": 0},   # 无 nukes
    })
    assert sk.stats.nukes == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_skill_stats_nukes.py -q`
Expected: FAIL（`SkillStats()` 无 `nukes` 属性 / `model_dump` 无 `nukes`）

- [ ] **Step 3: 实现** —— 在 `youzi/harness/skill.py` 的 `SkillStats` 里 `losses` 之后加一行

把:
```python
    n: int = 0
    wins: int = 0
    losses: int = 0
    ewma_winrate: float | None = None
```
改为:
```python
    n: int = 0
    wins: int = 0
    losses: int = 0
    nukes: int = 0           # 被砸(nuked)次数;nuke_rate = nukes/n。由 apply_credit 维护
    ewma_winrate: float | None = None
```
（`record()` 不变。）

- [ ] **Step 4: 跑测试确认通过 + harness 序列化回归**

Run: `python -m pytest tests/test_skill_stats_nukes.py tests/test_skill.py tests/test_harness_serialize.py tests/test_snapshot.py -q`
Expected: PASS（含既有序列化往返仍绿,证明 byte-identical 不破)

- [ ] **Step 5: commit**

```bash
git add youzi/harness/skill.py tests/test_skill_stats_nukes.py
git commit -m "feat(harness): SkillStats 加 nukes 字段(默认0,序列化前向兼容)"
```

---

### Task B2: `refine/credit.py` 信用分配

**Files:**
- Create: `youzi/refine/__init__.py`(空)
- Create: `youzi/refine/credit.py`
- Test: `tests/test_credit.py`

- [ ] **Step 1: 建空包** `youzi/refine/__init__.py`

```python
```
（空文件即可。）

- [ ] **Step 2: 写失败测试** `tests/test_credit.py`

```python
# tests/test_credit.py
from datetime import date, datetime, time

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.harness import HarnessState
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill
from youzi.refine.credit import apply_credit, resolve_skill
from youzi.schemas.market import MarketState

_SCORE = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


def _state(d, max_board=0):
    return MarketState(date=d, max_board_height=max_board, limit_up_count=0,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0,
                       echelon=[], money_effect_raw=0.0, sentiment_raw=0.0,
                       as_of=datetime.combine(d, time(15, 0)))


def _skill(sid, name="技能"):
    return Skill(skill_id=sid, name_cn=name, type="pattern",
                 trigger="t", entry="e", exit_stop="s", status="active")


def _harness(skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(skills),
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _step(d, code, pattern, oc, boards, max_board):
    sc = ScoredCandidate(decision_date=d, code=code, pattern=pattern, outcome=oc,
                         score=_SCORE[oc])
    return TrajectoryStep(
        date=d, market=_state(d, max_board),
        decision=DecisionPackage(date=d, candidates=[Candidate(code=code, pattern=pattern)]),
        entries={code: EntrySnap(code=code, status="limit_up", boards=boards)},
        scored=True, outcomes={code: sc})


def test_resolve_skill_by_id_then_name_then_none():
    h = _harness([_skill("pat_a", "龙头接力")])
    assert resolve_skill("pat_a", h).skill_id == "pat_a"       # by skill_id
    assert resolve_skill("龙头接力", h).skill_id == "pat_a"     # by name_cn
    assert resolve_skill("不存在", h) is None
    assert resolve_skill("", h) is None


def test_apply_credit_updates_stats_and_distinguishes_faded_nuked():
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[
        _step(d0, "X", "pat_a", "continued", 3, 3),
        _step(d1, "Y", "pat_a", "faded", 2, 3),
        _step(d2, "Z", "pat_a", "nuked", 3, 3),
    ], horizon=1)
    rep = apply_credit(traj, h)
    st = h.skills.get("pat_a").stats
    assert st.n == 3 and st.wins == 1 and st.losses == 2 and st.nukes == 1
    assert abs(st.expectancy - 0.0) < 1e-9               # mean(1,0,-1)=0
    # ewma:1.0 → 0.1*0+0.9*1=0.9 → 0.1*0+0.9*0.9=0.81
    assert abs(st.ewma_winrate - 0.81) < 1e-9
    cr = rep.per_skill["pat_a"]
    assert cr.n == 3 and cr.wins == 1 and cr.nukes == 1
    assert abs(cr.hit_rate - 1 / 3) < 1e-9 and abs(cr.expectancy) < 1e-9
    assert rep.n_scored == 3 and rep.unattributed is None


def test_apply_credit_unattributed_bucket():
    d0 = date(2024, 6, 26)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[_step(d0, "X", "无此技能", "nuked", 1, 2)], horizon=1)
    rep = apply_credit(traj, h)
    assert h.skills.get("pat_a").stats.n == 0           # 未匹配 → 不动任何技能
    assert rep.per_skill == {}
    assert rep.unattributed is not None
    assert rep.unattributed.n == 1 and rep.unattributed.nukes == 1


def test_apply_credit_idempotency_doubles():
    d0 = date(2024, 6, 26)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[_step(d0, "X", "pat_a", "continued", 3, 3)], horizon=1)
    apply_credit(traj, h)
    apply_credit(traj, h)                               # 契约:每条 trajectory 调一次;调两次=累计翻倍
    assert h.skills.get("pat_a").stats.n == 2
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest tests/test_credit.py -q`
Expected: FAIL（`ModuleNotFoundError: youzi.refine.credit`）

- [ ] **Step 4: 实现** `youzi/refine/credit.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from youzi.eval.oracle import SCORE
from youzi.eval.trajectory import Trajectory
from youzi.harness.harness import HarnessState
from youzi.harness.skill import Skill

UNATTRIBUTED = "__unattributed__"


class SkillCredit(BaseModel):
    """本次 trajectory 对某技能(或 unattributed 桶)的增量信用汇总(frozen)。"""
    model_config = ConfigDict(frozen=True)
    skill_id: str
    n: int
    wins: int
    losses: int
    nukes: int
    hit_rate: float
    nuke_rate: float
    expectancy: float


class CreditReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    per_skill: dict[str, SkillCredit] = Field(default_factory=dict)
    unattributed: SkillCredit | None = None
    n_scored: int = 0

    def __bool__(self) -> bool:
        return True


def resolve_skill(pattern: str, harness: HarnessState) -> Skill | None:
    """pattern → Skill:先 skill_id 精确,再 name_cn 精确(多命中取第一个);都不中 → None。"""
    if not pattern:
        return None
    s = harness.skills.get(pattern)
    if s is not None:
        return s
    for sk in harness.skills.all():
        if sk.name_cn == pattern:
            return sk
    return None


class _Acc:
    __slots__ = ("n", "wins", "losses", "nukes", "score_sum")

    def __init__(self) -> None:
        self.n = 0
        self.wins = 0
        self.losses = 0
        self.nukes = 0
        self.score_sum = 0.0

    def add(self, oc: str) -> None:
        self.n += 1
        self.score_sum += SCORE[oc]
        if oc == "continued":
            self.wins += 1
        else:
            self.losses += 1
        if oc == "nuked":
            self.nukes += 1

    def to_credit(self, skill_id: str) -> SkillCredit:
        return SkillCredit(skill_id=skill_id, n=self.n, wins=self.wins,
                           losses=self.losses, nukes=self.nukes,
                           hit_rate=self.wins / self.n, nuke_rate=self.nukes / self.n,
                           expectancy=self.score_sum / self.n)


def apply_credit(traj: Trajectory, harness: HarnessState, decay: float = 0.1) -> CreditReport:
    """对已打分轨迹做信用分配:就地更新被引用技能的 SkillStats(观测,不入 EditLog),返回本次增量汇总。

    契约:对一条 trajectory **调用一次**;重复调用会重复计入(stats 设计为累计)。
    防火墙:输入是走完轨迹的已实现结果,纯事后分析,不回灌 ≤t 推理。
    """
    per: dict[str, _Acc] = {}
    unattr = _Acc()
    n_scored = 0
    for step in traj.scored_steps():                  # 按 step 顺序=决策日序,忠实 ewma 衰减
        for code, sc in step.outcomes.items():
            n_scored += 1
            skill = resolve_skill(sc.pattern, harness)
            if skill is None:
                unattr.add(sc.outcome)                # 未匹配:进 unattributed,不动技能 stats
                continue
            win = sc.outcome == "continued"
            skill.stats.record(win, decay)            # 更新 n/wins/losses/ewma
            m = skill.stats.expectancy if skill.stats.expectancy is not None else 0.0
            skill.stats.expectancy = m + (SCORE[sc.outcome] - m) / skill.stats.n  # Welford 累计均值
            if sc.outcome == "nuked":
                skill.stats.nukes += 1
            per.setdefault(skill.skill_id, _Acc()).add(sc.outcome)
    return CreditReport(
        per_skill={sid: acc.to_credit(sid) for sid, acc in per.items()},
        unattributed=unattr.to_credit(UNATTRIBUTED) if unattr.n else None,
        n_scored=n_scored,
    )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_credit.py -q`
Expected: PASS（4 passed）

- [ ] **Step 6: commit**

```bash
git add youzi/refine/__init__.py youzi/refine/credit.py tests/test_credit.py
git commit -m "feat(refine): apply_credit 信用分配(oracle→SkillStats,unattributed 桶,faded≠nuked,Welford 期望)"
```

---

## Bundle C —— 失败签名

### Task C1: `refine/signatures.py` board-rank×outcome 四类入场签名

**Files:**
- Create: `youzi/refine/signatures.py`
- Test: `tests/test_signatures.py`

- [ ] **Step 1: 写失败测试** `tests/test_signatures.py`

```python
# tests/test_signatures.py
from datetime import date, datetime, time

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.harness import HarnessState
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill
from youzi.refine.signatures import extract_signatures
from youzi.schemas.market import MarketState

_SCORE = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


def _state(d, max_board):
    return MarketState(date=d, max_board_height=max_board, limit_up_count=0,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0,
                       echelon=[], money_effect_raw=0.0, sentiment_raw=0.0,
                       as_of=datetime.combine(d, time(15, 0)))


def _h():
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills([
            Skill(skill_id="pat_a", name_cn="接力", type="pattern",
                  trigger="t", entry="e", exit_stop="s", status="active")]),
        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _step(d, code, oc, boards, max_board, pattern="pat_a"):
    sc = ScoredCandidate(decision_date=d, code=code, pattern=pattern, outcome=oc,
                         score=_SCORE[oc])
    return TrajectoryStep(
        date=d, market=_state(d, max_board),
        decision=DecisionPackage(date=d, candidates=[Candidate(code=code, pattern=pattern)]),
        entries={code: EntrySnap(code=code, status="limit_up", boards=boards)},
        scored=True, outcomes={code: sc})


def test_signatures_four_kinds_and_skip_continued():
    d = date(2024, 6, 26)
    traj = Trajectory(steps=[
        _step(d, "TOP", "nuked", 3, 3),      # boards==max → chased_into_nuke
        _step(d, "WEED", "nuked", 1, 3),     # boards<max → weed_over_dragon
        _step(d, "UNK", "nuked", None, 3),   # boards None → generic_nuke
        _step(d, "FADE", "faded", 2, 3),     # faded → faded_miss
        _step(d, "WIN", "continued", 3, 3),  # continued → 无签名
    ], horizon=1)
    sigs = extract_signatures(traj, _h())
    kinds = {s.code: s.kind for s in sigs}
    assert kinds == {"TOP": "chased_into_nuke", "WEED": "weed_over_dragon",
                     "UNK": "generic_nuke", "FADE": "faded_miss"}
    assert all(s.skill_id == "pat_a" for s in sigs)        # pattern 命中技能
    top = next(s for s in sigs if s.code == "TOP")
    assert "boards=3/max=3" in top.evidence and top.score == -1.0


def test_signatures_unresolved_pattern_skill_id_none():
    d = date(2024, 6, 26)
    traj = Trajectory(steps=[_step(d, "X", "faded", 1, 2, pattern="无")], horizon=1)
    sigs = extract_signatures(traj, _h())
    assert len(sigs) == 1 and sigs[0].skill_id is None and sigs[0].kind == "faded_miss"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_signatures.py -q`
Expected: FAIL（`ModuleNotFoundError: youzi.refine.signatures`）

- [ ] **Step 3: 实现** `youzi/refine/signatures.py`

```python
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from youzi.eval.trajectory import Trajectory
from youzi.harness.harness import HarnessState
from youzi.refine.credit import resolve_skill

FailureKind = Literal["chased_into_nuke", "weed_over_dragon", "generic_nuke", "faded_miss"]


class FailureSignature(BaseModel):
    """一条确定性入场失败签名(board-rank × oracle outcome,无 OHLCV/相位)。"""
    model_config = ConfigDict(frozen=True)
    date: Date
    code: str
    pattern: str
    skill_id: str | None
    kind: FailureKind
    score: float
    evidence: str


def extract_signatures(traj: Trajectory, harness: HarnessState) -> list[FailureSignature]:
    """对已打分轨迹抽取入场类失败签名(continued 不产签名)。"""
    out: list[FailureSignature] = []
    for step in traj.scored_steps():
        mx = step.market.max_board_height
        for code, sc in step.outcomes.items():
            if sc.outcome == "continued":
                continue
            snap = step.entries.get(code)
            boards = snap.boards if snap is not None else None
            if sc.outcome == "faded":
                kind: FailureKind = "faded_miss"
                ev = f"boards={boards}/max={mx} → 入场后次日 faded(空耗,SCORE 0)"
            elif boards is not None and boards == mx:
                kind = "chased_into_nuke"
                ev = f"boards={boards}/max={mx} → 追最高板被闷(次日跌停/炸板)"
            elif boards is not None and boards < mx:
                kind = "weed_over_dragon"
                ev = f"boards={boards}/max={mx} → 接非最高板被砸(把杂毛当龙头)"
            else:
                kind = "generic_nuke"
                ev = f"boards={boards}/max={mx} → 被砸(板数未知或异常)"
            sk = resolve_skill(sc.pattern, harness)
            out.append(FailureSignature(
                date=step.date, code=code, pattern=sc.pattern,
                skill_id=sk.skill_id if sk is not None else None,
                kind=kind, score=sc.score, evidence=ev))
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_signatures.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: commit**

```bash
git add youzi/refine/signatures.py tests/test_signatures.py
git commit -m "feat(refine): extract_signatures 四类入场失败签名(board-rank×outcome,无OHLCV/相位)"
```

---

## Bundle D —— 集成 + 文档

### Task D1: 真实种子端到端集成测试

**Files:**
- Create: `tests/test_refine_integration.py`

- [ ] **Step 1: 写测试** `tests/test_refine_integration.py`

```python
# tests/test_refine_integration.py
from datetime import date
from pathlib import Path

import pandas as pd

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.walk_forward import WalkForwardEval
from youzi.harness.harness import HarnessState
from youzi.harness.loader import load_seeds
from youzi.refine.credit import apply_credit
from youzi.refine.signatures import extract_signatures
from tests.conftest import FakeSource

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def _src():
    """day0: LOSER 涨停(1板,即当日最高板);day1: LOSER 跌停(nuked)。"""
    d0, d1 = date(2024, 6, 26), date(2024, 6, 27)
    frames = {}
    frames[("zt", d0)] = pd.DataFrame({"code": ["LOSER"], "name": ["L"], "boards": [1]})
    frames[("blowup", d0)] = pd.DataFrame(); frames[("dt", d0)] = pd.DataFrame()
    frames[("zt", d1)] = pd.DataFrame(); frames[("blowup", d1)] = pd.DataFrame()
    frames[("dt", d1)] = pd.DataFrame({"code": ["LOSER"], "name": ["L"]})
    return FakeSource(frames, [d0, d1])


def test_pipeline_walk_credit_signatures_on_real_seeds():
    h = load_seeds(SEEDS)
    sid = h.skills.all()[0].skill_id            # 动态取真实种子技能,免硬编码
    assert h.skills.get(sid).stats.n == 0       # 载入即零,信用未跑

    class P:
        def decide(self, state, universe):
            return DecisionPackage(date=state.date,
                                   candidates=[Candidate(code="LOSER", pattern=sid)])

    traj = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 27), horizon=1).walk(P())
    rep = apply_credit(traj, h)
    sigs = extract_signatures(traj, h)

    # day0 决策 LOSER → day1 跌停=nuked,归因到真实种子技能
    st = h.skills.get(sid).stats
    assert st.n == 1 and st.nukes == 1 and st.wins == 0
    assert rep.per_skill[sid].nukes == 1 and rep.n_scored == 1
    # boards=1 == 当日 max_board_height=1 → chased_into_nuke
    assert len(sigs) == 1 and sigs[0].kind == "chased_into_nuke" and sigs[0].skill_id == sid


def test_harness_roundtrips_after_credit():
    h = load_seeds(SEEDS)
    sid = h.skills.all()[0].skill_id

    class P:
        def decide(self, state, universe):
            return DecisionPackage(date=state.date,
                                   candidates=[Candidate(code="LOSER", pattern=sid)])

    traj = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 27), horizon=1).walk(P())
    apply_credit(traj, h)
    h2 = HarnessState.from_dict(h.to_dict())            # 含 nukes 的 H 往返保真
    assert h2.skills.get(sid).stats.nukes == h.skills.get(sid).stats.nukes == 1
```

- [ ] **Step 2: 跑测试确认通过**

Run: `python -m pytest tests/test_refine_integration.py -q`
Expected: PASS（2 passed）

- [ ] **Step 3: 全量回归**

Run: `python -m pytest -q`
Expected: PASS（既有 145 + 本阶段新增全绿,离线不触网）

- [ ] **Step 4: commit**

```bash
git add tests/test_refine_integration.py
git commit -m "test(refine): 真实种子端到端 walk→credit→signatures + H 含 nukes 序列化往返"
```

---

### Task D2: 更新 `PROJECT_STATE.md`

**Files:**
- Modify: `PROJECT_STATE.md`(在 `### Phase-1a 已完成...` 段后、`Phase-1 分解` 行附近插入 1b-1 完成段)

- [ ] **Step 1: 在 `PROJECT_STATE.md` 的 "**Phase-1 分解**" 行之前插入**

```markdown
- **Phase-1b-1 已完成并入 main**(`youzi/eval/trajectory.py` + `walk_forward` 重构 + `youzi/refine/{credit,signatures}.py` + `SkillStats.nukes`):**确定性观测层(无 LLM,离线可测)**——`Trajectory/TrajectoryStep/EntrySnap`(frozen,记 market/decision/入场上下文/延迟 outcomes,尾部步显式 scored=False)+ `WalkForwardEval.walk()→Trajectory`(复用唯一延迟打分循环,`run()` 行为不变,等价性测试守既有)+ `apply_credit`(oracle→SkillStats:continued=win,faded/nuked=非win 但 expectancy 用 Welford 保留 0/−1 区别,nukes 单列,pattern→技能 resolve,未匹配进 unattributed 桶不静默丢)+ `extract_signatures`(board-rank×outcome 四类入场签名 chased_into_nuke/weed_over_dragon/generic_nuke/faded_miss)。**观测 vs 编辑边界**:stats 由信用直写不入 EditLog,结构性编辑留 1b-2 走 meta-tool。终审待评审。
  - **Phase-1b-1 债务/推迟(非阻塞)**:① 相位依赖签名(退潮接力 relay_in_ebb)待 `G_cycle` 相位分类器;② K线/持有退出签名(黄昏之星/出货分时/该走不走)待 OHLCV oracle / 持仓模型;③ "比同板更高板续板我却接杂毛"需对全 universe 打分(当前仅决策集);④ Trajectory 仅内存、未持久化(长回放/重启落点同 PITStore);⑤ apply_credit 批处理、非流式(在线增量信用留 1b-3)。
```

- [ ] **Step 2: commit**

```bash
git add PROJECT_STATE.md
git commit -m "docs: PROJECT_STATE 标记 Phase-1b-1 完成 + 残留债务"
```

---

## 收尾(实现完成后)

1. **两段评审 / 终审**:每 bundle 完成后按 `superpowers:subagent-driven-development` 做 ① spec 合规(对照本计划 + spec 逐条)② 代码质量(对抗性:防火墙侧信道、frozen 漏洞、faded/nuked 误归、unattributed 静默丢、Welford 数值、序列化往返)。全 bundle 完 → opus 终审(集成级:防火墙 airtight、run() 等价、观测/编辑边界成立)。
2. **finishing**:按 `superpowers:finishing-a-development-branch`——`phase-1b1-trajectory-credit` 全绿 → 合并 main(FF)→ 删分支 → 更新 memory(`youzi-self-evolving-project.md`)。
3. **1b-2 预告**:LLM Refiner 读本层的 `CreditReport`+`list[FailureSignature]`+τ,经 9 个 meta-tool 发四遍 CRUD(入 EditLog),并补 DeepSeekClient retry / 按 regime 选择性注入 / 把 stats+win-memory 注入 agent 提示。

---

## Self-Review(写计划者自查,已过)

- **Spec 覆盖**:Trajectory(A1)· walk/run 等价(A2)· nukes 字段+前向兼容(B1)· apply_credit+resolve+unattributed+faded/nuked+Welford(B2)· 四类签名+skip continued+unresolved(C1)· 真实种子端到端+H 往返(D1)· 文档(D2)。spec §4.1–4.5/§5/§6/§7/§8 全有对应 task。`relay_in_ebb` 推迟(spec §1.1/§4.5)已在 D2 债务记录。
- **Placeholder**:无 TBD/TODO;每步含完整代码与精确命令/预期。
- **类型一致**:`Trajectory.scored_steps()/n_decisions()/n_no_trade()`、`EntrySnap(code,status,boards)`、`ScoredCandidate(decision_date,code,pattern,outcome,score)`、`apply_credit(traj,harness,decay=0.1)->CreditReport`、`SkillCredit(skill_id,n,wins,losses,nukes,hit_rate,nuke_rate,expectancy)`、`extract_signatures(traj,harness)->list[FailureSignature]` 跨 task 一致;`report_from_trajectory` 落 `walk_forward.py`(已注记避免 import 环)。
