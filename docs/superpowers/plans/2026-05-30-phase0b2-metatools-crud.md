# Phase-0b-2 可编辑 Harness:CRUD meta-tools + 写保护 + 编辑审计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Harness 状态 `H=(p,K,M)` 可被**编辑**——实现论文的 meta-tool API(`write_skill/patch_skill/retire_skill/revive_skill/promote_skill/process_memory/rewrite_doctrine`),带 **immutable-core 写保护**(纪律红线 Refiner 不可改)、**技能生命周期**(active⇄incubating、active→dormant→incubating 的"轮回"复活)、以及**编辑审计 Δ 轨迹**;同时修掉终审标记的 **P0 多 regime 记忆漏检**。

**Architecture:** 在已合并的 `youzi/harness/` 上扩展。先把 `Lesson`/`DoctrineEntry` 的单值 `regime` 重构成多值 `phases/ecologies/applies_all`(P0 修复,用 `regime.parse_regime_field`),使 `for_regime` 成员匹配不再漏检;再给三个容器(`SkillRegistry`/`MemoryStore`/`Doctrine`)加 CRUD;最后用 `MetaTools` 门面统一这些编辑、强制 invariant、并把每次编辑写进 `EditLog`(Δ 审计)。纯 in-memory + pydantic,**全程离线可测**;集成测试载入**真实** `seeds/` 跑一串 meta-tool 编辑 + 验证 immutable 写保护。

**Tech Stack:** Python 3.11+ · pydantic v2(`validate_assignment` 让 patch/update 走校验)· pytest。无新依赖。

**范围边界:** 不做磁盘持久化/版本化快照/回滚(那是 **Phase-0b-3**,独立的持久化子系统);本计划交付"可编辑的内存 Harness + meta-tool API + 审计日志"。G(子 Agent)仍留待 Phase-1。

**关键设计点(对应蓝图/终审):**
- **P0 多 regime 修复(终审 Important):** `Lesson`/`DoctrineEntry` 的 `regime` 单值 → `phases:list/ecologies:list/applies_all:bool`(`主升/退潮`→两相位都可查;`次新生态/超跌生态`→生态可查;`all`→applies_all)。`for_regime(phase)` 改成员匹配(`phase in phases or applies_all`)。
- **immutable-core 写保护(蓝图 §6.5):** `rewrite_doctrine`/`remove` 命中 `immutable=True` 条目 → 抛 `ImmutableDoctrineError`。Refiner 永远改不动纪律红线。
- **技能生命周期(蓝图 §6.3 / §8 dormant 复活):** `retire`→dormant(默认,保 regime 指纹待"轮回"复活)或 retired(永久);`revive` dormant→incubating;`promote` incubating→active。状态转移非法 → 抛错。
- **编辑审计 Δ 轨迹(蓝图 §4 inner-loop CRUD):** 每次 meta-tool 调用写一条 `EditRecord`(seq 单调、tool、target、op、summary),构成 `Δ=(Δp,ΔG,ΔK,ΔM)` 的可回溯日志(为 0b-3 版本化/回滚铺路)。
- **校验赋值:** 模型加 `validate_assignment=True`,使 `patch`/`update` 的 setattr 仍走类型/`extra=forbid` 校验。

---

## File Structure

```
youzi/harness/
  regime.py            # MODIFY: + parse_regime_field(raw) -> (phases, ecologies, applies_all)
  memory_item.py       # MODIFY: Lesson regime 单值 → regime_raw/phases/ecologies/applies_all; +validate_assignment
  doctrine.py          # MODIFY: DoctrineEntry 同上; Doctrine.for_regime 成员匹配; +CRUD(get/add/rewrite/remove)+写保护
  memory_store.py      # MODIFY: for_regime/for_ecology 成员匹配; +CRUD(add/update/demote); 防御性拷贝
  registry.py          # MODIFY: +CRUD(write/patch/retire/revive/promote); 防御性拷贝
  skill.py             # MODIFY: Skill +validate_assignment(供 patch)
  errors.py            # NEW: ImmutableDoctrineError / InvalidTransitionError
  edit_log.py          # NEW: EditRecord + EditLog(Δ 审计)
  metatools.py         # NEW: MetaTools 门面(7 个 meta-tool, 强制 invariant + 写 EditLog)
tests/
  test_regime.py            # +parse_regime_field
  test_memory_item.py       # 改 Lesson 多 regime 断言
  test_doctrine.py          # 改 for_regime 成员匹配 + CRUD/写保护
  test_memory_store.py      # 改 for_regime/for_ecology + CRUD
  test_registry.py          # +CRUD/生命周期
  test_edit_log.py          # NEW
  test_metatools.py         # NEW(单元)
  test_metatools_integration.py  # NEW(载入真实 seeds 跑编辑序列 + 写保护)
```

**全局类型契约(后续任务一致引用):**
- `regime.parse_regime_field(raw: str) -> tuple[list[str], list[str], bool]`(phases, ecologies, applies_all)。
- `Lesson`/`DoctrineEntry` 字段:`regime_raw: str`、`phases: list[str]`、`ecologies: list[str]`、`applies_all: bool`(替换原 `regime`)。`from_seed` 丢弃 `regime` key、写入这四者。
- `MemoryStore.for_regime(phase)`、`for_ecology(ecology)`;`Doctrine.for_regime(phase)`、`for_ecology(ecology)` —— 成员匹配 + `applies_all`。
- `SkillRegistry`:`write(skill)`、`patch(skill_id, **fields) -> Skill`、`retire(skill_id, permanent=False)`、`revive(skill_id)`、`promote(skill_id)`。
- `MemoryStore`:`add(lesson)`、`update(lesson_id, **fields) -> Lesson`、`demote(lesson_id, factor)`。
- `Doctrine`:`get(section)`、`add(entry)`、`rewrite(section, new_guidance)`、`remove(section)`。
- `EditLog.append(tool, target_kind, target_id, op, summary="") -> EditRecord`;`records()/by_kind(kind)/by_tool(tool)/__len__`。
- `MetaTools(harness, log=None)` 方法:`write_skill/patch_skill/retire_skill/revive_skill/promote_skill/process_memory/update_memory/demote_memory/rewrite_doctrine`,各 `-> EditRecord`。

---

## Task 1: `regime.parse_regime_field`

**Files:** Modify `youzi/harness/regime.py`; Modify `tests/test_regime.py`

- [ ] **Step 1: 追加失败测试到 `tests/test_regime.py`**

```python
# append to tests/test_regime.py
from youzi.harness.regime import parse_regime_field


def test_parse_regime_field_multi_and_all():
    assert parse_regime_field("主升/退潮") == (["主升", "退潮"], [], False)
    assert parse_regime_field("修复/回暖/启动") == (["修复启动", "情绪回暖", "题材启动"], [], False)
    assert parse_regime_field("次新生态/超跌生态") == ([], ["次新生态", "超跌生态"], False)
    assert parse_regime_field("all") == ([], [], True)
    assert parse_regime_field("退潮期") == (["退潮"], [], False)
    assert parse_regime_field("") == ([], [], False)
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd "/Volumes/kairos/引力场量化/youzi-自进化版" && source .venv/bin/activate && pytest tests/test_regime.py -v`
Expected: FAIL（`ImportError: cannot import name 'parse_regime_field'`）

- [ ] **Step 3: 在 `youzi/harness/regime.py` 末尾追加**

```python
import re

_REGIME_SPLIT = re.compile(r"[/、,，\s]+")


def parse_regime_field(raw: str) -> tuple[list[str], list[str], bool]:
    """把单值 regime 串(可能复合如 '主升/退潮' 或 'all')解析为 (phases, ecologies, applies_all)。

    用于 Lesson/DoctrineEntry 的 regime 字段(单字符串);Skill 的 applicable_regime 已是列表,仍用 split_regimes。
    """
    s = (raw or "").strip()
    if not s:
        return ([], [], False)
    tokens = [t for t in _REGIME_SPLIT.split(s) if t]
    applies_all = "all" in tokens
    phases, ecologies = split_regimes([t for t in tokens if t != "all"])
    return (phases, ecologies, applies_all)
```

（`import re` 也可置于文件顶部;置于末尾函数前同样有效。）

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_regime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/regime.py tests/test_regime.py
git commit -m "feat(harness): parse_regime_field 解析多值/复合 regime 串"
```

---

## Task 2: `Lesson` 多 regime 重构

**Files:** Modify `youzi/harness/memory_item.py`; Modify `tests/test_memory_item.py`

- [ ] **Step 1: 改写 `tests/test_memory_item.py` 中涉及 regime 的断言**

把原 `test_lesson_from_seed_normalizes_regime_keeps_all` 与 `test_lesson_loss_with_analog` 替换为:

```python
def test_lesson_from_seed_parses_multi_regime():
    s = Lesson.from_seed({
        "lesson_id": "glory_peak", "regime": "主升/退潮", "outcome": "principle",
        "lesson": "盛极转衰非龙头早退龙头迟退", "source_lines": [344],
    })
    assert s.regime_raw == "主升/退潮"
    assert s.phases == ["主升", "退潮"]          # 两相位都可查(修复 P0 漏检)
    assert s.applies_all is False


def test_lesson_from_seed_all_and_ecology():
    a = Lesson.from_seed({"lesson_id": "disc", "regime": "all", "outcome": "principle",
                          "lesson": "计划交易不上头"})
    assert a.applies_all is True and a.phases == []
    e = Lesson.from_seed({"lesson_id": "cixin", "regime": "次新生态/超跌生态",
                          "outcome": "loss", "lesson": "次新与超跌互为生死"})
    assert e.ecologies == ["次新生态", "超跌生态"] and e.phases == []


def test_lesson_loss_with_analog():
    s = Lesson.from_seed({
        "lesson_id": "shenma_ebb", "regime": "退潮", "outcome": "loss",
        "failure_signature": "最高连板率先走弱断板大阴", "named_analog": "神马电力2024/6/28",
        "lesson": "由强转弱即退潮拐点, 回避高位", "source_lines": [437, 438],
    })
    assert s.named_analog == "神马电力2024/6/28" and s.phases == ["退潮"]
```

（保留 `test_importance_weight_and_demote` 不变。）

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_memory_item.py -v`
Expected: FAIL（`Lesson` 还没有 `regime_raw`/`phases` 字段）

- [ ] **Step 3: 改写 `youzi/harness/memory_item.py`**

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from youzi.harness.regime import parse_regime_field

Outcome = Literal["win", "loss", "principle"]


class Importance(BaseModel):
    """记忆重要度(可变)。weight = base × time_decay × regime_decay(双衰减,蓝图 §8)。"""
    base: float = 1.0
    time_decay: float = 1.0
    regime_decay: float = 1.0

    def weight(self) -> float:
        return self.base * self.time_decay * self.regime_decay

    def demote(self, factor: float) -> None:
        if not 0.0 < factor <= 1.0:
            raise ValueError(f"demote factor 必须在 (0,1], got {factor}")
        self.time_decay *= factor


class Lesson(BaseModel):
    """M 记忆条目(可变)。regime 解析为多值 phases/ecologies/applies_all。"""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    lesson_id: str
    regime_raw: str = ""              # 原始 regime 串(可溯源)
    phases: list[str] = Field(default_factory=list)
    ecologies: list[str] = Field(default_factory=list)
    applies_all: bool = False
    pattern: str = ""
    outcome: Outcome
    failure_signature: str = ""
    named_analog: str = ""
    lesson: str
    source_lines: list[int] = Field(default_factory=list)
    importance: Importance = Field(default_factory=Importance)

    @classmethod
    def from_seed(cls, d: dict) -> "Lesson":
        raw = d.get("regime", "")
        phases, ecologies, applies_all = parse_regime_field(raw)
        rest = {k: v for k, v in d.items() if k != "regime"}
        return cls(**rest, regime_raw=raw, phases=phases,
                   ecologies=ecologies, applies_all=applies_all)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_memory_item.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/memory_item.py tests/test_memory_item.py
git commit -m "refactor(harness): Lesson 多 regime(phases/ecologies/applies_all)修 for_regime 漏检"
```

---

## Task 3: `DoctrineEntry` 多 regime + `Doctrine` 成员匹配查询

**Files:** Modify `youzi/harness/doctrine.py`; Modify `tests/test_doctrine.py`

- [ ] **Step 1: 改写 `tests/test_doctrine.py`**

```python
# tests/test_doctrine.py  (整体替换)
from youzi.harness.doctrine import DoctrineEntry, Doctrine


def _entries():
    return [
        DoctrineEntry.from_seed({"section": "退潮作战", "regime": "退潮",
                                 "immutable": False, "guidance": "降题材预期"}),
        DoctrineEntry.from_seed({"section": "纪律红线:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮期禁止接力"}),
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升/震荡补涨",
                                 "immutable": False, "guidance": "持有龙头"}),
    ]


def test_from_seed_parses_multi_regime():
    e = _entries()[2]
    assert e.phases == ["主升", "震荡补涨"]
    assert e.regime_raw == "主升/震荡补涨"


def test_doctrine_for_regime_membership_and_all():
    doc = Doctrine(entries=_entries())
    assert [e.section for e in doc.for_regime("退潮")] == ["退潮作战", "纪律红线:退潮不接力"]
    # 主升作战 适用于 主升 与 震荡补涨 两相位; all 永远命中
    assert [e.section for e in doc.for_regime("震荡补涨")] == ["纪律红线:退潮不接力", "主升作战"]
    assert "纪律红线:退潮不接力" in [e.section for e in doc.for_regime("主升")]
    assert [e.section for e in doc.immutable_core()] == ["纪律红线:退潮不接力"]
    assert len(doc.mutable_entries()) == 2


def test_doctrine_entry_forbids_unknown_keys():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DoctrineEntry.from_seed({"section": "x", "regime": "all", "immutable": False,
                                 "guidance": "g", "typo_key": 1})
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_doctrine.py -v`
Expected: FAIL（`DoctrineEntry` 还没有 `phases` 字段 / `for_regime` 仍是旧语义）

- [ ] **Step 3: 改写 `youzi/harness/doctrine.py`(模型部分;CRUD 在 Task 7 追加)**

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from youzi.harness.regime import parse_regime_field


class DoctrineEntry(BaseModel):
    """p doctrine 条目(可变;immutable=True 为纪律红线,写保护在 rewrite/remove 强制)。"""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    section: str
    regime_raw: str = ""
    phases: list[str] = Field(default_factory=list)
    ecologies: list[str] = Field(default_factory=list)
    applies_all: bool = False
    immutable: bool = False
    guidance: str
    source_lines: list[int] = Field(default_factory=list)

    @classmethod
    def from_seed(cls, d: dict) -> "DoctrineEntry":
        raw = d.get("regime", "")
        phases, ecologies, applies_all = parse_regime_field(raw)
        rest = {k: v for k, v in d.items() if k != "regime"}
        return cls(**rest, regime_raw=raw, phases=phases,
                   ecologies=ecologies, applies_all=applies_all)


class Doctrine(BaseModel):
    """doctrine 容器。"""
    entries: list[DoctrineEntry] = Field(default_factory=list)

    def for_regime(self, phase: str) -> list[DoctrineEntry]:
        """某相位适用的 doctrine:phase ∈ phases 或 applies_all。原序返回。"""
        return [e for e in self.entries if phase in e.phases or e.applies_all]

    def for_ecology(self, ecology: str) -> list[DoctrineEntry]:
        return [e for e in self.entries if ecology in e.ecologies]

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
git commit -m "refactor(harness): DoctrineEntry 多 regime + Doctrine.for_regime 成员匹配"
```

---

## Task 4: `MemoryStore` 查询改成员匹配

**Files:** Modify `youzi/harness/memory_store.py`; Modify `tests/test_memory_store.py`

- [ ] **Step 1: 改写 `tests/test_memory_store.py`(查询部分)**

```python
# tests/test_memory_store.py  (整体替换)
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore


def _lessons():
    return [
        Lesson.from_seed({"lesson_id": "l1", "regime": "退潮", "pattern": "接力",
                          "outcome": "principle", "lesson": "退潮不接力"}),
        Lesson.from_seed({"lesson_id": "l2", "regime": "主升/退潮", "pattern": "高位",
                          "outcome": "loss", "named_analog": "神马电力2024/6/28",
                          "lesson": "由强转弱即退潮拐点"}),
        Lesson.from_seed({"lesson_id": "l3", "regime": "all", "pattern": "纪律",
                          "outcome": "principle", "lesson": "计划交易不上头"}),
        Lesson.from_seed({"lesson_id": "l4", "regime": "次新生态", "pattern": "次新",
                          "outcome": "loss", "lesson": "次新周期"}),
    ]


def test_for_regime_membership_and_all():
    store = MemoryStore.from_lessons(_lessons())
    # 退潮: l1(退潮) + l2(主升/退潮 命中退潮) + l3(all)
    assert {l.lesson_id for l in store.for_regime("退潮")} == {"l1", "l2", "l3"}
    # 主升: l2(命中主升) + l3(all)
    assert {l.lesson_id for l in store.for_regime("主升")} == {"l2", "l3"}


def test_for_ecology_and_other_queries():
    store = MemoryStore.from_lessons(_lessons())
    assert {l.lesson_id for l in store.for_ecology("次新生态")} == {"l4"}
    assert {l.lesson_id for l in store.by_outcome("principle")} == {"l1", "l3"}
    assert {l.lesson_id for l in store.by_pattern("纪律")} == {"l3"}
    assert store.get("l2").named_analog == "神马电力2024/6/28"
    assert len(store) == 4


def test_store_rejects_duplicate_ids():
    import pytest
    with pytest.raises(ValueError):
        MemoryStore.from_lessons([_lessons()[0], _lessons()[0]])
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_memory_store.py -v`
Expected: FAIL（`for_regime` 旧语义 / 无 `for_ecology`）

- [ ] **Step 3: 改写 `youzi/harness/memory_store.py`(查询部分;CRUD 在 Task 6 追加)**

```python
from __future__ import annotations

from youzi.harness.memory_item import Lesson


class MemoryStore:
    """记忆库 M(按 lesson_id 索引)。"""

    def __init__(self, lessons: dict[str, Lesson]) -> None:
        self._lessons = dict(lessons)          # 防御性拷贝,调用方不持有同一引用

    @classmethod
    def from_lessons(cls, lessons: list[Lesson]) -> "MemoryStore":
        index: dict[str, Lesson] = {}
        for lesson in lessons:
            if lesson.lesson_id in index:
                raise ValueError(f"重复 lesson_id: {lesson.lesson_id}")
            index[lesson.lesson_id] = lesson
        return cls(index)

    def get(self, lesson_id: str) -> Lesson | None:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    def for_regime(self, phase: str) -> list[Lesson]:
        """该相位适用的教训:phase ∈ phases 或 applies_all。"""
        return [l for l in self._lessons.values() if phase in l.phases or l.applies_all]

    def for_ecology(self, ecology: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if ecology in l.ecologies]

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
git commit -m "refactor(harness): MemoryStore for_regime/for_ecology 成员匹配 + 防御性拷贝"
```

---

## Task 5: 错误类型 `errors`

**Files:** Create `youzi/harness/errors.py`; Test `tests/test_errors.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_errors.py
from youzi.harness.errors import ImmutableDoctrineError, InvalidTransitionError


def test_error_types_are_distinct_runtime_errors():
    assert issubclass(ImmutableDoctrineError, RuntimeError)
    assert issubclass(InvalidTransitionError, RuntimeError)
    assert ImmutableDoctrineError is not InvalidTransitionError
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_errors.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/errors.py`**

```python
from __future__ import annotations


class ImmutableDoctrineError(RuntimeError):
    """试图改写/删除标记为 immutable 的纪律红线 doctrine 条目。"""


class InvalidTransitionError(RuntimeError):
    """非法的技能状态转移(如 revive 一个非 dormant 技能)。"""
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/errors.py tests/test_errors.py
git commit -m "feat(harness): ImmutableDoctrineError / InvalidTransitionError"
```

---

## Task 6: `SkillRegistry` CRUD + 生命周期

**Files:** Modify `youzi/harness/skill.py`(加 validate_assignment); Modify `youzi/harness/registry.py`; Modify `tests/test_registry.py`

- [ ] **Step 1: 追加失败测试到 `tests/test_registry.py`**

```python
# append to tests/test_registry.py
from youzi.harness.errors import InvalidTransitionError


def _one():
    return Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                            "applicable_regime": ["主升"], "trigger": "t",
                            "entry": "e", "exit_stop": "x", "status": "active"})


def test_registry_write_and_reject_dup():
    import pytest
    reg = SkillRegistry.from_skills([_one()])
    new = Skill.from_seed({"skill_id": "z", "name_cn": "新", "type": "pattern",
                           "applicable_regime": ["退潮"], "trigger": "t",
                           "entry": "e", "exit_stop": "x", "status": "incubating"})
    reg.write(new)
    assert reg.get("z").name_cn == "新"
    with pytest.raises(ValueError):
        reg.write(_one())            # 重复 id


def test_registry_patch_validates():
    import pytest
    reg = SkillRegistry.from_skills([_one()])
    reg.patch("a", notes="改了备注", status="dormant")
    assert reg.get("a").notes == "改了备注" and reg.get("a").status == "dormant"
    with pytest.raises(Exception):       # validate_assignment 拒绝非法值
        reg.patch("a", status="不存在的状态")
    with pytest.raises(KeyError):
        reg.patch("没有", notes="x")


def test_registry_lifecycle_retire_revive_promote():
    import pytest
    reg = SkillRegistry.from_skills([_one()])
    reg.retire("a")                       # active -> dormant(默认)
    assert reg.get("a").status == "dormant"
    reg.revive("a")                       # dormant -> incubating
    assert reg.get("a").status == "incubating"
    reg.promote("a")                      # incubating -> active
    assert reg.get("a").status == "active"
    reg.retire("a", permanent=True)       # -> retired(永久)
    assert reg.get("a").status == "retired"
    with pytest.raises(InvalidTransitionError):
        reg.revive("a")                   # retired 不能 revive(非 dormant)
```

- [ ] **Step 2: 给 `youzi/harness/skill.py` 的 `Skill` 加 validate_assignment**

把 `Skill` 的 `model_config = ConfigDict(extra="forbid")` 改为:

```python
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
```

- [ ] **Step 3: 运行,确认失败**

Run: `pytest tests/test_registry.py -v`
Expected: FAIL（`SkillRegistry` 还没有 `write/patch/retire/revive/promote`）

- [ ] **Step 4: 在 `youzi/harness/registry.py` 追加 CRUD(并改构造为防御性拷贝)**

把 `__init__` 改为防御性拷贝,并追加方法:

```python
from youzi.harness.errors import InvalidTransitionError
# (文件顶部已 import Skill)

    def __init__(self, skills: dict[str, Skill]) -> None:
        self._skills = dict(skills)          # 防御性拷贝

    def _require(self, skill_id: str) -> Skill:
        s = self._skills.get(skill_id)
        if s is None:
            raise KeyError(f"无此 skill_id: {skill_id}")
        return s

    def write(self, skill: Skill) -> None:
        if skill.skill_id in self._skills:
            raise ValueError(f"重复 skill_id: {skill.skill_id}")
        self._skills[skill.skill_id] = skill

    def patch(self, skill_id: str, **fields) -> Skill:
        s = self._require(skill_id)
        for k, v in fields.items():
            setattr(s, k, v)                 # validate_assignment 走校验
        return s

    def retire(self, skill_id: str, permanent: bool = False) -> Skill:
        """退役:默认 -> dormant(保指纹待轮回复活);permanent -> retired。"""
        s = self._require(skill_id)
        s.status = "retired" if permanent else "dormant"
        return s

    def revive(self, skill_id: str) -> Skill:
        """复活:仅允许 dormant -> incubating。"""
        s = self._require(skill_id)
        if s.status != "dormant":
            raise InvalidTransitionError(f"{skill_id} 非 dormant(当前 {s.status}),不能 revive")
        s.status = "incubating"
        return s

    def promote(self, skill_id: str) -> Skill:
        """晋升:仅允许 incubating -> active。"""
        s = self._require(skill_id)
        if s.status != "incubating":
            raise InvalidTransitionError(f"{skill_id} 非 incubating(当前 {s.status}),不能 promote")
        s.status = "active"
        return s
```

（保留已有 `from_skills/get/all/by_status/by_type/by_phase/by_ecology/__len__`。）

- [ ] **Step 5: 运行,确认通过**

Run: `pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add youzi/harness/skill.py youzi/harness/registry.py tests/test_registry.py
git commit -m "feat(harness): SkillRegistry CRUD + 生命周期(retire/revive/promote)"
```

---

## Task 7: `MemoryStore` CRUD + `Doctrine` CRUD(含写保护)

**Files:** Modify `youzi/harness/memory_store.py`; Modify `youzi/harness/doctrine.py`; Modify `tests/test_memory_store.py`, `tests/test_doctrine.py`

- [ ] **Step 1: 追加失败测试**

`tests/test_memory_store.py` 追加:

```python
def test_memory_store_crud():
    import pytest
    store = MemoryStore.from_lessons(_lessons())
    store.add(Lesson.from_seed({"lesson_id": "l9", "regime": "主升",
                                "outcome": "win", "lesson": "新教训"}))
    assert store.get("l9") is not None
    with pytest.raises(ValueError):
        store.add(_lessons()[0])                 # 重复 id
    store.update("l1", lesson="改写后的教训")
    assert store.get("l1").lesson == "改写后的教训"
    store.demote("l1", 0.5)
    assert abs(store.get("l1").importance.time_decay - 0.5) < 1e-9
    with pytest.raises(KeyError):
        store.update("没有", lesson="x")
```

`tests/test_doctrine.py` 追加:

```python
def test_doctrine_crud_with_immutable_protection():
    import pytest
    from youzi.harness.errors import ImmutableDoctrineError
    doc = Doctrine(entries=_entries())
    # 改写可变条目 OK
    doc.rewrite("退潮作战", "新的退潮指导")
    assert doc.get("退潮作战").guidance == "新的退潮指导"
    # 改写纪律红线 -> 拒绝
    with pytest.raises(ImmutableDoctrineError):
        doc.rewrite("纪律红线:退潮不接力", "篡改")
    # 删除纪律红线 -> 拒绝
    with pytest.raises(ImmutableDoctrineError):
        doc.remove("纪律红线:退潮不接力")
    # 删除可变条目 OK
    doc.remove("退潮作战")
    assert doc.get("退潮作战") is None
    # 新增 + 重复 section 拒绝
    doc.add(DoctrineEntry.from_seed({"section": "新作战", "regime": "主升",
                                     "immutable": False, "guidance": "g"}))
    with pytest.raises(ValueError):
        doc.add(DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升",
                                         "immutable": False, "guidance": "dup"}))
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_memory_store.py tests/test_doctrine.py -v`
Expected: FAIL（无 `add/update/demote` / 无 `get/add/rewrite/remove`）

- [ ] **Step 3: 给 `youzi/harness/memory_store.py` 追加 CRUD**

```python
# 追加到 MemoryStore 类内
    def add(self, lesson: Lesson) -> None:
        if lesson.lesson_id in self._lessons:
            raise ValueError(f"重复 lesson_id: {lesson.lesson_id}")
        self._lessons[lesson.lesson_id] = lesson

    def update(self, lesson_id: str, **fields) -> Lesson:
        l = self._lessons.get(lesson_id)
        if l is None:
            raise KeyError(f"无此 lesson_id: {lesson_id}")
        for k, v in fields.items():
            setattr(l, k, v)             # validate_assignment 走校验
        return l

    def demote(self, lesson_id: str, factor: float) -> Lesson:
        l = self._lessons.get(lesson_id)
        if l is None:
            raise KeyError(f"无此 lesson_id: {lesson_id}")
        l.importance.demote(factor)
        return l
```

- [ ] **Step 4: 给 `youzi/harness/doctrine.py` 的 `Doctrine` 追加 CRUD(写保护)**

在 `doctrine.py` 顶部 `from youzi.harness.errors import ImmutableDoctrineError`,并在 `Doctrine` 类内追加:

```python
    def get(self, section: str) -> DoctrineEntry | None:
        return next((e for e in self.entries if e.section == section), None)

    def add(self, entry: DoctrineEntry) -> None:
        if self.get(entry.section) is not None:
            raise ValueError(f"重复 section: {entry.section}")
        self.entries.append(entry)

    def rewrite(self, section: str, new_guidance: str) -> DoctrineEntry:
        e = self.get(section)
        if e is None:
            raise KeyError(f"无此 section: {section}")
        if e.immutable:
            raise ImmutableDoctrineError(f"纪律红线不可改写: {section}")
        e.guidance = new_guidance
        return e

    def remove(self, section: str) -> None:
        e = self.get(section)
        if e is None:
            raise KeyError(f"无此 section: {section}")
        if e.immutable:
            raise ImmutableDoctrineError(f"纪律红线不可删除: {section}")
        self.entries.remove(e)
```

- [ ] **Step 5: 运行,确认通过**

Run: `pytest tests/test_memory_store.py tests/test_doctrine.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add youzi/harness/memory_store.py youzi/harness/doctrine.py tests/test_memory_store.py tests/test_doctrine.py
git commit -m "feat(harness): MemoryStore/Doctrine CRUD + immutable 写保护"
```

---

## Task 8: 编辑审计 `edit_log`

**Files:** Create `youzi/harness/edit_log.py`; Test `tests/test_edit_log.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_edit_log.py
from youzi.harness.edit_log import EditLog, EditRecord


def test_edit_log_appends_with_monotonic_seq():
    log = EditLog()
    r0 = log.append("write_skill", "skill", "a", "create", "甲")
    r1 = log.append("rewrite_doctrine", "doctrine", "退潮作战", "rewrite")
    assert isinstance(r0, EditRecord)
    assert r0.seq == 0 and r1.seq == 1
    assert len(log) == 2


def test_edit_log_queries():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create")
    log.append("retire_skill", "skill", "a", "dormant")
    log.append("process_memory", "memory", "l1", "create")
    assert [r.target_id for r in log.by_kind("skill")] == ["a", "a"]
    assert [r.seq for r in log.by_tool("write_skill")] == [0]
    assert len(log.records()) == 3
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_edit_log.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/edit_log.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EditRecord(BaseModel):
    """一次 Harness 编辑的 Δ 审计记录(蓝图 §4 inner-loop CRUD 轨迹)。"""
    model_config = ConfigDict(frozen=True)
    seq: int
    tool: str                # write_skill / patch_skill / ... / rewrite_doctrine
    target_kind: str         # skill | memory | doctrine
    target_id: str           # skill_id / lesson_id / section
    op: str                  # create | update | retire | dormant | revive | promote | demote | rewrite
    summary: str = ""


class EditLog:
    """单调递增的编辑审计日志(Δ 轨迹);为 Phase-0b-3 版本化/回滚铺路。"""

    def __init__(self) -> None:
        self._records: list[EditRecord] = []

    def append(self, tool: str, target_kind: str, target_id: str,
               op: str, summary: str = "") -> EditRecord:
        rec = EditRecord(seq=len(self._records), tool=tool, target_kind=target_kind,
                         target_id=target_id, op=op, summary=summary)
        self._records.append(rec)
        return rec

    def records(self) -> list[EditRecord]:
        return list(self._records)

    def by_kind(self, target_kind: str) -> list[EditRecord]:
        return [r for r in self._records if r.target_kind == target_kind]

    def by_tool(self, tool: str) -> list[EditRecord]:
        return [r for r in self._records if r.tool == tool]

    def __len__(self) -> int:
        return len(self._records)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_edit_log.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/edit_log.py tests/test_edit_log.py
git commit -m "feat(harness): EditRecord/EditLog 编辑审计 Δ 轨迹"
```

---

## Task 9: `MetaTools` 门面

**Files:** Create `youzi/harness/metatools.py`; Test `tests/test_metatools.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_metatools.py
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.metatools import MetaTools


def _harness():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    mem = MemoryStore.from_lessons([
        Lesson.from_seed({"lesson_id": "l1", "regime": "退潮", "outcome": "loss",
                          "lesson": "教训"})])
    doc = Doctrine(entries=[
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升",
                                 "immutable": False, "guidance": "持有龙头"}),
        DoctrineEntry.from_seed({"section": "纪律:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮禁接力"})])
    cyc = StateMachine.from_seed_list([{"phase": "主升", "you_see": [], "transitions": []}])
    return HarnessState(doctrine=doc, skills=skills, memory=mem, cycle=cyc)


def test_metatools_edits_and_logs():
    mt = MetaTools(_harness())
    mt.write_skill(Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "pattern",
                                    "applicable_regime": ["退潮"], "trigger": "t",
                                    "entry": "e", "exit_stop": "x", "status": "incubating"}))
    mt.retire_skill("a")                          # active -> dormant
    mt.revive_skill("a")                          # dormant -> incubating
    mt.promote_skill("a")                         # incubating -> active
    mt.patch_skill("a", notes="备注")
    mt.process_memory(Lesson.from_seed({"lesson_id": "l2", "regime": "主升",
                                        "outcome": "win", "lesson": "新"}))
    mt.demote_memory("l1", 0.5)
    mt.rewrite_doctrine("主升作战", "新指导")
    h = mt.h
    assert h.skills.get("a").status == "active" and h.skills.get("a").notes == "备注"
    assert h.skills.get("b") is not None
    assert h.memory.get("l2") is not None
    assert abs(h.memory.get("l1").importance.time_decay - 0.5) < 1e-9
    assert h.doctrine.get("主升作战").guidance == "新指导"
    # 审计:8 条编辑,且每条都有 seq/tool/target
    assert len(mt.log) == 8
    assert [r.tool for r in mt.log.by_kind("skill")][0] == "write_skill"


def test_metatools_rewrite_immutable_rejected_and_not_logged():
    import pytest
    from youzi.harness.errors import ImmutableDoctrineError
    mt = MetaTools(_harness())
    with pytest.raises(ImmutableDoctrineError):
        mt.rewrite_doctrine("纪律:退潮不接力", "篡改")
    assert len(mt.log) == 0                       # 被拒的编辑不入审计
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_metatools.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/harness/metatools.py`**

```python
from __future__ import annotations

from youzi.harness.edit_log import EditLog, EditRecord
from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.skill import Skill


class MetaTools:
    """论文 meta-tool API:Agent/Refiner 通过它就地编辑 H=(p,K,M)。

    每个方法先执行编辑(失败则抛错、不记日志),成功后追加一条 EditRecord。
    """

    def __init__(self, harness: HarnessState, log: EditLog | None = None) -> None:
        self.h = harness
        self.log = log or EditLog()

    # ── K 技能 ──
    def write_skill(self, skill: Skill) -> EditRecord:
        self.h.skills.write(skill)
        return self.log.append("write_skill", "skill", skill.skill_id, "create", skill.name_cn)

    def patch_skill(self, skill_id: str, **fields) -> EditRecord:
        self.h.skills.patch(skill_id, **fields)
        return self.log.append("patch_skill", "skill", skill_id, "update", ",".join(fields))

    def retire_skill(self, skill_id: str, permanent: bool = False) -> EditRecord:
        self.h.skills.retire(skill_id, permanent=permanent)
        return self.log.append("retire_skill", "skill", skill_id,
                               "retired" if permanent else "dormant")

    def revive_skill(self, skill_id: str) -> EditRecord:
        self.h.skills.revive(skill_id)
        return self.log.append("revive_skill", "skill", skill_id, "revive")

    def promote_skill(self, skill_id: str) -> EditRecord:
        self.h.skills.promote(skill_id)
        return self.log.append("promote_skill", "skill", skill_id, "promote")

    # ── M 记忆 ──
    def process_memory(self, lesson: Lesson) -> EditRecord:
        self.h.memory.add(lesson)
        return self.log.append("process_memory", "memory", lesson.lesson_id, "create",
                               lesson.lesson[:24])

    def update_memory(self, lesson_id: str, **fields) -> EditRecord:
        self.h.memory.update(lesson_id, **fields)
        return self.log.append("process_memory", "memory", lesson_id, "update",
                               ",".join(fields))

    def demote_memory(self, lesson_id: str, factor: float) -> EditRecord:
        self.h.memory.demote(lesson_id, factor)
        return self.log.append("process_memory", "memory", lesson_id, "demote", str(factor))

    # ── p doctrine ──
    def rewrite_doctrine(self, section: str, new_guidance: str) -> EditRecord:
        self.h.doctrine.rewrite(section, new_guidance)   # immutable -> 抛错, 不记日志
        return self.log.append("rewrite_doctrine", "doctrine", section, "rewrite")
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_metatools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/metatools.py tests/test_metatools.py
git commit -m "feat(harness): MetaTools 门面(7 meta-tool + 审计)"
```

---

## Task 10: 真实种子集成 — 编辑序列 + 写保护

**Files:** Create `tests/test_metatools_integration.py`

- [ ] **Step 1: 写集成测试(载入真实 `seeds/`,跑 meta-tool 编辑序列)**

```python
# tests/test_metatools_integration.py
from pathlib import Path
import pytest
from youzi.harness.loader import load_seeds
from youzi.harness.metatools import MetaTools
from youzi.harness.skill import Skill
from youzi.harness.errors import ImmutableDoctrineError

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def test_metatool_edit_sequence_on_real_seeds():
    h = load_seeds(SEEDS)
    mt = MetaTools(h)
    n0 = len(h.skills)

    # 取一个真实 active 技能跑完整生命周期
    active = h.skills.by_status("active")[0]
    sid = active.skill_id
    mt.retire_skill(sid)
    assert h.skills.get(sid).status == "dormant"     # 退役不删(轮回保活)
    assert h.skills.get(sid) is not None
    mt.revive_skill(sid)
    assert h.skills.get(sid).status == "incubating"
    mt.promote_skill(sid)
    assert h.skills.get(sid).status == "active"

    # 新增一个孵化技能
    mt.write_skill(Skill.from_seed({"skill_id": "newborn_test", "name_cn": "新生测试",
                                    "type": "pattern", "applicable_regime": ["退潮"],
                                    "trigger": "t", "entry": "e", "exit_stop": "x",
                                    "status": "incubating"}))
    assert len(h.skills) == n0 + 1

    # 可变 doctrine 改写 OK
    mutable = h.doctrine.mutable_entries()[0]
    mt.rewrite_doctrine(mutable.section, "新的作战指导")
    assert h.doctrine.get(mutable.section).guidance == "新的作战指导"

    # 审计齐全(本序列 5 次成功编辑)
    assert len(mt.log) == 5


def test_immutable_core_is_write_protected_on_real_seeds():
    h = load_seeds(SEEDS)
    mt = MetaTools(h)
    core = h.doctrine.immutable_core()
    assert len(core) >= 10                       # v1 纪律红线
    before = core[0].guidance
    with pytest.raises(ImmutableDoctrineError):
        mt.rewrite_doctrine(core[0].section, "试图篡改纪律红线")
    assert h.doctrine.get(core[0].section).guidance == before   # 未被改动
    assert len(mt.log) == 0                       # 被拒不入审计


def test_for_regime_finds_multi_regime_lessons_on_real_seeds():
    # 验证 P0 修复:多 regime 记忆现在能被任一相位查到
    h = load_seeds(SEEDS)
    # 至少有一条记忆 phases 含 >1 相位(主升/退潮 之类)
    multi = [l for l in h.memory.all() if len(l.phases) > 1]
    assert multi, "应存在多相位记忆(P0 修复目标)"
    sample = multi[0]
    for phase in sample.phases:
        ids = {l.lesson_id for l in h.memory.for_regime(phase)}
        assert sample.lesson_id in ids            # 每个所属相位都能查到它
```

- [ ] **Step 2: 运行,确认通过**

Run: `pytest tests/test_metatools_integration.py -v`
Expected: PASS（若 `multi` 断言失败,说明真实种子里没有多相位记忆——回查 `seeds/memory.json`)

- [ ] **Step 3: 跑全量套件**

Run: `pytest -q`
Expected: 全绿(Phase-0a 31 + Phase-0b-1 30 + 本计划新增,约 90+ 用例)

- [ ] **Step 4: Commit**

```bash
git add tests/test_metatools_integration.py
git commit -m "test(harness): 真实种子 meta-tool 编辑序列 + immutable 写保护 + P0 多regime验证"
```

---

## Self-Review(已自检)

**1. Spec 覆盖(对照本计划 Goal/范围):**
- P0 多 regime 修复 → Task 1(parse_regime_field)+ Task 2(Lesson)+ Task 3(DoctrineEntry/Doctrine)+ Task 4(MemoryStore)+ Task 10 真实种子验证。✅
- meta-tool CRUD(write/patch/retire/revive/promote/process_memory/update/demote/rewrite)→ Task 6(registry)+ Task 7(store/doctrine)+ Task 9(MetaTools 门面)。✅
- immutable-core 写保护 → Task 5(错误类型)+ Task 7(Doctrine.rewrite/remove)+ Task 9/10(MetaTools 拒绝 + 不记日志)。✅
- 技能生命周期 dormant 复活 → Task 6(retire→dormant/revive/promote,InvalidTransitionError)+ Task 10 真实序列。✅
- 编辑审计 Δ 轨迹 → Task 8(EditLog)+ Task 9(每编辑一条 EditRecord)。✅
- **明确不在本计划**:磁盘持久化/版本化快照/回滚 → Phase-0b-3;G 子 Agent → Phase-1。

**2. Placeholder 扫描:** 无 TBD/TODO;每个改代码 step 均给完整代码 + 命令。✅

**3. 类型一致性:** `parse_regime_field` 返回 `(phases,ecologies,applies_all)` 在 Lesson/DoctrineEntry.from_seed 一致使用;`for_regime` 成员匹配在 MemoryStore/Doctrine 一致;`retire(permanent=)`/`revive`/`promote` 与 InvalidTransitionError 在 registry 定义、metatools 调用一致;`ImmutableDoctrineError` 在 errors 定义、doctrine.rewrite/remove 抛出、metatools/集成测试断言一致;`EditLog.append(tool,target_kind,target_id,op,summary)` 在 edit_log 定义、metatools 调用一致;`validate_assignment` 加在 Skill/Lesson/DoctrineEntry 三个被 patch/update 的模型上。✅

**4. 回归风险:** Task 2/3/4 改了已合并的 Lesson/DoctrineEntry/MemoryStore 的 regime 字段与查询语义 → 同步改了 `test_memory_item.py`/`test_doctrine.py`/`test_memory_store.py`;`test_loader_real_seeds.py` 不依赖 Lesson/Doctrine 的 regime 结构(只查 skills.phases 与 doctrine.immutable),保持绿。集成测试 Task 10 复核真实种子端到端。✅
