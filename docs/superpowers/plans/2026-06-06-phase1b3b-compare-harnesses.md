# Phase-1b-3b:HCH/Hexpert/Hmin 三方度量对比 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个 `compare_harnesses(...)` 把 HCH(自精炼内环)/ Hexpert(冻结种子 H + agent)/ Hmin(HighestBoard + NoTrade)四路跑在同窗同 oracle 上,出 `ComparisonReport`(三/四路 EvalReport + HCH−Hexpert delta + `hch_beats_hexpert` verdict + HCH 环信息),回答"自进化是否优于/退化于 frozen"。

**Architecture:** 新增 `youzi/loop/compare.py`(与 `inner_loop` 同包,顶层组合 InnerLoop + WalkForwardEval + baselines + LLMAgentPolicy)。用 **factory 注入**(harness/llm/store),每路拿独立 fresh 种子 H 与独立 LLM client(防 HCH 改 H / MockLLM 计数污染 Hexpert)。纯组合,不改 InnerLoop/WalkForwardEval。

**Tech Stack:** Python · pydantic(frozen 报告)· pytest(全离线:每路独立 `MockLLMClient` via 有状态 factory + `FakeSource` + `SnapshotStore(tmp_path)`,不触网)。

**分支:** `phase-1b3b-compare`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-06-phase1b3b-compare-harnesses-design.md`。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **230 passed**。

**Bundle:** 单 bundle(Task 1-2),小切片。

---

### Task 1: `compare.py` 报告模型(ArmReport / ComparisonReport)

**Files:**
- Create: `youzi/loop/compare.py`(本任务只放模型 + import;`compare_harnesses` 留 Task 2)
- Test: `tests/test_compare.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_compare.py
import pytest

from youzi.loop.compare import ArmReport, ComparisonReport
from youzi.eval.metrics import EvalReport


def _empty_eval():
    return EvalReport(n_decisions=0, n_no_trade=0, n_candidates=0,
                      hit_rate=0.0, nuke_rate=0.0, mean_score=0.0)


def test_models_frozen_and_truthy():
    arm = ArmReport(name="HCH", report=_empty_eval(), n_refines=3,
                    n_breaker_trips=0, frozen_from=None)
    cr = ComparisonReport(arms={"HCH": arm},
                          hch_minus_hexpert_mean_score=0.0,
                          hch_minus_hexpert_hit_rate=0.0,
                          hch_minus_hexpert_nuke_rate=0.0,
                          hch_beats_hexpert=False)
    assert bool(cr) is True
    assert cr.arms["HCH"].n_refines == 3
    with pytest.raises(Exception):
        cr.hch_beats_hexpert = True            # frozen
    with pytest.raises(Exception):
        arm.name = "X"                          # frozen
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_compare.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.loop.compare`)

- [ ] **Step 3: 实现模型 + import**

```python
# youzi/loop/compare.py
from __future__ import annotations

from datetime import date as Date
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.baselines import HighestBoardPolicy, NoTradePolicy
from youzi.eval.metrics import EvalReport
from youzi.eval.walk_forward import WalkForwardEval, report_from_trajectory
from youzi.harness.harness import HarnessState
from youzi.harness.manager import HarnessManager
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import LLMClient
from youzi.loop.inner_loop import InnerLoop, LoopConfig
from youzi.refine.refiner import RefinerConfig


class ArmReport(BaseModel):
    """一路对比的结果(frozen)。HCH 额外带环信息。"""
    model_config = ConfigDict(frozen=True)
    name: str
    report: EvalReport
    n_refines: int | None = None         # 仅 HCH:refine 次数
    n_breaker_trips: int | None = None   # 仅 HCH:熔断次数
    frozen_from: Date | None = None      # 仅 HCH:熔断冻结起始日


class ComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    arms: dict[str, ArmReport] = Field(default_factory=dict)
    hch_minus_hexpert_mean_score: float
    hch_minus_hexpert_hit_rate: float
    hch_minus_hexpert_nuke_rate: float
    hch_beats_hexpert: bool

    def __bool__(self) -> bool:
        return True
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_compare.py -q`
Expected: PASS(1 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/loop/compare.py tests/test_compare.py
git commit -m "feat(loop): compare 报告模型 ArmReport/ComparisonReport"
```

---

### Task 2: `compare_harnesses` 四路对比

**Files:**
- Modify: `youzi/loop/compare.py`(加 `compare_harnesses`)
- Test: `tests/test_compare.py`(追加)

- [ ] **Step 1: 追加失败测试**

```python
from datetime import date

import pandas as pd

from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import MockLLMClient
from tests.conftest import FakeSource
from tests.test_inner_loop import _seed_h, _decision

_PICK_W = _decision("W")
_NO_TRADE = '{"candidates": [], "no_trade_reason": "空仓"}'


def _w_src():
    """单码 W 每日涨停(continued);3 日。"""
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame({"code": ["W"], "name": ["赢家"], "boards": [2]}) for d in days}
    return FakeSource(frames, days)


class _SeqFactory:
    """第 k 次调用返回第 k 个脚本对应的 client(超出则用最后一个);记 calls。"""
    def __init__(self, scripts):
        self._scripts = scripts
        self._i = 0
        self.calls = 0

    def __call__(self):
        self.calls += 1
        c = MockLLMClient(self._scripts[min(self._i, len(self._scripts) - 1)])
        self._i += 1
        return c


class _CountFactory:
    def __init__(self, fn):
        self._fn = fn
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._fn()


def _compare(tmp_path, agent_scripts, refiner_script='{"ops": []}', cfg=None):
    src = _w_src()
    agent_f = _SeqFactory(agent_scripts)
    refiner_f = _SeqFactory([refiner_script])
    store_f = _CountFactory(lambda: SnapshotStore(tmp_path))
    harness_f = _CountFactory(_seed_h)
    rep = compare_harnesses(
        harness_f, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=agent_f, refiner_llm_factory=refiner_f,
        store_factory=store_f, loop_config=cfg or LoopConfig())
    return rep, agent_f, refiner_f, store_f, harness_f


def test_four_arms_and_verdict_true(tmp_path):
    # HCH 选 W(continued, mean=1.0);Hexpert 空仓(mean=0.0)→ HCH 胜
    rep, *_ = _compare(tmp_path, [_PICK_W, _NO_TRADE])
    assert set(rep.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    assert rep.arms["HCH"].report.mean_score == 1.0
    assert rep.arms["Hexpert"].report.mean_score == 0.0
    assert rep.arms["Hmin_highest"].report.mean_score == 1.0   # HighestBoard 也追 W
    assert rep.arms["Hmin_notrade"].report.mean_score == 0.0
    assert rep.hch_minus_hexpert_mean_score == 1.0
    assert rep.hch_beats_hexpert is True
    assert rep.arms["HCH"].n_refines >= 1                       # W 续板有证据 → refine 触发
    assert rep.arms["HCH"].n_breaker_trips == 0


def test_verdict_false_when_hch_worse(tmp_path):
    # HCH 空仓(mean=0.0);Hexpert 选 W(mean=1.0)→ HCH 退化于 frozen
    rep, *_ = _compare(tmp_path, [_NO_TRADE, _PICK_W])
    assert rep.hch_minus_hexpert_mean_score == -1.0
    assert rep.hch_beats_hexpert is False
    assert rep.arms["HCH"].n_refines == 0                       # 全空仓无评分证据 → 不 refine


def test_same_script_delta_zero(tmp_path):
    # HCH 与 Hexpert 同脚本(都选 W)→ delta=0、verdict False,但 HCH 仍 refine(MockLLM 局限:refine 不改脚本化决策)
    rep, *_ = _compare(tmp_path, [_PICK_W])     # 两路都拿到 _PICK_W(SeqFactory 超出用末元素)
    assert rep.arms["HCH"].report.mean_score == rep.arms["Hexpert"].report.mean_score == 1.0
    assert rep.hch_minus_hexpert_mean_score == 0.0
    assert rep.hch_beats_hexpert is False
    assert rep.arms["HCH"].n_refines >= 1


def test_factory_call_counts_and_isolation(tmp_path):
    rep, agent_f, refiner_f, store_f, harness_f = _compare(tmp_path, [_PICK_W, _NO_TRADE])
    assert harness_f.calls == 2      # HCH + Hexpert 各一份 fresh H
    assert agent_f.calls == 2        # HCH agent + Hexpert agent
    assert refiner_f.calls == 1      # 仅 HCH refiner
    assert store_f.calls == 1        # 仅 HCH 用 store
```

> 复用 `tests/test_inner_loop.py` 的 `_seed_h`(返回含技能 `longtou`/name_cn 龙头接力 + mutable doctrine 的 fresh HarnessState)与 `_decision`(pattern "龙头接力");`_seed_h` 每次调用构造新实例,适合当 harness_factory。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_compare.py::test_four_arms_and_verdict_true -q`
Expected: FAIL(`ImportError: cannot import name 'compare_harnesses'`)

- [ ] **Step 3: 实现 `compare_harnesses`(加到 `youzi/loop/compare.py` 末尾)**

```python
def compare_harnesses(
    harness_factory: Callable[[], HarnessState],
    source, start: Date, end: Date, *,
    agent_llm_factory: Callable[[], LLMClient],
    refiner_llm_factory: Callable[[], LLMClient],
    store_factory: Callable[[], SnapshotStore],
    loop_config: LoopConfig | None = None,
    refiner_config: RefinerConfig | None = None,
) -> ComparisonReport:
    """四路同窗同 oracle 对比:HCH(自精炼内环)vs Hexpert(冻结种子 H + agent,无 Refiner)
    vs Hmin(HighestBoard / NoTrade)。每路独立 fresh 种子 H + 独立 LLM client(防交叉污染)。"""
    cfg = loop_config or LoopConfig()

    # HCH:自精炼内环
    mgr = HarnessManager(harness_factory(), store_factory())
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(),
                     refiner_llm_factory(), cfg, refiner_config)
    lr = loop.run()
    hch_eval = report_from_trajectory(lr.trajectory)
    hch_arm = ArmReport(name="HCH", report=hch_eval,
                        n_refines=len(lr.refine_events),
                        n_breaker_trips=len(lr.breaker_events),
                        frozen_from=lr.frozen_from)

    # Hexpert:冻结种子 H + agent(无 Refiner → H 全程不变)
    wf = WalkForwardEval(source, start, end, horizon=cfg.horizon)
    hexpert_eval = wf.run(LLMAgentPolicy(harness_factory(), agent_llm_factory()))
    hexpert_arm = ArmReport(name="Hexpert", report=hexpert_eval)

    # Hmin:裸基线(同一 wf 实例可复用:run() 内部每次 new ReplayEngine,无状态残留)
    hmin_hb = ArmReport(name="Hmin_highest", report=wf.run(HighestBoardPolicy()))
    hmin_nt = ArmReport(name="Hmin_notrade", report=wf.run(NoTradePolicy()))

    d_mean = hch_eval.mean_score - hexpert_eval.mean_score
    d_hit = hch_eval.hit_rate - hexpert_eval.hit_rate
    d_nuke = hch_eval.nuke_rate - hexpert_eval.nuke_rate
    return ComparisonReport(
        arms={"HCH": hch_arm, "Hexpert": hexpert_arm,
              "Hmin_highest": hmin_hb, "Hmin_notrade": hmin_nt},
        hch_minus_hexpert_mean_score=d_mean,
        hch_minus_hexpert_hit_rate=d_hit,
        hch_minus_hexpert_nuke_rate=d_nuke,
        hch_beats_hexpert=d_mean > 0,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_compare.py -q`
Expected: PASS(5 passed)

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS(230 + 本阶段新增 = 235,全绿,离线不触网)

- [ ] **Step 6: 提交**

```bash
git add youzi/loop/compare.py tests/test_compare.py
git commit -m "feat(loop): compare_harnesses 四路同窗同oracle对比(HCH/Hexpert/Hmin + delta/verdict)"
```

---

## 收尾(Task 2 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`:Phase-1b-3b 完成 + 债务。
- [ ] 更新 `后续开发文档.md`:状态表 1b-3b → ✅;§4 路线图(下一步 1b-3c 影子地板 / 1c);§5 债务。
- [ ] 更新 memory `youzi-self-evolving-project.md` + `MEMORY.md`:下一步 → 1b-3c(影子 Hexpert 严格地板)或 1c。

**本阶段债务(登记,非阻塞)**:① 影子 Hexpert 环内严格地板 = 1b-3c;② 按 regime 分层对比(需 `G_cycle` 分类器);③ N 日/收益幅度 oracle、成本/滑点(需 OHLCV);④ 多 episode/多窗口聚合对比;⑤ **MockLLM 测不了 refine 实效**(忽略提示)——真实"自进化是否胜 frozen"需真实 DeepSeek 多日跑(先跑 `scripts/smoke_deepseek_agent.py`)。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage:** §4.1 模型(ArmReport/ComparisonReport)→ Task 1 ✅;§4.2 `compare_harnesses`(HCH/Hexpert/Hmin 四路 + factory 注入 + delta/verdict + HCH 环信息)→ Task 2 ✅;§6 防火墙(复用 InnerLoop/walk,不持 source)→ 由组合保证,终审复核;§7 测试(四路齐全/delta·verdict 机器/同脚本基线/factory 隔离)→ Task 2 全覆盖;§8 DoD 全覆盖;§9 out-of-scope(影子地板)未触碰。真实种子端到端(spec §7)→ 终审阶段补(同 1b-3a 的 real-seeds 终审测试)。

**2. Placeholder scan:** 无 TBD/TODO;每步完整代码 + 确切命令/预期。

**3. Type consistency:** `compare_harnesses(harness_factory, source, start, end, *, agent_llm_factory, refiner_llm_factory, store_factory, loop_config, refiner_config)`、`ArmReport(name/report/n_refines/n_breaker_trips/frozen_from)`、`ComparisonReport(arms/hch_minus_hexpert_{mean_score,hit_rate,nuke_rate}/hch_beats_hexpert)` 跨 Task 1/2 一致;复用 `InnerLoop(mgr,source,start,end,agent_llm,refiner_llm,cfg,refiner_cfg)`、`LoopReport(trajectory/refine_events/breaker_events/frozen_from)`、`WalkForwardEval(source,start,end,horizon).run(policy)`、`report_from_trajectory`、`LLMAgentPolicy(harness,llm)`、`HarnessManager(harness,store)`、`SnapshotStore(path)`、`HighestBoardPolicy/NoTradePolicy`、`EvalReport(mean_score/hit_rate/nuke_rate)` 均与既有源一致。
