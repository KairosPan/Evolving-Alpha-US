# Phase-1a LLM Agent(act 半环:DeepSeek-backed DecisionPolicy)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Continual Harness 的 **act 半环**——一个 **DeepSeek 驱动的 `DecisionPolicy`**:读当日 `MarketState` + 候选 `CandidateUniverse` + Harness `H=(p,K,M)`(doctrine/技能/记忆),构造提示 → 调 LLM → 解析成 `DecisionPackage`。它**即刻可被 Phase-0d 的 `WalkForwardEval` 用同一把 oracle 尺量**,与 Hmin 基线对照;**全程离线可测**(MockLLM,不触网)。这是"harness 包住基础模型"的落地,也是 Phase-1b Refiner 自进化所需的轨迹来源。

**Architecture:** 新 `youzi/llm/`(LLM 客户端抽象:Protocol + MockLLMClient + DeepSeekClient,lazy openai)+ `youzi/agent/`(`prompt.py` 把 H 渲染进系统提示、把盘面/候选渲染进用户提示;`parse.py` 把 LLM JSON 鲁棒解析成 DecisionPackage、**幻觉 code 过滤**、malformed→空仓兜底;`agent.py` `LLMAgentPolicy` 实现 `DecisionPolicy`)。LLM 是唯一触网处,测试一律用 MockLLM;DeepSeekClient 仅由手动 smoke 触发(同 akshare)。

**Tech Stack:** Python 3.11+ · pydantic v2 · pytest · **openai SDK**(DeepSeek 走 OpenAI 兼容,lazy import;新增依赖)。

**范围边界(1a):** **只做 act**(选股决策),不做 Refiner/轨迹/自进化(Phase-1b)、不做协同学习/微调(Phase-1c)。H 在一次 run 内静态(无 Refiner 编辑);`decide` 每次按当前 H 重建系统提示(前向兼容 1b 的 Refiner 改 H)。v1 把整本 playbook(active 技能+全 doctrine+记忆)compact 注入提示,LLM 自行判读 regime + 选股;**按 regime 选择性注入是 1b 优化**。

**关键设计点:**
- **harness 包住模型**:系统提示 = 纪律红线(immutable doctrine,绝对遵守)+ 作战 doctrine + 情绪周期状态机 + active 模式库 + 复盘教训 + 输出 JSON 契约。这就是 `p/K/M` 进入 LLM 上下文的方式。
- **幻觉防护(LLM-agent 头号风险)**:`parse_decision` 只保留 code **在当日候选 universe 里**的候选,丢弃 LLM 编造的标的;malformed JSON → 空仓兜底;confidence 钳到 [0,1]。
- **可测性**:agent 是个 `DecisionPolicy`,直接进 `WalkForwardEval`;MockLLM 返回脚本化 JSON,端到端离线可测 + 可量化。
- **未来函数**:agent 只拿 `(state, universe)`(Phase-0d 已证 ≤t 的 frozen 快照,无 source 句柄)→ 结构上够不到未来;LLM 也只看到这些渲染文本。

---

## File Structure

```
pyproject.toml         # MODIFY: + openai 依赖
youzi/llm/
  __init__.py
  client.py            # LLMClient(Protocol) + MockLLMClient + DeepSeekClient(lazy openai)
youzi/agent/
  __init__.py
  prompt.py            # build_system_prompt(harness) + build_user_prompt(state, universe)
  parse.py             # parse_decision(raw, date, universe) -> DecisionPackage (鲁棒/幻觉过滤)
  agent.py             # LLMAgentPolicy(harness, llm) implements DecisionPolicy
scripts/
  smoke_deepseek_agent.py   # 手动: 真实 DeepSeek 跑一天(需 DEEPSEEK_API_KEY + 网络)
tests/
  test_llm_client.py
  test_prompt.py
  test_parse.py
  test_agent.py
  test_agent_integration.py    # LLMAgentPolicy + MockLLM 过 WalkForwardEval
```

**全局类型契约:**
- `LLMClient`(Protocol):`complete(system: str, user: str) -> str`。`MockLLMClient(scripted: str | list[str])`,有 `.calls` 记录。`DeepSeekClient(model="deepseek-chat", api_key=None, base_url="https://api.deepseek.com")`。
- `build_system_prompt(harness: HarnessState) -> str`;`build_user_prompt(state: MarketState, universe: CandidateUniverse) -> str`。
- `parse_decision(raw: str, date: Date, universe: CandidateUniverse) -> DecisionPackage`。
- `LLMAgentPolicy(harness: HarnessState, llm: LLMClient)`,`decide(state, universe) -> DecisionPackage`(满足 `DecisionPolicy`)。

---

## Task 1: LLM 客户端(Protocol + Mock + DeepSeek)

**Files:** Modify `pyproject.toml`; Create `youzi/llm/__init__.py`, `youzi/llm/client.py`; Test `tests/test_llm_client.py`

- [ ] **Step 1: 加 openai 依赖**

`pyproject.toml` 的 `dependencies` 列表追加一行(保留已有项):
```toml
    "openai>=1.0",
```
（DeepSeek 走 OpenAI 兼容接口;`DeepSeekClient` lazy import,测试不需要它安装,但 smoke 脚本需要。)

- [ ] **Step 2: 写失败测试**

```python
# tests/test_llm_client.py
from youzi.llm.client import MockLLMClient


def test_mock_returns_fixed_and_records_calls():
    m = MockLLMClient('{"x":1}')
    assert m.complete("sys", "u1") == '{"x":1}'
    assert m.complete("sys", "u2") == '{"x":1}'
    assert m.calls == [("sys", "u1"), ("sys", "u2")]


def test_mock_scripted_list_repeats_last():
    m = MockLLMClient(["a", "b"])
    assert m.complete("s", "x") == "a"
    assert m.complete("s", "y") == "b"
    assert m.complete("s", "z") == "b"      # 用尽后重复最后一个


def test_mock_satisfies_llmclient_protocol():
    from youzi.llm.client import LLMClient
    m = MockLLMClient("ok")
    assert isinstance(m, LLMClient)          # runtime-checkable Protocol
```

- [ ] **Step 3: 实现 `youzi/llm/__init__.py` 与 `youzi/llm/client.py`**

`youzi/llm/__init__.py`:
```python
"""LLM 客户端抽象:Protocol + Mock(测试)+ DeepSeek(实盘,OpenAI 兼容)。"""
```

`youzi/llm/client.py`:
```python
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """最小 LLM 接口:给系统/用户提示,返回文本(期望是 JSON 字符串)。"""
    def complete(self, system: str, user: str) -> str: ...


class MockLLMClient:
    """离线测试用:返回脚本化响应,并记录每次 (system, user) 调用。"""

    def __init__(self, scripted: "str | list[str]") -> None:
        self._responses: list[str] = [scripted] if isinstance(scripted, str) else list(scripted)
        if not self._responses:
            raise ValueError("scripted 不能为空")
        self._i = 0
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r


class DeepSeekClient:
    """DeepSeek(OpenAI 兼容)。lazy import openai;实盘/smoke 用,测试不触达。"""

    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None,
                 base_url: str = "https://api.deepseek.com", temperature: float = 0.3) -> None:
        from openai import OpenAI  # lazy
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY")
        self._client = OpenAI(api_key=key, base_url=base_url)
        self._model = model
        self._temperature = temperature

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=self._temperature,
        )
        return resp.choices[0].message.content or ""
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd "/Volumes/kairos/引力场量化/youzi-自进化版" && source .venv/bin/activate && pytest tests/test_llm_client.py -v`
Expected: PASS（若 openai 未装,`pip install -e ".[dev]"` 或 `pip install openai`;但这些测试不 import openai,Mock 不依赖它)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml youzi/llm/__init__.py youzi/llm/client.py tests/test_llm_client.py
git commit -m "feat(llm): LLMClient 协议 + MockLLMClient + DeepSeekClient(lazy)"
```

---

## Task 2: 提示构造(把 H 渲染进上下文)

**Files:** Create `youzi/agent/__init__.py`, `youzi/agent/prompt.py`; Test `tests/test_prompt.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_prompt.py
from datetime import date, datetime
from youzi.harness.loader import load_seeds
from youzi.schemas.market import MarketState, EchelonRung
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.agent.prompt import build_system_prompt, build_user_prompt
from pathlib import Path

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def test_system_prompt_injects_harness_sections():
    h = load_seeds(SEEDS)
    sys = build_system_prompt(h)
    # 关键段落都在
    assert "纪律红线" in sys
    assert "模式库" in sys and "复盘教训" in sys
    assert "情绪周期" in sys
    assert "JSON" in sys                       # 输出契约
    # 至少注入了一条 immutable doctrine 与一个 active 技能名
    core = h.doctrine.immutable_core()[0]
    assert core.guidance in sys
    an_active = h.skills.by_status("active")[0]
    assert an_active.name_cn in sys


def test_user_prompt_lists_candidate_codes():
    state = MarketState(date=date(2024, 6, 27), max_board_height=7, limit_up_count=2,
                        blowup_count=1, blowup_rate=0.33, limit_down_count=1,
                        echelon=[EchelonRung(height=7, count=1, representatives=["龙头"])],
                        money_effect_raw=1.5, sentiment_raw=10.0, sentiment_norm=None,
                        as_of=datetime(2024, 6, 27, 15, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(code="000001", name="甲", status="limit_up", boards=7, industry="芯片"),
        StockSnapshot(code="300002", name="乙", status="limit_up", boards=2),
        StockSnapshot(code="000003", name="跌", status="limit_down")])
    user = build_user_prompt(state, uni)
    assert "2024-06-27" in user
    assert "000001" in user and "300002" in user        # 涨停候选列出
    assert "000003" not in user                          # 跌停不在候选池
    assert "7" in user                                   # 连板高度等盘面量
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_prompt.py -v`
Expected: FAIL（`ModuleNotFoundError: youzi.agent.prompt`）

- [ ] **Step 3: 实现 `youzi/agent/__init__.py` 与 `youzi/agent/prompt.py`**

`youzi/agent/__init__.py`:
```python
"""LLM Agent:把 Harness H 渲染进提示,产出决策包。"""
```

`youzi/agent/prompt.py`:
```python
from __future__ import annotations

from youzi.harness.harness import HarnessState
from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse

_OUTPUT_CONTRACT = (
    '输出格式(严格 JSON,不要 markdown 围栏):'
    '{"regime_read": "<当前情绪相位>", '
    '"candidates": [{"code": "<6位代码,必须来自候选池>", "pattern": "<命中的模式名/skill_id>", '
    '"reason": "<简短理由>", "confidence": <0到1的小数>}], '
    '"no_trade_reason": "<若判断空仓则填理由,否则空字符串>"}'
)


def build_system_prompt(h: HarnessState) -> str:
    """把 H=(p,K,M)+状态机渲染成系统提示——harness 包住模型的核心。"""
    out: list[str] = [
        "你是 A股游资/超短交易 co-pilot。读当日盘面与候选池,依据下面的纪律红线、作战 doctrine、"
        "情绪周期、模式库与复盘教训,判读当前相位并产出一个决策包 JSON。人类游资会确认后下单。",
        "\n## 纪律红线(绝对遵守,违背即错):",
    ]
    for e in h.doctrine.immutable_core():
        out.append(f"- {e.section}:{e.guidance}")
    out.append("\n## 作战 doctrine(按相位):")
    for e in h.doctrine.mutable_entries():
        out.append(f"- [{e.regime_raw or 'all'}] {e.section}:{e.guidance}")
    out.append("\n## 情绪周期相位(据此判读 regime_read):")
    for p in h.cycle.phases:
        sigs = ";".join(f"{t.signal}→{t.to}" for t in p.transitions)
        out.append(f"- {p.phase}:你看到[{'/'.join(p.you_see)}] 转移[{sigs}]")
    out.append("\n## 模式库(可用技能,只在适用相位用):")
    for s in h.skills.by_status("active"):
        tags = "/".join(s.phases) + (("|" + "/".join(s.ecologies)) if s.ecologies else "")
        out.append(f"- {s.name_cn}({s.skill_id})[{s.type}] 适用[{tags}] "
                   f"触发:{s.trigger} 买点:{s.entry} 卖/止:{s.exit_stop} "
                   f"禁忌:{';'.join(s.taboo)}")
    out.append("\n## 复盘教训(口诀与失败签名):")
    for l in h.memory.all():
        if l.outcome == "principle":
            out.append(f"- [口诀] {l.lesson}")
    for l in h.memory.all():
        if l.outcome == "loss":
            tag = f"{l.named_analog}:" if l.named_analog else ""
            out.append(f"- [失败] {tag}{l.lesson}")
    out.append("\n## " + _OUTPUT_CONTRACT)
    return "\n".join(out)


def build_user_prompt(state: MarketState, universe: CandidateUniverse) -> str:
    """渲染当日盘面 + 候选池(只能从候选池里选 code)。"""
    out = [
        f"## 今日盘面 {state.date}:",
        f"情绪值(归一):{state.sentiment_norm}  原始复合分:{state.sentiment_raw:.1f}",
        f"最高连板:{state.max_board_height}  涨停数:{state.limit_up_count}  "
        f"炸板率:{state.blowup_rate:.2f}  跌停数:{state.limit_down_count}",
        f"赚钱效应(昨涨停今表现均值):{state.money_effect_raw:.2f}",
    ]
    if state.echelon:
        ech = ";".join(f"{r.height}板×{r.count}({'/'.join(r.representatives)})"
                       for r in state.echelon)
        out.append(f"连板梯队:{ech}")
    out.append("\n## 候选池(只能从这里面选 code;名 连板 行业):")
    ups = sorted(universe.by_status("limit_up"), key=lambda s: -(s.boards or 0))
    for s in ups:
        out.append(f"- {s.code} {s.name} {s.boards or '?'}板 {s.industry or ''}")
    if not ups:
        out.append("(今日无涨停候选)")
    return "\n".join(out)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_prompt.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/agent/__init__.py youzi/agent/prompt.py tests/test_prompt.py
git commit -m "feat(agent): 提示构造(把 H=(p,K,M)+状态机+盘面候选渲染进上下文)"
```

---

## Task 3: 响应解析(鲁棒 + 幻觉过滤)

**Files:** Create `youzi/agent/parse.py`; Test `tests/test_parse.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_parse.py
from datetime import date
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.agent.parse import parse_decision


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(code="000001", name="甲", status="limit_up", boards=7),
        StockSnapshot(code="300002", name="乙", status="limit_up", boards=2)])


def test_parse_valid_keeps_universe_codes():
    raw = ('{"regime_read":"主升","candidates":['
           '{"code":"000001","pattern":"highest_board","reason":"龙头","confidence":0.8}],'
           '"no_trade_reason":""}')
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert len(pkg.candidates) == 1
    c = pkg.candidates[0]
    assert c.code == "000001" and c.name == "甲" and c.pattern == "highest_board"
    assert c.confidence == 0.8


def test_parse_drops_hallucinated_code():
    raw = ('{"candidates":[{"code":"999999","pattern":"x","reason":"幻觉","confidence":0.9},'
           '{"code":"300002","pattern":"y","reason":"真","confidence":0.5}]}')
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert {c.code for c in pkg.candidates} == {"300002"}        # 999999 不在候选池,丢弃


def test_parse_clamps_confidence_and_handles_markdown_fence():
    raw = '```json\n{"candidates":[{"code":"000001","confidence":1.7}]}\n```'
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert pkg.candidates[0].confidence == 1.0                    # 钳到 [0,1] + 去围栏


def test_parse_malformed_falls_back_to_no_trade():
    pkg = parse_decision("这不是 JSON", date(2024, 6, 27), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_parse_no_trade_passthrough():
    raw = '{"candidates":[],"no_trade_reason":"退潮空仓"}'
    pkg = parse_decision(raw, date(2024, 6, 27), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason == "退潮空仓"
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_parse.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/agent/parse.py`**

```python
from __future__ import annotations

import json
from datetime import date as Date

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.universe.universe import CandidateUniverse


def _extract_json(raw: str) -> str:
    """去 markdown 围栏 / 取第一个 { 到最后一个 } 的子串。"""
    s = (raw or "").strip()
    if "```" in s:
        # 去掉 ```json ... ``` 围栏
        s = s.replace("```json", "```").split("```")[1] if s.count("```") >= 2 else s
        s = s.strip()
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j != -1 and j > i:
        return s[i:j + 1]
    return s


def _clamp01(v: object, default: float = 0.5) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, f))


def _match_code(raw_code: object, universe: CandidateUniverse):
    code = str(raw_code or "").strip()
    if not code:
        return None
    return universe.get(code) or universe.get(code.zfill(6))


def parse_decision(raw: str, date: Date, universe: CandidateUniverse) -> DecisionPackage:
    """把 LLM 文本鲁棒解析成 DecisionPackage:幻觉 code 丢弃,malformed → 空仓兜底。"""
    try:
        data = json.loads(_extract_json(raw))
        if not isinstance(data, dict):
            raise ValueError("顶层非对象")
    except (json.JSONDecodeError, ValueError, IndexError):
        return DecisionPackage(date=date, no_trade_reason="LLM 输出解析失败")

    cands: list[Candidate] = []
    seen: set[str] = set()
    for c in (data.get("candidates") or []):
        if not isinstance(c, dict):
            continue
        snap = _match_code(c.get("code"), universe)
        if snap is None or snap.code in seen:        # 幻觉/不在候选池/重复 → 丢
            continue
        seen.add(snap.code)
        cands.append(Candidate(
            code=snap.code, name=snap.name,
            pattern=str(c.get("pattern", "")), reason=str(c.get("reason", "")),
            confidence=_clamp01(c.get("confidence", 0.5))))
    return DecisionPackage(date=date, candidates=cands,
                           no_trade_reason=str(data.get("no_trade_reason", "")))
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_parse.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/agent/parse.py tests/test_parse.py
git commit -m "feat(agent): 响应解析(鲁棒 JSON + 幻觉 code 过滤 + 兜底)"
```

---

## Task 4: `LLMAgentPolicy`(实现 DecisionPolicy)

**Files:** Create `youzi/agent/agent.py`; Test `tests/test_agent.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_agent.py
from datetime import date, datetime
from pathlib import Path
from youzi.harness.loader import load_seeds
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.llm.client import MockLLMClient
from youzi.agent.agent import LLMAgentPolicy

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def _state():
    return MarketState(date=date(2024, 6, 27), max_board_height=7, limit_up_count=2,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0, echelon=[],
                       money_effect_raw=2.0, sentiment_raw=12.0, sentiment_norm=None,
                       as_of=datetime(2024, 6, 27, 15, 0))


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(code="000001", name="甲", status="limit_up", boards=7),
        StockSnapshot(code="300002", name="乙", status="limit_up", boards=2)])


def test_agent_decides_via_llm_and_parses():
    llm = MockLLMClient('{"regime_read":"主升","candidates":'
                        '[{"code":"000001","pattern":"highest_board","reason":"龙头","confidence":0.7}],'
                        '"no_trade_reason":""}')
    agent = LLMAgentPolicy(load_seeds(SEEDS), llm)
    pkg = agent.decide(_state(), _uni())
    assert {c.code for c in pkg.candidates} == {"000001"}
    # LLM 确实收到了渲染好的系统/用户提示
    sys, user = llm.calls[0]
    assert "纪律红线" in sys and "000001" in user


def test_agent_is_a_decision_policy():
    # 结构上满足 WalkForwardEval 期望的 DecisionPolicy(有 decide(state, universe))
    agent = LLMAgentPolicy(load_seeds(SEEDS), MockLLMClient('{"candidates":[]}'))
    pkg = agent.decide(_state(), _uni())
    assert pkg.candidates == []
```

- [ ] **Step 2: 运行,确认失败**

Run: `pytest tests/test_agent.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `youzi/agent/agent.py`**

```python
from __future__ import annotations

from youzi.agent.parse import parse_decision
from youzi.agent.prompt import build_system_prompt, build_user_prompt
from youzi.eval.decision import DecisionPackage
from youzi.harness.harness import HarnessState
from youzi.llm.client import LLMClient
from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class LLMAgentPolicy:
    """LLM 驱动的 DecisionPolicy:harness 包住模型,读盘面+候选→决策包。

    持有 harness 而非预渲染提示:每次 decide 按当前 H 重建系统提示,
    使 Phase-1b 的 Refiner 改 H 后立即对 agent 可见。
    """

    def __init__(self, harness: HarnessState, llm: LLMClient) -> None:
        self._harness = harness
        self._llm = llm

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        system = build_system_prompt(self._harness)
        user = build_user_prompt(state, universe)
        raw = self._llm.complete(system, user)
        return parse_decision(raw, state.date, universe)
```

- [ ] **Step 4: 运行,确认通过**

Run: `pytest tests/test_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add youzi/agent/agent.py tests/test_agent.py
git commit -m "feat(agent): LLMAgentPolicy(DecisionPolicy,harness 包住模型)"
```

---

## Task 5: 集成 — Agent(MockLLM)过 WalkForwardEval

**Files:** Create `tests/test_agent_integration.py`

> 证明 agent 作为 DecisionPolicy 插进 Phase-0d 评测尺,端到端产出可量化 EvalReport,且无前视。

- [ ] **Step 1: 写集成测试**

```python
# tests/test_agent_integration.py
from datetime import date
from pathlib import Path
import pandas as pd
from youzi.harness.loader import load_seeds
from youzi.llm.client import MockLLMClient
from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.walk_forward import WalkForwardEval
from tests.conftest import FakeSource

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def _src():
    """3 天,代码 A 每日涨停(MockLLM 固定选 A → continued)。"""
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    frames = {}
    for d, b in [(d0, 2), (d1, 3), (d2, 4)]:
        frames[("zt", d)] = pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [b]})
        frames[("blowup", d)] = pd.DataFrame()
        frames[("dt", d)] = pd.DataFrame()
    return FakeSource(frames, [d0, d1, d2])


def test_agent_runs_through_eval_harness():
    # MockLLM 固定选 A(候选池里有 A)
    llm = MockLLMClient('{"regime_read":"主升","candidates":'
                        '[{"code":"A","pattern":"highest_board","reason":"龙头","confidence":0.7}],'
                        '"no_trade_reason":""}')
    agent = LLMAgentPolicy(load_seeds(SEEDS), llm)
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(agent)
    # day0 选A→day1 A涨停=continued; day1 选A→day2 A涨停=continued; day2 选A 无次日丢弃
    assert rep.n_decisions == 3 and rep.n_candidates == 2
    assert rep.hit_rate == 1.0 and rep.mean_score == 1.0
    assert "highest_board" in rep.by_pattern
    # 防幻觉:即便 agent 每天都返回 "A",A 在每天候选池里才被计入(已验证)


def test_agent_hallucination_yields_no_candidates():
    # MockLLM 选一个不存在的 code → parse 丢弃 → 全程空仓
    llm = MockLLMClient('{"candidates":[{"code":"ZZZ","pattern":"x","confidence":0.9}]}')
    agent = LLMAgentPolicy(load_seeds(SEEDS), llm)
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(agent)
    assert rep.n_candidates == 0          # 幻觉 code 全被丢弃
```

- [ ] **Step 2: 运行,确认通过**

Run: `pytest tests/test_agent_integration.py -v`
Expected: PASS

- [ ] **Step 3: 跑全量套件**

Run: `pytest -p no:cacheprovider`(`-q` 摘要经管道会空,看退出码;约 145+ 用例)
Expected: exit 0,全绿

- [ ] **Step 4: Commit**

```bash
git add tests/test_agent_integration.py
git commit -m "test(agent): LLMAgentPolicy(MockLLM)过 WalkForwardEval 端到端 + 幻觉防护"
```

---

## Task 6: DeepSeek 真实冒烟脚本(手动,触网)

**Files:** Create `scripts/smoke_deepseek_agent.py`

> 不入 CI。验证真实 DeepSeek 能产出可解析的决策包。需要 `DEEPSEEK_API_KEY` + 网络 + akshare 真实数据。

- [ ] **Step 1: 写脚本**

```python
# scripts/smoke_deepseek_agent.py
"""手动冒烟:真实 DeepSeek 跑一天选股。
Run: DEEPSEEK_API_KEY=... python scripts/smoke_deepseek_agent.py 20240627
需要:openai 已装、网络、akshare 可拉数、seeds/ 在位。"""
from __future__ import annotations

import sys
from datetime import datetime

from youzi.data.source import AkshareSource
from youzi.replay.firewall import AsOfGuard
from youzi.data.source import GuardedSource
from youzi.universe.universe import build_universe
from youzi.features.builder import build_market_state
from youzi.harness.loader import load_seeds
from youzi.llm.client import DeepSeekClient
from youzi.agent.agent import LLMAgentPolicy


def main(ymd: str) -> None:
    day = datetime.strptime(ymd, "%Y%m%d").date()
    src = AkshareSource()
    guard = AsOfGuard(day)
    gs = GuardedSource(src, guard)
    state = build_market_state(day, gs, history=[], as_of=datetime.now())
    universe = build_universe(gs, day)
    print(f"[{day}] 涨停候选 {len(universe.by_status('limit_up'))} 只")

    from pathlib import Path
    seeds = Path(__file__).resolve().parent.parent / "seeds"
    agent = LLMAgentPolicy(load_seeds(seeds), DeepSeekClient())
    pkg = agent.decide(state, universe)
    print("regime/候选:")
    print("  no_trade:", pkg.no_trade_reason or "(有候选)")
    for c in pkg.candidates:
        print(f"  {c.code} {c.name} 模式={c.pattern} 信心={c.confidence} 理由={c.reason}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "20240627")
```

- [ ] **Step 2: 手动跑(需 key+网络,不在 CI)**

Run: `DEEPSEEK_API_KEY=... python scripts/smoke_deepseek_agent.py 20240627`
Expected: 打印涨停候选数 + DeepSeek 选出的候选(code 均在候选池内)。**这同时顺带验证 akshare 真实列名**(Phase-0c 债务);若候选池为空或字段异常,回查 `_RENAME`/网络。

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_deepseek_agent.py
git commit -m "chore(agent): DeepSeek 真实冒烟脚本(手动,不入 CI)"
```

---

## Self-Review(已自检)

**1. Spec 覆盖(对照 Goal/范围):**
- LLM 客户端(Protocol+Mock+DeepSeek)→ Task 1。✅
- 提示构造(H→系统提示;盘面候选→用户提示)→ Task 2。✅
- 响应解析(鲁棒+幻觉过滤+兜底+confidence 钳)→ Task 3。✅
- `LLMAgentPolicy`(DecisionPolicy,harness 包住模型)→ Task 4。✅
- 集成(Agent+MockLLM 过 WalkForwardEval,可量化+幻觉防护)→ Task 5。✅
- DeepSeek 真实冒烟(手动,顺带核 akshare 列名)→ Task 6。✅
- **明确不在 1a**:Refiner/轨迹/自进化(1b)、协同学习/微调(1c)、按 regime 选择性注入提示(1b 优化)。

**2. Placeholder 扫描:** 无 TBD/TODO;每个改代码 step 均给完整代码 + 命令。✅

**3. 类型一致性:** `LLMClient.complete(system,user)->str` 在 Task 1 定义、Mock/DeepSeek 实现、Task 4 agent 调用一致;`build_system_prompt(harness)`/`build_user_prompt(state,universe)` 在 Task 2 定义、Task 4 使用一致;`parse_decision(raw,date,universe)->DecisionPackage` 在 Task 3 定义、Task 4 使用一致;`LLMAgentPolicy.decide(state,universe)` 满足 Phase-0d `DecisionPolicy`,Task 5 直接进 `WalkForwardEval`;复用 `HarnessState`(harness)、`Candidate/DecisionPackage`(eval.decision)、`CandidateUniverse`、`MarketState`。✅

**4. 防火墙/幻觉:** agent.decide 只拿 `(state, universe)`——Phase-0d 已证为 ≤t 的无 source frozen 快照,结构上够不到未来(LLM 也只见渲染文本)。`parse_decision` 用 `universe.get` 过滤,LLM 编造的 code 一律丢弃(Task 3/5 显式测)。✅

**5. 回归风险:** 纯新增 `youzi/{llm,agent}/` + pyproject 加 openai(lazy,测试不 import)。复用 Phase-0a/0c/0d 公共接口,不改已有模块 → 既有 129 测试不受影响。MockLLM 全离线;DeepSeek 仅 smoke 触发。✅
