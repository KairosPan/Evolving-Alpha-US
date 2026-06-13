# Phase-1b-2:LLM Refiner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 LLM Refiner 读 1b-1 的证据(`CreditReport`/`FailureSignature`/已填 `SkillStats`)+ 当前 H,经 9 个 meta-tool 把教训结构性写回 H(进 `EditLog`),系统开始自进化;同时清掉相邻三项(信用注入 agent 提示、鲁棒 JSON 提取器、DeepSeek retry)。

**Architecture:** 论文式 4-pass CRUD(Δp→ΔG→ΔK→ΔM,reset-free,顺序执行同一 `HarnessState`),ΔG 因 G 子 Agent 未建作占位 no-op(不发 LLM 调用)。Refiner 是纯组件 `refine(traj, credit, signatures) -> RefineReport`,就地编辑、不 checkpoint/不回滚(那是 1b-3)。LLM 输出经白名单+schema 校验+caps+rationale 必填的拒绝管线过滤,immutable/非法转移/越权/幻觉/malformed 一律拒绝、绝不半应用、绝不崩。

**Tech Stack:** Python · pydantic(frozen 快照 + `extra="forbid"` + `validate_assignment`)· pytest(全离线,`MockLLMClient` + 真实/构造种子 H,不触网)。

**分支:** `phase-1b2-llm-refiner`(执行时建)。**先读** spec:`docs/superpowers/specs/2026-06-06-phase1b2-llm-refiner-design.md` 与 `后续开发文档.md` §2 不变量。

**Bundle 分组(供 subagent-driven 派活):**
- **Bundle A(相邻三项,独立)**:Task 1-4
- **Bundle B(审计 + Refiner 基件)**:Task 5-7
- **Bundle C(4-pass 编排 + 提示 + 集成)**:Task 8-9

**全量回归基线:** `python -m pytest -q` 当前 163 passed。每个 Task 末尾跑相关测试 + 不破回归。

---

## Bundle A — 相邻三项

### Task 1: 鲁棒共享 JSON 提取器(③)

**Files:**
- Create: `youzi/llm/extract.py`
- Test: `tests/test_llm_extract.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_llm_extract.py
from youzi.llm.extract import extract_json_object


def test_pure_object():
    assert extract_json_object('{"a": 1}') == '{"a": 1}'


def test_prose_prefix():
    assert extract_json_object('好的,结果如下:{"a": 1} 完毕') == '{"a": 1}'


def test_thinking_blob_prefix():
    raw = '让我想想... 也许 {不是JSON 这里 然后\n最终答案:{"ops": [{"tool": "x"}]}'
    # 第一个 '{' 是 "{不是JSON ..." —— 它不配平到合法 JSON,但配平扫描按括号深度截断
    out = extract_json_object(raw)
    assert out is not None and out.startswith("{") and out.endswith("}")


def test_markdown_fence():
    raw = '```json\n{"a": 1, "b": {"c": 2}}\n```'
    assert extract_json_object(raw) == '{"a": 1, "b": {"c": 2}}'


def test_nested_object():
    assert extract_json_object('{"a": {"b": {"c": 1}}}') == '{"a": {"b": {"c": 1}}}'


def test_braces_inside_string_not_counted():
    s = '{"k": "有个 } 和 { 在字符串里", "n": 1}'
    assert extract_json_object(s) == s


def test_escaped_quote_inside_string():
    s = '{"k": "他说\\"对\\"了 }", "n": 1}'
    assert extract_json_object(s) == s


def test_multiple_objects_takes_first():
    assert extract_json_object('{"a": 1}{"b": 2}') == '{"a": 1}'


def test_no_object_returns_none():
    assert extract_json_object("没有大括号") is None
    assert extract_json_object("") is None


def test_unbalanced_returns_none():
    assert extract_json_object('{"a": 1') is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_llm_extract.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.llm.extract`)

- [ ] **Step 3: 实现**

```python
# youzi/llm/extract.py
from __future__ import annotations


def extract_json_object(raw: str) -> str | None:
    """从含 prose/markdown 围栏/thinking 前缀的文本里取第一个**配平**的 JSON 对象子串。

    扫描:跳到第一个 '{',按括号深度配平;字符串字面量内的 '{'/'}' 不计深度(尊重 \\ 转义)。
    深度归零处截断返回。找不到配平对象 → None。
    已知限制:若 prose 中先出现一个配平的 {...}(非目标 JSON),会返回它——agent/Refiner 均用
    json_object 模式,响应基本是纯 JSON,故风险低。
    """
    s = raw or ""
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_llm_extract.py -q`
Expected: PASS(10 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/llm/extract.py tests/test_llm_extract.py
git commit -m "feat(llm): 鲁棒配平括号 JSON 提取器 extract_json_object(③)"
```

---

### Task 2: `agent/parse._extract_json` 复用提取器(③)

**Files:**
- Modify: `youzi/agent/parse.py:10-21`
- Test: `tests/test_parse.py`(既有,守等价)+ 新增一例

- [ ] **Step 1: 加一条 thinking-前缀回归测试**

追加到 `tests/test_parse.py` 末尾:

```python
def test_parse_tolerates_prose_prefix():
    from datetime import date
    from youzi.agent.parse import parse_decision
    from youzi.universe.universe import CandidateUniverse
    from youzi.universe.stock import StockSnapshot
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(code="000001", name="平安", status="limit_up", boards=2)])
    raw = '我分析后认为:\n{"candidates": [{"code": "000001", "pattern": "接力", "confidence": 0.7}], "no_trade_reason": ""}'
    pkg = parse_decision(raw, date(2024, 6, 27), uni)
    assert [c.code for c in pkg.candidates] == ["000001"]
```

- [ ] **Step 2: 跑新测试确认失败**

Run: `python -m pytest tests/test_parse.py::test_parse_tolerates_prose_prefix -q`
Expected: FAIL(旧 `_extract_json` first-`{`-to-last-`}` 对该输入恰好也能过?若已 PASS,仍继续 Step 3 重构以共享实现并锁回归)

- [ ] **Step 3: 重构 `_extract_json` 委托给提取器**

把 `youzi/agent/parse.py` 顶部 import 加上,并替换 `_extract_json`(第 10-21 行)整体为:

```python
from youzi.llm.extract import extract_json_object


def _extract_json(raw: str) -> str:
    """委托共享提取器(贪婪配平);找不到对象 → 空串(交给上层 json.loads 兜底为空仓)。"""
    return extract_json_object(raw) or ""
```

(删除原 markdown-fence 特判与 first-`{`-to-last-`}` 逻辑;`extract_json_object` 已覆盖围栏与配平。)

- [ ] **Step 4: 跑测试确认通过(含既有等价)**

Run: `python -m pytest tests/test_parse.py -q`
Expected: PASS(既有用例全绿 + 新例通过)

- [ ] **Step 5: 提交**

```bash
git add youzi/agent/parse.py tests/test_parse.py
git commit -m "refactor(agent): parse._extract_json 复用 extract_json_object,守既有等价(③)"
```

---

### Task 3: agent 系统提示注入战绩 + win 记忆(②)

**Files:**
- Modify: `youzi/agent/prompt.py:32-45`
- Test: `tests/test_agent_prompt_stats.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_agent_prompt_stats.py
from youzi.agent.prompt import build_system_prompt
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState


def _h(skills, lessons):
    return HarnessState(
        doctrine=Doctrine(entries=[]),
        skills=SkillRegistry.from_skills(skills),
        memory=MemoryStore.from_lessons(lessons),
        cycle=StateMachine.from_seed_list([]))


def _skill(sid="s1", status="active"):
    return Skill.from_seed({"skill_id": sid, "name_cn": "龙头接力", "type": "pattern",
                            "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                            "exit_stop": "x", "status": status})


def test_no_stats_no_winmem_is_unchanged_skill_line():
    s = _skill()
    h = _h([s], [])
    prompt = build_system_prompt(h)
    # n==0:技能行不含战绩串
    assert "战绩" not in prompt
    assert "[成功]" not in prompt
    # 行体与原格式一致
    assert "- 龙头接力(s1)[pattern] 适用[主升] 触发:t 买点:e 卖/止:x 禁忌:" in prompt


def test_stats_rendered_when_n_positive():
    s = _skill()
    s.stats.n = 5
    s.stats.wins = 1
    s.stats.nukes = 3
    s.stats.ewma_winrate = 0.2
    s.stats.expectancy = -0.4
    h = _h([s], [])
    prompt = build_system_prompt(h)
    assert "[战绩 n=5 胜率=0.20 nukes=3 exp=-0.40]" in prompt


def test_win_memory_rendered():
    s = _skill()
    win = Lesson.from_seed({"lesson_id": "w1", "regime": "主升", "outcome": "win",
                            "named_analog": "妖股X", "lesson": "低吸成功"})
    h = _h([s], [win])
    prompt = build_system_prompt(h)
    assert "- [成功] 妖股X:低吸成功" in prompt
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_agent_prompt_stats.py -q`
Expected: FAIL(`战绩`/`[成功]` 未渲染)

- [ ] **Step 3: 改 `build_system_prompt`**

把 `youzi/agent/prompt.py` 第 32-37 行的技能循环替换为:

```python
    out.append("\n## 模式库(可用技能,只在适用相位用):")
    for s in h.skills.by_status("active"):
        tags = "/".join(s.phases) + (("|" + "/".join(s.ecologies)) if s.ecologies else "")
        line = (f"- {s.name_cn}({s.skill_id})[{s.type}] 适用[{tags}] "
                f"触发:{s.trigger} 买点:{s.entry} 卖/止:{s.exit_stop} "
                f"禁忌:{';'.join(s.taboo)}")
        st = s.stats
        if st.n > 0:                                   # 有战绩才渲染,让 agent 看到亏/被砸
            bits = f"n={st.n}"
            if st.ewma_winrate is not None:
                bits += f" 胜率={st.ewma_winrate:.2f}"
            bits += f" nukes={st.nukes}"
            if st.expectancy is not None:
                bits += f" exp={st.expectancy:+.2f}"
            line += f" [战绩 {bits}]"
        out.append(line)
```

并在第 42-45 行 `loss` 循环之后,追加 `win` 循环:

```python
    for l in h.memory.all():
        if l.outcome == "win":
            tag = f"{l.named_analog}:" if l.named_analog else ""
            out.append(f"- [成功] {tag}{l.lesson}")
```

- [ ] **Step 4: 跑测试确认通过 + 回归 prompt 测试**

Run: `python -m pytest tests/test_agent_prompt_stats.py tests/test_prompt.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add youzi/agent/prompt.py tests/test_agent_prompt_stats.py
git commit -m "feat(agent): 系统提示注入技能战绩 + win 记忆,闭合 1b-1→agent(②)"
```

---

### Task 4: `DeepSeekClient` retry/backoff(①)

**Files:**
- Modify: `youzi/llm/client.py:30-51`
- Test: `tests/test_deepseek_retry.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_deepseek_retry.py
import types
import pytest
from youzi.llm.client import DeepSeekClient


class _FakeCreate:
    def __init__(self, fails, content):
        self.calls = 0
        self.fails = fails
        self.content = content

    def __call__(self, **kw):
        self.calls += 1
        if self.calls <= self.fails:
            raise RuntimeError("boom")
        msg = types.SimpleNamespace(content=self.content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def _client_with_fake(fails, content='{"ok": 1}', max_retries=3):
    sleeps = []
    c = DeepSeekClient(api_key="test", max_retries=max_retries, backoff=1.0,
                       sleep=lambda d: sleeps.append(d))
    fake = _FakeCreate(fails, content)
    c._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=fake)))
    return c, fake, sleeps


def test_retry_then_success():
    c, fake, sleeps = _client_with_fake(fails=2)
    assert c.complete("s", "u") == '{"ok": 1}'
    assert fake.calls == 3
    assert sleeps == [1.0, 2.0]          # backoff*2**0, *2**1


def test_retry_exhausted_raises():
    c, fake, sleeps = _client_with_fake(fails=10, max_retries=3)
    with pytest.raises(RuntimeError):
        c.complete("s", "u")
    assert fake.calls == 4               # 1 + 3 retries
    assert sleeps == [1.0, 2.0, 4.0]


def test_success_first_try_no_sleep():
    c, fake, sleeps = _client_with_fake(fails=0)
    assert c.complete("s", "u") == '{"ok": 1}'
    assert fake.calls == 1
    assert sleeps == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_deepseek_retry.py -q`
Expected: FAIL(`DeepSeekClient.__init__` 不接受 `max_retries/backoff/sleep`)

- [ ] **Step 3: 改 `DeepSeekClient`**

替换 `youzi/llm/client.py` 第 30-51 行整段为:

```python
class DeepSeekClient:
    """DeepSeek(OpenAI 兼容)。lazy import openai;实盘/smoke 用,测试不触达。

    带 retry/backoff:网络/限流/5xx 等异常时指数退避重试;耗尽仍失败则向上抛
    (由 1b-3 编排或 LLMAgentPolicy 决定空仓兜底,本类不吞异常)。sleep 可注入便于测试。
    """

    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None,
                 base_url: str = "https://api.deepseek.com", temperature: float = 0.3,
                 max_retries: int = 3, backoff: float = 1.0,
                 sleep=None) -> None:
        import time
        from openai import OpenAI  # lazy
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY")
        self._client = OpenAI(api_key=key, base_url=base_url)
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep

    def complete(self, system: str, user: str) -> str:
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    temperature=self._temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:           # noqa: BLE001 — 网络/限流/5xx 皆重试
                last = e
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                else:
                    raise
        raise last  # pragma: no cover — 循环必 return 或 raise
```

> `import time` 移进 `__init__` 内(与 lazy openai 同处),保持模块顶层 import 不变(顶层仍只有 `os`/`typing`)。

- [ ] **Step 4: 跑测试确认通过 + 回归 client 测试**

Run: `python -m pytest tests/test_deepseek_retry.py tests/test_llm_client.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add youzi/llm/client.py tests/test_deepseek_retry.py
git commit -m "feat(llm): DeepSeekClient 指数退避重试(可注入 sleep,不触网可测)(①)"
```

---

## Bundle B — 审计字段 + Refiner 基件

### Task 5: `EditRecord.rationale` + meta-tool 透传

**Files:**
- Modify: `youzi/harness/edit_log.py:6-29`
- Modify: `youzi/harness/metatools.py`(9 个方法加 `rationale` 末参)
- Test: `tests/test_edit_log_rationale.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_edit_log_rationale.py
from youzi.harness.edit_log import EditLog, EditRecord
from youzi.harness.metatools import MetaTools
from tests.test_metatools import _harness   # 复用既有 fixture
from youzi.harness.memory_item import Lesson


def test_append_carries_rationale():
    log = EditLog()
    rec = log.append("write_skill", "skill", "x", "create", "甲", rationale="因为亏")
    assert rec.rationale == "因为亏"


def test_rationale_defaults_empty():
    rec = EditLog().append("promote_skill", "skill", "x", "promote")
    assert rec.rationale == ""


def test_old_dict_without_rationale_loads():
    old = [{"seq": 0, "tool": "promote_skill", "target_kind": "skill",
            "target_id": "x", "op": "promote", "summary": "", "payload": None}]
    log = EditLog.from_dict(old)
    assert log.records()[0].rationale == ""


def test_roundtrip_byte_identical():
    log = EditLog()
    log.append("write_skill", "skill", "x", "create", "甲", rationale="r1")
    d1 = log.to_dict()
    d2 = EditLog.from_dict(d1).to_dict()
    assert d1 == d2


def test_metatool_forwards_rationale():
    mt = MetaTools(_harness())
    rec = mt.update_memory("l1", lesson="改", rationale="教训过时")
    assert rec.rationale == "教训过时"
    assert mt.log.records()[-1].rationale == "教训过时"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_edit_log_rationale.py -q`
Expected: FAIL(`EditRecord` 无 `rationale` 字段 / `append` 不接受 `rationale`)

- [ ] **Step 3: 改 `edit_log.py`**

`youzi/harness/edit_log.py` —— 给 `EditRecord` 加字段(第 13 行 `payload` 之后):

```python
    payload: dict | None = None   # old→new 等结构化负载,为 0b-3 回滚预留
    rationale: str = ""           # Refiner 给出的编辑理由(默认空,向后兼容)
```

并给 `append` 加 `rationale` 形参(替换第 24-29 行):

```python
    def append(self, tool: str, target_kind: str, target_id: str,
               op: str, summary: str = "", payload: dict | None = None,
               rationale: str = "") -> EditRecord:
        rec = EditRecord(seq=len(self._records), tool=tool, target_kind=target_kind,
                         target_id=target_id, op=op, summary=summary, payload=payload,
                         rationale=rationale)
        self._records.append(rec)
        return rec
```

- [ ] **Step 4: 改 `metatools.py`——9 方法透传 `rationale`**

整体替换 `youzi/harness/metatools.py` 的 `MetaTools` 类方法区(第 24-88 行)为:

```python
    # ── K 技能 ──
    def write_skill(self, skill: Skill, rationale: str = "") -> EditRecord:
        self.h.skills.write(skill)
        return self.log.append("write_skill", "skill", skill.skill_id, "create",
                               skill.name_cn, rationale=rationale)

    def patch_skill(self, skill_id: str, rationale: str = "", **fields) -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = {k: _jsonable(getattr(s, k)) for k in fields if s is not None and k in type(s).model_fields}
        self.h.skills.patch(skill_id, **fields)
        after = {k: _jsonable(v) for k, v in fields.items()}
        return self.log.append("patch_skill", "skill", skill_id, "update",
                               ",".join(f"{k}={v}" for k, v in fields.items()),
                               payload={"before": before, "after": after}, rationale=rationale)

    def retire_skill(self, skill_id: str, permanent: bool = False, rationale: str = "") -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.retire(skill_id, permanent=permanent)
        after = "retired" if permanent else "dormant"
        return self.log.append("retire_skill", "skill", skill_id, "retire", after,
                               payload={"before": before, "after": after}, rationale=rationale)

    def revive_skill(self, skill_id: str, rationale: str = "") -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.revive(skill_id)
        return self.log.append("revive_skill", "skill", skill_id, "revive", "",
                               payload={"before": before, "after": "incubating"}, rationale=rationale)

    def promote_skill(self, skill_id: str, rationale: str = "") -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.promote(skill_id)
        return self.log.append("promote_skill", "skill", skill_id, "promote", "",
                               payload={"before": before, "after": "active"}, rationale=rationale)

    # ── M 记忆 ──
    def process_memory(self, lesson: Lesson, rationale: str = "") -> EditRecord:
        self.h.memory.add(lesson)
        return self.log.append("process_memory", "memory", lesson.lesson_id, "create",
                               lesson.lesson[:24], rationale=rationale)

    def update_memory(self, lesson_id: str, rationale: str = "", **fields) -> EditRecord:
        lesson = self.h.memory.get(lesson_id)
        before = {k: _jsonable(getattr(lesson, k)) for k in fields
                  if lesson is not None and k in type(lesson).model_fields}
        self.h.memory.update(lesson_id, **fields)
        after = {k: _jsonable(v) for k, v in fields.items()}
        return self.log.append("update_memory", "memory", lesson_id, "update",
                               ",".join(fields), payload={"before": before, "after": after},
                               rationale=rationale)

    def demote_memory(self, lesson_id: str, factor: float, rationale: str = "") -> EditRecord:
        lesson = self.h.memory.get(lesson_id)
        before_td = lesson.importance.time_decay if lesson is not None else None
        self.h.memory.demote(lesson_id, factor)
        return self.log.append("demote_memory", "memory", lesson_id, "demote", str(factor),
                               payload={"before_time_decay": before_td, "factor": factor},
                               rationale=rationale)

    # ── p doctrine ──
    def rewrite_doctrine(self, section: str, new_guidance: str, rationale: str = "") -> EditRecord:
        old = self.h.doctrine.get(section)
        old_guidance = old.guidance if old is not None else None
        self.h.doctrine.rewrite(section, new_guidance)   # immutable -> 抛错, 不记日志
        return self.log.append("rewrite_doctrine", "doctrine", section, "rewrite",
                               payload={"old": old_guidance, "new": new_guidance},
                               rationale=rationale)
```

- [ ] **Step 5: 跑测试确认通过 + 回归(metatools/serialize/snapshot)**

Run: `python -m pytest tests/test_edit_log_rationale.py tests/test_edit_log.py tests/test_metatools.py tests/test_metatools_integration.py tests/test_harness_serialize.py tests/test_snapshot.py tests/test_manager.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add youzi/harness/edit_log.py youzi/harness/metatools.py tests/test_edit_log_rationale.py
git commit -m "feat(harness): EditRecord 加 rationale,9 个 meta-tool 透传进审计账本"
```

---

### Task 6: `refine/ops.py`——op schema + pass 白名单 + 解析

**Files:**
- Create: `youzi/refine/ops.py`
- Test: `tests/test_refine_ops.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_refine_ops.py
from youzi.refine.ops import RefineOp, PASS_TOOLS, parse_ops


def test_pass_tools_whitelist():
    assert PASS_TOOLS["p"] == frozenset({"rewrite_doctrine"})
    assert PASS_TOOLS["G"] == frozenset()
    assert "write_skill" in PASS_TOOLS["K"] and "promote_skill" in PASS_TOOLS["K"]
    assert PASS_TOOLS["M"] == frozenset({"process_memory", "update_memory", "demote_memory"})


def test_parse_ops_happy():
    raw = '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "a"}, "rationale": "胜率高"}]}'
    ops = parse_ops(raw)
    assert len(ops) == 1
    assert ops[0].tool == "promote_skill"
    assert ops[0].args == {"skill_id": "a"}
    assert ops[0].rationale == "胜率高"


def test_parse_ops_defaults_and_skips_malformed():
    raw = ('{"ops": ['
           '{"tool": "promote_skill"},'              # 无 args/rationale → 默认 {} / ""
           '{"args": {"x": 1}},'                     # 无 tool → 跳过
           '"不是对象",'                              # 非 dict → 跳过
           '{"tool": "patch_skill", "args": "坏"}'   # args 非 dict → 跳过
           ']}')
    ops = parse_ops(raw)
    assert len(ops) == 1
    assert ops[0].tool == "promote_skill" and ops[0].args == {} and ops[0].rationale == ""


def test_parse_ops_with_prose_prefix():
    raw = '复盘结论:\n{"ops": [{"tool": "demote_memory", "args": {"lesson_id": "l1", "factor": 0.5}, "rationale": "过时"}]}'
    ops = parse_ops(raw)
    assert len(ops) == 1 and ops[0].tool == "demote_memory"


def test_parse_ops_garbage_returns_empty():
    assert parse_ops("毫无 JSON") == []
    assert parse_ops('{"no_ops_key": 1}') == []
    assert parse_ops('{"ops": "不是列表"}') == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_refine_ops.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.refine.ops`)

- [ ] **Step 3: 实现**

```python
# youzi/refine/ops.py
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from youzi.llm.extract import extract_json_object

PassKind = Literal["p", "G", "K", "M"]

# pass → 允许的 meta-tool 白名单(ΔG 为空集:G 子 Agent 未建,占位 no-op)
PASS_TOOLS: dict[PassKind, frozenset[str]] = {
    "p": frozenset({"rewrite_doctrine"}),
    "G": frozenset(),
    "K": frozenset({"write_skill", "patch_skill", "retire_skill",
                    "revive_skill", "promote_skill"}),
    "M": frozenset({"process_memory", "update_memory", "demote_memory"}),
}


class RefineOp(BaseModel):
    """一条待应用编辑(frozen)。"""
    model_config = ConfigDict(frozen=True)
    tool: str                                  # meta-tool 名(必填)
    args: dict = Field(default_factory=dict)   # 该 tool 的参数
    rationale: str = ""                        # apply 阶段强制非空


def parse_ops(raw: str) -> list[RefineOp]:
    """LLM 文本 → list[RefineOp]。

    extract_json_object → json.loads → 取 "ops":[...];非对象/无 ops/条目缺 tool 或 args 非 dict
    → 跳过该条(不崩);整体失败 → []。rationale 缺失不在此跳过(默认 ""),留到 apply 阶段
    作为 rejected 上报,使所有 rationale 问题统一可见。
    """
    s = extract_json_object(raw)
    if s is None:
        return []
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw_ops = data.get("ops")
    if not isinstance(raw_ops, list):
        return []
    out: list[RefineOp] = []
    for o in raw_ops:
        if not isinstance(o, dict):
            continue
        tool = o.get("tool")
        if not isinstance(tool, str) or not tool:
            continue
        args = o.get("args")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            continue
        rationale = o.get("rationale")
        rationale = rationale if isinstance(rationale, str) else ""
        out.append(RefineOp(tool=tool, args=args, rationale=rationale))
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_refine_ops.py -q`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/refine/ops.py tests/test_refine_ops.py
git commit -m "feat(refine): RefineOp/PASS_TOOLS/parse_ops——编辑 op schema 与 pass 白名单"
```

---

### Task 7: `refine/refiner.py`——报告模型 + 拒绝管线 `_apply_op`

**Files:**
- Create: `youzi/refine/refiner.py`
- Test: `tests/test_refiner.py`(本任务建 apply 级用例;Task 9 加 refine 循环用例)

- [ ] **Step 1: 写失败测试(apply 级,不经 LLM)**

```python
# tests/test_refiner.py
import pytest
from youzi.refine.refiner import Refiner, RefinerConfig, RefineReport, AppliedEdit, RejectedEdit
from youzi.refine.ops import RefineOp
from youzi.harness.metatools import MetaTools
from youzi.llm.client import MockLLMClient
from tests.test_metatools import _harness


def _refiner(h=None, cfg=None):
    h = h or _harness()
    meta = MetaTools(h)
    r = Refiner(h, MockLLMClient('{"ops": []}'), meta, cfg or RefinerConfig())
    return r, h, meta


def test_apply_op_accept_promote():
    # _harness 的技能 a 是 active;先 retire→revive 使其 incubating,再 promote
    r, h, meta = _refiner()
    meta.retire_skill("a"); meta.revive_skill("a")     # a -> incubating
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"},
                                   rationale="胜率回升"), "K", PASS_K())
    assert ok and isinstance(res, AppliedEdit)
    assert res.tool == "promote_skill" and res.target_id == "a"
    assert h.skills.get("a").status == "active"


def test_apply_op_reject_immutable():
    r, h, meta = _refiner()
    ok, res = r._apply_op(RefineOp(tool="rewrite_doctrine",
                                   args={"section": "纪律:退潮不接力", "new_guidance": "篡改"},
                                   rationale="想放松"), "p", PASS_P())
    assert not ok and isinstance(res, RejectedEdit)
    assert "Immutable" in res.reason
    assert h.doctrine.get("纪律:退潮不接力").guidance == "退潮禁接力"   # 未变
    assert len(meta.log) == 0                                           # 未记日志


def test_apply_op_reject_invalid_transition():
    r, h, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="revive_skill", args={"skill_id": "a"},
                                   rationale="复活"), "K", PASS_K())   # a 是 active,非 dormant
    assert not ok and "InvalidTransition" in res.reason


def test_apply_op_reject_wrong_pass_tool():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="rewrite_doctrine", args={"section": "x", "new_guidance": "y"},
                                   rationale="r"), "K", PASS_K())      # rewrite 不在 K-pass
    assert not ok and "本 K-pass" in res.reason


def test_apply_op_reject_missing_rationale():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="  "),
                          "K", PASS_K())
    assert not ok and "rationale" in res.reason


def test_apply_op_reject_hallucinated_target():
    r, _, _ = _refiner()
    ok, res = r._apply_op(RefineOp(tool="patch_skill", args={"skill_id": "不存在", "notes": "x"},
                                   rationale="r"), "K", PASS_K())
    assert not ok and "KeyError" in res.reason


def test_apply_op_reject_duplicate_write():
    r, _, _ = _refiner()
    skill = {"skill_id": "a", "name_cn": "重复", "type": "pattern",
             "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
             "exit_stop": "x", "status": "incubating"}
    ok, res = r._apply_op(RefineOp(tool="write_skill", args=skill, rationale="r"), "K", PASS_K())
    assert not ok and "重复" in res.reason


def test_apply_op_reject_malformed_skill_args():
    r, _, _ = _refiner()
    bad = {"skill_id": "z", "name_cn": "缺字段"}        # 缺 type/trigger/... → ValidationError
    ok, res = r._apply_op(RefineOp(tool="write_skill", args=bad, rationale="r"), "K", PASS_K())
    assert not ok and ("ValidationError" in res.reason or "validation" in res.reason.lower())


# 小工具:从 ops 取白名单,避免在测试里硬写 frozenset
def PASS_K():
    from youzi.refine.ops import PASS_TOOLS
    return PASS_TOOLS["K"]


def PASS_P():
    from youzi.refine.ops import PASS_TOOLS
    return PASS_TOOLS["p"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_refiner.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.refine.refiner`)

- [ ] **Step 3: 实现 `refiner.py`(模型 + `_apply_op`/`_dispatch`/`_target_id`;`refine` 留 Task 9)**

```python
# youzi/refine/refiner.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from youzi.eval.trajectory import Trajectory
from youzi.harness.errors import ImmutableDoctrineError, InvalidTransitionError
from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.metatools import MetaTools
from youzi.harness.skill import Skill
from youzi.llm.client import LLMClient
from youzi.refine.credit import CreditReport
from youzi.refine.ops import PASS_TOOLS, PassKind, RefineOp, parse_ops
from youzi.refine.signatures import FailureSignature
# 注:refiner_prompt 的 import 在 Task 9 实现 refine() 时再补——彼时该模块(Task 8)才建好,
#     此处先不引,避免 Bundle B 内 refiner.py 在 refiner_prompt 尚未存在时 import 失败。

_PASS_ORDER: tuple[PassKind, ...] = ("p", "G", "K", "M")


class RefinerConfig(BaseModel):
    max_edits_per_pass: int = 5
    max_edits_per_refine: int = 12
    window: int = 10


class AppliedEdit(BaseModel):
    model_config = ConfigDict(frozen=True)
    pass_kind: PassKind
    tool: str
    target_id: str
    seq: int
    rationale: str


class RejectedEdit(BaseModel):
    model_config = ConfigDict(frozen=True)
    pass_kind: PassKind
    tool: str
    target_id: str | None
    reason: str


class RefineReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    applied: list[AppliedEdit] = Field(default_factory=list)
    rejected: list[RejectedEdit] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def __bool__(self) -> bool:
        return True


def _target_id(tool: str, args: dict) -> str | None:
    if tool in ("write_skill", "patch_skill", "retire_skill", "revive_skill", "promote_skill"):
        return args.get("skill_id")
    if tool in ("process_memory", "update_memory", "demote_memory"):
        return args.get("lesson_id")
    if tool == "rewrite_doctrine":
        return args.get("section")
    return None


class Refiner:
    """LLM 复盘官:读证据 → 经 MetaTools 结构性编辑 H → RefineReport。

    就地编辑传入的 HarnessState(reset-free,agent 立即可见);不 checkpoint/不回滚(1b-3)。
    """

    def __init__(self, harness: HarnessState, llm: LLMClient,
                 meta: MetaTools, config: RefinerConfig | None = None) -> None:
        self._h = harness
        self._llm = llm
        self._meta = meta
        self._cfg = config or RefinerConfig()

    def _apply_op(self, op: RefineOp, pk: PassKind,
                  allowed: frozenset[str]) -> tuple[bool, object]:
        tid = _target_id(op.tool, op.args)
        if op.tool not in allowed:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason=f"tool 不属于本 {pk}-pass 或未知")
        if not op.rationale.strip():
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason="缺 rationale")
        try:
            rec = self._dispatch(op)
        except (ImmutableDoctrineError, InvalidTransitionError, KeyError,
                ValueError, ValidationError, TypeError) as e:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason=f"{type(e).__name__}: {e}")
        return True, AppliedEdit(pass_kind=pk, tool=op.tool,
                                 target_id=str(rec.target_id), seq=rec.seq,
                                 rationale=op.rationale)

    def _dispatch(self, op: RefineOp):
        a = dict(op.args)
        r = op.rationale
        m = self._meta
        if op.tool == "write_skill":
            return m.write_skill(Skill.from_seed(a), rationale=r)
        if op.tool == "patch_skill":
            sid = a.pop("skill_id")
            return m.patch_skill(sid, rationale=r, **a)
        if op.tool == "retire_skill":
            sid = a.pop("skill_id")
            perm = bool(a.pop("permanent", False))
            return m.retire_skill(sid, permanent=perm, rationale=r)
        if op.tool == "revive_skill":
            return m.revive_skill(a["skill_id"], rationale=r)
        if op.tool == "promote_skill":
            return m.promote_skill(a["skill_id"], rationale=r)
        if op.tool == "process_memory":
            return m.process_memory(Lesson.from_seed(a), rationale=r)
        if op.tool == "update_memory":
            lid = a.pop("lesson_id")
            return m.update_memory(lid, rationale=r, **a)
        if op.tool == "demote_memory":
            return m.demote_memory(a["lesson_id"], a["factor"], rationale=r)
        if op.tool == "rewrite_doctrine":
            return m.rewrite_doctrine(a["section"], a["new_guidance"], rationale=r)
        raise ValueError(f"未知 tool: {op.tool}")

    def refine(self, traj: Trajectory, credit: CreditReport,
               signatures: list[FailureSignature]) -> RefineReport:
        raise NotImplementedError  # Task 9 实现 4-pass 编排
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_refiner.py -q`
Expected: PASS(apply 级用例全绿)

- [ ] **Step 5: 提交**

```bash
git add youzi/refine/refiner.py tests/test_refiner.py
git commit -m "feat(refine): Refiner 报告模型 + 拒绝管线 _apply_op(immutable/转移/越权/幻觉/malformed 全拒)"
```

---

## Bundle C — 4-pass 编排 + 提示 + 集成

### Task 8: `refine/refiner_prompt.py`——各 pass 系统提示 + 证据 user 提示

**Files:**
- Create: `youzi/refine/refiner_prompt.py`
- Test: `tests/test_refiner_prompt.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_refiner_prompt.py
from datetime import date, datetime
from youzi.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt
from youzi.refine.credit import CreditReport, SkillCredit
from youzi.refine.signatures import FailureSignature
from youzi.eval.trajectory import Trajectory, TrajectoryStep
from youzi.eval.decision import DecisionPackage, Candidate
from youzi.eval.metrics import ScoredCandidate
from youzi.schemas.market import MarketState
from tests.test_metatools import _harness


def test_system_prompt_k_pass_lists_skill_tools_and_rules():
    p = build_refiner_system_prompt(_harness(), "K")
    assert "write_skill" in p and "promote_skill" in p
    assert "rationale" in p
    assert "immutable" in p or "红线" in p
    assert "ops" in p                                   # 输出契约
    assert "rewrite_doctrine" not in p                  # K-pass 不暴露 doctrine 工具


def test_system_prompt_p_pass_lists_mutable_doctrine():
    p = build_refiner_system_prompt(_harness(), "p")
    assert "rewrite_doctrine" in p
    assert "主升作战" in p                              # mutable 段渲染出来


def test_system_prompt_m_pass_lists_memory_tools():
    p = build_refiner_system_prompt(_harness(), "M")
    assert "process_memory" in p and "demote_memory" in p


def test_user_prompt_renders_evidence():
    mkt = MarketState(date=date(2024, 6, 27), max_board_height=5, limit_up_count=10,
                      blowup_count=3, blowup_rate=0.3, limit_down_count=1, echelon=[],
                      money_effect_raw=1.0, sentiment_raw=0.0, sentiment_norm=0.5,
                      as_of=datetime(2024, 6, 27, 15, 0))
    step = TrajectoryStep(
        date=date(2024, 6, 27), market=mkt,
        decision=DecisionPackage(date=date(2024, 6, 27),
                                 candidates=[Candidate(code="000001", name="平安",
                                                       pattern="接力", reason="r", confidence=0.6)]),
        scored=True,
        outcomes={"000001": ScoredCandidate(decision_date=date(2024, 6, 27), code="000001",
                                            pattern="接力", outcome="nuked", score=-1.0)})
    traj = Trajectory(steps=[step], horizon=1)
    credit = CreditReport(per_skill={"a": SkillCredit(skill_id="a", n=3, wins=0, losses=3,
                                                      nukes=2, hit_rate=0.0, nuke_rate=0.67,
                                                      expectancy=-0.67)}, n_scored=3)
    sigs = [FailureSignature(date=date(2024, 6, 27), code="000001", pattern="接力",
                             skill_id="a", kind="chased_into_nuke", score=-1.0,
                             evidence="boards=5/max=5 → 追最高板被闷")]
    u = build_refiner_user_prompt(traj, credit, sigs, window=10)
    assert "000001" in u and "nuked" in u
    assert "a" in u and "nuke" in u.lower()
    assert "chased_into_nuke" in u and "追最高板被闷" in u
```

> 字段签名已对照 `schemas/market.py`/`eval/metrics.py`/`eval/decision.py` 核实(`MarketState` 必填含 `blowup_count`/`as_of`,`sentiment_norm` 为 `float|None`;`ScoredCandidate` 为 `decision_date/code/pattern/outcome/score`)。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_refiner_prompt.py -q`
Expected: FAIL(`ModuleNotFoundError: youzi.refine.refiner_prompt`)

- [ ] **Step 3: 实现**

```python
# youzi/refine/refiner_prompt.py
from __future__ import annotations

from youzi.eval.trajectory import Trajectory
from youzi.harness.harness import HarnessState
from youzi.refine.credit import CreditReport
from youzi.refine.ops import PassKind
from youzi.refine.signatures import FailureSignature

_PASS_DESC: dict[str, str] = {
    "p": "改写 mutable 作战 doctrine(纪律红线 immutable 改不动,试图改写会被拒绝)",
    "K": "增删改技能库 K(write/patch/retire/revive/promote)",
    "M": "增删改复盘记忆 M(process/update/demote)",
}

_PASS_TOOLS_DOC: dict[str, str] = {
    "p": '- rewrite_doctrine: {"section": "<已存在的 mutable 段名>", "new_guidance": "<新指导>"}',
    "K": ('- write_skill: {"skill_id","name_cn","type":"pattern|feature|failure_detector",'
          '"applicable_regime":[...],"trigger","entry","exit_stop","taboo":[...],"status":"incubating"}\n'
          '- patch_skill: {"skill_id","<字段>":<值>,...}(不可改 status/phases/ecologies)\n'
          '- retire_skill: {"skill_id","permanent":false}\n'
          '- revive_skill: {"skill_id"}(仅 dormant→incubating)\n'
          '- promote_skill: {"skill_id"}(仅 incubating→active)'),
    "M": ('- process_memory: {"lesson_id","regime","outcome":"win|loss|principle","lesson",'
          '"pattern","failure_signature","named_analog"}\n'
          '- update_memory: {"lesson_id","<字段>":<值>,...}\n'
          '- demote_memory: {"lesson_id","factor":<0~1 之间>}'),
}


def build_refiner_system_prompt(h: HarnessState, pass_kind: PassKind) -> str:
    """某 pass 的复盘官系统提示:本 pass 改哪个容器 + 可用 meta-tool schema + 规则 + 当前 H 切片。"""
    out = [
        "你是 A股游资/超短交易系统的**复盘官(Refiner)**。读最近复盘窗口的决策与已实现结果、"
        "技能信用、失败签名,据此对当前打法 H 做**结构性编辑**,让系统下次更强。",
        f"\n## 本轮只允许:{_PASS_DESC[pass_kind]}",
        "## 可用编辑(严格按参数 schema):",
        _PASS_TOOLS_DOC[pass_kind],
        "\n## 规则:",
        "- 纪律红线(immutable)绝对改不动,试图改写会被拒绝。",
        "- 每条编辑必须带非空 rationale(理由),否则被拒绝。",
        "- 谨慎、少而精;只在证据充分时编辑,无可改则给空列表。",
    ]
    if pass_kind == "p":
        out.append("\n## 当前 mutable doctrine(可改写):")
        for e in h.doctrine.mutable_entries():
            out.append(f"- {e.section}: {e.guidance}")
        out.append("## 纪律红线(immutable,改不动,仅供参考):")
        for e in h.doctrine.immutable_core():
            out.append(f"- {e.section}: {e.guidance}")
    elif pass_kind == "K":
        out.append("\n## 当前技能(含战绩):")
        for s in h.skills.all():
            st = s.stats
            perf = f" [n={st.n} nukes={st.nukes}]" if st.n > 0 else ""
            out.append(f"- {s.skill_id}({s.name_cn})[{s.type}/{s.status}]{perf}")
    elif pass_kind == "M":
        out.append("\n## 当前记忆:")
        for l in h.memory.all():
            out.append(f"- {l.lesson_id}[{l.outcome}]: {l.lesson}")
    out.append('\n## 输出严格 JSON(无 markdown 围栏):'
               '{"ops": [{"tool": "...", "args": {...}, "rationale": "..."}]}')
    return "\n".join(out)


def build_refiner_user_prompt(traj: Trajectory, credit: CreditReport,
                              signatures: list[FailureSignature], window: int = 10) -> str:
    """渲染证据:最近 window 步决策→结果 + 技能信用 + 失败签名。"""
    out = ["## 最近复盘窗口(决策 → 已实现结果):"]
    for st in traj.scored_steps()[-window:]:
        picks = ", ".join(f"{c.code}({c.pattern})" for c in st.decision.candidates) or "空仓"
        outs = ", ".join(f"{code}:{sc.outcome}" for code, sc in st.outcomes.items()) or "—"
        out.append(f"- {st.date} 选[{picks}] → {outs}")

    out.append("\n## 技能信用(本轮谁在亏):")
    if credit.per_skill:
        for sid, c in credit.per_skill.items():
            out.append(f"- {sid}: n={c.n} 胜率={c.hit_rate:.2f} "
                       f"nuke率={c.nuke_rate:.2f} exp={c.expectancy:+.2f}")
    else:
        out.append("(无)")
    if credit.unattributed:
        u = credit.unattributed
        out.append(f"- [未归因] n={u.n} 胜率={u.hit_rate:.2f} exp={u.expectancy:+.2f}")

    out.append("\n## 失败签名(入场坑):")
    if signatures:
        for s in signatures:
            out.append(f"- {s.date} {s.code} [{s.kind}] pattern={s.pattern} "
                       f"skill={s.skill_id or '?'}: {s.evidence}")
    else:
        out.append("(无)")
    return "\n".join(out)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_refiner_prompt.py -q`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add youzi/refine/refiner_prompt.py tests/test_refiner_prompt.py
git commit -m "feat(refine): 各 pass 复盘官系统提示 + 证据 user 提示"
```

---

### Task 9: `Refiner.refine`——4-pass CRUD 编排(ΔG 占位)+ 端到端集成

**Files:**
- Modify: `youzi/refine/refiner.py`(实现 `refine`)
- Test: `tests/test_refiner.py`(追加 refine 循环用例)

- [ ] **Step 1: 追加失败测试(端到端,MockLLM 脚本化每 pass)**

追加到 `tests/test_refiner.py`:

```python
from youzi.refine.refiner_prompt import build_refiner_system_prompt  # noqa
from youzi.refine.credit import CreditReport
from youzi.eval.trajectory import Trajectory


def _empty_evidence():
    return Trajectory(steps=[], horizon=1), CreditReport(n_scored=0), []


def _run_refine(scripts, h=None, cfg=None):
    """scripts:按 p/K/M 三次 live 调用顺序给出的 LLM 响应列表。"""
    h = h or _harness()
    meta = MetaTools(h)
    llm = MockLLMClient(scripts)
    r = Refiner(h, llm, meta, cfg or RefinerConfig())
    traj, credit, sigs = _empty_evidence()
    return r.refine(traj, credit, sigs), h, meta, llm


def test_refine_g_pass_is_noop_three_live_calls():
    # 三个 pass 都给空 ops;ΔG 不发调用 → MockLLM 恰好被调 3 次
    rep, h, meta, llm = _run_refine(['{"ops": []}', '{"ops": []}', '{"ops": []}'])
    assert len(llm.calls) == 3
    assert any("G-pass reserved" in n for n in rep.notes)
    assert rep.applied == [] and rep.rejected == []


def test_refine_happy_path_applies_and_logs():
    # p: 改 mutable doctrine;K: 新建 failure_detector 技能;M: 写一条 loss 教训
    p_ops = '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "主升作战", "new_guidance": "只打最高板"}, "rationale": "杂毛连亏"}]}'
    k_ops = ('{"ops": [{"tool": "write_skill", "args": {"skill_id": "fd1", "name_cn": "追高板防闷",'
             ' "type": "failure_detector", "applicable_regime": ["主升"], "trigger": "最高板尾盘弱",'
             ' "entry": "不追", "exit_stop": "次日低开走", "status": "incubating"}, "rationale": "chased_into_nuke 反复"}]}')
    m_ops = '{"ops": [{"tool": "process_memory", "args": {"lesson_id": "ls1", "regime": "主升", "outcome": "loss", "lesson": "追最高板被闷"}, "rationale": "记牢"}]}'
    rep, h, meta, llm = _run_refine([p_ops, k_ops, m_ops])
    assert {e.tool for e in rep.applied} == {"rewrite_doctrine", "write_skill", "process_memory"}
    assert rep.rejected == []
    assert h.doctrine.get("主升作战").guidance == "只打最高板"
    assert h.skills.get("fd1") is not None and h.skills.get("fd1").type == "failure_detector"
    assert h.memory.get("ls1") is not None
    # 全进 EditLog,且带 rationale
    assert len(meta.log) == 3
    assert all(rec.rationale for rec in meta.log.records())


def test_refine_rejects_immutable_in_p_pass():
    p_ops = '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "纪律:退潮不接力", "new_guidance": "放松"}, "rationale": "想改"}]}'
    rep, h, meta, llm = _run_refine([p_ops, '{"ops": []}', '{"ops": []}'])
    assert rep.applied == []
    assert len(rep.rejected) == 1 and "Immutable" in rep.rejected[0].reason
    assert h.doctrine.get("纪律:退潮不接力").guidance == "退潮禁接力"
    assert len(meta.log) == 0


def test_refine_per_pass_cap_enforced():
    # K-pass 给 3 个 promote,但 cap=1 → 1 applied(被 a 占用?需先 incubating)+ 余者超限拒绝
    h = _harness()
    # 准备 3 个 incubating 技能 b/c/d
    from youzi.harness.skill import Skill
    for sid in ("b", "c", "d"):
        h.skills.write(Skill.from_seed({"skill_id": sid, "name_cn": sid, "type": "pattern",
                                        "applicable_regime": ["主升"], "trigger": "t",
                                        "entry": "e", "exit_stop": "x", "status": "incubating"}))
    k_ops = ('{"ops": ['
             '{"tool": "promote_skill", "args": {"skill_id": "b"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "c"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "d"}, "rationale": "r"}]}')
    cfg = RefinerConfig(max_edits_per_pass=1, max_edits_per_refine=12)
    rep, h2, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'], h=h, cfg=cfg)
    assert len(rep.applied) == 1
    assert len(rep.rejected) == 2 and all("per-pass" in r.reason for r in rep.rejected)


def test_refine_per_refine_cap_enforced():
    h = _harness()
    from youzi.harness.skill import Skill
    for sid in ("b", "c", "d"):
        h.skills.write(Skill.from_seed({"skill_id": sid, "name_cn": sid, "type": "pattern",
                                        "applicable_regime": ["主升"], "trigger": "t",
                                        "entry": "e", "exit_stop": "x", "status": "incubating"}))
    k_ops = ('{"ops": ['
             '{"tool": "promote_skill", "args": {"skill_id": "b"}, "rationale": "r"},'
             '{"tool": "promote_skill", "args": {"skill_id": "c"}, "rationale": "r"}]}')
    cfg = RefinerConfig(max_edits_per_pass=5, max_edits_per_refine=1)
    rep, h2, meta, llm = _run_refine(['{"ops": []}', k_ops, '{"ops": []}'], h=h, cfg=cfg)
    assert len(rep.applied) == 1
    assert len(rep.rejected) == 1 and "per-refine" in rep.rejected[0].reason
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_refiner.py -q`
Expected: FAIL(`refine` 抛 `NotImplementedError`)

- [ ] **Step 3: 实现 `refine`**

先在 `youzi/refine/refiner.py` 顶部 import 区补一行(Task 7 刻意未引,因彼时 `refiner_prompt` 尚未建):

```python
from youzi.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt
```

再替换 `refine` 方法的 `raise NotImplementedError` 为:

```python
    def refine(self, traj: Trajectory, credit: CreditReport,
               signatures: list[FailureSignature]) -> RefineReport:
        applied: list[AppliedEdit] = []
        rejected: list[RejectedEdit] = []
        notes: list[str] = []
        for pk in _PASS_ORDER:
            allowed = PASS_TOOLS[pk]
            if not allowed:                                   # ΔG 占位 no-op(不发 LLM 调用)
                notes.append(f"{pk}-pass reserved(G 子 Agent 未建,跳过)")
                continue
            system = build_refiner_system_prompt(self._h, pk)
            user = build_refiner_user_prompt(traj, credit, signatures, self._cfg.window)
            ops = parse_ops(self._llm.complete(system, user))
            pass_count = 0
            for op in ops:
                if len(applied) >= self._cfg.max_edits_per_refine:
                    rejected.append(RejectedEdit(pass_kind=pk, tool=op.tool,
                        target_id=_target_id(op.tool, op.args), reason="超出 per-refine 编辑上限"))
                    continue
                if pass_count >= self._cfg.max_edits_per_pass:
                    rejected.append(RejectedEdit(pass_kind=pk, tool=op.tool,
                        target_id=_target_id(op.tool, op.args), reason="超出 per-pass 编辑上限"))
                    continue
                ok, res = self._apply_op(op, pk, allowed)
                if ok:
                    applied.append(res)
                    pass_count += 1
                else:
                    rejected.append(res)
        return RefineReport(applied=applied, rejected=rejected, notes=notes)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_refiner.py -q`
Expected: PASS(apply 级 + refine 循环用例全绿)

- [ ] **Step 5: 全量回归**

Run: `python -m pytest -q`
Expected: PASS(原 163 + 本阶段新增,全绿,离线不触网)

- [ ] **Step 6: 提交**

```bash
git add youzi/refine/refiner.py tests/test_refiner.py
git commit -m "feat(refine): Refiner.refine 4-pass CRUD 编排(ΔG 占位 no-op)+ caps + 端到端集成"
```

---

## 收尾(Task 9 之后,subagent-driven 终审前)

- [ ] 更新 `PROJECT_STATE.md`:Phase-1b-2 完成 + 残留债务(见下)。
- [ ] 更新 `后续开发文档.md`:状态表 1b-2 → ✅;§4 路线图;§5 债务。
- [ ] 更新 memory `youzi-self-evolving-project.md`:下一步 → 1b-3 内环编排。

**本阶段产生/保留的债务(登记,非阻塞):**
- ΔG live pass 待 G 子 Agent 群建成。
- 涌现技能审计闸(防 reward-hack 作弊技能)未做——债务。
- 提示注入全量(未按 regime 选择性,卡在缺 `G_cycle` 分类器)。
- checkpoint-before / 能力地板熔断 / 何时触发 refine = 1b-3。
- `extract_json_object` 已知限制:prose 中先出现配平 `{...}` 会被取(json_object 模式下风险低)。
- caps 默认值(per-pass 5 / per-refine 12)为初值,实盘多日跑后按编辑质量调。

---

## Self-Review(写计划后自查,已执行)

**1. Spec coverage(逐条对 spec §3 文件表):**
- `llm/extract.py`(③)→ Task 1 ✅;`agent/parse.py` 重构 → Task 2 ✅;`agent/prompt.py` 注入(②)→ Task 3 ✅;`llm/client.py` retry(①)→ Task 4 ✅;`edit_log.py`+`metatools.py` rationale → Task 5 ✅;`refine/ops.py` → Task 6 ✅;`refine/refiner.py` 模型+拒绝管线 → Task 7 ✅;`refine/refiner_prompt.py` → Task 8 ✅;`refine/refiner.py` 4-pass → Task 9 ✅。
- spec §7 测试清单 7 个文件全部有对应 Task。spec §8 DoD:happy path/immutable/转移/越权/缺 rationale/caps/幻觉/malformed/ΔG note + 3 次调用 → Task 7+9 覆盖;相邻三项 → Task 1-4;防火墙(Refiner 无 source 句柄、不取数)→ 结构上由"只收 frozen 证据、只调 MetaTools"保证,终审复核。
- 全量回归 163 + 新增 → Task 9 Step 5。

**2. Placeholder scan:** 无 TBD/TODO/"添加适当错误处理";每个代码步给了完整代码与确切命令/预期。Task 2/8 含"若字段签名不符照既有测试对齐"的指引(非占位,是对既有真实接口的防漂移备注)。

**3. Type consistency:** `RefineOp(tool/args/rationale)`、`PASS_TOOLS[PassKind]`、`_apply_op(op,pk,allowed)->(bool,AppliedEdit|RejectedEdit)`、`_dispatch`/`_target_id`、`MetaTools.*(rationale=...)`、`EditRecord.rationale`、`RefineReport(applied/rejected/notes)` 跨 Task 6/7/8/9 一致;`refine(traj,credit,signatures)` 与 spec §4.7 一致。
