# Phase-0b-1 Harness 状态模型 + 种子载入器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `seeds/*.json` 的游资 playbook 种子,载入成**类型化、相位归一、可查询**的 Harness 状态 `H=(p,K,M)`(doctrine / 技能库 / 记忆 + 情绪周期状态机)。

**Architecture:** 在 `youzi/harness/` 新增一层。`regime`(相位词表归一)← `skill`/`memory_item`/`doctrine`/`cycle`(pydantic 模型,各带 `from_seed` 归一构造)← `registry`/`memory_store`(集合容器 + 查询)← `harness`(`HarnessState` 总容器 + 查询助手)← `loader`(读 `seeds/*.json` → 校验 + 归一 → `HarnessState`)。纯 Python + pydantic,**全程离线可测**;集成测试直接载入**真实** `seeds/`(57 技能/21 记忆/22 doctrine/7 相位)。

**Tech Stack:** Python 3.11+ · pydantic v2 · pytest。(无新依赖;沿用 Phase-0a 的 `.venv`/`pyproject.toml`。)

**范围边界(本计划只做"读/载入/查询"):** 不做 CRUD 编辑(write/patch/retire/revive/process_memory/rewrite_doctrine)、不做版本化快照/回滚、不做 immutable-core 写保护——这些是 **Phase-0b-2(Refiner 的编辑底座)**,随 Agent/Refiner 一起落地。本计划交付"能把种子 playbook 载入成可查询的 H"。

**关键设计点(对应蓝图):**
- **相位归一(P0 ② 一致 regime 词表):** 种子里 `applicable_regime` 用词不统一(启动/题材启动…)。`regime.split_regimes` 把变体归一到 7 个 canonical 相位 `[混沌冰点·修复启动·情绪回暖·题材启动·主升·震荡补涨·退潮]`,并把生态标签 `[连板/容量/20cm/次新/超跌/ST/北交 生态]` 单列;非相位的触发条件(如"情绪极值1500-")丢弃(不污染 regime 字段)。映射规则见 `seeds/README.md`。
- **decay-weighted 技能统计(蓝图 §8,放弃"单调累积"):** `SkillStats` 用 EWMA 滚动胜率(`record(win, decay)`),为后续 time×regime 双衰减留接口。本阶段种子统计为空初值。
- **不可变核标记(蓝图 §6.5):** `DoctrineEntry.immutable` 如实载入(纪律红线=true);**写保护的强制**在 0b-2,本阶段只读出 + 提供 `immutable_core()` 查询。
- **可溯源:** 模型保留 `source_lines`(指向 `/tmp/lunhui.txt` 或轮回.docx 行号)。

---

## File Structure

```
youzi/harness/
  __init__.py
  regime.py            # CANONICAL_PHASES / ECOLOGY_TAGS / classify_regime / split_regimes
  skill.py             # SkillStats(可变, EWMA) + Skill(pydantic, from_seed 归一)
  memory_item.py       # Importance(衰减) + Lesson(pydantic, from_seed)
  doctrine.py          # DoctrineEntry(pydantic, from_seed) + Doctrine(容器: for_regime/immutable_core)
  cycle.py             # Transition + EmotionPhase + StateMachine(from_seed_list)
  registry.py          # SkillRegistry(from_skills; get; by_status/by_phase/by_type/by_ecology)
  memory_store.py      # MemoryStore(from_lessons; by_regime/by_outcome/by_pattern)
  harness.py           # HarnessState(doctrine,skills,memory,cycle) + active_skills_for(phase)
  loader.py            # load_seeds(seeds_dir) -> HarnessState (校验 + 归一)
tests/
  test_regime.py
  test_skill.py
  test_memory_item.py
  test_doctrine.py
  test_cycle.py
  test_registry.py
  test_memory_store.py
  test_harness.py
  test_loader_real_seeds.py     # 载入真实 seeds/,断言计数 + 全部归一/合法
```

**全局类型契约(后续任务一致引用,勿改名):**
- `regime.split_regimes(raw: list[str]) -> tuple[list[str], list[str]]`(返回 `(phases, ecologies)`)。
- `Skill.from_seed(d: dict) -> Skill`;字段 `skill_id/name_cn/type/applicable_regime/phases/ecologies/trigger/entry/exit_stop/taboo/depends_on/examples/source_lines/status/notes/stats`。
- `Lesson.from_seed(d: dict) -> Lesson`;`Doctrine` 容器 `from_seed_list`;`StateMachine.from_seed_list`。
- `SkillRegistry.from_skills(list[Skill])`,方法 `get/by_status/by_phase/by_type/by_ecology`。
- `MemoryStore.from_lessons(list[Lesson])`,方法 `by_regime/by_outcome/by_pattern`。
- `HarnessState`(属性 `doctrine: Doctrine`,`skills: SkillRegistry`,`memory: MemoryStore`,`cycle: StateMachine`),方法 `active_skills_for(phase: str) -> list[Skill]`。
- `loader.load_seeds(seeds_dir: str | Path) -> HarnessState`。

---

## Task 0: harness 包脚手架

**Files:** Create `youzi/harness/__init__.py`

- [ ] **Step 1: 建包**

```python
# youzi/harness/__init__.py
"""Harness 状态层 H=(p,G,K,M):doctrine / 技能库 / 记忆 / 情绪周期状态机。"""
```

- [ ] **Step 2: 确认可被发现**

Run: `cd "/Volumes/kairos/引力场量化/youzi-自进化版" && source .venv/bin/activate && python -c "import youzi.harness"`
Expected: 无输出、无错误。

- [ ] **Step 3: Commit**

```bash
git add youzi/harness/__init__.py
git commit -m "chore(harness): Phase-0b-1 包脚手架"
```

---

## Task 1: 相位归一 `regime`

**Files:** Create `youzi/harness/regime.py`; Test `tests/test_regime.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_regime.py
from youzi.harness.regime import classify_regime, split_regimes, CANONICAL_PHASES


def test_classify_phase_variants():
    assert classify_regime("情绪冰点") == ("phase", "混沌冰点")
    assert classify_regime("修复启动") == ("phase", "修复启动")
    assert classify_regime("启动") == ("phase", "题材启动")
    assert classify_regime("主升期") == ("phase", "主升")
    assert classify_regime("震荡补涨") == ("phase", "震荡补涨")
    assert classify_regime("退潮期") == ("phase", "退潮")


def test_classify_ecology_and_other():
    assert classify_regime("连板生态") == ("ecology", "连板生态")
    assert classify_regime("20cm生态") == ("ecology", "20cm生态")
    assert classify_regime("情绪极值1500-") == ("other", None)
    assert classify_regime("") == ("other", None)


def test_split_regimes_dedup_and_order():
    phases, ecologies = split_regimes(
        ["启动", "修复", "连板生态", "情绪极值1500-", "启动"])
    assert phases == ["题材启动", "修复启动"]   # 首见序, 去重
    assert ecologies == ["连板生态"]


def test_canonical_phases_are_seven():
    assert len(CANONICAL_PHASES) == 7
    assert CANONICAL_PHASES[0] == "混沌冰点" and CANONICAL_PHASES[-1] == "退潮"
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_regime.py -v`
Expected: FAIL（`ModuleNotFoundError: youzi.harness.regime`）

- [ ] **Step 3: 实现 `youzi/harness/regime.py`**

```python
from __future__ import annotations

CANONICAL_PHASES = ["混沌冰点", "修复启动", "情绪回暖", "题材启动", "主升", "震荡补涨", "退潮"]
ECOLOGY_TAGS = ["连板生态", "容量生态", "20cm生态", "次新生态", "超跌生态", "ST生态", "北交生态"]

# 优先级有序:"修复" 必须在 "启动" 之前判定,否则 "修复启动" 会被错归到 题材启动。
_PHASE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("混沌", "冰点"), "混沌冰点"),
    (("修复",), "修复启动"),
    (("回暖",), "情绪回暖"),
    (("题材启动", "启动"), "题材启动"),
    (("主升",), "主升"),
    (("震荡", "补涨"), "震荡补涨"),
    (("退潮",), "退潮"),
]


def classify_regime(raw: str) -> tuple[str, str | None]:
    """归一单个 regime 串。返回 (kind, value),kind ∈ {'phase','ecology','other'}。"""
    s = (raw or "").strip()
    if not s:
        return ("other", None)
    for tag in ECOLOGY_TAGS:
        if tag in s:
            return ("ecology", tag)
    for keywords, phase in _PHASE_RULES:
        if any(k in s for k in keywords):
            return ("phase", phase)
    return ("other", None)


def split_regimes(raw: list[str]) -> tuple[list[str], list[str]]:
    """把 raw applicable_regime 列表归一为 (canonical_phases, ecologies),首见序去重,非相位丢弃。"""
    phases: list[str] = []
    ecologies: list[str] = []
    for item in raw or []:
        kind, value = classify_regime(item)
        if kind == "phase" and value not in phases:
            phases.append(value)
        elif kind == "ecology" and value not in ecologies:
            ecologies.append(value)
    return (phases, ecologies)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_regime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/regime.py tests/test_regime.py
git commit -m "feat(harness): 相位词表归一 regime"
```

---

## Task 2: 技能模型 `skill`（含 decay-weighted 统计）

**Files:** Create `youzi/harness/skill.py`; Test `tests/test_skill.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skill.py
from youzi.harness.skill import Skill, SkillStats


def test_skill_stats_ewma_winrate():
    st = SkillStats()
    assert st.n == 0 and st.ewma_winrate is None
    st.record(win=True, decay=0.5)
    assert st.n == 1 and st.ewma_winrate == 1.0     # 首样本直接置入
    st.record(win=False, decay=0.5)
    # ewma = 0.5*0 + 0.5*1.0 = 0.5
    assert st.n == 2 and abs(st.ewma_winrate - 0.5) < 1e-9


def test_skill_from_seed_normalizes_regime():
    seed = {
        "skill_id": "relay_2to3_w2s", "name_cn": "二进三弱转强", "type": "pattern",
        "applicable_regime": ["主升", "启动", "连板生态", "情绪极值1500-"],
        "trigger": "二板放量封死", "entry": "竞价弱转强扫", "exit_stop": "承接无力放弃",
        "taboo": ["板块死口不做"], "status": "active", "source_lines": [893, 894],
    }
    s = Skill.from_seed(seed)
    assert s.skill_id == "relay_2to3_w2s"
    assert s.phases == ["主升", "题材启动"]       # 归一 + 去重, 顺序保留
    assert s.ecologies == ["连板生态"]
    assert s.applicable_regime == ["主升", "启动", "连板生态", "情绪极值1500-"]  # 原始保留
    assert s.stats.n == 0


def test_skill_defaults_for_optional_fields():
    s = Skill.from_seed({
        "skill_id": "x", "name_cn": "x", "type": "feature",
        "applicable_regime": [], "trigger": "t", "entry": "e", "exit_stop": "x",
        "status": "incubating",
    })
    assert s.taboo == [] and s.depends_on == [] and s.examples == []
    assert s.notes == "" and s.phases == [] and s.ecologies == []
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_skill.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/skill.py`**

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from youzi.harness.regime import split_regimes

SkillType = Literal["pattern", "feature", "failure_detector"]
SkillStatus = Literal["active", "incubating", "dormant", "retired"]


class SkillStats(BaseModel):
    """技能滚动绩效(可变, 运行期更新)。EWMA 胜率为 time-decay 雏形,后续接 regime 双衰减。"""
    n: int = 0
    wins: int = 0
    losses: int = 0
    ewma_winrate: float | None = None
    pnl_ratio: float | None = None
    expectancy: float | None = None
    oracle_gap: float | None = None

    def record(self, win: bool, decay: float = 0.1) -> None:
        """记一次结果。首样本直接置入 ewma;之后 ewma = decay*x + (1-decay)*ewma。"""
        x = 1.0 if win else 0.0
        self.n += 1
        self.wins += int(win)
        self.losses += int(not win)
        self.ewma_winrate = x if self.ewma_winrate is None else decay * x + (1 - decay) * self.ewma_winrate


class Skill(BaseModel):
    """K 技能(可变 harness 状态;Refiner 后续编辑)。"""
    skill_id: str
    name_cn: str
    type: SkillType
    applicable_regime: list[str] = Field(default_factory=list)   # 原始(可溯源)
    phases: list[str] = Field(default_factory=list)              # 归一 canonical 相位
    ecologies: list[str] = Field(default_factory=list)           # 归一生态标签
    trigger: str
    entry: str
    exit_stop: str
    taboo: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    source_lines: list[int] = Field(default_factory=list)
    status: SkillStatus = "incubating"
    notes: str = ""
    stats: SkillStats = Field(default_factory=SkillStats)

    @classmethod
    def from_seed(cls, d: dict) -> "Skill":
        phases, ecologies = split_regimes(d.get("applicable_regime", []))
        return cls(**{**d, "phases": phases, "ecologies": ecologies})
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_skill.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/skill.py tests/test_skill.py
git commit -m "feat(harness): Skill 模型 + decay-weighted SkillStats"
```

---

## Task 3: 记忆模型 `memory_item`

**Files:** Create `youzi/harness/memory_item.py`; Test `tests/test_memory_item.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_memory_item.py
from youzi.harness.memory_item import Lesson, Importance


def test_importance_weight_and_demote():
    imp = Importance(base=0.8, time_decay=1.0, regime_decay=1.0)
    assert abs(imp.weight() - 0.8) < 1e-9
    imp.demote(0.5)                       # 同时打到 time_decay
    assert abs(imp.time_decay - 0.5) < 1e-9
    assert abs(imp.weight() - 0.4) < 1e-9


def test_lesson_from_seed_normalizes_regime_keeps_all():
    s = Lesson.from_seed({
        "lesson_id": "no_relay_in_ebb", "regime": "退潮期", "outcome": "principle",
        "lesson": "退潮不接力", "source_lines": [1272],
    })
    assert s.regime == "退潮"             # 归一
    assert s.outcome == "principle"
    s2 = Lesson.from_seed({
        "lesson_id": "disc", "regime": "all", "outcome": "principle",
        "lesson": "计划交易不上头",
    })
    assert s2.regime == "all"             # all 保留不归一


def test_lesson_loss_with_analog():
    s = Lesson.from_seed({
        "lesson_id": "shenma_ebb", "regime": "退潮", "outcome": "loss",
        "failure_signature": "最高连板率先走弱断板大阴", "named_analog": "神马电力2024/6/28",
        "lesson": "由强转弱即退潮拐点, 回避高位", "source_lines": [437, 438],
    })
    assert s.named_analog == "神马电力2024/6/28" and s.outcome == "loss"
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_memory_item.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/memory_item.py`**

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from youzi.harness.regime import classify_regime

Outcome = Literal["win", "loss", "principle"]


class Importance(BaseModel):
    """记忆重要度(可变)。weight = base × time_decay × regime_decay(双衰减,蓝图 §8)。"""
    base: float = 1.0
    time_decay: float = 1.0
    regime_decay: float = 1.0

    def weight(self) -> float:
        return self.base * self.time_decay * self.regime_decay

    def demote(self, factor: float) -> None:
        """按 factor 压低 time_decay(越过的区域降权,不删)。"""
        self.time_decay *= factor


def _norm_regime(raw: str) -> str:
    """记忆的 regime:'all' 原样保留;否则归一到 canonical 相位,归一失败则原样保留。"""
    s = (raw or "").strip()
    if s == "all":
        return "all"
    kind, value = classify_regime(s)
    return value if kind == "phase" else s


class Lesson(BaseModel):
    """M 记忆条目(可变)。"""
    lesson_id: str
    regime: str
    pattern: str = ""
    outcome: Outcome
    failure_signature: str = ""
    named_analog: str = ""
    lesson: str
    source_lines: list[int] = Field(default_factory=list)
    importance: Importance = Field(default_factory=Importance)

    @classmethod
    def from_seed(cls, d: dict) -> "Lesson":
        return cls(**{**d, "regime": _norm_regime(d.get("regime", ""))})
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_memory_item.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/memory_item.py tests/test_memory_item.py
git commit -m "feat(harness): Lesson 记忆模型 + 双衰减 Importance"
```

---

## Task 4: doctrine 模型与容器

**Files:** Create `youzi/harness/doctrine.py`; Test `tests/test_doctrine.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_doctrine.py
from youzi.harness.doctrine import DoctrineEntry, Doctrine


def _entries():
    return [
        DoctrineEntry.from_seed({"section": "退潮作战", "regime": "退潮期",
                                 "immutable": False, "guidance": "降题材预期"}),
        DoctrineEntry.from_seed({"section": "纪律红线:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮期禁止接力"}),
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升",
                                 "immutable": False, "guidance": "持有龙头"}),
    ]


def test_from_seed_normalizes_regime():
    e = _entries()[0]
    assert e.regime == "退潮"          # 归一


def test_doctrine_queries():
    doc = Doctrine(entries=_entries())
    assert [e.section for e in doc.for_regime("退潮")] == ["退潮作战", "纪律红线:退潮不接力"]
    # all 适用于任何相位
    assert "纪律红线:退潮不接力" in [e.section for e in doc.for_regime("主升")]
    assert [e.section for e in doc.immutable_core()] == ["纪律红线:退潮不接力"]
    assert len(doc.mutable_entries()) == 2
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_doctrine.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/doctrine.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from youzi.harness.regime import classify_regime


def _norm(raw: str) -> str:
    s = (raw or "").strip()
    if s == "all":
        return "all"
    kind, value = classify_regime(s)
    return value if kind == "phase" else s


class DoctrineEntry(BaseModel):
    """p doctrine 条目(可变;但 immutable=True 的为纪律红线,写保护在 Phase-0b-2 强制)。"""
    section: str
    regime: str
    immutable: bool = False
    guidance: str
    source_lines: list[int] = Field(default_factory=list)

    @classmethod
    def from_seed(cls, d: dict) -> "DoctrineEntry":
        return cls(**{**d, "regime": _norm(d.get("regime", ""))})


class Doctrine(BaseModel):
    """doctrine 容器。"""
    entries: list[DoctrineEntry] = Field(default_factory=list)

    def for_regime(self, phase: str) -> list[DoctrineEntry]:
        """某相位适用的 doctrine:匹配该相位的 + regime=='all' 的。原序返回。"""
        return [e for e in self.entries if e.regime == phase or e.regime == "all"]

    def immutable_core(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if e.immutable]

    def mutable_entries(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if not e.immutable]

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "Doctrine":
        return cls(entries=[DoctrineEntry.from_seed(d) for d in items])
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_doctrine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/doctrine.py tests/test_doctrine.py
git commit -m "feat(harness): DoctrineEntry + Doctrine 容器(immutable 标记)"
```

---

## Task 5: 情绪周期状态机 `cycle`

**Files:** Create `youzi/harness/cycle.py`; Test `tests/test_cycle.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cycle.py
from youzi.harness.cycle import StateMachine, EmotionPhase


def _states():
    return [
        {"phase": "退潮", "you_see": ["龙头与补涨龙共振下跌"],
         "transitions": [{"to": "混沌冰点", "signal": "板高降至4B-"}],
         "source_lines": [372]},
        {"phase": "主升", "you_see": ["龙头不断突破"],
         "transitions": [{"to": "震荡补涨", "signal": "第一根强分歧阴K且次日非强修复"}]},
    ]


def test_state_machine_get_and_signals():
    sm = StateMachine.from_seed_list(_states())
    assert sm.get("退潮").you_see == ["龙头与补涨龙共振下跌"]
    assert sm.next_signals("主升") == [("震荡补涨", "第一根强分歧阴K且次日非强修复")]
    assert sm.get("不存在") is None
    assert sm.phase_names() == ["退潮", "主升"]
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_cycle.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/cycle.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class Transition(BaseModel):
    to: str
    signal: str


class EmotionPhase(BaseModel):
    phase: str
    you_see: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    source_lines: list[int] = Field(default_factory=list)


class StateMachine(BaseModel):
    """情绪周期状态机(G_cycle 种子;只读结构,Phase-0b-1 不做推断)。"""
    phases: list[EmotionPhase] = Field(default_factory=list)

    def get(self, phase: str) -> EmotionPhase | None:
        return next((p for p in self.phases if p.phase == phase), None)

    def next_signals(self, phase: str) -> list[tuple[str, str]]:
        p = self.get(phase)
        return [(t.to, t.signal) for t in p.transitions] if p else []

    def phase_names(self) -> list[str]:
        return [p.phase for p in self.phases]

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "StateMachine":
        return cls(phases=[EmotionPhase(**d) for d in items])
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_cycle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/cycle.py tests/test_cycle.py
git commit -m "feat(harness): 情绪周期状态机 StateMachine"
```

---

## Task 6: 技能注册表 `registry`

**Files:** Create `youzi/harness/registry.py`; Test `tests/test_registry.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_registry.py
import pytest
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry


def _skills():
    return [
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升", "连板生态"], "trigger": "t",
                         "entry": "e", "exit_stop": "x", "status": "active"}),
        Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "failure_detector",
                         "applicable_regime": ["退潮"], "trigger": "t",
                         "entry": "规避", "exit_stop": "N/A", "status": "active"}),
        Skill.from_seed({"skill_id": "c", "name_cn": "丙", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t",
                         "entry": "e", "exit_stop": "x", "status": "dormant"}),
    ]


def test_registry_rejects_duplicate_ids():
    s = _skills()
    with pytest.raises(ValueError):
        SkillRegistry.from_skills([s[0], s[0]])


def test_registry_queries():
    reg = SkillRegistry.from_skills(_skills())
    assert reg.get("b").name_cn == "乙"
    assert reg.get("zzz") is None
    assert {s.skill_id for s in reg.by_status("active")} == {"a", "b"}
    assert {s.skill_id for s in reg.by_phase("主升")} == {"a", "c"}
    assert {s.skill_id for s in reg.by_type("pattern")} == {"a", "c"}
    assert {s.skill_id for s in reg.by_ecology("连板生态")} == {"a"}
    assert len(reg) == 3
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_registry.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/registry.py`**

```python
from __future__ import annotations

from youzi.harness.skill import Skill


class SkillRegistry:
    """技能库 K(按 id 索引)。Phase-0b-1 只读/查询;CRUD 编辑见 Phase-0b-2。"""

    def __init__(self, skills: dict[str, Skill]) -> None:
        self._skills = skills

    @classmethod
    def from_skills(cls, skills: list[Skill]) -> "SkillRegistry":
        index: dict[str, Skill] = {}
        for s in skills:
            if s.skill_id in index:
                raise ValueError(f"重复 skill_id: {s.skill_id}")
            index[s.skill_id] = s
        return cls(index)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def by_status(self, status: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.status == status]

    def by_type(self, type_: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.type == type_]

    def by_phase(self, phase: str) -> list[Skill]:
        return [s for s in self._skills.values() if phase in s.phases]

    def by_ecology(self, ecology: str) -> list[Skill]:
        return [s for s in self._skills.values() if ecology in s.ecologies]

    def __len__(self) -> int:
        return len(self._skills)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/registry.py tests/test_registry.py
git commit -m "feat(harness): SkillRegistry 技能库索引与查询"
```

---

## Task 7: 记忆库 `memory_store`

**Files:** Create `youzi/harness/memory_store.py`; Test `tests/test_memory_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_memory_store.py
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore


def _lessons():
    return [
        Lesson.from_seed({"lesson_id": "l1", "regime": "退潮", "pattern": "接力",
                          "outcome": "principle", "lesson": "退潮不接力"}),
        Lesson.from_seed({"lesson_id": "l2", "regime": "退潮", "pattern": "高位",
                          "outcome": "loss", "named_analog": "神马电力2024/6/28",
                          "lesson": "由强转弱即退潮拐点"}),
        Lesson.from_seed({"lesson_id": "l3", "regime": "all", "pattern": "纪律",
                          "outcome": "principle", "lesson": "计划交易不上头"}),
    ]


def test_memory_store_queries():
    store = MemoryStore.from_lessons(_lessons())
    assert store.get("l2").named_analog == "神马电力2024/6/28"
    assert {l.lesson_id for l in store.by_regime("退潮")} == {"l1", "l2"}
    assert {l.lesson_id for l in store.by_outcome("principle")} == {"l1", "l3"}
    assert {l.lesson_id for l in store.by_pattern("纪律")} == {"l3"}
    assert len(store) == 3
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_memory_store.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/memory_store.py`**

```python
from __future__ import annotations

from youzi.harness.memory_item import Lesson


class MemoryStore:
    """记忆库 M(按 lesson_id 索引)。Phase-0b-1 只读/查询;process_memory CRUD 见 Phase-0b-2。"""

    def __init__(self, lessons: dict[str, Lesson]) -> None:
        self._lessons = lessons

    @classmethod
    def from_lessons(cls, lessons: list[Lesson]) -> "MemoryStore":
        index: dict[str, Lesson] = {}
        for l in lessons:
            if l.lesson_id in index:
                raise ValueError(f"重复 lesson_id: {l.lesson_id}")
            index[l.lesson_id] = l
        return cls(index)

    def get(self, lesson_id: str) -> Lesson | None:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    def by_regime(self, regime: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.regime == regime]

    def by_outcome(self, outcome: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.outcome == outcome]

    def by_pattern(self, pattern: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.pattern == pattern]

    def __len__(self) -> int:
        return len(self._lessons)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_memory_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/memory_store.py tests/test_memory_store.py
git commit -m "feat(harness): MemoryStore 记忆库索引与查询"
```

---

## Task 8: Harness 总容器 `harness`

**Files:** Create `youzi/harness/harness.py`; Test `tests/test_harness.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_harness.py
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.memory_item import Lesson
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState


def _h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"}),
        Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "dormant"}),
    ])
    mem = MemoryStore.from_lessons([
        Lesson.from_seed({"lesson_id": "l1", "regime": "all", "outcome": "principle",
                          "lesson": "计划交易"})])
    doc = Doctrine(entries=[DoctrineEntry.from_seed(
        {"section": "主升作战", "regime": "主升", "immutable": False, "guidance": "持有龙头"})])
    cyc = StateMachine.from_seed_list([{"phase": "主升", "you_see": [], "transitions": []}])
    return HarnessState(doctrine=doc, skills=skills, memory=mem, cycle=cyc)


def test_active_skills_for_phase_excludes_dormant():
    h = _h()
    got = h.active_skills_for("主升")
    assert {s.skill_id for s in got} == {"a"}   # 只 active, 排除 dormant


def test_harness_holds_all_four_components():
    h = _h()
    assert h.skills.get("a") is not None
    assert h.memory.get("l1") is not None
    assert [e.section for e in h.doctrine.for_regime("主升")] == ["主升作战"]
    assert h.cycle.get("主升") is not None
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_harness.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/harness.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill


@dataclass
class HarnessState:
    """Harness 状态 H=(p,K,M)+情绪周期状态机。Phase-0b-1 为只读载入态;编辑/版本化见 0b-2。

    G(子 Agent)留待 Phase-1(LLM 驱动模块),此处暂不建模。
    """
    doctrine: Doctrine          # p
    skills: SkillRegistry       # K
    memory: MemoryStore         # M
    cycle: StateMachine         # G_cycle 种子

    def active_skills_for(self, phase: str) -> list[Skill]:
        """该相位下当前可用(active)的技能。"""
        return [s for s in self.skills.by_phase(phase) if s.status == "active"]
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_harness.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/harness.py tests/test_harness.py
git commit -m "feat(harness): HarnessState 总容器 + active_skills_for"
```

---

## Task 9: 种子载入器 `loader` + 真实种子集成测试

**Files:** Create `youzi/harness/loader.py`; Test `tests/test_loader_real_seeds.py`

- [ ] **Step 1: 写失败测试（载入真实 `seeds/`）**

```python
# tests/test_loader_real_seeds.py
from pathlib import Path
from youzi.harness.loader import load_seeds
from youzi.harness.harness import HarnessState
from youzi.harness.regime import CANONICAL_PHASES

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def test_load_real_seeds_counts_and_validity():
    h = load_seeds(SEEDS)
    assert isinstance(h, HarnessState)
    # 计数与提交的 v1 种子一致(变更种子需同步改这里)
    assert len(h.skills) == 57
    assert len(h.memory) == 21
    assert len(h.doctrine.entries) == 22
    assert len(h.cycle.phases) == 7


def test_loaded_skill_phases_are_canonical_or_empty():
    h = load_seeds(SEEDS)
    allowed = set(CANONICAL_PHASES)
    for s in h.skills.all():
        # 归一后的 phases 必须全是 canonical(或空), 不得残留变体/触发条件
        assert set(s.phases) <= allowed, f"{s.skill_id} 残留非 canonical 相位: {s.phases}"


def test_loaded_doctrine_has_immutable_core():
    h = load_seeds(SEEDS)
    core = h.doctrine.immutable_core()
    assert len(core) >= 8                       # v1 有 10 条纪律红线
    assert all(e.immutable for e in core)


def test_loader_missing_dir_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_seeds(SEEDS / "does_not_exist")
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_loader_real_seeds.py -v`
Expected: FAIL（`ModuleNotFoundError: youzi.harness.loader`）

- [ ] **Step 3: 实现 `youzi/harness/loader.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill


def _read_json(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"种子文件缺失: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_seeds(seeds_dir: str | Path) -> HarnessState:
    """读 seeds/{skills,memory,doctrine,state_machine}.json,归一+校验,组装 HarnessState。"""
    d = Path(seeds_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"种子目录缺失: {d}")

    skills = SkillRegistry.from_skills(
        [Skill.from_seed(x) for x in _read_json(d / "skills.json")])
    memory = MemoryStore.from_lessons(
        [Lesson.from_seed(x) for x in _read_json(d / "memory.json")])
    doctrine = Doctrine.from_seed_list(_read_json(d / "doctrine.json"))
    cycle = StateMachine.from_seed_list(_read_json(d / "state_machine.json"))

    return HarnessState(doctrine=doctrine, skills=skills, memory=memory, cycle=cycle)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_loader_real_seeds.py -v`
Expected: PASS（若计数断言失败,说明 `seeds/` 被改过——同步更新断言）

- [ ] **Step 5: 跑全量套件**

Run: `pytest -q`
Expected: 全绿（Phase-0a 的 31 + 本计划新增,约 50+ 用例）

- [ ] **Step 6: Commit**

```bash
git add youzi/harness/loader.py tests/test_loader_real_seeds.py
git commit -m "feat(harness): 种子载入器 load_seeds + 真实种子集成测试"
```

---

## Self-Review(已自检)

**1. Spec 覆盖(对照本计划 Goal/范围):**
- 相位归一(canonical 词表)→ Task 1 `regime` + 各 `from_seed` 调用 + Task 9 断言 phases ⊆ canonical。✅
- K 技能模型 + decay-weighted 统计 → Task 2(`Skill`/`SkillStats.record` EWMA)。✅
- M 记忆模型 + 双衰减重要度 → Task 3(`Lesson`/`Importance`)。✅
- p doctrine + immutable 标记(读出 + 查询)→ Task 4;写保护明确划到 0b-2。✅
- 情绪周期状态机种子 → Task 5。✅
- 容器与查询(registry/store/harness)→ Task 6/7/8。✅
- 载入真实 `seeds/` → Task 9 集成测试(计数 + 归一 + immutable core)。✅
- **明确不在本计划**:CRUD 编辑、版本化快照/回滚、immutable 写保护强制、meta-tool API → Phase-0b-2(已在范围边界声明)。

**2. Placeholder 扫描:** 无 TBD/TODO;每个改代码 step 均给完整可运行代码 + 确切命令。✅

**3. 类型一致性:** `split_regimes` 返回 `(phases, ecologies)` 在 `Skill.from_seed` 使用一致;`from_seed`/`from_seed_list`/`from_skills`/`from_lessons` 命名贯穿;`HarnessState` 字段 `doctrine/skills/memory/cycle` 在 Task 8 定义、Task 9 组装一致;`by_phase`/`by_status`/`by_type`/`by_ecology` 在 Task 6 定义、Task 8 `active_skills_for` 使用一致;`regime` 归一在 skill/memory/doctrine 三处用同一 `classify_regime`。✅
