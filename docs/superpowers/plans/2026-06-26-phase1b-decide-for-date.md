# Phase 1B — `decide` for a Live Date (PIT-guarded) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Phase 1A's fixed default state/universe behind the conversational `decide` tool with a real, PIT-guarded build from a data source for a model-supplied date — so the B-WIDE conversational face decides on real market data (`decide({"date": "2026-06-12"})`).

**Architecture:** Mirror the proven single-day perception chain from `scripts/save_decisions.py:59-63`: `GuardedSource(source, AsOfGuard(day)) → build_universe(guarded, day) → build_market_state(universe, day, as_of=close) → LLMAgentPolicy.decide`. Additive: a new `make_decide_for_date_tool(harness, agent_llm, source)` composes Phase 1A's `make_decide_tool` (it adds the state-building front-half). `build_converse_registry`/`converse` gain a `source` and register the date-based tool; the Phase-1A `_default_state`/`_default_universe` scaffolding is removed. The single ad-hoc decide passes no `history`/`prev_gainers` (their empty defaults reproduce the minimal build — `follow_through_rate=None`, `sentiment_norm=None`).

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses `alpha.data.source.{GuardedSource, FakeSource}`, `alpha.data.firewall.AsOfGuard`, `alpha.universe.universe.build_universe`, `alpha.state.builder.build_market_state`, `alpha.data.registry.make_source`, and Phase-1A `alpha.converse.*`.

## Global Constraints

- **Python `>=3.11`**, pydantic v2. Tests deterministic: drive the agent LLM with `MockLLMClient` and the data with `FakeSource` (offline, no keys). Never a live LLM or live data.
- **PIT-guarded:** the date-based decide MUST wrap the source in `GuardedSource(source, AsOfGuard(day))` (no look-ahead), exactly as `save_decisions.py:59`. `as_of = DateTime(day.year, day.month, day.day, 16, 0)` (market close).
- **Additive / minimal churn:** keep Phase-1A `make_decide_tool(harness, agent_llm) -> (schema, decide(state, universe))` and its test unchanged — the new date-based tool *composes* it. The existing suite (`python -m pytest -q`, currently **583 passed**) must stay green except the one Phase-1A converse e2e test, which Task 2 updates to the date-based call.
- The conversational `decide` tool's wire form becomes `{"tool": "decide", "args": {"date": "YYYY-MM-DD"}}` (was no-args in 1A).
- Out of scope (later): threading `history`/`prev_gainers` across a multi-turn session; SQLite session persistence; PIT memory recall (already landed separately); provenance.
- English; follow existing patterns (model on `scripts/save_decisions.py` + `tests/scripts/test_save_decisions.py`).

## File Structure

- Modify: `alpha/converse/tools.py` — add `make_decide_for_date_tool`.
- Modify: `alpha/converse/agent.py` — `build_converse_registry`/`converse` gain `source`; register the date-based decide; drop `_default_state`/`_default_universe`.
- Modify: `tests/converse/test_tools.py` — add the date-based tool test.
- Modify: `tests/converse/test_agent.py` — update the e2e test to a date + `FakeSource`.

---

### Task 1: `make_decide_for_date_tool` (PIT-guarded build from a date)

**Files:**
- Modify: `alpha/converse/tools.py`
- Modify: `tests/converse/test_tools.py`

**Interfaces:**
- Consumes: Phase-1A `make_decide_tool`; `GuardedSource`, `AsOfGuard`, `build_universe`, `build_market_state`.
- Produces: `make_decide_for_date_tool(harness, agent_llm, source) -> tuple[dict, Callable]`; the callable is `decide(date: str) -> DecisionPackage` (ISO date → PIT-guarded universe+state → typed package). The schema requires `date`. Consumed by Task 2.

- [ ] **Step 1: Write the failing test** (append to `tests/converse/test_tools.py`; the `_fake_source` helper mirrors `tests/scripts/test_save_decisions.py::_fake`)

```python
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.converse.tools import make_decide_for_date_tool

def _fake_source():
    cal = [date(2026, 6, d) for d in range(10, 14)]      # 4 trading days
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)      # RUN rises 15%/day -> a gainer (>= gainer_pct 10)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def _agent_llm():
    return MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                         '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')

def test_decide_for_date_builds_pit_state_and_returns_typed_package():
    schema, decide = make_decide_for_date_tool(_h(), _agent_llm(), _fake_source())
    assert schema["name"] == "decide" and "date" in schema["parameters"]["required"]
    pkg = decide(date="2026-06-12")
    from alpha.eval.decision import DecisionPackage
    assert isinstance(pkg, DecisionPackage)
    assert pkg.date == date(2026, 6, 12)                  # built for the requested date
    assert pkg.as_of == datetime(2026, 6, 12, 16, 0)      # PIT close stamp
    assert [c.symbol for c in pkg.candidates] == ["RUN"]  # RUN surfaced as a gainer and survived
```

(Note: `_h()` and `MockLLMClient` are already imported at the top of `tests/converse/test_tools.py` from Phase 1A — reuse them; only add the new imports `date, datetime, pandas as pd, FakeSource, make_decide_for_date_tool`.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_tools.py::test_decide_for_date_builds_pit_state_and_returns_typed_package -v`
Expected: FAIL — `ImportError: cannot import name 'make_decide_for_date_tool'`.

- [ ] **Step 3: Implement** — append to `alpha/converse/tools.py`:

```python
from datetime import date as _Date, datetime as _DateTime
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state

def make_decide_for_date_tool(harness, agent_llm, source):
    """Date-driven decide tool: build the PIT-guarded universe + state for an ISO date, then delegate
    to the Phase-1A decider. Mirrors scripts/save_decisions.py's single-day perception chain. A single
    ad-hoc decide passes no history/prev_gainers (empty defaults -> follow_through/sentiment_norm None)."""
    _schema, raw_decide = make_decide_tool(harness, agent_llm)        # reuse the low-level (state, universe) decider
    def decide(date: str):
        day = _Date.fromisoformat(date)
        guarded = GuardedSource(source, AsOfGuard(day))
        universe = build_universe(guarded, day)
        state = build_market_state(universe, day,
                                   as_of=_DateTime(day.year, day.month, day.day, 16, 0))
        return raw_decide(state=state, universe=universe)
    schema = {"name": "decide",
              "description": "Decide for a trading date (PIT-guarded). args: {\"date\": \"YYYY-MM-DD\"}.",
              "parameters": {"type": "object",
                             "properties": {"date": {"type": "string", "description": "ISO trading date"}},
                             "required": ["date"]}}
    return schema, decide
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_tools.py -v`
Expected: all PASS (the new date-based test + the Phase-1A decide/gated-write tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/tools.py tests/converse/test_tools.py
git commit -m "feat(converse): decide-for-date tool (PIT-guarded build from a source)"
```

---

### Task 2: Rewire `build_converse_registry`/`converse` with a source

**Files:**
- Modify: `alpha/converse/agent.py`
- Modify: `tests/converse/test_agent.py`

**Interfaces:**
- Consumes: `make_decide_for_date_tool` (Task 1); `alpha.data.registry.make_source`.
- Produces:
  - `build_converse_registry(harness, agent_llm, source) -> ToolRegistry` — registers the **date-based** `decide` + `propose_memory_edit`.
  - `converse(harness, user_text, *, agent_llm=None, chat_llm=None, source=None, max_iters=8)` — `source = source or make_source()`.
  - `_default_state`/`_default_universe` are removed.

- [ ] **Step 1: Update the failing tests** — rewrite `tests/converse/test_agent.py` so the e2e drives a date + a `FakeSource`:

```python
# tests/converse/test_agent.py  (replace the file's body below the imports)
from datetime import date
import pandas as pd
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.agent import build_converse_registry, build_system_prompt, converse

def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active"),
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))

def _fake_source():
    cal = [date(2026, 6, d) for d in range(10, 14)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def _agent_llm():
    return MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                         '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')

def test_registry_has_both_tools():
    reg = build_converse_registry(_h(), _agent_llm(), _fake_source())
    assert {s["name"] for s in reg.specs()} == {"decide", "propose_memory_edit"}

def test_system_prompt_lists_tools_and_convention():
    reg = build_converse_registry(_h(), _agent_llm(), _fake_source())
    sys = build_system_prompt(_h(), reg)
    assert "decide" in sys and "propose_memory_edit" in sys
    assert '"tool"' in sys

def test_converse_calls_decide_for_date_then_finalizes():
    chat_llm = MockLLMClient(['{"tool": "decide", "args": {"date": "2026-06-12"}}',
                              "My read: RUN looks like a gap-and-go."])
    res = converse(_h(), "what's your read on RUN for 2026-06-12?",
                   agent_llm=_agent_llm(), chat_llm=chat_llm, source=_fake_source())
    assert res.hit_max_iters is False
    assert res.final_text == "My read: RUN looks like a gap-and-go."
    assert [c["tool"] for c in res.tool_calls] == ["decide"]
    assert res.tool_calls[0]["result"].candidates[0].symbol == "RUN"   # DecisionPackage (frozen pydantic; attr access)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_agent.py -v`
Expected: FAIL — `build_converse_registry()` takes 2 positional args (no `source`) / `converse()` has no `source` kwarg.

- [ ] **Step 3: Implement** — edit `alpha/converse/agent.py`:

Replace the imports block + the `_default_state`/`_default_universe`/`build_converse_registry`/`converse` definitions with:

```python
from __future__ import annotations
from alpha.harness.state import HarnessState
from alpha.llm.chat import ChatMessage
from alpha.llm.config import make_client
from alpha.data.registry import make_source
from alpha.converse.registry import ToolRegistry
from alpha.converse.loop import run_conversation, ConversationResult
from alpha.converse.tools import make_decide_for_date_tool, make_gated_write_tool

def build_converse_registry(harness: HarnessState, agent_llm, source) -> ToolRegistry:
    reg = ToolRegistry()
    decide_schema, decide_fn = make_decide_for_date_tool(harness, agent_llm, source)
    reg.register("decide", decide_schema, decide_fn)
    write_schema, write_fn = make_gated_write_tool(harness)
    reg.register("propose_memory_edit", write_schema, write_fn)
    return reg
```

Keep `build_system_prompt` exactly as it is (no change). Replace `converse(...)`:

```python
def converse(harness: HarnessState, user_text: str, *, agent_llm=None, chat_llm=None, source=None,
             max_iters: int = 8) -> ConversationResult:
    agent_llm = agent_llm if agent_llm is not None else make_client("agent")
    chat_llm = chat_llm if chat_llm is not None else make_client("converse")
    source = source if source is not None else make_source()
    registry = build_converse_registry(harness, agent_llm, source)
    system = build_system_prompt(harness, registry)
    return run_conversation(registry, chat_llm, system, [ChatMessage(role="user", text=user_text)],
                            max_iters=max_iters)
```

Delete the now-unused `_default_state()` / `_default_universe()` functions and their `MarketState`/`StockSnapshot`/`CandidateUniverse`/`date`/`datetime` imports.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_agent.py -v`
Expected: 3 PASS — the registry has both tools, the prompt lists them, and the e2e conversation decides for `2026-06-12` (real PIT build over the `FakeSource`) then finalizes.

- [ ] **Step 5: Run the whole suite (no regressions)**

Run: `python -m pytest -q`
Expected: **583 passed** (the prior count) — the Phase-1A `make_decide_tool` test still green (composed, not removed); only the converse e2e changed shape.

- [ ] **Step 6: Commit**

```bash
git add alpha/converse/agent.py tests/converse/test_agent.py
git commit -m "feat(converse): wire the conversational face to a data source (decide-for-date)"
```

---

## Self-Review

**Spec coverage (Phase 1B):**
- `decide` tool builds real state from `(date, source)` instead of the fixed default → Task 1 (`make_decide_for_date_tool`). ✓
- PIT-guarded (`GuardedSource` + `AsOfGuard`, close as_of) → Task 1's chain mirrors `save_decisions.py:59-63`; the test asserts `pkg.as_of == close`. ✓
- The conversational face is wired to a source end-to-end → Task 2 (`build_converse_registry`/`converse` gain `source`; e2e decides for a date over a `FakeSource`). ✓
- Additive: Phase-1A `make_decide_tool` kept + composed → Task 1 delegates to it; its test stays green. ✓
- 583 suite stays green → Task 2 Step 5. ✓

**Placeholder scan:** No "TBD"/"TODO"; every step shows the exact code. The `_fake_source` helper is duplicated across the two test files deliberately (each test module is self-contained; matching the existing `tests/scripts/test_save_decisions.py::_fake` convention — the codebase does not share such fixtures via conftest for these).

**Type consistency:** `make_decide_for_date_tool(harness, agent_llm, source) -> (schema, decide)` (Task 1) is called by `build_converse_registry(harness, agent_llm, source)` (Task 2). `decide(date: str) -> DecisionPackage` matches the e2e's `{"tool":"decide","args":{"date":...}}`. The chain `GuardedSource(source, AsOfGuard(day))`, `build_universe(guarded, day)`, `build_market_state(universe, day, as_of=…)` matches `save_decisions.py:59-63` and the verified signatures (`build_market_state` history/prev_gainers default empty). `converse(…, source=None)` defaults via `make_source()`.
