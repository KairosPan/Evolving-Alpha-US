# Phase 1A — Conversational Tool-Calling Face (B-WIDE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productionize the spike-proven conversational tool-calling loop into a real `alpha/converse/` package: a multi-turn chat loop that, against the shared brain `H`, can call a `decide` tool (returning a typed `DecisionPackage`) and a gated write tool (routing through the existing `try_apply_op`), driven by a new `converse` LLM role.

**Architecture:** A new, additive package `alpha/converse/` that sits *beside* the existing deterministic day-agent — it does NOT modify `LLMAgentPolicy.decide` or the `InnerLoop` (decision (a): one `H`, two faces). The loop is reimplemented thin in Python (Phase 0 proved Hermes's `conversation_loop.py` cannot be vendored — eager footprint 28 files, drags the monolith). Tool calls ride in the chat reply text as a JSON object (the codebase's chat clients return text, matching Sonia's `extract_json_object` pattern), so everything is offline-testable with `MockLLMClient`.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses `alpha.llm.chat.ChatLLMClient`/`ChatMessage`, `alpha.llm.extract.extract_json_object`, `alpha.llm.config.make_client`, `alpha.agent.agent.LLMAgentPolicy`, `alpha.refine.apply.try_apply_op`, `alpha.refine.ops.{RefineOp, PASS_TOOLS}`, `alpha.harness.metatools.MetaTools`, `alpha.harness.edit_log.EditLog`.

## Global Constraints

- **Python `>=3.11`**, pydantic v2. Tests deterministic: drive the loop with `MockLLMClient` (it implements `chat(system, messages) -> str`, returning canned replies in sequence) — never a live LLM.
- **ADDITIVE only — do NOT modify `alpha/agent/agent.py`'s `decide`, `alpha/loop/inner_loop.py`, or any existing test.** The conversational face shares `H` but is a separate package. The existing suite (`python -m pytest -q`, currently **555 passed**) must stay green.
- **One-gate invariant:** the gated write tool's ONLY path to mutate `H` is `try_apply_op`. No direct `h.memory`/`h.skills`/`h.doctrine` writes anywhere in `alpha/converse/`.
- **Tool-call wire convention (fixed for this package):** the model's chat reply is EITHER a tool call — a JSON object `{"tool": "<name>", "args": {...}}` anywhere in the reply (extracted via `extract_json_object`) — OR a final answer (prose with no such JSON object). Tool results are fed back as a `ChatMessage(role="user", text="[tool:<name> result]\n<serialized>")`.
- **New LLM role `converse`** defaults to `("openai_compat", "deepseek-v4-pro")` like the other roles.
- **English** code/docs. Follow existing patterns (model the chat usage on `alpha/meta/sonia_agent.py`; model decide/gated-write on the validated spike under `spikes/2026-06-26-hermes-vendor-feasibility/`).
- Out of scope (later sub-phases): SQLite session persistence, PIT-safe memory recall, git-workspace artifacts, per-turn provenance.

## File Structure

- `alpha/converse/__init__.py` — package marker.
- `alpha/converse/registry.py` — `Tool`, `ToolRegistry` (register / call / specs).
- `alpha/converse/loop.py` — `run_conversation(...)` + `ConversationResult` (the multi-turn tool-calling loop).
- `alpha/converse/tools.py` — `make_decide_tool(...)`, `make_gated_write_tool(...)`.
- `alpha/converse/agent.py` — `build_system_prompt(...)`, `build_converse_registry(...)`, `converse(...)` (the assembled entry point).
- `tests/converse/test_registry.py`, `test_loop.py`, `test_tools.py`, `test_agent.py`.
- Modify: `alpha/llm/config.py` (add `converse` role); `tests/llm/test_config.py` (cover it).

---

### Task 1: Add the `converse` LLM role

**Files:**
- Modify: `alpha/llm/config.py:8` (the `Role` Literal) and `alpha/llm/config.py` `_DEFAULTS`
- Test: `tests/llm/test_config.py`

**Interfaces:**
- Produces: `make_client("converse")` resolvable; `Role` includes `"converse"`.

- [ ] **Step 1: Write the failing test** (append to `tests/llm/test_config.py`)

```python
def test_converse_role_resolves(monkeypatch):
    monkeypatch.setenv("ALPHA_CONVERSE_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "{}")
    assert isinstance(make_client("converse"), MockLLMClient)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/llm/test_config.py::test_converse_role_resolves -v`
Expected: FAIL — `ValueError: unknown role: 'converse'`.

- [ ] **Step 3: Add the role** — edit `alpha/llm/config.py`:

Change the `Role` line:
```python
Role = Literal["agent", "refiner", "sonia", "converse"]
```
Add to `_DEFAULTS` (after the `"sonia"` entry):
```python
    "converse": ("openai_compat", "deepseek-v4-pro"),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/llm/test_config.py -v`
Expected: PASS (all config tests, including the new one).

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/config.py tests/llm/test_config.py
git commit -m "feat(converse): add the converse LLM role"
```

---

### Task 2: `ToolRegistry`

**Files:**
- Create: `alpha/converse/__init__.py` (empty), `alpha/converse/registry.py`
- Test: `tests/converse/test_registry.py` (create `tests/converse/__init__.py` too if the suite needs it — match the existing `tests/` layout; existing test dirs have no `__init__.py`, so do not add one)

**Interfaces:**
- Produces: `Tool` (dataclass: `name: str`, `schema: dict`, `fn`); `ToolRegistry` with `.register(name: str, schema: dict, fn)`, `.call(name: str, **kwargs)` (raises `KeyError` on unknown), `.specs() -> list[dict]` (the registered schemas, for the system prompt). Consumed by Tasks 3 and 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_registry.py
import pytest
from alpha.converse.registry import ToolRegistry

def test_register_call_and_specs():
    reg = ToolRegistry()
    reg.register("echo", {"name": "echo", "description": "echoes"}, lambda msg: f"got:{msg}")
    assert reg.call("echo", msg="hi") == "got:hi"
    assert reg.specs() == [{"name": "echo", "description": "echoes"}]

def test_unknown_tool_raises():
    with pytest.raises(KeyError):
        ToolRegistry().call("nope")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.converse'`.

- [ ] **Step 3: Implement**

```python
# alpha/converse/__init__.py
```
(empty file)

```python
# alpha/converse/registry.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class Tool:
    name: str
    schema: dict
    fn: Callable[..., Any]

@dataclass
class ToolRegistry:
    """Name -> tool. Mirrors an OpenAI-function-calling registry; the B-WIDE loop dispatches by name."""
    _tools: dict[str, Tool] = field(default_factory=dict)
    def register(self, name: str, schema: dict, fn: Callable[..., Any]) -> None:
        self._tools[name] = Tool(name, schema, fn)
    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name].fn(**kwargs)
    def specs(self) -> list[dict]:
        return [t.schema for t in self._tools.values()]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_registry.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/__init__.py alpha/converse/registry.py tests/converse/test_registry.py
git commit -m "feat(converse): tool registry"
```

---

### Task 3: `run_conversation` — the multi-turn tool-calling loop

**Files:**
- Create: `alpha/converse/loop.py`
- Test: `tests/converse/test_loop.py`

**Interfaces:**
- Consumes: `ToolRegistry` (Task 2); `alpha.llm.chat.{ChatLLMClient, ChatMessage}`; `alpha.llm.extract.extract_json_object`.
- Produces: `ConversationResult` (pydantic: `final_text: str`, `messages: list[ChatMessage]`, `tool_calls: list[dict]`, `hit_max_iters: bool`); `run_conversation(registry, chat, system, messages, *, max_iters=8) -> ConversationResult`. Consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

```python
# tests/converse/test_loop.py
from alpha.converse.registry import ToolRegistry
from alpha.converse.loop import run_conversation
from alpha.llm.chat import ChatMessage
from alpha.llm.client import MockLLMClient

def _reg():
    reg = ToolRegistry()
    reg.register("echo", {"name": "echo"}, lambda msg: f"got:{msg}")
    return reg

def test_dispatches_tool_then_finalizes():
    # turn 1: model calls echo; turn 2: model gives a prose final answer
    llm = MockLLMClient(['{"tool": "echo", "args": {"msg": "hi"}}', "all done"])
    res = run_conversation(_reg(), llm, "sys", [ChatMessage(role="user", text="go")])
    assert res.final_text == "all done"
    assert res.hit_max_iters is False
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0]["tool"] == "echo" and res.tool_calls[0]["result"] == "got:hi"

def test_no_tool_call_is_immediate_final():
    llm = MockLLMClient(["just prose, no json"])
    res = run_conversation(_reg(), llm, "sys", [ChatMessage(role="user", text="hi")])
    assert res.final_text == "just prose, no json"
    assert res.tool_calls == []

def test_unknown_tool_is_reported_not_raised():
    llm = MockLLMClient(['{"tool": "ghost", "args": {}}', "done"])
    res = run_conversation(_reg(), llm, "sys", [ChatMessage(role="user", text="go")])
    assert res.tool_calls[0]["result"] == {"error": "unknown tool: ghost"}
    assert res.final_text == "done"

def test_respects_max_iters():
    # model always emits a tool call -> never finalizes -> budget exhausts
    llm = MockLLMClient(['{"tool": "echo", "args": {"msg": "x"}}'])
    res = run_conversation(_reg(), llm, "sys", [ChatMessage(role="user", text="go")], max_iters=3)
    assert res.hit_max_iters is True
    assert len(res.tool_calls) == 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/converse/test_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.converse.loop'`.

- [ ] **Step 3: Implement**

```python
# alpha/converse/loop.py
from __future__ import annotations
import json
from pydantic import BaseModel, Field
from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.extract import extract_json_object
from alpha.converse.registry import ToolRegistry

class ConversationResult(BaseModel):
    final_text: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)   # [{"tool","args","result"}]
    hit_max_iters: bool = False

def _result_text(result) -> str:
    if hasattr(result, "model_dump_json"):
        return result.model_dump_json()
    try:
        return json.dumps(result, default=str)
    except TypeError:
        return str(result)

def _parse_tool_call(reply: str) -> dict | None:
    block = extract_json_object(reply)
    if not block:
        return None
    try:
        obj = json.loads(block)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) and "tool" in obj else None

def run_conversation(registry: ToolRegistry, chat: ChatLLMClient, system: str,
                     messages: list[ChatMessage], *, max_iters: int = 8) -> ConversationResult:
    """Multi-turn tool-calling loop. Each iter: ask the model; if its reply is a tool call, dispatch
    it and feed the result back; otherwise the reply is the final answer. Bounded by max_iters."""
    msgs = list(messages)
    calls: list[dict] = []
    for _ in range(max_iters):
        reply = chat.chat(system, msgs)
        call = _parse_tool_call(reply)
        if call is None:
            return ConversationResult(final_text=reply.strip(), messages=msgs, tool_calls=calls)
        name, args = call["tool"], call.get("args", {}) or {}
        try:
            result = registry.call(name, **args)
        except KeyError:
            result = {"error": f"unknown tool: {name}"}
        except Exception as e:                       # a tool raising must not kill the conversation
            result = {"error": f"{type(e).__name__}: {e}"}
        calls.append({"tool": name, "args": args, "result": result})
        msgs.append(ChatMessage(role="assistant", text=reply))
        msgs.append(ChatMessage(role="user", text=f"[tool:{name} result]\n{_result_text(result)}"))
    return ConversationResult(final_text="", messages=msgs, tool_calls=calls, hit_max_iters=True)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/converse/test_loop.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/loop.py tests/converse/test_loop.py
git commit -m "feat(converse): multi-turn tool-calling loop"
```

---

### Task 4: `make_decide_tool` — the deterministic decider as a tool

**Files:**
- Create: `alpha/converse/tools.py`
- Test: `tests/converse/test_tools.py`

**Interfaces:**
- Consumes: `alpha.agent.agent.LLMAgentPolicy`, `alpha.state.market.MarketState`, `alpha.universe.universe.CandidateUniverse`, `alpha.eval.decision.DecisionPackage`.
- Produces: `make_decide_tool(harness, agent_llm) -> tuple[dict, Callable]`; the callable is `decide(state, universe) -> DecisionPackage`. Consumed by Task 6.

- [ ] **Step 1: Write the failing test** (fixtures copied from `tests/agent/test_agent.py`)

```python
# tests/converse/test_tools.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.client import MockLLMClient
from alpha.eval.decision import DecisionPackage
from alpha.converse.tools import make_decide_tool

def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active"),
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))

def _state():
    return MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=0.6, as_of=datetime(2026, 6, 12, 16, 0))

def _uni():
    return CandidateUniverse.from_stocks([StockSnapshot(symbol="RUN", name="Runner", status="gainer")])

def test_decide_tool_returns_typed_package():
    agent_llm = MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                              '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    schema, decide = make_decide_tool(_h(), agent_llm)
    assert schema["name"] == "decide"
    pkg = decide(state=_state(), universe=_uni())
    assert isinstance(pkg, DecisionPackage)
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_tools.py::test_decide_tool_returns_typed_package -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.converse.tools'`.

- [ ] **Step 3: Implement** (start `alpha/converse/tools.py`)

```python
# alpha/converse/tools.py
from __future__ import annotations
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse
from alpha.eval.decision import DecisionPackage

def make_decide_tool(harness, agent_llm):
    """Expose the EXISTING deterministic decider as a tool (decision a: one decide, two callers).
    Returns the typed DecisionPackage unchanged — not free text."""
    def decide(state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return LLMAgentPolicy(harness, agent_llm).decide(state, universe)
    schema = {"name": "decide",
              "description": "Run the deterministic decider; returns a typed DecisionPackage.",
              "parameters": {"type": "object", "properties": {}, "required": []}}
    return schema, decide
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_tools.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/tools.py tests/converse/test_tools.py
git commit -m "feat(converse): decide tool returns a typed DecisionPackage"
```

---

### Task 5: `make_gated_write_tool` — mutate `H` only through `try_apply_op`

**Files:**
- Modify: `alpha/converse/tools.py` (add the function)
- Modify: `tests/converse/test_tools.py` (add tests)

**Interfaces:**
- Consumes: `alpha.harness.metatools.MetaTools`, `alpha.harness.edit_log.EditLog`, `alpha.refine.apply.try_apply_op`, `alpha.refine.ops.{RefineOp, PASS_TOOLS}`.
- Produces: `make_gated_write_tool(harness, *, min_retire_samples=5, min_promote_samples=3) -> tuple[dict, Callable]`; the callable is `propose_memory_edit(tool: str, args: dict, rationale: str) -> dict` returning `{"status": "applied"}` or `{"status": "rejected", "reason": str}`. Consumed by Task 6.

- [ ] **Step 1: Write the failing tests** (append to `tests/converse/test_tools.py`)

```python
from alpha.converse.tools import make_gated_write_tool

def _bare_h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))

def test_gated_write_applies_valid_memory_op():
    h = _bare_h()
    _schema, propose = make_gated_write_tool(h)
    out = propose(tool="process_memory",
                  args={"lesson_id": "c-mem-1", "phases": ["trend"],
                        "outcome": "win", "lesson": "converse: gate routing works"},
                  rationale="prove the gated write path")
    assert out["status"] == "applied"
    assert any(l.lesson_id == "c-mem-1" for l in h.memory.all())

def test_gated_write_rejects_non_whitelisted_op():
    h = _bare_h()
    _schema, propose = make_gated_write_tool(h)
    out = propose(tool="rewrite_doctrine", args={"section": "x", "new_guidance": "y"},
                  rationale="not in the M whitelist")
    assert out["status"] == "rejected"
    assert out["reason"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/converse/test_tools.py -k gated_write -v`
Expected: FAIL — `ImportError: cannot import name 'make_gated_write_tool'`.

- [ ] **Step 3: Implement** (append to `alpha/converse/tools.py`)

```python
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp, PASS_TOOLS

def make_gated_write_tool(harness, *, min_retire_samples: int = 5, min_promote_samples: int = 3):
    """A tool whose ONLY path to mutate H is try_apply_op (the one write-waist). Restricted to the
    M-pass whitelist for this face; the gate enforces rationale / evidence floors / red-lines."""
    def propose_memory_edit(tool: str, args: dict, rationale: str) -> dict:
        op = RefineOp(tool=tool, args=args, rationale=rationale)
        rec, reason = try_apply_op(MetaTools(harness, EditLog()), harness, op,
                                   allowed=PASS_TOOLS["M"],
                                   min_retire_samples=min_retire_samples,
                                   min_promote_samples=min_promote_samples)
        return {"status": "applied"} if rec is not None else {"status": "rejected", "reason": reason}
    schema = {"name": "propose_memory_edit",
              "description": "Propose a memory edit; applied only if it clears the gate.",
              "parameters": {"type": "object",
                             "properties": {"tool": {"type": "string"}, "args": {"type": "object"},
                                            "rationale": {"type": "string"}},
                             "required": ["tool", "args", "rationale"]}}
    return schema, propose_memory_edit
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/converse/test_tools.py -v`
Expected: all PASS (decide + 2 gated-write).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/tools.py tests/converse/test_tools.py
git commit -m "feat(converse): gated write tool routes through try_apply_op"
```

---

### Task 6: Assemble — `build_converse_registry`, `build_system_prompt`, `converse()`

**Files:**
- Create: `alpha/converse/agent.py`
- Test: `tests/converse/test_agent.py`

**Interfaces:**
- Consumes: everything above + `alpha.llm.config.make_client`.
- Produces:
  - `build_converse_registry(harness, agent_llm) -> ToolRegistry` (registers `decide` + `propose_memory_edit`).
  - `build_system_prompt(harness, registry) -> str` (doctrine headline + tool specs + the tool-call convention).
  - `converse(harness, user_text, *, agent_llm=None, chat_llm=None, max_iters=8) -> ConversationResult` — assembles the registry + system prompt, seeds a one-message history, runs `run_conversation`. Defaults: `agent_llm = make_client("agent")`, `chat_llm = make_client("converse")`.

- [ ] **Step 1: Write the failing test** (end-to-end: a 2-step conversation that calls `decide` then finalizes — all offline via MockLLMClient)

```python
# tests/converse/test_agent.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.llm.client import MockLLMClient
from alpha.converse.agent import build_converse_registry, build_system_prompt, converse

def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active"),
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))

def test_registry_has_both_tools():
    reg = build_converse_registry(_h(), MockLLMClient("{}"))
    names = {s["name"] for s in reg.specs()}
    assert names == {"decide", "propose_memory_edit"}

def test_system_prompt_lists_tools_and_convention():
    reg = build_converse_registry(_h(), MockLLMClient("{}"))
    sys = build_system_prompt(_h(), reg)
    assert "decide" in sys and "propose_memory_edit" in sys
    assert '"tool"' in sys  # documents the tool-call JSON convention

def test_converse_calls_decide_then_finalizes():
    # the conversational (converse-role) LLM drives a 2-step turn:
    #   reply 1 -> call decide ; reply 2 -> final prose
    chat_llm = MockLLMClient(['{"tool": "decide", "args": {}}', "My read: RUN looks like a gap-and-go."])
    # the day-agent LLM that `decide` invokes returns a canned DecisionPackage
    agent_llm = MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                              '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    # decide() needs a state+universe; for 1A the tool is called with no args, so converse() must
    # supply them — assert the loop reached a final answer after one decide call.
    res = converse(_h(), "what's your read on RUN today?", agent_llm=agent_llm, chat_llm=chat_llm)
    assert res.hit_max_iters is False
    assert res.final_text == "My read: RUN looks like a gap-and-go."
    assert [c["tool"] for c in res.tool_calls] == ["decide"]
    assert res.tool_calls[0]["result"]["candidates"][0]["symbol"] == "RUN"
```

> **Note for the implementer:** the `decide` tool's callable takes `(state, universe)`, but the model calls it with no args (`{"tool":"decide","args":{}}`). For Phase 1A, `build_converse_registry` must wrap the raw decide callable so it is callable with no args by supplying a **default state+universe** the same way `tests/agent/test_agent.py` builds them (a single `RUN` gainer on `2026-06-12`). Put a `_default_state()` / `_default_universe()` helper in `agent.py` and have the registered `decide` tool close over them. (Building state from a live date+source is deferred to Phase 1B.) The result fed back is the `DecisionPackage`, so `res.tool_calls[0]["result"]` is that package object; `["candidates"][0]["symbol"]` reads it via its dict view — if the package object is not subscriptable, assert on `res.tool_calls[0]["result"].candidates[0].symbol` instead.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.converse.agent'`.

- [ ] **Step 3: Implement**

```python
# alpha/converse/agent.py
from __future__ import annotations
from datetime import date, datetime
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.chat import ChatMessage
from alpha.llm.config import make_client
from alpha.converse.registry import ToolRegistry
from alpha.converse.loop import run_conversation, ConversationResult
from alpha.converse.tools import make_decide_tool, make_gated_write_tool

# Phase 1A: a fixed default perception context for the no-arg `decide` tool. Building state from a
# live (source, date) is Phase 1B; here the conversational face proves the loop + tool plumbing.
def _default_state() -> MarketState:
    return MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=0.6, as_of=datetime(2026, 6, 12, 16, 0))

def _default_universe() -> CandidateUniverse:
    return CandidateUniverse.from_stocks([StockSnapshot(symbol="RUN", name="Runner", status="gainer")])

def build_converse_registry(harness: HarnessState, agent_llm) -> ToolRegistry:
    reg = ToolRegistry()
    decide_schema, decide_fn = make_decide_tool(harness, agent_llm)
    reg.register("decide", decide_schema,
                 lambda: decide_fn(state=_default_state(), universe=_default_universe()))
    write_schema, write_fn = make_gated_write_tool(harness)
    reg.register("propose_memory_edit", write_schema, write_fn)
    return reg

def build_system_prompt(harness: HarnessState, registry: ToolRegistry) -> str:
    lines = [
        "You are evolving-alpha's conversational face. You share one brain (H) with the deterministic "
        "decider. You may use tools.",
        "",
        "TOOLS:",
    ]
    for s in registry.specs():
        lines.append(f"- {s['name']}: {s.get('description', '')}")
    lines += [
        "",
        "To CALL a tool, reply with a JSON object: {\"tool\": \"<name>\", \"args\": {...}}.",
        "To FINISH, reply with prose and no such JSON object.",
        "",
        f"DOCTRINE: {harness.doctrine.summary() if hasattr(harness.doctrine, 'summary') else ''}",
    ]
    return "\n".join(lines)

def converse(harness: HarnessState, user_text: str, *, agent_llm=None, chat_llm=None,
             max_iters: int = 8) -> ConversationResult:
    agent_llm = agent_llm if agent_llm is not None else make_client("agent")
    chat_llm = chat_llm if chat_llm is not None else make_client("converse")
    registry = build_converse_registry(harness, agent_llm)
    system = build_system_prompt(harness, registry)
    return run_conversation(registry, chat_llm, system, [ChatMessage(role="user", text=user_text)],
                            max_iters=max_iters)
```

> **Implementer check:** confirm `Doctrine` has a `summary()` method; if not, render an empty string or the doctrine's first headline field — do NOT invent a method. Inspect `alpha/harness/doctrine.py` and use what exists. The system-prompt doctrine line is informational; the two tool-name assertions and the convention assertion are what the test gates on.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_agent.py -v`
Expected: 3 PASS — the registry has both tools, the prompt documents them + the convention, and the end-to-end conversation calls `decide` then finalizes.

- [ ] **Step 5: Run the whole suite (no regressions)**

Run: `python -m pytest -q`
Expected: `555 passed` PLUS the new `tests/converse/` tests (the existing 555 unchanged, the day-agent/InnerLoop untouched).

- [ ] **Step 6: Commit**

```bash
git add alpha/converse/agent.py tests/converse/test_agent.py
git commit -m "feat(converse): assemble the B-WIDE conversational face (registry + prompt + converse entry)"
```

---

## Self-Review

**Spec coverage (Phase 1A slice):**
- A production multi-turn tool-calling loop in `alpha/` (not the spike) → Tasks 2 + 3. ✓
- `decide` registered, returns a typed `DecisionPackage` → Task 4 + wired in Task 6. ✓
- gated write registered, routes through `try_apply_op` → Task 5 + wired in Task 6. ✓
- Driven by a new `converse` role → Task 1 (default) used in Task 6's `converse()`. ✓
- Shares `H`, additive, does NOT modify `decide`/`InnerLoop` → no task touches `alpha/agent/agent.py` or `alpha/loop/`. ✓
- Multi-turn state in memory (no SQLite) → Task 3's `msgs` list; persistence explicitly deferred. ✓

**Placeholder scan:** No "TBD"/"TODO". Two implementer-check notes (Task 6: `DecisionPackage` subscriptability; `Doctrine.summary()` existence) name the exact file to inspect and the fallback — they are verification instructions, not placeholders, because the spec values they protect (tool names, convention) are concretely asserted.

**Type consistency:** `ToolRegistry.register(name, schema, fn)` / `.call(name, **kwargs)` / `.specs()` are used identically in Tasks 3 and 6. `make_decide_tool(harness, agent_llm) -> (schema, decide)` and `make_gated_write_tool(harness, *, …) -> (schema, propose_memory_edit)` match their Task-6 call sites. `run_conversation(registry, chat, system, messages, *, max_iters)` matches Task 6's call. `try_apply_op(meta, harness, op, *, allowed, min_retire_samples, min_promote_samples)` matches `alpha/refine/apply.py:66`. The `converse` role string matches the `_DEFAULTS` key added in Task 1. `ChatMessage(role=, text=)` and `MockLLMClient(list)` returning replies in sequence match `alpha/llm/chat.py` and `alpha/llm/client.py`.
