# Phase 0 — Hermes Vendor-Feasibility Spike — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the "narrow-waist vendor" (Strategy C) is real before committing to it — measure how deeply Hermes's `tools/registry.py` + `hermes_state` couple to the rest of the ~374 MB monolith, and prove a `decide` tool and a gated write tool both route correctly through a minimal tool-calling loop and the **existing** `try_apply_op` gate.

**Architecture:** A throwaway-by-design **spike** living entirely under `spikes/2026-06-26-hermes-vendor-feasibility/`. It does NOT touch the production `alpha/` package or the 555-test suite. Two independent halves: (1) a **static coupling measurement** over a pinned Hermes clone (answers "can we lift the modules?"); (2) an **integration proof** — our own ~40-line registry + turn loop registering two tools backed by the *real* `alpha.agent.LLMAgentPolicy.decide` and `alpha.refine.apply.try_apply_op` (answers "are alpha's capabilities tool-registry-shaped and gate-routable?", and incidentally demonstrates the fallback of reimplementing the registry against Hermes's schema is cheap). The GO/NO-GO combines both.

**Tech Stack:** Python ≥3.11, pytest, `alpha.*` (already importable), `ast` (stdlib, for the import-graph analyzer), `git` (to clone/pin Hermes). No new third-party dependency is added to the project.

## Global Constraints

- **Python `>=3.11`** (project floor). Tests are deterministic: use `MockLLMClient`, never a live LLM.
- **Do NOT modify `alpha/` production code or any file under `tests/`.** The main suite (`python -m pytest -q`, currently **555 passed**) MUST stay green and unchanged throughout.
- **One-gate invariant:** the gated write tool's ONLY path to mutate `H` is `alpha.refine.apply.try_apply_op`. No direct `h.memory`/`h.skills`/`h.doctrine` writes anywhere in the spike.
- **The Hermes clone is NOT committed** (it is ~374 MB) — it lives under `spikes/2026-06-26-hermes-vendor-feasibility/_hermes/` and is gitignored. Only its pinned commit SHA is recorded.
- **Work on a branch** `spike/hermes-vendor-feasibility` (branch off `main`). Commits stay **local** — do not push (push needs explicit user authorization).
- **English** docs/reports (repo convention).
- Spec of record: `docs/superpowers/specs/2026-06-25-evolving-alpha-hermes-rebase-architecture-design.md` (§9 Phase 0).

## File Structure

All paths under `spikes/2026-06-26-hermes-vendor-feasibility/`:

- `README.md` — goal, the pinned Hermes SHA, how to run the spike.
- `_hermes/` — the pinned Hermes clone (gitignored, not committed).
- `conftest.py` — adds the spike dir to `sys.path` so spike tests can `import spike_loop` etc.
- `coupling.py` — AST import-graph analyzer; computes the transitive Hermes-internal import set of each target module and whether `agent/` is dragged in.
- `COUPLING.md` — the analyzer's report (the GO/NO-GO data).
- `spike_loop.py` — minimal `Registry` + `run_turn` (mirrors Hermes's OpenAI-function-calling dispatch contract).
- `decide_tool.py` — `make_decide_tool()` → a registry tool returning a typed `DecisionPackage`.
- `gated_write_tool.py` — `make_gated_write_tool()` → a registry tool routing a `RefineOp` through `try_apply_op`.
- `test_spike_loop.py`, `test_decide_tool.py`, `test_gated_write_tool.py` — the integration proofs.
- `FINDINGS.md` — the GO/NO-GO writeup + the §8 pin-vs-rebase recommendation.

Repo-root change: append `spikes/2026-06-26-hermes-vendor-feasibility/_hermes/` to `.gitignore`.

---

### Task 1: Spike scaffold + pin the Hermes clone

**Files:**
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/README.md`
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/conftest.py`
- Modify: `.gitignore` (append the `_hermes/` ignore line)
- Clone (gitignored): `spikes/2026-06-26-hermes-vendor-feasibility/_hermes/`

**Interfaces:**
- Produces: a pinned Hermes working tree at `spikes/2026-06-26-hermes-vendor-feasibility/_hermes/` containing `tools/registry.py`, `hermes_state.py`, `agent/conversation_loop.py`; the pinned SHA recorded in `README.md`; a `conftest.py` that puts the spike dir on `sys.path`.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/pan/Desktop/self-evolve/evolving-alpha-us
git checkout -b spike/hermes-vendor-feasibility
mkdir -p spikes/2026-06-26-hermes-vendor-feasibility
```

- [ ] **Step 2: Gitignore the clone**

Append this line to `.gitignore`:

```
spikes/2026-06-26-hermes-vendor-feasibility/_hermes/
```

- [ ] **Step 3: Clone and pin Hermes**

```bash
cd spikes/2026-06-26-hermes-vendor-feasibility
git clone --depth 1 https://github.com/NousResearch/hermes-agent _hermes
cd _hermes && git rev-parse HEAD > ../HERMES_SHA.txt && cd ..
cat HERMES_SHA.txt
```

Expected: a 40-char SHA printed. **If `git clone` is blocked by network**, fallback: fetch the three target files individually via `https://raw.githubusercontent.com/NousResearch/hermes-agent/main/<path>` into `_hermes/<path>`, and record the resolved commit SHA from `https://api.github.com/repos/NousResearch/hermes-agent/commits/main`. Note the fallback in `README.md`.

- [ ] **Step 4: Verify the three target files exist**

```bash
ls -la _hermes/tools/registry.py _hermes/hermes_state.py _hermes/agent/conversation_loop.py
```

Expected: all three listed. (If a path differs in the pinned tree, record the actual path in `README.md` and use it in Task 2.)

- [ ] **Step 5: Write `conftest.py`**

```python
# spikes/2026-06-26-hermes-vendor-feasibility/conftest.py
import os, sys
sys.path.insert(0, os.path.dirname(__file__))  # so spike tests can `import spike_loop`, etc.
```

- [ ] **Step 6: Write `README.md`** (goal + pinned SHA + run instructions)

```markdown
# Phase 0 Spike — Hermes vendor feasibility

Pinned Hermes commit: <paste the SHA from HERMES_SHA.txt>
Clone (gitignored): ./_hermes/

Run the integration proof:   python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/ -v
Run the coupling analysis:   python spikes/2026-06-26-hermes-vendor-feasibility/coupling.py

GO/NO-GO and the §8 vendor-tracking recommendation live in FINDINGS.md.
```

- [ ] **Step 7: Confirm the main suite is untouched**

Run: `python -m pytest -q`
Expected: `555 passed` (unchanged — the spike adds nothing to `tests/`).

- [ ] **Step 8: Commit**

```bash
cd /Users/pan/Desktop/self-evolve/evolving-alpha-us
git add .gitignore spikes/2026-06-26-hermes-vendor-feasibility/README.md spikes/2026-06-26-hermes-vendor-feasibility/HERMES_SHA.txt spikes/2026-06-26-hermes-vendor-feasibility/conftest.py
git commit -m "spike(phase0): scaffold + pin Hermes clone for vendor-feasibility"
```

---

### Task 2: Coupling-depth analyzer + report (the GO/NO-GO data)

**Files:**
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/coupling.py`
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/COUPLING.md` (generated, then committed)
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/test_coupling.py`

**Interfaces:**
- Consumes: the pinned `_hermes/` tree from Task 1.
- Produces: `transitive_internal_imports(entry_relpath: str) -> dict` returning `{"reachable": set[str], "drags_agent_pkg": bool, "file_count": int, "loc": int}`; and a written `COUPLING.md`.

- [ ] **Step 1: Write the failing test**

```python
# spikes/2026-06-26-hermes-vendor-feasibility/test_coupling.py
from coupling import transitive_internal_imports

def test_registry_reachability_is_measurable():
    r = transitive_internal_imports("tools/registry.py")
    assert isinstance(r["reachable"], set) and r["file_count"] >= 1
    assert isinstance(r["drags_agent_pkg"], bool)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/test_coupling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'coupling'`.

- [ ] **Step 3: Write `coupling.py`**

```python
# spikes/2026-06-26-hermes-vendor-feasibility/coupling.py
"""Static AST import-graph over the pinned Hermes tree. For an entry module, compute the set of
*Hermes-internal* .py files it transitively imports, whether it reaches the `agent/` package, and
the total file/LOC weight. This is the narrow-waist measurement: a small reachable set that does
NOT drag in `agent/` => Strategy C (vendor the module) is viable for that module."""
from __future__ import annotations
import ast, os

HERMES = os.path.join(os.path.dirname(__file__), "_hermes")

def _module_to_relpath(mod: str) -> str | None:
    """Map a dotted module name to a file under _hermes, if it is Hermes-internal."""
    parts = mod.split(".")
    cand_mod = os.path.join(HERMES, *parts) + ".py"
    cand_pkg = os.path.join(HERMES, *parts, "__init__.py")
    if os.path.isfile(cand_mod):
        return os.path.relpath(cand_mod, HERMES)
    if os.path.isfile(cand_pkg):
        return os.path.relpath(cand_pkg, HERMES)
    return None

def _imports_of(relpath: str) -> set[str]:
    src = open(os.path.join(HERMES, relpath), encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                out.add(n.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out

def transitive_internal_imports(entry_relpath: str) -> dict:
    seen: set[str] = set()
    stack = [entry_relpath]
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.add(rel)
        for mod in _imports_of(rel):
            rp = _module_to_relpath(mod)
            if rp and rp not in seen:
                stack.append(rp)
    loc = sum(sum(1 for _ in open(os.path.join(HERMES, r), errors="replace")) for r in seen)
    return {
        "reachable": seen,
        "drags_agent_pkg": any(r.startswith("agent" + os.sep) or r == "agent.py" for r in seen if r != entry_relpath),
        "file_count": len(seen),
        "loc": loc,
    }

if __name__ == "__main__":
    targets = ["tools/registry.py", "hermes_state.py", "agent/conversation_loop.py"]
    lines = ["# Hermes coupling measurement\n"]
    for t in targets:
        r = transitive_internal_imports(t)
        lines.append(f"## `{t}`\n")
        lines.append(f"- reachable Hermes-internal files: **{r['file_count']}**, total LOC: **{r['loc']}**")
        lines.append(f"- drags in the `agent/` package: **{r['drags_agent_pkg']}**")
        lines.append(f"- verdict: **{'DRAGS MONOLITH' if r['drags_agent_pkg'] else 'liftable'}**\n")
    open(os.path.join(os.path.dirname(__file__), "COUPLING.md"), "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/test_coupling.py -v`
Expected: PASS.

- [ ] **Step 5: Generate the report**

Run: `python spikes/2026-06-26-hermes-vendor-feasibility/coupling.py`
Expected: prints the report and writes `COUPLING.md`. Read it — the load-bearing numbers are `file_count`, `loc`, and `drags_agent_pkg` for `tools/registry.py` and `hermes_state.py`.

- [ ] **Step 6: Commit**

```bash
git add spikes/2026-06-26-hermes-vendor-feasibility/coupling.py spikes/2026-06-26-hermes-vendor-feasibility/test_coupling.py spikes/2026-06-26-hermes-vendor-feasibility/COUPLING.md
git commit -m "spike(phase0): static coupling analyzer + COUPLING.md report"
```

---

### Task 3: Minimal registry + tool-calling turn loop

**Files:**
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/spike_loop.py`
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/test_spike_loop.py`

**Interfaces:**
- Produces: `Registry` with `.register(name: str, schema: dict, fn: Callable)` and `.call(name: str, **kwargs)`; `run_turn(registry: Registry, llm) -> Any` (the llm exposes `.complete(system, user) -> str` returning JSON `{"tool": str, "args": {...}}`). Consumed by Tasks 4 and 5.

- [ ] **Step 1: Write the failing test**

```python
# spikes/2026-06-26-hermes-vendor-feasibility/test_spike_loop.py
from spike_loop import Registry, run_turn
from alpha.llm.client import MockLLMClient

def test_registry_dispatches_one_tool_call():
    reg = Registry()
    reg.register("echo", {"name": "echo"}, lambda msg: f"got:{msg}")
    llm = MockLLMClient('{"tool": "echo", "args": {"msg": "hi"}}')
    assert run_turn(reg, llm) == "got:hi"

def test_unknown_tool_raises():
    import pytest
    reg = Registry()
    llm = MockLLMClient('{"tool": "nope", "args": {}}')
    with pytest.raises(KeyError):
        run_turn(reg, llm)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/test_spike_loop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'spike_loop'`.

- [ ] **Step 3: Write `spike_loop.py`**

```python
# spikes/2026-06-26-hermes-vendor-feasibility/spike_loop.py
"""A ~40-line tool registry + single-turn dispatch loop, mirroring Hermes's OpenAI-function-calling
contract (register a tool with a JSON schema; the model returns one tool call; dispatch it). This is
deliberately tiny: if Hermes's real tools/registry.py lifts cleanly (Task 2), swap this for it; if it
drags the monolith, this IS the fallback reimplementation."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class Tool:
    name: str
    schema: dict
    fn: Callable[..., Any]

@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)
    def register(self, name: str, schema: dict, fn: Callable[..., Any]) -> None:
        self.tools[name] = Tool(name, schema, fn)
    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self.tools:
            raise KeyError(f"unknown tool: {name}")
        return self.tools[name].fn(**kwargs)

def run_turn(registry: Registry, llm) -> Any:
    """One tool-calling turn. `llm.complete(system, user)` returns JSON {"tool": name, "args": {...}}."""
    call = json.loads(llm.complete("You may call one registered tool.", ""))
    return registry.call(call["tool"], **call.get("args", {}))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/test_spike_loop.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add spikes/2026-06-26-hermes-vendor-feasibility/spike_loop.py spikes/2026-06-26-hermes-vendor-feasibility/test_spike_loop.py
git commit -m "spike(phase0): minimal registry + tool-calling turn loop"
```

---

### Task 4: The `decide` tool → typed `DecisionPackage`

**Files:**
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/decide_tool.py`
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/test_decide_tool.py`

**Interfaces:**
- Consumes: `Registry` (Task 3); `alpha.agent.agent.LLMAgentPolicy.decide(state, universe) -> DecisionPackage`.
- Produces: `make_decide_tool(harness, agent_llm) -> tuple[dict, Callable]` — the schema + a `decide(state, universe) -> DecisionPackage` callable to register.

- [ ] **Step 1: Write the failing test** (state/universe/harness built exactly as `tests/agent/test_agent.py`)

```python
# spikes/2026-06-26-hermes-vendor-feasibility/test_decide_tool.py
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
from spike_loop import Registry
from decide_tool import make_decide_tool

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

def test_decide_tool_returns_typed_package_through_registry():
    agent_llm = MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                              '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    schema, decide = make_decide_tool(_h(), agent_llm)
    reg = Registry()
    reg.register("decide", schema, decide)
    pkg = reg.call("decide", state=_state(), universe=_uni())
    assert isinstance(pkg, DecisionPackage)
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
    assert pkg.regime_read == "trend frontside"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/test_decide_tool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'decide_tool'`.

- [ ] **Step 3: Write `decide_tool.py`**

```python
# spikes/2026-06-26-hermes-vendor-feasibility/decide_tool.py
"""Expose the EXISTING deterministic decider as a registry tool. The whole point of decision (a):
one implementation of `decide`, two callers (the offline InnerLoop and this conversational tool).
The tool returns the strongly-typed DecisionPackage unchanged — NOT free text (decision b)."""
from __future__ import annotations
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse
from alpha.eval.decision import DecisionPackage

def make_decide_tool(harness, agent_llm):
    def decide(state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return LLMAgentPolicy(harness, agent_llm).decide(state, universe)
    schema = {
        "name": "decide",
        "description": "Run the deterministic decider; returns a typed DecisionPackage.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
    return schema, decide
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/test_decide_tool.py -v`
Expected: PASS — a registered tool returned a typed `DecisionPackage` with candidate `RUN`.

- [ ] **Step 5: Commit**

```bash
git add spikes/2026-06-26-hermes-vendor-feasibility/decide_tool.py spikes/2026-06-26-hermes-vendor-feasibility/test_decide_tool.py
git commit -m "spike(phase0): decide tool returns a typed DecisionPackage through the registry"
```

---

### Task 5: The gated write tool → `try_apply_op`

**Files:**
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/gated_write_tool.py`
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/test_gated_write_tool.py`

**Interfaces:**
- Consumes: `alpha.refine.apply.try_apply_op`, `alpha.refine.ops.{RefineOp, PASS_TOOLS}`, `alpha.harness.metatools.MetaTools`, `alpha.harness.edit_log.EditLog`.
- Produces: `make_gated_write_tool(harness, *, min_retire_samples=5, min_promote_samples=3) -> tuple[dict, Callable]`; the callable signature is `propose_memory_edit(tool: str, args: dict, rationale: str) -> dict` returning `{"status": "applied"}` or `{"status": "rejected", "reason": str}`.

- [ ] **Step 1: Write the failing tests**

```python
# spikes/2026-06-26-hermes-vendor-feasibility/test_gated_write_tool.py
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from gated_write_tool import make_gated_write_tool

def _h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))

def test_gated_write_applies_a_valid_memory_op():
    h = _h()
    _schema, propose = make_gated_write_tool(h)
    out = propose(tool="process_memory",
                  args={"lesson_id": "spike-mem-1", "phases": ["trend"],
                        "outcome": "win", "lesson": "spike: gate routing works"},
                  rationale="prove the gated write path")
    assert out["status"] == "applied"
    assert any(l.lesson_id == "spike-mem-1" for l in h.memory.all())   # H actually mutated, via the gate

def test_gated_write_rejects_a_non_whitelisted_op():
    h = _h()
    _schema, propose = make_gated_write_tool(h)
    out = propose(tool="rewrite_doctrine",
                  args={"section": "x", "new_guidance": "y"},
                  rationale="should be blocked — not in the M whitelist")
    assert out["status"] == "rejected"
    assert out["reason"]                                  # a non-empty gate reason
    assert h.memory.all() == [] or all(l.lesson_id != "x" for l in h.memory.all())
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/test_gated_write_tool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gated_write_tool'`.

- [ ] **Step 3: Write `gated_write_tool.py`**

```python
# spikes/2026-06-26-hermes-vendor-feasibility/gated_write_tool.py
"""A registry tool whose ONLY way to mutate H is the existing one-write-waist try_apply_op. Proves
Strategy C's invariant survives the re-base: a Hermes-style tool call cannot bypass the gate. The
restricted whitelist (PASS_TOOLS['M']) is the literal mechanism the spec's fast self-study tier uses;
here it just proves routing + whitelist + reject-reason all work from a tool call."""
from __future__ import annotations
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp, PASS_TOOLS

def make_gated_write_tool(harness, *, min_retire_samples: int = 5, min_promote_samples: int = 3):
    def propose_memory_edit(tool: str, args: dict, rationale: str) -> dict:
        op = RefineOp(tool=tool, args=args, rationale=rationale)
        rec, reason = try_apply_op(
            MetaTools(harness, EditLog()), harness, op,
            allowed=PASS_TOOLS["M"],
            min_retire_samples=min_retire_samples,
            min_promote_samples=min_promote_samples,
        )
        return {"status": "applied"} if rec is not None else {"status": "rejected", "reason": reason}
    schema = {
        "name": "propose_memory_edit",
        "description": "Propose a memory edit; applied only if it clears the gate (try_apply_op).",
        "parameters": {"type": "object",
                       "properties": {"tool": {"type": "string"}, "args": {"type": "object"},
                                      "rationale": {"type": "string"}},
                       "required": ["tool", "args", "rationale"]},
    }
    return schema, propose_memory_edit
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/test_gated_write_tool.py -v`
Expected: 2 PASS — a valid op is applied (H mutated through the gate), a non-whitelisted op is rejected with a reason.

- [ ] **Step 5: Run the whole spike suite + confirm the main suite is still green**

Run: `python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/ -v && python -m pytest -q`
Expected: all spike tests PASS; main suite still `555 passed`.

- [ ] **Step 6: Commit**

```bash
git add spikes/2026-06-26-hermes-vendor-feasibility/gated_write_tool.py spikes/2026-06-26-hermes-vendor-feasibility/test_gated_write_tool.py
git commit -m "spike(phase0): gated write tool routes a RefineOp through try_apply_op (one-gate invariant)"
```

---

### Task 6: GO/NO-GO writeup + §8 vendor-tracking decision

**Files:**
- Create: `spikes/2026-06-26-hermes-vendor-feasibility/FINDINGS.md`

**Interfaces:**
- Consumes: `COUPLING.md` (Task 2) + the integration proofs (Tasks 3–5).
- Produces: a clear GO/NO-GO for Strategy C and a concrete §8 recommendation (hard-pin vs periodic rebase), consumed by the human before Phase 1 starts.

- [ ] **Step 1: Re-read the evidence**

Run: `cat spikes/2026-06-26-hermes-vendor-feasibility/COUPLING.md` and confirm Tasks 3–5 tests are green (`python -m pytest spikes/2026-06-26-hermes-vendor-feasibility/ -q`).

- [ ] **Step 2: Write `FINDINGS.md`** using this exact skeleton, filling each bracketed slot from the measured evidence (no slot left bracketed):

```markdown
# Phase 0 Findings — Hermes vendor feasibility

Pinned Hermes SHA: [from HERMES_SHA.txt]

## Vendorability (from COUPLING.md)
| target | reachable files | LOC | drags `agent/`? | verdict |
|---|---|---|---|---|
| tools/registry.py | [n] | [loc] | [bool] | [liftable / drags-monolith] |
| hermes_state.py | [n] | [loc] | [bool] | [liftable / drags-monolith] |
| agent/conversation_loop.py | [n] | [loc] | [bool] | [liftable / drags-monolith] |

## Integration proof (Tasks 3–5)
- registry + turn loop: [PASS/FAIL]
- decide tool returns a typed DecisionPackage through the registry: [PASS/FAIL]
- gated write tool routes through try_apply_op (applied + rejected): [PASS/FAIL]

## GO / NO-GO for Strategy C (narrow-waist vendor)
[GO if registry + hermes_state are liftable (do NOT drag agent/) AND all integration proofs pass.
 NO-GO/fallback if registry/hermes_state drag the monolith — then: reimplement the registry against
 Hermes's tool *schema* (the spike's own spike_loop.py is that fallback, already proven) and vendor
 only the leaf hermes_state if it is clean. State which.]

## §8 vendor-tracking recommendation
[Hard-pin the SHA above if coupling is deep or the reachable set is large/volatile (manual bumps);
 periodic rebase only if the reachable set is small AND stable. Justify from the file/LOC counts.]

## What Phase 1 should vendor vs reimplement
[Per-module disposition, grounded in the table above.]
```

- [ ] **Step 3: Commit**

```bash
git add spikes/2026-06-26-hermes-vendor-feasibility/FINDINGS.md
git commit -m "spike(phase0): GO/NO-GO findings + §8 vendor-tracking recommendation"
```

- [ ] **Step 4: Surface the decision to the user**

Report the GO/NO-GO + the §8 recommendation. **Do not start Phase 1** — the human decides whether Strategy C is confirmed (proceed to Phase 1) or the fallback is taken (revise the spec's §8 + Phase 1 boundary first).

---

## Self-Review

**Spec coverage (§9 Phase 0):**
- "extract registry + hermes_state + minimal loop" → Tasks 2 (measure liftability of registry/hermes_state) + 3 (minimal loop). ✓
- "demonstrate a `decide` tool and a gated write tool both routing through `try_apply_op`" → Tasks 4 + 5. ✓ (decide returns a typed package; the write tool routes through the gate.)
- "without dragging in the whole `agent/` monolith" → Task 2's `drags_agent_pkg` flag. ✓
- "vendored module set + transitive imports enumerated; coupling depth measured" → Task 2 `COUPLING.md`. ✓
- "Fallback if deep coupling … reimplement registry against the schema" → Task 6 records it; `spike_loop.py` (Task 3) IS that reimplementation, already proven. ✓
- "Decide the upstream-tracking policy (§8) here" → Task 6 §8 section. ✓

**Placeholder scan:** Task 6's `FINDINGS.md` uses bracketed slots, but Step 2 explicitly requires every slot filled from measured evidence (it is a fill-in template, not a deliverable placeholder). No code step contains a placeholder — all code is complete and uses verified `alpha` signatures.

**Type consistency:** `Registry.register(name, schema, fn)` / `.call(name, **kwargs)` and `run_turn(registry, llm)` are used identically in Tasks 3–5. `make_decide_tool(harness, agent_llm) -> (schema, decide)` and `make_gated_write_tool(harness, ...) -> (schema, propose_memory_edit)` match their call sites. `try_apply_op(meta, harness, op, *, allowed, min_retire_samples, min_promote_samples) -> (EditRecord|None, str|None)` matches `alpha/refine/apply.py:66`. Valid `process_memory` args (`lesson_id/phases/outcome/lesson`) match `tests/harness/test_metatools.py:55`.
