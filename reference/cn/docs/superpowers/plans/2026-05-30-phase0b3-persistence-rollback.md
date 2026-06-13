# Phase-0b-3 Harness 持久化:版本化快照 + 回滚 + Δ 补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把可编辑的 Harness 状态 `H=(p,K,M)` + `EditLog` **序列化落盘、版本化快照、可回滚**;并补齐终审标记的债务(EditLog 序列化、Δ payload 的 before-image、immutable 跨往返保真、`Skill.applies_all`)。让 Refiner/协同学习能在崩溃/迭代间持久化与回退 H,为蓝图 §7.1"每次 Δ 留 diff、可回滚"落地。

**Architecture:** 在已合并的 `youzi/harness/` 上扩展。`Skill` 补 `applies_all`(模型最终化)→ `HarnessState.to_dict/from_dict` 与 `EditLog.to_dict/from_dict`(pydantic `model_dump`/`model_validate` 往返,immutable 经 `model_validate` 重建、绕过 `__setattr__` 守卫故构造成功)→ `MetaTools` 给每个编辑记 before-image payload(Δ 可逆)→ `SnapshotStore`(每版本一个 JSON)→ `HarnessManager`(持有 live H+log+tools+store,`checkpoint`/`rollback_to` 重绑)。纯 Python + pydantic + 本地 JSON,**全程离线可测**;集成测试载入真实 `seeds/` 跑"编辑→快照→再编辑→回滚→断言还原"。

**Tech Stack:** Python 3.11+ · pydantic v2 · pytest · 标准库 json/pathlib。无新依赖。

**范围边界:** 不做并发/多进程锁、不做增量 delta-replay 回滚(本阶段回滚=加载整版快照,简单稳健;before-image 仅作审计可逆性铺垫)、不做 MetaTools.h/log 强封装(终审债务#3,留 Phase-1 读写边界时处理)、不修 3 条种子非 canonical token(数据债务#6,见 seeds/README)。G 子 Agent 仍待 Phase-1。

**关键设计点(对应终审债务):**
- **#5 Skill.applies_all:** `applicable_regime` 含 `"all"` → `applies_all=True`;`by_phase`/`active_skills_for` 认 `applies_all`。先做,使快照 schema 最终化。
- **#1 EditLog 序列化:** `to_dict`/`from_dict` 往返,`seq` 保真、续号正确。
- **#2 before-image:** 每个 mutate 型 meta-tool 在 payload 记 `before`/`after`,使 Δ 可逆、可人读审计。
- **#4 immutable 跨往返保真:** `model_validate` 重建 immutable 条目(绕过 `__setattr__` 守卫,构造成功),还原后守卫仍生效、纪律红线仍不可改。
- **回滚=加载整版快照**(snapshot-based),`HarnessManager.rollback_to` 重绑 `tools` 到还原后的 H+log。

---

## File Structure

```
youzi/harness/
  skill.py          # MODIFY: + applies_all 字段; from_seed 解析 "all"
  registry.py       # MODIFY: by_phase 认 applies_all
  harness.py        # MODIFY: HarnessState + to_dict / from_dict
  edit_log.py       # MODIFY: EditLog + to_dict / from_dict
  metatools.py      # MODIFY: 各 mutate meta-tool 记 before-image payload
  snapshot.py       # NEW: SnapshotStore(每版本一个 JSON 文件)
  manager.py        # NEW: HarnessManager(checkpoint / rollback_to / latest_version)
tests/
  test_skill.py                  # + applies_all
  test_registry.py               # + by_phase applies_all
  test_harness_serialize.py      # NEW: H 往返(immutable + stats + status 保真)
  test_edit_log.py               # + 序列化往返
  test_metatools.py              # + before-image payload
  test_snapshot.py               # NEW
  test_manager.py                # NEW
  test_phase0b3_integration.py   # NEW: 真实种子 编辑→快照→再编辑→回滚→断言
```

**全局类型契约(后续任务一致引用):**
- `Skill.applies_all: bool`;`Skill.from_seed` 把 `applicable_regime` 里的 `"all"` 解析为 `applies_all=True`(其余经 `split_regimes`)。`SkillRegistry.by_phase(phase)` = `phase in s.phases or s.applies_all`。
- `HarnessState.to_dict() -> dict`;`HarnessState.from_dict(d) -> HarnessState`(用 `model_validate` 重建)。
- `EditLog.to_dict() -> list[dict]`;`EditLog.from_dict(data) -> EditLog`(保真 seq)。
- `SnapshotStore(root)`:`save(harness, log, label="") -> int`、`list_versions() -> list[int]`、`latest() -> int|None`、`load(version) -> tuple[HarnessState, EditLog]`。
- `HarnessManager(harness, store, log=None)`:`.harness`/`.log`/`.tools`(MetaTools)/`.store`;`checkpoint(label="") -> int`、`rollback_to(version)`、`latest_version()`。
- MetaTools mutate 方法的 `EditRecord.payload` 含 `before`/`after`(或等价 before-image)。

---

## Task 1: `Skill.applies_all`(模型最终化,债务#5)

**Files:** Modify `youzi/harness/skill.py`, `youzi/harness/registry.py`; Modify `tests/test_skill.py`, `tests/test_registry.py`

- [ ] **Step 1: 追加失败测试**

`tests/test_skill.py` 追加:
```python
def test_skill_from_seed_applies_all():
    s = Skill.from_seed({"skill_id": "u", "name_cn": "通用", "type": "pattern",
                         "applicable_regime": ["all"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})
    assert s.applies_all is True
    assert s.phases == [] and s.ecologies == []      # "all" 不进 phases
    s2 = Skill.from_seed({"skill_id": "v", "name_cn": "甲", "type": "pattern",
                          "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                          "exit_stop": "x", "status": "active"})
    assert s2.applies_all is False and s2.phases == ["主升"]
```

`tests/test_registry.py` 追加:
```python
def test_by_phase_honors_applies_all():
    universal = Skill.from_seed({"skill_id": "risk", "name_cn": "风控通则", "type": "failure_detector",
                                 "applicable_regime": ["all"], "trigger": "t", "entry": "规避",
                                 "exit_stop": "N/A", "status": "active"})
    reg = SkillRegistry.from_skills([_one(), universal])
    # universal 对任意相位都命中;_one() 只在 主升
    assert {s.skill_id for s in reg.by_phase("退潮")} == {"risk"}
    assert {s.skill_id for s in reg.by_phase("主升")} == {"a", "risk"}
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd "/Volumes/kairos/引力场量化/youzi-自进化版" && source .venv/bin/activate && pytest tests/test_skill.py tests/test_registry.py -v`
Expected: FAIL（`Skill` 无 `applies_all` / `by_phase` 未认 applies_all）

- [ ] **Step 3: 改 `youzi/harness/skill.py`**

给 `Skill` 加字段(放在 `ecologies` 之后):
```python
    applies_all: bool = False             # applicable_regime 含 "all" 则对任意相位通用
```
改 `from_seed`:
```python
    @classmethod
    def from_seed(cls, d: dict) -> "Skill":
        raw = d.get("applicable_regime", [])
        applies_all = "all" in raw
        phases, ecologies = split_regimes([r for r in raw if r != "all"])
        return cls(**{**d, "phases": phases, "ecologies": ecologies,
                      "applies_all": applies_all})
```

- [ ] **Step 4: 改 `youzi/harness/registry.py` 的 `by_phase`**

```python
    def by_phase(self, phase: str) -> list[Skill]:
        return [s for s in self._skills.values() if phase in s.phases or s.applies_all]
```

- [ ] **Step 5: 运行,确认通过**

Run: `pytest tests/test_skill.py tests/test_registry.py -v`
Expected: PASS（注意真实种子里无 "all" 技能,`active_skills_for` 行为不变)

- [ ] **Step 6: Commit**

```bash
git add youzi/harness/skill.py youzi/harness/registry.py tests/test_skill.py tests/test_registry.py
git commit -m "feat(harness): Skill.applies_all + by_phase 认通用技能(债务#5)"
```

---

## Task 2: `HarnessState` 序列化往返

**Files:** Modify `youzi/harness/harness.py`; Test `tests/test_harness_serialize.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_harness_serialize.py
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.errors import ImmutableDoctrineError


def _harness():
    a = Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})
    a.stats.record(win=True, decay=0.3)          # 让 stats 非默认
    a.status = "dormant"
    skills = SkillRegistry.from_skills([a])
    mem = MemoryStore.from_lessons([
        Lesson.from_seed({"lesson_id": "l1", "regime": "主升/退潮", "outcome": "loss",
                          "lesson": "教训"})])
    mem.demote("l1", 0.5)
    doc = Doctrine(entries=[
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升",
                                 "immutable": False, "guidance": "持有龙头"}),
        DoctrineEntry.from_seed({"section": "纪律:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮禁接力"})])
    cyc = StateMachine.from_seed_list([{"phase": "主升", "you_see": ["龙头突破"],
                                        "transitions": [{"to": "震荡补涨", "signal": "强分歧阴K"}]}])
    return HarnessState(doctrine=doc, skills=skills, memory=mem, cycle=cyc)


def test_harness_roundtrip_preserves_state():
    h = _harness()
    h2 = HarnessState.from_dict(h.to_dict())
    # 技能:status / stats 保真
    s = h2.skills.get("a")
    assert s.status == "dormant"
    assert s.stats.n == 1 and s.stats.ewma_winrate == 1.0
    assert s.phases == ["主升"]
    # 记忆:多 regime + importance 保真
    l = h2.memory.get("l1")
    assert l.phases == ["主升", "退潮"]
    assert abs(l.importance.time_decay - 0.5) < 1e-9
    # doctrine / cycle 数量保真
    assert len(h2.doctrine.entries) == 2
    assert h2.cycle.get("主升").you_see == ["龙头突破"]


def test_roundtrip_preserves_immutable_protection():
    h2 = HarnessState.from_dict(_harness().to_dict())
    imm = h2.doctrine.immutable_core()[0]
    assert imm.immutable is True
    import pytest
    with pytest.raises(ImmutableDoctrineError):
        imm.guidance = "篡改"           # 还原后守卫仍生效
    # 可变条目仍可改
    mut = h2.doctrine.mutable_entries()[0]
    mut.guidance = "改了"
    assert mut.guidance == "改了"
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_harness_serialize.py -v`
Expected: FAIL（`HarnessState` 无 `to_dict`/`from_dict`）

- [ ] **Step 3: 给 `youzi/harness/harness.py` 加序列化**

在 import 区追加 `from youzi.harness.memory_item import Lesson`,并给 `HarnessState` 加方法:
```python
    def to_dict(self) -> dict:
        """序列化整个 H(skills/memory 各 model_dump 列表 + doctrine/cycle model_dump)。"""
        return {
            "skills": [s.model_dump() for s in self.skills.all()],
            "memory": [l.model_dump() for l in self.memory.all()],
            "doctrine": self.doctrine.model_dump(),
            "cycle": self.cycle.model_dump(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HarnessState":
        """从 to_dict 还原。用 model_validate 重建(immutable 条目经 core 构造,绕过 __setattr__ 守卫故成功)。"""
        return cls(
            doctrine=Doctrine.model_validate(d["doctrine"]),
            skills=SkillRegistry.from_skills([Skill.model_validate(x) for x in d["skills"]]),
            memory=MemoryStore.from_lessons([Lesson.model_validate(x) for x in d["memory"]]),
            cycle=StateMachine.model_validate(d["cycle"]),
        )
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_harness_serialize.py -v`
Expected: PASS（特别是 immutable 还原后守卫仍生效 + stats/importance 保真）

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/harness.py tests/test_harness_serialize.py
git commit -m "feat(harness): HarnessState 序列化往返(immutable/stats/importance 保真)"
```

---

## Task 3: `EditLog` 序列化(债务#1)

**Files:** Modify `youzi/harness/edit_log.py`; Modify `tests/test_edit_log.py`

- [ ] **Step 1: 追加失败测试到 `tests/test_edit_log.py`**

```python
def test_edit_log_roundtrip_preserves_seq_and_continues():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create", "甲")
    log.append("retire_skill", "skill", "a", "retire", "dormant", payload={"before": "active"})
    data = log.to_dict()
    assert isinstance(data, list) and len(data) == 2

    restored = EditLog.from_dict(data)
    assert len(restored) == 2
    assert [r.seq for r in restored.records()] == [0, 1]
    assert restored.records()[1].payload == {"before": "active"}
    # 续号:还原后再 append 接着 seq=2
    r2 = restored.append("promote_skill", "skill", "a", "promote")
    assert r2.seq == 2
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_edit_log.py -v`
Expected: FAIL（`EditLog` 无 `to_dict`/`from_dict`）

- [ ] **Step 3: 给 `youzi/harness/edit_log.py` 的 `EditLog` 加序列化**

```python
    def to_dict(self) -> list[dict]:
        return [r.model_dump() for r in self._records]

    @classmethod
    def from_dict(cls, data: list[dict]) -> "EditLog":
        log = cls()
        log._records = [EditRecord.model_validate(r) for r in data]
        return log
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_edit_log.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/edit_log.py tests/test_edit_log.py
git commit -m "feat(harness): EditLog 序列化往返(seq 保真,债务#1)"
```

---

## Task 4: MetaTools before-image payload(债务#2)

**Files:** Modify `youzi/harness/metatools.py`; Modify `tests/test_metatools.py`

> 给 mutate 型 meta-tool 在 payload 记 `before`/`after`,使 Δ 可逆、可人读。读取 before 发生在 CRUD 之前(CRUD 抛错则不记日志)。

- [ ] **Step 1: 追加失败测试到 `tests/test_metatools.py`**

```python
def test_metatools_payload_has_before_after():
    mt = MetaTools(_harness())
    mt.patch_skill("a", notes="新备注")
    rec = mt.log.records()[-1]
    assert rec.payload["before"] == {"notes": ""} and rec.payload["after"] == {"notes": "新备注"}

    mt.retire_skill("a")
    rec = mt.log.records()[-1]
    assert rec.payload == {"before": "active", "after": "dormant"}

    mt.demote_memory("l1", 0.5)
    rec = mt.log.records()[-1]
    assert rec.payload["factor"] == 0.5 and "before_time_decay" in rec.payload
```

（`_harness()` 复用 `tests/test_metatools.py` 已有的 fixture;若其 doctrine/skill 字段不同,按其实际值调整断言。`_harness()` 里 skill "a" 初始 `notes=""`、`status="active"`。)

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_metatools.py -v`
Expected: FAIL（payload 还没有 before/after）

- [ ] **Step 3: 改 `youzi/harness/metatools.py` 的 mutate 方法记 before-image**

把以下方法改为先读 before、再 CRUD、再记带 payload 的日志(其余方法不变):
```python
    def patch_skill(self, skill_id: str, **fields) -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = {k: getattr(s, k) for k in fields if s is not None and k in type(s).model_fields}
        self.h.skills.patch(skill_id, **fields)
        return self.log.append("patch_skill", "skill", skill_id, "update",
                               ",".join(f"{k}={v}" for k, v in fields.items()),
                               payload={"before": before, "after": fields})

    def retire_skill(self, skill_id: str, permanent: bool = False) -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.retire(skill_id, permanent=permanent)
        after = "retired" if permanent else "dormant"
        return self.log.append("retire_skill", "skill", skill_id, "retire", after,
                               payload={"before": before, "after": after})

    def revive_skill(self, skill_id: str) -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.revive(skill_id)
        return self.log.append("revive_skill", "skill", skill_id, "revive", "",
                               payload={"before": before, "after": "incubating"})

    def promote_skill(self, skill_id: str) -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.promote(skill_id)
        return self.log.append("promote_skill", "skill", skill_id, "promote", "",
                               payload={"before": before, "after": "active"})

    def update_memory(self, lesson_id: str, **fields) -> EditRecord:
        l = self.h.memory.get(lesson_id)
        before = {k: getattr(l, k) for k in fields if l is not None and k in type(l).model_fields}
        self.h.memory.update(lesson_id, **fields)
        return self.log.append("update_memory", "memory", lesson_id, "update",
                               ",".join(fields), payload={"before": before, "after": fields})

    def demote_memory(self, lesson_id: str, factor: float) -> EditRecord:
        l = self.h.memory.get(lesson_id)
        before_td = l.importance.time_decay if l is not None else None
        self.h.memory.demote(lesson_id, factor)
        return self.log.append("demote_memory", "memory", lesson_id, "demote", str(factor),
                               payload={"before_time_decay": before_td, "factor": factor})
```
（`write_skill`/`process_memory`/`rewrite_doctrine` 保持 Phase-0b-2 实现:write/process 为 create 无 before;rewrite_doctrine 已记 `{"old","new"}`。)

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_metatools.py -v`
Expected: PASS（被拒编辑仍不记日志:CRUD 抛错发生在 append 之前)

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/metatools.py tests/test_metatools.py
git commit -m "feat(harness): meta-tool before-image payload(Δ 可逆,债务#2)"
```

---

## Task 5: `SnapshotStore`(版本化磁盘快照)

**Files:** Create `youzi/harness/snapshot.py`; Test `tests/test_snapshot.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_snapshot.py
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.edit_log import EditLog
from youzi.harness.snapshot import SnapshotStore


def _h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    return HarnessState(doctrine=Doctrine(), skills=skills,
                        memory=MemoryStore.from_lessons([]),
                        cycle=StateMachine())


def test_snapshot_save_list_load(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.list_versions() == [] and store.latest() is None
    log = EditLog()
    log.append("write_skill", "skill", "a", "create")
    v0 = store.save(_h(), log, label="初始")
    v1 = store.save(_h(), EditLog(), label="次版")
    assert v0 == 0 and v1 == 1
    assert store.list_versions() == [0, 1] and store.latest() == 1

    h, lg = store.load(0)
    assert h.skills.get("a").name_cn == "甲"
    assert len(lg) == 1 and lg.records()[0].tool == "write_skill"


def test_snapshot_load_missing_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        SnapshotStore(tmp_path).load(99)
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_snapshot.py -v`
Expected: FAIL（`ModuleNotFoundError: youzi.harness.snapshot`）

- [ ] **Step 3: 实现 `youzi/harness/snapshot.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from youzi.harness.edit_log import EditLog
from youzi.harness.harness import HarnessState


class SnapshotStore:
    """版本化磁盘快照:每个版本一个 JSON 文件 root/snap_<NNNN>.json,内含 {version,label,harness,log}。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, version: int) -> Path:
        return self._root / f"snap_{version:04d}.json"

    def list_versions(self) -> list[int]:
        if not self._root.is_dir():
            return []
        out: list[int] = []
        for p in self._root.glob("snap_*.json"):
            try:
                out.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return sorted(out)

    def latest(self) -> int | None:
        vs = self.list_versions()
        return vs[-1] if vs else None

    def save(self, harness: HarnessState, log: EditLog, label: str = "") -> int:
        self._root.mkdir(parents=True, exist_ok=True)
        latest = self.latest()
        version = 0 if latest is None else latest + 1
        payload = {"version": version, "label": label,
                   "harness": harness.to_dict(), "log": log.to_dict()}
        self._path(version).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return version

    def load(self, version: int) -> tuple[HarnessState, EditLog]:
        p = self._path(version)
        if not p.exists():
            raise FileNotFoundError(f"无此快照版本: {version} ({p})")
        data = json.loads(p.read_text(encoding="utf-8"))
        return (HarnessState.from_dict(data["harness"]), EditLog.from_dict(data["log"]))
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_snapshot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/snapshot.py tests/test_snapshot.py
git commit -m "feat(harness): SnapshotStore 版本化磁盘快照"
```

---

## Task 6: `HarnessManager`(checkpoint + 回滚)

**Files:** Create `youzi/harness/manager.py`; Test `tests/test_manager.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_manager.py
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.snapshot import SnapshotStore
from youzi.harness.manager import HarnessManager


def _h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    return HarnessState(doctrine=Doctrine(), skills=skills,
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def test_checkpoint_then_edit_then_rollback(tmp_path):
    mgr = HarnessManager(_h(), SnapshotStore(tmp_path))
    v0 = mgr.checkpoint(label="干净")
    assert v0 == 0 and mgr.latest_version() == 0

    # 编辑:退役 a + 新增 b
    mgr.tools.retire_skill("a")
    mgr.tools.write_skill(Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "pattern",
                                           "applicable_regime": ["退潮"], "trigger": "t",
                                           "entry": "e", "exit_stop": "x", "status": "incubating"}))
    assert mgr.harness.skills.get("a").status == "dormant"
    assert mgr.harness.skills.get("b") is not None
    assert len(mgr.log) == 2

    # 回滚到 v0:编辑全部撤销
    mgr.rollback_to(0)
    assert mgr.harness.skills.get("a").status == "active"   # 退役被撤销
    assert mgr.harness.skills.get("b") is None              # 新增被撤销
    assert len(mgr.log) == 0                                # 日志回到 v0(空)
    # tools 已重绑到还原后的 H:继续编辑作用在还原态上
    mgr.tools.retire_skill("a")
    assert mgr.harness.skills.get("a").status == "dormant"
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_manager.py -v`
Expected: FAIL（`ModuleNotFoundError: youzi.harness.manager`）

- [ ] **Step 3: 实现 `youzi/harness/manager.py`**

```python
from __future__ import annotations

from youzi.harness.edit_log import EditLog
from youzi.harness.harness import HarnessState
from youzi.harness.metatools import MetaTools
from youzi.harness.snapshot import SnapshotStore


class HarnessManager:
    """持有 live H + EditLog + MetaTools + SnapshotStore;统一 checkpoint / rollback。

    回滚 = 加载整版快照并把 tools 重绑到还原后的 H+log,后续编辑作用在还原态上。
    """

    def __init__(self, harness: HarnessState, store: SnapshotStore,
                 log: EditLog | None = None) -> None:
        self.harness = harness
        self.log = log or EditLog()
        self.store = store
        self.tools = MetaTools(self.harness, self.log)

    def checkpoint(self, label: str = "") -> int:
        return self.store.save(self.harness, self.log, label)

    def rollback_to(self, version: int) -> None:
        self.harness, self.log = self.store.load(version)
        self.tools = MetaTools(self.harness, self.log)     # 重绑到还原态

    def latest_version(self) -> int | None:
        return self.store.latest()
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/harness/manager.py tests/test_manager.py
git commit -m "feat(harness): HarnessManager checkpoint + 快照回滚"
```

---

## Task 7: 真实种子端到端集成

**Files:** Create `tests/test_phase0b3_integration.py`

- [ ] **Step 1: 写集成测试(载入真实 `seeds/`,编辑→快照→再编辑→回滚)**

```python
# tests/test_phase0b3_integration.py
from pathlib import Path
import pytest
from youzi.harness.loader import load_seeds
from youzi.harness.snapshot import SnapshotStore
from youzi.harness.manager import HarnessManager
from youzi.harness.skill import Skill
from youzi.harness.errors import ImmutableDoctrineError

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def test_full_persist_edit_rollback_cycle(tmp_path):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tmp_path))
    n0 = len(mgr.harness.skills)
    log0 = len(mgr.log)

    v0 = mgr.checkpoint(label="种子初始")

    # 一串编辑
    active = mgr.harness.skills.by_status("active")[0]
    mgr.tools.retire_skill(active.skill_id)
    mgr.tools.write_skill(Skill.from_seed({"skill_id": "p0b3_new", "name_cn": "新生", "type": "pattern",
                                           "applicable_regime": ["退潮"], "trigger": "t",
                                           "entry": "e", "exit_stop": "x", "status": "incubating"}))
    mutable = mgr.harness.doctrine.mutable_entries()[0]
    mgr.tools.rewrite_doctrine(mutable.section, "新作战指导")
    assert len(mgr.harness.skills) == n0 + 1
    assert len(mgr.log) == log0 + 3

    v1 = mgr.checkpoint(label="编辑后")
    assert sorted(mgr.store.list_versions()) == [v0, v1]

    # 回滚到 v0:全部编辑撤销
    mgr.rollback_to(v0)
    assert len(mgr.harness.skills) == n0
    assert mgr.harness.skills.get("p0b3_new") is None
    assert mgr.harness.skills.get(active.skill_id).status == "active"
    assert mgr.harness.doctrine.get(mutable.section).guidance == mutable.guidance  # 改写被撤销
    assert len(mgr.log) == log0

    # 还原后 immutable 守卫仍生效
    core = mgr.harness.doctrine.immutable_core()
    assert len(core) >= 10
    with pytest.raises(ImmutableDoctrineError):
        mgr.tools.rewrite_doctrine(core[0].section, "试图篡改")


def test_rollback_to_edited_version_keeps_edits(tmp_path):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tmp_path))
    mgr.checkpoint()                                  # v0 干净
    sid = mgr.harness.skills.by_status("active")[0].skill_id
    mgr.tools.retire_skill(sid)
    v1 = mgr.checkpoint()                              # v1 含退役
    mgr.rollback_to(0)
    assert mgr.harness.skills.get(sid).status == "active"
    mgr.rollback_to(v1)                               # 回到编辑后版本
    assert mgr.harness.skills.get(sid).status == "dormant"
```

- [ ] **Step 2: 运行,确认通过**

Run: `pytest tests/test_phase0b3_integration.py -v`
Expected: PASS

- [ ] **Step 3: 跑全量套件**

Run: `pytest -p no:cacheprovider` （`-q` 摘要在本 shell 经管道会空,直接看退出码/逐项;约 95+ 用例全绿）
Expected: exit 0,全绿

- [ ] **Step 4: Commit**

```bash
git add tests/test_phase0b3_integration.py
git commit -m "test(harness): Phase-0b-3 真实种子 编辑→快照→回滚 端到端 + immutable 保真"
```

---

## Self-Review(已自检)

**1. Spec 覆盖(对照本计划 Goal/范围):**
- 版本化磁盘快照 → Task 5 `SnapshotStore`。✅
- 回滚 → Task 6 `HarnessManager.rollback_to`(加载整版快照 + 重绑 tools)+ Task 7 端到端。✅
- HarnessState 序列化往返(含 immutable/stats/importance 保真)→ Task 2。✅
- 债务#1 EditLog 序列化 → Task 3。✅
- 债务#2 before-image payload → Task 4。✅
- 债务#4 immutable 跨往返保真 → Task 2 `test_roundtrip_preserves_immutable_protection` + Task 7。✅
- 债务#5 Skill.applies_all → Task 1。✅
- **明确不在本计划**:#3 MetaTools.h/log 强封装(留 Phase-1)、#6 种子 token 修正(数据,见 README)、增量 delta-replay 回滚、并发锁、G 子 Agent(Phase-1)。

**2. Placeholder 扫描:** 无 TBD/TODO;每个改代码 step 均给完整代码 + 命令。✅

**3. 类型一致性:** `Skill.applies_all` 在 Task 1 加、`by_phase`/`active_skills_for` 用、Task 2 序列化 model_dump/validate 自动带;`HarnessState.to_dict/from_dict` 在 Task 2 定义、Task 5 `SnapshotStore` 调用一致;`EditLog.to_dict/from_dict` 在 Task 3 定义、Task 5 调用一致;`HarnessManager(.harness/.log/.tools/.store)` 在 Task 6 定义、Task 7 使用一致;before-image `payload{before,after}` 在 Task 4 写、Task 4 测试断言一致。✅

**4. 回归风险:** Task 1 改 `Skill`(加 applies_all 默认 False)与 `by_phase`(加 `or applies_all`)——真实种子无 "all" 技能故 `active_skills_for`/`test_loader_real_seeds` 行为不变;Task 4 改 `metatools.py` 的 payload——Phase-0b-2 的 `test_metatools` 既有断言查 `len(mt.log)`/`tool`/`op`,不查 payload 细节,保持绿(新增断言查 payload)。序列化用 `model_validate` 重建 immutable 条目,经 core 构造绕过 `__setattr__` 守卫,故还原成功且守卫随后生效——Task 2/7 显式验证。✅
