# Phase-1b-3a:内环编排 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 1b-2 的 Refiner 编排成交错内环——每日 agent 用 live H 决策、延迟打分、在线信用回填 SkillStats、每日 refine 编辑 live H(次日可见),reset-free + 能力地板熔断(自相对地板:跌破基线/绝对地板 → rollback 上个 checkpoint + 冻结)。

**Architecture:** 新增 `youzi/loop/inner_loop.py`(顶层整合 eval+refine+harness)。`InnerLoop.run()` 复刻 `WalkForwardEval` 的延迟打分循环,但内联交错:决策(live H)→ 延迟打分 → 每步在线 `apply_credit`(就地改 stats,不重复)→ 熔断检查 →(每日)checkpoint-before + `Refiner.refine`(窗口证据,经 `merge_credit_reports` 只读合并)。持有 `HarnessManager`;rollback 后 rebind agent+refiner 到还原态。HCH/Hexpert/Hmin 度量 = 1b-3b(out-of-scope)。

**Tech Stack:** Python · pydantic(frozen 报告 + 可变 config)· pytest(全离线:`FakeSource` + 两个 `MockLLMClient`,`SnapshotStore(tmp_path)`,不触网)。

**分支:** `phase-1b3a-inner-loop`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-06-phase1b3a-inner-loop-design.md` 与 `后续开发文档.md` §2 不变量。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **217 passed**。每个 Task 末尾跑相关测试 + 不破回归。

**Bundle 分组(供 subagent-driven 派活):**
- **Bundle A**:Task 1-2(merge + 模型/骨架)
- **Bundle B**:Task 3-5(run() 核心 → refine → 熔断,逐步扩展同一方法)

---

## Bundle A

### Task 1: `merge_credit_reports`(只读合并增量信用)

**Files:**
- Modify: `youzi/refine/credit.py`(文件末尾加函数)
- Test: `tests/test_merge_credit.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_merge_credit.py
from youzi.refine.credit import merge_credit_reports, CreditReport, SkillCredit, UNATTRIBUTED


def _rep(per, unattr=None, n_scored=0):
    return CreditReport(per_skill=per, unattributed=unattr, n_scored=n_scored)


def _sc(sid, n, wins, losses, nukes, expectancy):
    return SkillCredit(skill_id=sid, n=n, wins=wins, losses=losses, nukes=nukes,
                       hit_rate=wins / n, nuke_rate=nukes / n, expectancy=expectancy)


def test_merge_empty_is_empty():
    m = merge_credit_reports([])
    assert m.per_skill == {} and m.unattributed is None and m.n_scored == 0


def test_merge_accumulates_per_skill():
    # 报告1: 技能 a n=2 wins=2 exp=1.0;报告2: a n=2 wins=0 nukes=2 exp=-1.0
    r1 = _rep({"a": _sc("a", 2, 2, 0, 0, 1.0)}, n_scored=2)
    r2 = _rep({"a": _sc("a", 2, 0, 2, 2, -1.0)}, n_scored=2)
    m = merge_credit_reports([r1, r2])
    a = m.per_skill["a"]
    assert a.n == 4 and a.wins == 2 and a.losses == 2 and a.nukes == 2
    assert a.hit_rate == 0.5 and a.nuke_rate == 0.5
    assert a.expectancy == 0.0          # (2*1.0 + 2*-1.0)/4
    assert m.n_scored == 4


def test_merge_unattributed_and_distinct_skills():
    r1 = _rep({"a": _sc("a", 1, 1, 0, 0, 1.0)},
              unattr=_sc(UNATTRIBUTED, 1, 0, 1, 0, 0.0), n_scored=2)
    r2 = _rep({"b": _sc("b", 1, 0, 1, 1, -1.0)}, n_scored=1)
    m = merge_credit_reports([r1, r2])
    assert set(m.per_skill) == {"a", "b"}
    assert m.unattributed is not None and m.unattributed.n == 1
    assert m.n_scored == 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_merge_credit.py -q`
Expected: FAIL(`ImportError: cannot import name 'merge_credit_reports'`)

- [ ] **Step 3: 实现(加到 `youzi/refine/credit.py` 末尾)**

```python
def merge_credit_reports(reports: list[CreditReport]) -> CreditReport:
    """把多份增量 CreditReport 合并为一份(纯只读,不触 SkillStats)。

    per_skill 按 skill_id 累加 n/wins/losses/nukes 与 score_sum(=expectancy*n),
    经 _Acc.to_credit 重算 hit_rate/nuke_rate/expectancy;unattributed 同法;n_scored 累加。
    给内环 refiner 当"本窗口谁在亏"的只读证据,区别于 H 内由 apply_credit 直写的累计 stats。
    """
    per: dict[str, _Acc] = {}
    unattr = _Acc()
    n_scored = 0

    def _absorb(acc: _Acc, sc: SkillCredit) -> None:
        acc.n += sc.n
        acc.wins += sc.wins
        acc.losses += sc.losses
        acc.nukes += sc.nukes
        acc.score_sum += sc.expectancy * sc.n

    for rep in reports:
        n_scored += rep.n_scored
        for sid, sc in rep.per_skill.items():
            _absorb(per.setdefault(sid, _Acc()), sc)
        if rep.unattributed is not None:
            _absorb(unattr, rep.unattributed)
    return CreditReport(
        per_skill={sid: acc.to_credit(sid) for sid, acc in per.items()},
        unattributed=unattr.to_credit(UNATTRIBUTED) if unattr.n else None,
        n_scored=n_scored,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_merge_credit.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/refine/credit.py tests/test_merge_credit.py
git commit -m "feat(refine): merge_credit_reports 只读合并增量信用(内环 refiner 证据用)"
```

---

### Task 2: `loop` 包 + 配置/报告模型 + `InnerLoop` 骨架

**Files:**
- Create: `youzi/loop/__init__.py`(空)
- Create: `youzi/loop/inner_loop.py`(模型 + `InnerLoop.__init__`/`_rebind`;`run` 留 Task 3)
- Test: `tests/test_inner_loop.py`(本任务建模型/构造用例)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_inner_loop.py
from datetime import date, timedelta

import pandas as pd
import pytest

from youzi.eval.trajectory import Trajectory
from youzi.loop.inner_loop import InnerLoop, LoopConfig, LoopReport, RefineEvent, BreakerEvent
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.snapshot import SnapshotStore
from youzi.harness.manager import HarnessManager
from youzi.llm.client import MockLLMClient
from tests.conftest import FakeSource


def _seed_h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "longtou", "name_cn": "龙头接力", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    doc = Doctrine(entries=[DoctrineEntry.from_seed(
        {"section": "主升作战", "regime": "主升", "immutable": False, "guidance": "持有龙头"})])
    return HarnessState(doctrine=doc, skills=skills,
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _mgr(tmp_path):
    return HarnessManager(_seed_h(), SnapshotStore(tmp_path))


def _decision(code):
    return ('{"candidates": [{"code": "%s", "pattern": "龙头接力", "confidence": 0.7}],'
            ' "no_trade_reason": ""}') % code


def _loop(tmp_path, src, agent_scripts, refiner_scripts, config=None):
    mgr = _mgr(tmp_path)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient(agent_scripts), MockLLMClient(refiner_scripts),
                     config=config), mgr


def test_models_frozen_and_truthy():
    rep = LoopReport(trajectory=Trajectory())
    assert bool(rep) is True
    with pytest.raises(Exception):
        rep.frozen_from = date(2024, 1, 1)        # frozen


def test_loop_constructs_and_rebinds(tmp_path):
    src = FakeSource({("zt", date(2024, 6, 26)): pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [1]})},
                     [date(2024, 6, 26)])
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'])
    # 构造后 agent/refiner 已绑定到 mgr.harness
    assert loop._agent._harness is mgr.harness
    assert loop._refiner._h is mgr.harness
    # rollback 后 _rebind 指向还原态新对象
    v = mgr.checkpoint("c0")
    mgr.tools.retire_skill("longtou")
    mgr.rollback_to(v)
    loop._rebind()
    assert loop._agent._harness is mgr.harness
    assert loop._refiner._h is mgr.harness
    assert mgr.harness.skills.get("longtou").status == "active"   # 还原
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.loop.inner_loop`)

- [ ] **Step 3: 建包 + 模型 + 骨架**

创建空文件 `youzi/loop/__init__.py`,然后写 `youzi/loop/inner_loop.py`:

```python
# youzi/loop/inner_loop.py
from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field

from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.oracle import SCORE, PoolRecord, outcome
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.harness.manager import HarnessManager
from youzi.llm.client import LLMClient
from youzi.refine.credit import apply_credit, merge_credit_reports
from youzi.refine.refiner import RefineReport, Refiner, RefinerConfig
from youzi.refine.signatures import extract_signatures
from youzi.replay.engine import ReplayEngine
from youzi.universe.universe import build_universe


class LoopConfig(BaseModel):
    horizon: int = 1                  # 延迟打分窗口(同 WalkForwardEval)
    refine_every: int = 1             # 每 N 交易日 refine 一次(默认每日)
    credit_window: int = 10           # 给 refiner 的证据窗口(最近 N 个已评分步)
    breaker_window: int = 20          # 滚动 expectancy 窗口(最近 N 个已评分候选)
    baseline_window: int = 20         # 基线 = 前 N 个已评分候选均值
    floor_abs: float = -0.2           # 绝对地板:rolling < floor_abs → 熔断
    floor_rel_margin: float = 0.15    # 相对地板:rolling < baseline - margin → 熔断
    breaker_min_samples: int = 40     # 已评分候选数 >= 此值才可能熔断


class RefineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    checkpoint_version: int | None
    report: RefineReport


class BreakerEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    rolling: float
    baseline: float | None
    reason: str
    rolled_back_to: int | None


class LoopReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    trajectory: Trajectory
    refine_events: list[RefineEvent] = Field(default_factory=list)
    breaker_events: list[BreakerEvent] = Field(default_factory=list)
    frozen_from: Date | None = None
    n_edits: int = 0

    def __bool__(self) -> bool:
        return True


class InnerLoop:
    """内环编排:交错 act→延迟打分→在线信用→(每日)refine,reset-free + 能力地板熔断。

    持有 HarnessManager(live H + EditLog + MetaTools + SnapshotStore);
    agent/refiner 由 manager.harness/manager.tools 构造,rollback 后 _rebind 重建。
    """

    def __init__(self, manager: HarnessManager, source, start: Date, end: Date,
                 agent_llm: LLMClient, refiner_llm: LLMClient,
                 config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None) -> None:
        self._mgr = manager
        self._source = source
        self._start = start
        self._end = end
        self._agent_llm = agent_llm
        self._refiner_llm = refiner_llm
        self._cfg = config or LoopConfig()
        self._refiner_cfg = refiner_config or RefinerConfig()
        self._rebind()

    def _rebind(self) -> None:
        """(重)绑定 agent/refiner 到 manager 当前的 harness/tools——启动与 rollback 后调用。"""
        self._agent = LLMAgentPolicy(self._mgr.harness, self._agent_llm)
        self._refiner = Refiner(self._mgr.harness, self._refiner_llm,
                                self._mgr.tools, self._refiner_cfg)

    def run(self) -> LoopReport:
        raise NotImplementedError  # Task 3 实现
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py -q`
Expected: PASS(2 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/loop/__init__.py youzi/loop/inner_loop.py tests/test_inner_loop.py
git commit -m "feat(loop): InnerLoop 配置/报告模型 + 构造/_rebind 骨架"
```

---

## Bundle B

### Task 3: `run()` 核心——交错 act + 延迟打分 + 在线信用

**Files:**
- Modify: `youzi/loop/inner_loop.py`(实现 `run`)
- Test: `tests/test_inner_loop.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
def _continued_src():
    """A 每日涨停(continued);3 日。"""
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {}
    for d in days:
        frames[("zt", d)] = pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]})
    return FakeSource(frames, days)


def test_run_interleaves_scoring_and_online_credit(tmp_path):
    src = _continued_src()
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_samples=10_000))  # 不熔断
    rep = loop.run()
    # 轨迹:3 步,前 2 步已打分(horizon=1),尾步未打分
    assert rep.trajectory.n_decisions() == 3
    assert [s.date for s in rep.trajectory.scored_steps()] == [date(2024, 6, 26), date(2024, 6, 27)]
    assert rep.trajectory.steps[2].scored is False
    assert rep.trajectory.steps[0].outcomes["A"].outcome == "continued"
    # 在线信用:技能 longtou(pattern "龙头接力")被引用且 continued → stats 在 H 内已更新
    st = mgr.harness.skills.get("longtou").stats
    assert st.n == 2 and st.wins == 2          # 2 个已打分决策都归因到 longtou 且 continued
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py::test_run_interleaves_scoring_and_online_credit -q`
Expected: FAIL(`NotImplementedError`)

- [ ] **Step 3: 实现 `run()`(替换 Task 2 的 `raise NotImplementedError`)**

```python
    def run(self) -> LoopReport:
        cfg = self._cfg
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        drafts: list[dict] = []
        pending: list[int] = []
        scored_steps: list[TrajectoryStep] = []
        per_step_credits: list = []
        scores: list[float] = []
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()
            universe = build_universe(engine.guarded_source, cursor)
            record.record(cursor, universe)
            decision = self._agent.decide(state, universe)
            entries: dict[str, EntrySnap] = {}
            for c in decision.candidates:
                if c.code in entries:
                    continue
                snap = universe.get(c.code)
                if snap is not None:
                    entries[c.code] = EntrySnap(code=c.code, status=snap.status, boards=snap.boards)
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "scored": False, "outcomes": {}})
            pending.append(idx)
            # 延迟打分(复刻 WalkForwardEval 机制)
            newly: list[TrajectoryStep] = []
            remaining: list[int] = []
            for j in pending:
                if idx >= j + cfg.horizon:
                    mem = record.get(days_seen[j + cfg.horizon])
                    assert mem is not None, f"BUG: {days_seen[j + cfg.horizon]} 未录成员"
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
                    step_j = TrajectoryStep(**drafts[j])
                    scored_steps.append(step_j)
                    newly.append(step_j)
                else:
                    remaining.append(j)
            pending = remaining
            # 在线信用(每个刚评分步调一次 apply_credit,就地改 stats、不重复)+ 熔断分数序列
            for step in newly:
                cr = apply_credit(Trajectory(steps=[step], horizon=cfg.horizon), self._mgr.harness)
                per_step_credits.append(cr)
                for sc in step.outcomes.values():
                    scores.append(sc.score)
            idx += 1
            if not engine.step():
                break
        traj = Trajectory(steps=[TrajectoryStep(**d) for d in drafts], horizon=cfg.horizon)
        return LoopReport(trajectory=traj, n_edits=len(self._mgr.log))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/loop/inner_loop.py tests/test_inner_loop.py
git commit -m "feat(loop): run() 交错 act+延迟打分+在线信用(reset-free 核心)"
```

---

### Task 4: `run()` + 每日 refine(checkpoint-before + 编辑 live H,次日可见)

**Files:**
- Modify: `youzi/loop/inner_loop.py`(扩展 `run`)
- Test: `tests/test_inner_loop.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
def test_refine_edits_visible_next_day_resetfree(tmp_path):
    src = _continued_src()
    # refiner:refine1 在 K-pass 退役 longtou;p/M 空;之后全空(MockLLM 重复末元素)
    refiner_scripts = ['{"ops": []}',
                       '{"ops": [{"tool": "retire_skill", "args": {"skill_id": "longtou"},'
                       ' "rationale": "示例退役"}]}',
                       '{"ops": []}']
    loop, mgr = _loop(tmp_path, src, [_decision("A")], refiner_scripts,
                      config=LoopConfig(breaker_min_samples=10_000))  # 不熔断
    rep = loop.run()
    # refine 每日触发(有新证据起):day1、day2 各一次
    assert [e.date for e in rep.refine_events] == [date(2024, 6, 27), date(2024, 6, 28)]
    assert rep.refine_events[0].checkpoint_version is not None
    # reset-free:day1 决策(call#1)系统提示仍含 longtou;day2(call#2)已不含(退役于 day1 refine 后)
    sys_day1 = loop._agent_llm.calls[1][0]
    sys_day2 = loop._agent_llm.calls[2][0]
    assert "龙头接力" in sys_day1
    assert "龙头接力" not in sys_day2
    # 编辑入 EditLog(带 rationale)
    assert any(r.tool == "retire_skill" and r.rationale for r in mgr.log.records())
```

> 注:`loop._agent_llm` 是构造时传入的 agent MockLLMClient;`.calls[i]` = 第 i 次 `(system, user)`。day0/1/2 决策分别是 calls[0/1/2]。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py::test_refine_edits_visible_next_day_resetfree -q`
Expected: FAIL(无 `refine_events`:当前 run() 不 refine)

- [ ] **Step 3: 扩展 `run()`(在 `pending = remaining` 后的在线信用块之后、`idx += 1` 之前,插入 refine 块;并把 `return` 改为带 refine_events)**

把 Task 3 的 `run()` 整体替换为(新增 `refine_events` 累计 + refine 块):

```python
    def run(self) -> LoopReport:
        cfg = self._cfg
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        drafts: list[dict] = []
        pending: list[int] = []
        scored_steps: list[TrajectoryStep] = []
        per_step_credits: list = []
        scores: list[float] = []
        refine_events: list[RefineEvent] = []
        last_ckpt: int | None = None
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()
            universe = build_universe(engine.guarded_source, cursor)
            record.record(cursor, universe)
            decision = self._agent.decide(state, universe)
            entries: dict[str, EntrySnap] = {}
            for c in decision.candidates:
                if c.code in entries:
                    continue
                snap = universe.get(c.code)
                if snap is not None:
                    entries[c.code] = EntrySnap(code=c.code, status=snap.status, boards=snap.boards)
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "scored": False, "outcomes": {}})
            pending.append(idx)
            newly: list[TrajectoryStep] = []
            remaining: list[int] = []
            for j in pending:
                if idx >= j + cfg.horizon:
                    mem = record.get(days_seen[j + cfg.horizon])
                    assert mem is not None, f"BUG: {days_seen[j + cfg.horizon]} 未录成员"
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
                    step_j = TrajectoryStep(**drafts[j])
                    scored_steps.append(step_j)
                    newly.append(step_j)
                else:
                    remaining.append(j)
            pending = remaining
            for step in newly:
                cr = apply_credit(Trajectory(steps=[step], horizon=cfg.horizon), self._mgr.harness)
                per_step_credits.append(cr)
                for sc in step.outcomes.values():
                    scores.append(sc.score)
            # 每日 refine(有新证据 + 到节奏):checkpoint-before → refiner.refine 编辑 live H
            if newly and (idx % cfg.refine_every == 0):
                ver = self._mgr.checkpoint(label=f"pre-refine {cursor}")
                last_ckpt = ver
                win = scored_steps[-cfg.credit_window:]
                win_traj = Trajectory(steps=win, horizon=cfg.horizon)
                credit = merge_credit_reports(per_step_credits[-cfg.credit_window:])
                sigs = extract_signatures(win_traj, self._mgr.harness)
                report = self._refiner.refine(win_traj, credit, sigs)
                refine_events.append(RefineEvent(date=cursor, checkpoint_version=ver, report=report))
            idx += 1
            if not engine.step():
                break
        traj = Trajectory(steps=[TrajectoryStep(**d) for d in drafts], horizon=cfg.horizon)
        return LoopReport(trajectory=traj, refine_events=refine_events, n_edits=len(self._mgr.log))
```

> `last_ckpt` 本任务未被读(熔断 Task 5 才用),但 checkpoint-before 已在每次 refine 落地,Task 5 直接复用。

- [ ] **Step 4: 跑测试确认通过 + 回归**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py -q`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/loop/inner_loop.py tests/test_inner_loop.py
git commit -m "feat(loop): run() 每日 refine(checkpoint-before + 编辑 live H,reset-free 次日可见)"
```

---

### Task 5: `run()` + 能力地板熔断(rollback 上个 checkpoint + 冻结)

**Files:**
- Modify: `youzi/loop/inner_loop.py`(扩展 `run`)
- Test: `tests/test_inner_loop.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
def _nuke_src(n_days):
    """每日 C_i 涨停;次日 C_i 跌停(被选后必 nuked)。"""
    days = [date(2024, 6, 1) + timedelta(days=k) for k in range(n_days)]
    frames = {}
    for i, d in enumerate(days):
        frames[("zt", d)] = pd.DataFrame({"code": [f"C{i}"], "name": [f"C{i}"], "boards": [1]})
        if i >= 1:
            frames[("dt", d)] = pd.DataFrame({"code": [f"C{i-1}"], "name": [f"C{i-1}"]})
    return FakeSource(frames, days)


def test_breaker_trips_rolls_back_and_freezes(tmp_path):
    n = 8
    src = _nuke_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]    # 每日选当日涨停 C_i
    cfg = LoopConfig(breaker_window=2, baseline_window=2, breaker_min_samples=3,
                     floor_abs=-0.5, refine_every=1)
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'], config=cfg)
    rep = loop.run()
    # 每个被选 code 次日跌停 → 全 nuked(-1)→ rolling 跌破 floor_abs(-0.5)→ 熔断
    assert len(rep.breaker_events) == 1
    be = rep.breaker_events[0]
    assert be.reason in ("rolling<floor_abs", "rolling<baseline-margin")
    assert be.rolled_back_to is not None          # 熔断前已有 refine → 有 checkpoint
    assert rep.frozen_from == be.date
    # 冻结后不再有 refine
    assert all(e.date < rep.frozen_from for e in rep.refine_events)


def test_breaker_freezes_without_checkpoint_when_no_refine(tmp_path):
    n = 6
    src = _nuke_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]
    # refine_every 极大 → 永不 refine → 熔断时无 checkpoint
    cfg = LoopConfig(breaker_window=2, baseline_window=2, breaker_min_samples=3,
                     floor_abs=-0.5, refine_every=10_000)
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'], config=cfg)
    rep = loop.run()
    assert len(rep.breaker_events) == 1
    assert rep.breaker_events[0].rolled_back_to is None       # 无 checkpoint → 只冻结
    assert rep.refine_events == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py::test_breaker_trips_rolls_back_and_freezes -q`
Expected: FAIL(无 `breaker_events`:当前 run() 不熔断)

- [ ] **Step 3: 扩展 `run()`(加 `frozen`/`frozen_from`/`breaker_events`;在线信用块后、refine 块前插入熔断检查;refine 块加 `not frozen` 守卫)**

把 Task 4 的 `run()` 整体替换为:

```python
    def run(self) -> LoopReport:
        cfg = self._cfg
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        drafts: list[dict] = []
        pending: list[int] = []
        scored_steps: list[TrajectoryStep] = []
        per_step_credits: list = []
        scores: list[float] = []
        refine_events: list[RefineEvent] = []
        breaker_events: list[BreakerEvent] = []
        last_ckpt: int | None = None
        frozen = False
        frozen_from: Date | None = None
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()
            universe = build_universe(engine.guarded_source, cursor)
            record.record(cursor, universe)
            decision = self._agent.decide(state, universe)
            entries: dict[str, EntrySnap] = {}
            for c in decision.candidates:
                if c.code in entries:
                    continue
                snap = universe.get(c.code)
                if snap is not None:
                    entries[c.code] = EntrySnap(code=c.code, status=snap.status, boards=snap.boards)
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "scored": False, "outcomes": {}})
            pending.append(idx)
            newly: list[TrajectoryStep] = []
            remaining: list[int] = []
            for j in pending:
                if idx >= j + cfg.horizon:
                    mem = record.get(days_seen[j + cfg.horizon])
                    assert mem is not None, f"BUG: {days_seen[j + cfg.horizon]} 未录成员"
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
                    step_j = TrajectoryStep(**drafts[j])
                    scored_steps.append(step_j)
                    newly.append(step_j)
                else:
                    remaining.append(j)
            pending = remaining
            for step in newly:
                cr = apply_credit(Trajectory(steps=[step], horizon=cfg.horizon), self._mgr.harness)
                per_step_credits.append(cr)
                for sc in step.outcomes.values():
                    scores.append(sc.score)
            # 能力地板熔断(自相对 + 绝对;只触发一次)
            if not frozen and len(scores) >= cfg.breaker_min_samples:
                baseline = sum(scores[:cfg.baseline_window]) / cfg.baseline_window
                window = scores[-cfg.breaker_window:]
                rolling = sum(window) / len(window)
                reason: str | None = None
                if rolling < cfg.floor_abs:
                    reason = "rolling<floor_abs"
                elif rolling < baseline - cfg.floor_rel_margin:
                    reason = "rolling<baseline-margin"
                if reason is not None:
                    rolled: int | None = None
                    if last_ckpt is not None:
                        self._mgr.rollback_to(last_ckpt)
                        self._rebind()
                        rolled = last_ckpt
                    frozen = True
                    frozen_from = cursor
                    breaker_events.append(BreakerEvent(date=cursor, rolling=rolling, baseline=baseline,
                                                       reason=reason, rolled_back_to=rolled))
            # 每日 refine(未冻结 + 有新证据 + 到节奏)
            if not frozen and newly and (idx % cfg.refine_every == 0):
                ver = self._mgr.checkpoint(label=f"pre-refine {cursor}")
                last_ckpt = ver
                win = scored_steps[-cfg.credit_window:]
                win_traj = Trajectory(steps=win, horizon=cfg.horizon)
                credit = merge_credit_reports(per_step_credits[-cfg.credit_window:])
                sigs = extract_signatures(win_traj, self._mgr.harness)
                report = self._refiner.refine(win_traj, credit, sigs)
                refine_events.append(RefineEvent(date=cursor, checkpoint_version=ver, report=report))
            idx += 1
            if not engine.step():
                break
        traj = Trajectory(steps=[TrajectoryStep(**d) for d in drafts], horizon=cfg.horizon)
        return LoopReport(trajectory=traj, refine_events=refine_events,
                          breaker_events=breaker_events, frozen_from=frozen_from,
                          n_edits=len(self._mgr.log))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_inner_loop.py -q`
Expected: PASS(6 passed)

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS(217 + 本阶段新增 = 226,全绿,离线不触网)

- [ ] **Step 6: 提交**

```bash
git add youzi/loop/inner_loop.py tests/test_inner_loop.py
git commit -m "feat(loop): run() 能力地板熔断(自相对+绝对→rollback上个checkpoint+rebind+冻结)"
```

---

## 收尾(Task 5 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`:Phase-1b-3a 完成 + 残留债务。
- [ ] 更新 `后续开发文档.md`:状态表 1b-3 → 拆 3a(✅)/3b(下一步);§4 路线图;§5 债务。
- [ ] 更新 memory `youzi-self-evolving-project.md` + `MEMORY.md`:下一步 → 1b-3b(HCH/Hexpert/Hmin 度量)。

**本阶段债务(登记,非阻塞)**:① 熔断默认初值(floor_abs/margin/window)为初值,实盘调;② rollback 到"上个 checkpoint"(非"退化窗口前 good 态");③ 每日 checkpoint = N 个磁盘快照(keep-last-K/内存 ring 增强);④ 基线含早期 refine 效应(纯种子基线需 no-refine burn-in);⑤ 影子 Hexpert 严格地板 + HCH/Hexpert/Hmin 三方对比 = 1b-3b。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage(逐条对 spec):**
- §4.1 `merge_credit_reports` → Task 1 ✅;§4.2 模型(LoopConfig/RefineEvent/BreakerEvent/LoopReport)→ Task 2 ✅;§4.3 `InnerLoop.__init__`/`_rebind` → Task 2 ✅,`run()` 交错+延迟打分+在线信用 → Task 3 ✅,每日 refine+checkpoint-before → Task 4 ✅,熔断+rollback+rebind+冻结(含无 checkpoint)→ Task 5 ✅。
- §6 防火墙:run() 复刻 walk 的 ≤t 决策 + 延迟打分 + 只用已实现证据,Trajectory 无 source 句柄 → 由构造保证,终审复核。
- §7 测试:merge(Task1)、模型/构造/rebind(Task2)、交错+在线信用(Task3)、refine+reset-free 可见(Task4)、熔断 trip/rollback/freeze + 无 checkpoint(Task5);§7 回归 → Task5 Step5。
- §8 DoD 全覆盖;§9 out-of-scope 未触碰(无 HCH/Hexpert/Hmin、无影子 Hexpert)。

**2. Placeholder scan:** 无 TBD/TODO;每个代码步给完整代码 + 确切命令/预期。run() 在 Task 3/4/5 各给完整方法(逐步扩展,非"参考 Task N")。

**3. Type consistency:** `LoopConfig`(horizon/refine_every/credit_window/breaker_window/baseline_window/floor_abs/floor_rel_margin/breaker_min_samples)、`RefineEvent(date/checkpoint_version/report)`、`BreakerEvent(date/rolling/baseline/reason/rolled_back_to)`、`LoopReport(trajectory/refine_events/breaker_events/frozen_from/n_edits)`、`InnerLoop(manager,source,start,end,agent_llm,refiner_llm,config,refiner_config)`、`_rebind`/`run`、`merge_credit_reports`、`apply_credit`/`extract_signatures`/`Refiner.refine` 跨 Task 一致;复用 `ScoredCandidate(decision_date/code/pattern/outcome/score)`、`EntrySnap(code/status/boards)`、`Trajectory/TrajectoryStep`、`HarnessManager(harness/log/tools/checkpoint/rollback_to)`、`LLMAgentPolicy._harness`、`Refiner._h` 均与既有源一致。
