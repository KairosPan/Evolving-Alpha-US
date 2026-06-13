# Phase-1b-3d:Refiner 纪律化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 治真实数据指出的退化根因——给 `retire_skill` 加硬证据门(目标技能 `stats.n < min_retire_samples` 即拒绝)+ K-pass 提示纪律(retire 需 n≥K、faded 是空耗非亏损、能 patch 别 retire),防 Refiner 在 n=2~4 极小样本上过度退役技能。

**Architecture:** 纯改 `youzi/refine/{refiner_prompt,refiner}.py`,不动 MetaTools/registry(门是 Refiner 策略,人经 MetaTools 仍可随时退役)。门落在 `Refiner._apply_op`(rationale 检查后、dispatch 前),只读 `skill.stats.n`(观测,不改);提示注入 K 值让 LLM 知道门槛。

**Tech Stack:** Python · pydantic(`Field(ge=1)`)· pytest(全离线,MockLLM + 构造 H,不触网)。

**分支:** `phase-1b3d-refiner-discipline`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-07-phase1b3d-refiner-discipline-design.md` 与 `docs/findings/2026-06-06-real-data-hch-vs-hexpert.md`(退化根因)。

**全量回归基线:** `.venv/bin/python -m pytest -q` 当前 **237 passed**。

**任务顺序说明**:先 Task 1(给 `build_refiner_system_prompt` 加**带默认值**的 `min_retire_samples` 参 → 既有 2-参调用不破),再 Task 2(加 config 字段 + 门 + 把真实 K 值传进提示)。两个中间态都可跑。

---

### Task 1: K-pass 提示纪律(`build_refiner_system_prompt` 加 `min_retire_samples` 参 + 收缩纪律段)

**Files:**
- Modify: `youzi/refine/refiner_prompt.py:31`(函数签名)+ K-pass 分支
- Test: `tests/test_refiner_prompt.py`

- [ ] **Step 1: 写失败测试(追加到 `tests/test_refiner_prompt.py`)**

```python
def test_k_pass_prompt_has_retire_discipline():
    from youzi.refine.refiner_prompt import build_refiner_system_prompt
    from tests.test_metatools import _harness
    p = build_refiner_system_prompt(_harness(), "K", min_retire_samples=7)
    assert "n≥7" in p                      # 注入的真实门槛值
    assert "收缩纪律" in p
    assert "faded" in p and "nuked" in p and "空耗" in p
    # p-pass 不含收缩纪律段(纪律是 K 专属)
    assert "收缩纪律" not in build_refiner_system_prompt(_harness(), "p", min_retire_samples=7)


def test_build_prompt_backward_compatible_two_args():
    from youzi.refine.refiner_prompt import build_refiner_system_prompt
    from tests.test_metatools import _harness
    # 2-参调用仍可用(默认 K=5)
    p = build_refiner_system_prompt(_harness(), "K")
    assert "n≥5" in p
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_refiner_prompt.py -q`
Expected: FAIL(`build_refiner_system_prompt` 不接受 `min_retire_samples` / 无"收缩纪律")

- [ ] **Step 3: 改 `refiner_prompt.py`**

签名(第 31 行)改为:

```python
def build_refiner_system_prompt(h: HarnessState, pass_kind: PassKind,
                                min_retire_samples: int = 5) -> str:
```

在 K-pass 分支(`elif pass_kind == "K":` 渲染技能列表的循环之后)追加收缩纪律段:

```python
        out.append(
            f"\n## 收缩纪律(重要):结构性收缩(retire / 加 taboo)要克制——"
            f"**retire 需 n≥{min_retire_samples}**(样本不足会被拒);"
            f"**faded 是空耗(没续上,score 0)不是亏损**,别只因 1-2 次 faded 就退役/加禁忌;"
            f"**nuked(跌停/炸板)才是真亏**,优先据 nuke 收缩;能 patch 微调就别 retire。")
```

- [ ] **Step 4: 跑测试确认通过 + 回归既有 prompt 测试**

Run: `.venv/bin/python -m pytest tests/test_refiner_prompt.py -q`
Expected: PASS(新 2 例 + 既有全绿)

- [ ] **Step 5: 提交**

```bash
git add youzi/refine/refiner_prompt.py tests/test_refiner_prompt.py
git commit -m "feat(refine): K-pass 提示加收缩纪律(retire 需 n≥K + faded≠nuked)"
```

---

### Task 2: 退役证据门 + `RefinerConfig.min_retire_samples` + 提示注入真实 K

**Files:**
- Modify: `youzi/refine/refiner.py`(RefinerConfig 第 21-24 行;`_apply_op`;refine() 第 139 行调用)
- Test: `tests/test_refiner.py`

- [ ] **Step 1: 追加失败测试(到 `tests/test_refiner.py`)**

```python
def test_retire_gate_rejects_thin_samples():
    # _harness 技能 "a" stats.n=0(默认)< K=5 → 退役被拒、技能未退役、未记日志
    h = _harness()
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "a"}, rationale="想退役"),
                          "K", PASS_K())
    assert not ok and isinstance(res, RejectedEdit)
    assert "证据不足" in res.reason and "min_retire_samples" in res.reason
    assert h.skills.get("a").status == "active"     # 未退役
    assert len(meta.log) == 0


def test_retire_gate_allows_when_enough_samples():
    h = _harness()
    h.skills.get("a").stats.n = 5                   # 样本足够
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "a"}, rationale="n=5真亏"),
                          "K", PASS_K())
    assert ok and isinstance(res, AppliedEdit)
    assert h.skills.get("a").status == "dormant"


def test_retire_gate_applies_to_permanent_too():
    h = _harness()                                  # a.stats.n=0 < 5
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill",
                                   args={"skill_id": "a", "permanent": True}, rationale="永久"),
                          "K", PASS_K())
    assert not ok and "证据不足" in res.reason
    assert h.skills.get("a").status == "active"


def test_retire_gate_does_not_swallow_hallucinated_target():
    # 不存在的技能仍走 dispatch 的 KeyError(门只挡"存在但样本不足"),不误吞
    h = _harness()
    r = Refiner(h, MockLLMClient('{"ops": []}'), MetaTools(h), RefinerConfig(min_retire_samples=5))
    ok, res = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "不存在"}, rationale="r"),
                          "K", PASS_K())
    assert not ok and "KeyError" in res.reason


def test_refine_level_rejects_thin_retire():
    # refine() 整轮:K-pass 脚本退役 n<K 技能 → 进 rejected、H 未变
    k_ops = '{"ops": [{"tool": "retire_skill", "args": {"skill_id": "a"}, "rationale": "想退"}]}'
    rep, h, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'],
                                    cfg=RefinerConfig(min_retire_samples=5))
    assert rep.applied == []
    assert len(rep.rejected) == 1 and "证据不足" in rep.rejected[0].reason
    assert h.skills.get("a").status == "active"


def test_refiner_config_rejects_degenerate_min_retire():
    import pytest
    with pytest.raises(Exception):
        RefinerConfig(min_retire_samples=0)
```

> 复用 `tests/test_refiner.py` 既有的 `_harness`(技能 "a" active,stats 默认 n=0)、`PASS_K()`、`_run_refine`、`Refiner`/`RefinerConfig`/`RefineOp`/`MetaTools`/`MockLLMClient`/`AppliedEdit`/`RejectedEdit` import。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_refiner.py -q`
Expected: FAIL(无门:thin retire 当前会成功;`min_retire_samples` 字段不存在)

- [ ] **Step 3a: `RefinerConfig` 加字段(第 21-24 行)**

```python
class RefinerConfig(BaseModel):
    max_edits_per_pass: int = 5
    max_edits_per_refine: int = 12
    window: int = 10
    min_retire_samples: int = Field(default=5, ge=1)   # retire_skill 需 skill.stats.n>=此值,防小样本过度退役
```
(`Field` 已在第 4 行 import,无需新增。)

- [ ] **Step 3b: `_apply_op` 加退役证据门(在 rationale 检查之后、`try: rec = self._dispatch(op)` 之前)**

```python
        if not op.rationale.strip():
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason="缺 rationale")
        # 退役证据门(治真实数据退化根因:小样本过度退役)。只读 stats.n,不改 stats。
        if op.tool == "retire_skill":
            sk = self._h.skills.get(str(tid)) if tid else None
            if sk is not None and sk.stats.n < self._cfg.min_retire_samples:
                return False, RejectedEdit(
                    pass_kind=pk, tool=op.tool, target_id=tid,
                    reason=(f"证据不足:n={sk.stats.n}<min_retire_samples="
                            f"{self._cfg.min_retire_samples},不退役(faded 是空耗非亏损,样本不足别退役)"))
        try:
            rec = self._dispatch(op)
```

- [ ] **Step 3c: refine() 把真实 K 传进提示(第 139 行)**

```python
            system = build_refiner_system_prompt(self._h, pk, self._cfg.min_retire_samples)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_refiner.py -q`
Expected: PASS(新 6 例 + 既有全绿)

- [ ] **Step 5: 全量回归**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS(237 + 本阶段新增 = 245,全绿,离线不触网)

- [ ] **Step 6: 提交**

```bash
git add youzi/refine/refiner.py tests/test_refiner.py
git commit -m "feat(refine): retire 证据门(n≥min_retire_samples)+ config 字段,治小样本过度退役(真实数据根因)"
```

---

## 收尾(Task 2 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`:Phase-1b-3d 完成。
- [ ] 更新 `后续开发文档.md`:状态表 + §4 路线图(下一步 1b-3c 影子地板)+ §5 债务。
- [ ] 更新 memory:下一步 → 1b-3c。
- [ ] **(可选,人工)改进后再跑真实三窗** `scripts/smoke_compare.py`,看 HCH 退役是否被纪律纠正、Δ(HCH−Hexpert) 是否改善,记进 `docs/findings/`。

**本阶段债务(登记,非阻塞)**:① friction(`update_memory(regime=…)` 合法路径、提示列已有记忆避免重复 lesson_id、漏 lesson_id 友好报错);② 限制性 patch(加 taboo)的机械门;③ 1b-3c 影子 Hexpert 严格地板;④ faded/nuked 数值化加权信用;⑤ 多窗口/regime 聚合 + 统计显著性。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage(逐条对 spec):** §4.1 `min_retire_samples` 字段 → Task 2 Step 3a ✅;§4.2 `_apply_op` 退役门(n<K 拒、permanent 同门、幻觉 target 仍 KeyError、只读 stats)→ Task 2 Step 3b + 测试 ✅;§4.3 提示 K-pass 纪律 + 注入 K + 2-参兼容 → Task 1 ✅,refine() 传真实 K → Task 2 Step 3c ✅;§6 防火墙(只读 stats.n、不半应用)→ 门在 dispatch 前 + 测试断言 H 未变/log 空 ✅;§7 测试全覆盖(n<K/n≥K/permanent/幻觉/refine 级/config)→ Task 2 ✅;§8 DoD + 全量回归 → Task 2 Step 5 ✅。

**2. Placeholder scan:** 无 TBD/TODO;每步完整代码 + 确切命令/预期。

**3. Type consistency:** `RefinerConfig.min_retire_samples`、`_apply_op` 用 `self._h.skills.get`/`self._cfg.min_retire_samples`/`_target_id` 的 `tid`、`RejectedEdit(pass_kind/tool/target_id/reason)`、`build_refiner_system_prompt(h, pass_kind, min_retire_samples=5)` 跨 Task 1/2 一致;复用 `Refiner(harness, llm, meta, config)`、`RefineOp(tool/args/rationale)`、`PASS_K()`、`_run_refine(scripts, cfg=...)`、`Skill.stats.n` 均与既有源一致。**任务顺序**:Task 1 先加带默认的提示参(refine() 2-参调用不破)→ Task 2 再改 refine() 传真实 K,无中间态破裂。
