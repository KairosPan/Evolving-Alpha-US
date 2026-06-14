# US-2a LLM Clients + Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the LLM into the loop — a provider-agnostic `LLMClient` layer (Mock / Claude / OpenAI-compatible) with per-role config, and the `LLMAgentPolicy` (the "act" half-loop) that wraps the harness `H`, reads a `MarketState` + `CandidateUniverse`, and emits a `DecisionPackage`, with hallucination defense.

**Architecture:** `LLMClient` is a one-method protocol (`complete(system, user) -> str`). `MockLLMClient` (offline tests) replays scripted JSON; `ClaudeClient` / `OpenAICompatClient` are smoke-only real adapters with retry/backoff + lazy SDK import + injectable transport (so retry is testable offline without keys). `config.make_client(role)` picks the provider+model per role from env (agent cheap, refiner Claude; `mock` for tests; temp=0 for eval determinism). The agent **holds the harness, not a pre-rendered prompt** — each `decide()` rebuilds the system prompt from the *current* `H` (so the US-2b Refiner's edits are immediately visible), retrieves a budgeted slice of skills/memory by phase (family-aware retrieval deferred — US-2a has no per-line/family signal yet), renders state+universe into the user prompt, and `parse_decision` robustly extracts JSON and **drops hallucinated/duplicate symbols, re-anchoring to the universe** (malformed → no-trade).

**Tech Stack:** Python ≥3.11, pydantic v2, pytest; `anthropic` + `openai` SDKs as the optional `live` extra (offline tests use `MockLLMClient` + injected transports). No network in tests.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (§8 per-role LLM; §4 agent / master-dispatch; §0 co-pilot human-confirmed). Sub-plan **US-2a** of US-2 (first; before 2b Refiner, 2c inner loop, 2d compare). The agent produces the action `a_t`; the Refiner that *edits* `H` is US-2b.

**Scope boundary (US-2a only):** LLM clients + per-role config + the agent (retrieval/prompt/parse/policy). **Deferred:** the **record/replay `CachedLLMClient`** (golden-run determinism) → a later US-2 sub-plan when real-run replay is needed for the compare (MockLLM suffices for US-2a tests); **wiring sizing(L3)/guard(L4) into the DecisionPackage** (size_tier/fill_feasibility/taboo_check population) → US-2c inner loop (US-2a's agent fills the core candidate fields — symbol/pattern/reason/confidence + regime_read); the **Refiner** → US-2b; **master-dispatch + named G sub-agents** (spec §4 / §US-2) → collapsed to a single orchestrating agent for v1 — a deliberate REDUCTION of the spec (not merely a later enhancement), auditable against §4; the dispatch refinement is a later US-2 enhancement. **Reused:** US-1 `HarnessState`/`Skill`/`Lesson`/`Doctrine`, `MarketState`, `CandidateUniverse`, `DecisionPolicy`/`Candidate`/`DecisionPackage` (eval/decision.py), `normalize_phase`/`is_family`/`CANONICAL_PHASES` (harness/regime.py), `default_us_cycle` (regime/cycle.py).

**Conventions:** all code/comments English; `from __future__ import annotations` at top of every module; commit after every passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. `MockLLMClient` records every `(system, user)` call and replays scripted responses (deterministic offline).
2. Real clients retry with exponential backoff on transient errors and re-raise after exhaustion — verified offline with an injected failing transport + injected `sleep` (no real network/keys).
3. `make_client(role)` selects provider+model per env, defaults agent→cheap / refiner→Claude, returns a `MockLLMClient` for `provider=mock`, and raises on an unknown provider.
4. The agent rebuilds the prompt from the *current* `H` each `decide()` (default `injection="retrieval"`: a budgeted, phase-prior-ordered slice — the spec's intent as `H` grows; `"full"` is an opt-in debug path); `parse_decision` drops symbols not in the universe and duplicates, clamps confidence to [0,1], and returns a no-trade package on malformed output (firewall: the agent only ever sees `(state, universe)`, never the source).
5. The agent threads only a CANONICAL phase as `phase_prior` — extracted from its prior `regime_read` (the output contract makes that a multi-token string like `trend frontside`, which `normalize_phase` alone maps to `None`) — and stamps `DecisionPackage.as_of = state.as_of` on every decision, incl. no-trade (the inference-path timestamp the §4.1 schema assigns to the agent).

---

### Task 1: LLM client protocol + Mock + JSON extractor

**Files:**
- Create: `alpha/llm/__init__.py`
- Create: `alpha/llm/client.py`
- Create: `alpha/llm/extract.py`
- Create: `tests/llm/__init__.py`
- Create: `tests/llm/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/__init__.py
```

```python
# tests/llm/test_client.py
import pytest
from alpha.llm.client import LLMClient, MockLLMClient
from alpha.llm.extract import extract_json_object


def test_mock_records_and_replays():
    m = MockLLMClient(['{"a": 1}', '{"b": 2}'])
    assert m.complete("sys1", "usr1") == '{"a": 1}'
    assert m.complete("sys2", "usr2") == '{"b": 2}'
    assert m.complete("sys3", "usr3") == '{"b": 2}'           # past the end -> last response repeats
    assert m.calls == [("sys1", "usr1"), ("sys2", "usr2"), ("sys3", "usr3")]
    assert isinstance(m, LLMClient)                            # satisfies the runtime-checkable protocol


def test_mock_empty_rejected():
    with pytest.raises(ValueError):
        MockLLMClient([])


def test_extract_json_object():
    assert extract_json_object('prose {"x": 1} tail') == '{"x": 1}'
    assert extract_json_object('```json\n{"x": {"y": 2}}\n```') == '{"x": {"y": 2}}'
    assert extract_json_object('a string with } brace then {"ok": "}"}') == '{"ok": "}"}'
    assert extract_json_object("no json here") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/llm/test_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.llm'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/llm/__init__.py
```

```python
# alpha/llm/client.py
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Minimal LLM interface: given system/user prompts, return text (expected to be a JSON string)."""
    def complete(self, system: str, user: str) -> str: ...


class MockLLMClient:
    """Offline test client: replays scripted responses and records every (system, user) call."""

    def __init__(self, scripted: "str | list[str]") -> None:
        self._responses: list[str] = [scripted] if isinstance(scripted, str) else list(scripted)
        if not self._responses:
            raise ValueError("scripted must be non-empty")
        self._i = 0
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r
```

```python
# alpha/llm/extract.py
from __future__ import annotations


def extract_json_object(raw: str) -> str | None:
    """Return the first BALANCED JSON object substring from text that may contain prose / markdown
    fences / thinking prefixes. Scans to the first '{', balances by brace depth; braces inside string
    literals don't count (respecting \\ escapes). Returns None if no balanced object is found."""
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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/llm/test_client.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/__init__.py alpha/llm/client.py alpha/llm/extract.py tests/llm/__init__.py tests/llm/test_client.py
git commit -m "US-2a Task 1: LLM client protocol + MockLLMClient + JSON extractor"
```

---

### Task 2: OpenAI-compatible client (cheap; retry/backoff)

**Files:**
- Create: `alpha/llm/openai_compat.py`
- Create: `tests/llm/test_openai_compat.py`
- Modify: `pyproject.toml` (add `openai>=1.0` to the `live` optional-dependency extra)

Real adapter (DeepSeek/OpenAI base_url), smoke-only — but retry/backoff is tested offline via an injected fake transport + injected `sleep`. The SDK is a lazy import, so the offline suite needs no install; add `openai>=1.0` to the `live` extra in `pyproject.toml` so `pip install -e ".[live]"` enables the real smoke path.

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_openai_compat.py
import pytest
from alpha.llm.openai_compat import OpenAICompatClient


class _FakeResp:
    def __init__(self, text): self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]


class _FakeChat:
    """Fails `fail_n` times then returns the text (exercises retry/backoff)."""
    def __init__(self, text, fail_n=0):
        self._text, self._fail_n, self.calls = text, fail_n, 0
        self.chat = type("X", (), {"completions": self})()
    def create(self, **kw):
        self.calls += 1
        if self.calls <= self._fail_n:
            raise RuntimeError("transient 503")
        return _FakeResp(self._text)


def _client(fake, sleeps):
    c = OpenAICompatClient(model="deepseek-chat", api_key="test", backoff=0.0,
                           sleep=lambda s: sleeps.append(s))
    c._client = fake                       # inject transport (no network)
    return c


def test_returns_content():
    fake = _FakeChat('{"ok": 1}')
    assert _client(fake, []).complete("s", "u") == '{"ok": 1}'


def test_retries_then_succeeds():
    fake = _FakeChat('{"ok": 1}', fail_n=2)
    sleeps = []
    assert _client(fake, sleeps).complete("s", "u") == '{"ok": 1}'
    assert fake.calls == 3 and len(sleeps) == 2          # 2 retries before success


def test_raises_after_exhaustion():
    fake = _FakeChat('{"ok": 1}', fail_n=99)
    with pytest.raises(RuntimeError):
        _client(fake, []).complete("s", "u")


def test_exposes_model_and_temperature_for_cache_key():
    c = OpenAICompatClient(model="deepseek-chat", api_key="test", temperature=0.0)
    assert c.model == "deepseek-chat" and c.temperature == 0.0


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)   # session-safe; pytest auto-restores
    with pytest.raises(RuntimeError):
        OpenAICompatClient(model="deepseek-chat", api_key=None, api_key_env="DEEPSEEK_API_KEY")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/llm/test_openai_compat.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.llm.openai_compat'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/llm/openai_compat.py
from __future__ import annotations

import os
import time


class OpenAICompatClient:
    """OpenAI-compatible client (DeepSeek by default; any base_url). Smoke-only for real calls.

    Retry/backoff on transient errors; re-raises after exhaustion (the caller/loop decides the
    no-trade fallback — this class does not swallow). `sleep` is injectable for offline tests.
    `model`/`temperature` are public for the (future) cache key.
    """

    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None,
                 api_key_env: str = "DEEPSEEK_API_KEY", base_url: str = "https://api.deepseek.com",
                 temperature: float = 0.0, max_retries: int = 3, backoff: float = 1.0,
                 sleep=None) -> None:
        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"missing {api_key_env}")
        try:
            from openai import OpenAI  # lazy
            self._client = OpenAI(api_key=key, base_url=base_url)
        except ImportError:
            self._client = None        # openai not installed (offline tests inject _client)
        self.model = model
        self.temperature = temperature
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep

    def complete(self, system: str, user: str) -> str:
        if self._client is None:
            raise RuntimeError("openai not installed (pip install openai)")
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    temperature=self.temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:           # noqa: BLE001 — transient (network/rate/5xx): back off
                last = e
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                else:
                    raise
        raise last  # pragma: no cover
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/llm/test_openai_compat.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/openai_compat.py tests/llm/test_openai_compat.py pyproject.toml
git commit -m "US-2a Task 2: OpenAI-compatible client (cheap; retry/backoff; injectable transport)"
```

---

### Task 3: Claude client (Anthropic; retry/backoff)

**Files:**
- Create: `alpha/llm/anthropic.py`
- Create: `tests/llm/test_anthropic.py`
- Modify: `pyproject.toml` (add `anthropic>=0.40` to the `live` optional-dependency extra)

Claude returns text; the agent's `parse_decision` extracts JSON (Claude has no `response_format=json_object`, so the prompt asks for JSON and the extractor handles it). Retry/backoff + injectable transport. Lazy import (offline suite needs no install); add `anthropic>=0.40` to the `live` extra in `pyproject.toml`.

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_anthropic.py
import pytest
from alpha.llm.anthropic import ClaudeClient


class _Block:
    def __init__(self, text): self.text = text


class _Msg:
    def __init__(self, text): self.content = [_Block(text)]


class _FakeMessages:
    def __init__(self, text, fail_n=0):
        self._text, self._fail_n, self.calls = text, fail_n, 0
        self.messages = self
    def create(self, **kw):
        self.calls += 1
        if self.calls <= self._fail_n:
            raise RuntimeError("overloaded")
        return _Msg(self._text)


def _client(fake, sleeps):
    c = ClaudeClient(model="claude-sonnet-4-6", api_key="test", backoff=0.0,
                     sleep=lambda s: sleeps.append(s))
    c._client = fake
    return c


def test_returns_text():
    assert _client(_FakeMessages('{"ok": 1}'), []).complete("s", "u") == '{"ok": 1}'


def test_retries_then_succeeds():
    fake = _FakeMessages('{"ok": 1}', fail_n=2)
    sleeps = []
    assert _client(fake, sleeps).complete("s", "u") == '{"ok": 1}'
    assert fake.calls == 3 and len(sleeps) == 2


def test_raises_after_exhaustion():
    with pytest.raises(RuntimeError):
        _client(_FakeMessages('{"ok": 1}', fail_n=99), []).complete("s", "u")


def test_exposes_model_and_temperature():
    c = ClaudeClient(model="claude-sonnet-4-6", api_key="test", temperature=0.0)
    assert c.model == "claude-sonnet-4-6" and c.temperature == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/llm/test_anthropic.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.llm.anthropic'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/llm/anthropic.py
from __future__ import annotations

import os
import time


class ClaudeClient:
    """Anthropic Claude client. Smoke-only for real calls; retry/backoff; injectable transport.

    Claude has no OpenAI-style json_object mode, so the system prompt asks for raw JSON and the
    agent's extractor pulls the balanced object. `model`/`temperature` are public for the cache key.
    """

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None,
                 api_key_env: str = "ANTHROPIC_API_KEY", temperature: float = 0.0,
                 max_tokens: int = 4096, max_retries: int = 3, backoff: float = 1.0,
                 sleep=None) -> None:
        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"missing {api_key_env}")
        try:
            import anthropic  # lazy
            self._client = anthropic.Anthropic(api_key=key)
        except ImportError:
            self._client = None        # anthropic not installed (offline tests inject _client)
        self.model = model
        self.temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep if sleep is not None else time.sleep

    def complete(self, system: str, user: str) -> str:
        if self._client is None:
            raise RuntimeError("anthropic not installed (pip install anthropic)")
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                msg = self._client.messages.create(
                    model=self.model, max_tokens=self._max_tokens, temperature=self.temperature,
                    system=system, messages=[{"role": "user", "content": user}],
                )
                parts = [b.text for b in msg.content if getattr(b, "text", None)]
                return "".join(parts)
            except Exception as e:           # noqa: BLE001 — transient: back off
                last = e
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                else:
                    raise
        raise last  # pragma: no cover
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/llm/test_anthropic.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/anthropic.py tests/llm/test_anthropic.py pyproject.toml
git commit -m "US-2a Task 3: Claude client (Anthropic; retry/backoff; injectable transport)"
```

---

### Task 4: Per-role LLM config

**Files:**
- Create: `alpha/llm/config.py`
- Create: `tests/llm/test_config.py`

`make_client(role)` resolves provider+model per env. Defaults: agent → cheap (`openai_compat`/deepseek), refiner → Claude. `mock` returns a `MockLLMClient` (offline). temp=0 for eval determinism.

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_config.py
import pytest
from alpha.llm.client import MockLLMClient
from alpha.llm.config import make_client


def test_mock_provider(monkeypatch):
    monkeypatch.setenv("ALPHA_AGENT_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"no_trade_reason": "mock"}')
    c = make_client("agent")
    assert isinstance(c, MockLLMClient)
    assert c.complete("s", "u") == '{"no_trade_reason": "mock"}'


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        make_client("refiner")


def test_provider_selects_class_without_keys(monkeypatch):
    # provider=mock for both roles -> offline-safe; assert role-scoped env is read
    monkeypatch.setenv("ALPHA_AGENT_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    assert isinstance(make_client("agent"), MockLLMClient)
    assert isinstance(make_client("refiner"), MockLLMClient)


def test_bad_role_raises():
    with pytest.raises(ValueError):
        make_client("nonsense")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/llm/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.llm.config'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/llm/config.py
from __future__ import annotations

import os
from typing import Literal

from alpha.llm.client import LLMClient, MockLLMClient

Role = Literal["agent", "refiner"]

# (provider, model) defaults per role: agent cheap (many rollouts), refiner Claude (edits H).
_DEFAULTS: dict[str, tuple[str, str]] = {
    "agent": ("openai_compat", "deepseek-chat"),
    "refiner": ("anthropic", "claude-sonnet-4-6"),
}


def make_client(role: Role) -> LLMClient:
    """Build the LLM client for a role from env (ALPHA_<ROLE>_PROVIDER / _MODEL).

    providers: 'mock' (offline), 'anthropic' (ClaudeClient), 'openai_compat' (OpenAICompatClient).
    temperature defaults to 0.0 (eval determinism); override with ALPHA_LLM_TEMPERATURE.
    """
    if role not in _DEFAULTS:
        raise ValueError(f"unknown role: {role!r} (expected one of {sorted(_DEFAULTS)})")
    def_provider, def_model = _DEFAULTS[role]
    provider = os.environ.get(f"ALPHA_{role.upper()}_PROVIDER", def_provider)
    model = os.environ.get(f"ALPHA_{role.upper()}_MODEL", def_model)
    temperature = float(os.environ.get("ALPHA_LLM_TEMPERATURE", "0"))

    if provider == "mock":
        return MockLLMClient(os.environ.get("ALPHA_MOCK_RESPONSE", "{}"))
    if provider == "anthropic":
        from alpha.llm.anthropic import ClaudeClient
        return ClaudeClient(model=model, temperature=temperature)
    if provider == "openai_compat":
        from alpha.llm.openai_compat import OpenAICompatClient
        return OpenAICompatClient(model=model, temperature=temperature)
    raise ValueError(f"unknown provider: {provider!r} (expected mock|anthropic|openai_compat)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/llm/test_config.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/config.py tests/llm/test_config.py
git commit -m "US-2a Task 4: per-role LLM config (agent cheap / refiner Claude; mock for tests)"
```

---

### Task 5: Retrieval (budgeted skill/memory selection)

**Files:**
- Create: `alpha/agent/__init__.py`
- Create: `alpha/agent/retrieval.py`
- Create: `tests/agent/__init__.py`
- Create: `tests/agent/test_retrieval.py`

Select a budgeted slice of `H` to inject: active skills (phase-prior hit first, then by stats), incubating trial slots, and lessons by importance weight. Pure + deterministic. (Family-aware retrieval — the spec's seed→filter→retrieval family flow — is deferred: US-2a has no per-line/family signal to key on yet.)

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/__init__.py
```

```python
# tests/agent/test_retrieval.py
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.memory import Lesson, Importance
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.agent.retrieval import select_for_prompt


def _skill(sid, status="active", phases=("trend",), n=0, family="runner"):
    return Skill(skill_id=sid, name=sid, type="pattern", family=family, phases=list(phases),
                 status=status, stats=SkillStats(n=n))


def _h():
    skills = SkillRegistry.from_skills([
        _skill("hit", phases=["trend"], n=1), _skill("miss", phases=["washout"], n=9),
        _skill("inc", status="incubating"),
    ])
    memory = MemoryStore.from_lessons([
        Lesson(lesson_id="strong", phases=["trend"], outcome="principle", lesson="x",
               importance=Importance(base=1.0)),
        Lesson(lesson_id="weak", phases=["trend"], outcome="loss", lesson="y",
               importance=Importance(base=0.05)),     # below MIN_MEMORY_WEIGHT -> dropped
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=memory)


def test_phase_hit_ranked_first():
    sel = select_for_prompt(_h(), phase_prior="trend", skill_budget=5)
    assert [s.skill_id for s in sel.skills] == ["hit", "miss"]   # 'hit' matches phase, ranked first
    assert [s.skill_id for s in sel.trials] == ["inc"]           # incubating -> trial slot
    assert [l.lesson_id for l in sel.lessons] == ["strong"]      # weak lesson dropped (low weight)


def test_budget_truncates():
    sel = select_for_prompt(_h(), phase_prior="trend", skill_budget=1)
    assert len(sel.skills) == 1 and sel.skills[0].skill_id == "hit"


def test_no_phase_prior_falls_back_to_stats():
    sel = select_for_prompt(_h(), phase_prior=None, skill_budget=5)
    # no phase hit dimension -> order by stats.n desc: 'miss' (n=9) before 'hit' (n=1)
    assert [s.skill_id for s in sel.skills] == ["miss", "hit"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/test_retrieval.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.agent'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/agent/__init__.py
```

```python
# alpha/agent/retrieval.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.memory import Lesson
from alpha.harness.regime import normalize_phase
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState

DEFAULT_SKILL_BUDGET = 16
DEFAULT_MEMORY_BUDGET = 10
DEFAULT_TRIAL_SLOTS = 3
MIN_MEMORY_WEIGHT = 0.15     # lessons below this weight aren't rendered (demote takes effect at once)


class Selection(BaseModel):
    """Budgeted prompt-injection selection (frozen; members are read-only refs into H)."""
    model_config = ConfigDict(frozen=True)
    skills: list[Skill] = Field(default_factory=list)
    trials: list[Skill] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)


def select_for_prompt(h: HarnessState, *, phase_prior: str | None,
                      skill_budget: int = DEFAULT_SKILL_BUDGET,
                      memory_budget: int = DEFAULT_MEMORY_BUDGET,
                      trial_slots: int = DEFAULT_TRIAL_SLOTS) -> Selection:
    """Pick the skills/trials/lessons to inject (pure, deterministic, read-only).

    skills: active, ranked (phase-prior hit first, then stats.n desc, then skill_id), top skill_budget.
    trials: incubating, newest-first (registry insertion order reversed), top trial_slots.
    lessons: importance.weight() >= MIN_MEMORY_WEIGHT, by (weight desc, lesson_id), top memory_budget.
    """
    canon = normalize_phase(phase_prior) if phase_prior else None

    def _hit(s: Skill) -> bool:
        return canon is not None and (s.applies_all_phases or canon in s.phases)

    actives = sorted(h.skills.by_status("active"),
                     key=lambda s: (not _hit(s), -s.stats.n, s.skill_id))
    trials = list(reversed(h.skills.by_status("incubating")))[:trial_slots]
    lessons = sorted((l for l in h.memory.all() if l.importance.weight() >= MIN_MEMORY_WEIGHT),
                     key=lambda l: (-l.importance.weight(), l.lesson_id))
    return Selection(skills=actives[:skill_budget], trials=trials, lessons=lessons[:memory_budget])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/test_retrieval.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/__init__.py alpha/agent/retrieval.py tests/agent/__init__.py tests/agent/test_retrieval.py
git commit -m "US-2a Task 5: retrieval (budgeted skill/memory selection by phase-prior)"
```

---

### Task 6: Prompt rendering (system + user + output contract)

**Files:**
- Create: `alpha/agent/prompt.py`
- Create: `tests/agent/test_prompt.py`

`build_system_prompt(h, ...)` renders the doctrine (p) + selected skills/trials (K) + lessons (M) + the 6-state cycle vocabulary + the strict JSON output contract. `build_user_prompt(state, universe)` renders the day's state + candidate universe.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_prompt.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.agent.prompt import build_system_prompt, build_user_prompt, PROMPT_FINGERPRINT


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="gap + hold", entry="ORB reclaim", exit_stop="lose VWAP",
              status="active"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "respect the stop"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_system_prompt_contains_skill_doctrine_contract():
    sp = build_system_prompt(_h(), phase_prior="trend")
    assert "gap_and_go" in sp and "respect the stop" in sp
    assert "washout" in sp and "flush" in sp          # the 6-state cycle vocabulary
    assert '"candidates"' in sp and '"symbol"' in sp  # the JSON output contract
    assert isinstance(PROMPT_FINGERPRINT, str) and PROMPT_FINGERPRINT


def test_user_prompt_renders_state_and_universe():
    state = MarketState(date=date(2026, 6, 12), gainer_count=2, gap_up_count=1, loser_count=1,
                        failed_breakout_count=0, max_runner_tier=2, echelon=[], breadth_raw=1.0,
                        sentiment_norm=0.6, as_of=datetime(2026, 6, 12, 16, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="RUN", name="Runner", status="gainer", pct_change=30.0, rvol=4.0),
    ])
    up = build_user_prompt(state, uni)
    assert "2026-06-12" in up and "RUN" in up and "gainer" in up
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/test_prompt.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.agent.prompt'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/agent/prompt.py
from __future__ import annotations

from alpha.agent.retrieval import (
    DEFAULT_MEMORY_BUDGET, DEFAULT_SKILL_BUDGET, DEFAULT_TRIAL_SLOTS, select_for_prompt,
)
from alpha.harness.regime import CANONICAL_PHASES
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse

# Bump when the prompt template changes (used by the future LLM cache key to invalidate old records).
PROMPT_FINGERPRINT = "us2a-v1"

_OUTPUT_CONTRACT = (
    'Output STRICT JSON (no markdown fences): '
    '{"regime_read": "<one of the 6 phases + frontside/backside>", '
    '"candidates": [{"symbol": "<MUST be a ticker from the candidate universe>", '
    '"pattern": "<the matched skill_id>", "reason": "<brief>", "confidence": <0..1>}], '
    '"no_trade_reason": "<reason if no trade, else empty string>"}'
)


def _skill_line(s: Skill) -> str:
    line = (f"- {s.name} ({s.skill_id}) [{s.type}, {s.family or 'any'}] phases[{'/'.join(s.phases)}] "
            f"trigger: {s.trigger} | entry: {s.entry} | exit: {s.exit_stop} "
            f"| taboo: {'; '.join(s.taboo)}")
    st = s.stats
    if st.n > 0:                                   # show track record (incl. losses/nukes)
        bits = f"n={st.n} nukes={st.nukes}"
        if st.ewma_winrate is not None:
            bits += f" win={st.ewma_winrate:.2f}"
        if st.expectancy is not None:
            bits += f" exp={st.expectancy:+.2f}"
        line += f" [{bits}]"
    return line


def build_system_prompt(h: HarnessState, *, injection: str = "full", phase_prior: str | None = None,
                        skill_budget: int = DEFAULT_SKILL_BUDGET,
                        memory_budget: int = DEFAULT_MEMORY_BUDGET,
                        trial_slots: int = DEFAULT_TRIAL_SLOTS) -> str:
    """Render H=(p,K,M) + the regime cycle + the output contract into the system prompt.

    injection='full' renders all active skills + all lessons; 'retrieval' renders a budgeted slice
    (phase-prior hit first). Rebuilt every decide() so Refiner edits to H are immediately visible.
    """
    if injection == "retrieval":
        sel = select_for_prompt(h, phase_prior=phase_prior, skill_budget=skill_budget,
                                memory_budget=memory_budget, trial_slots=trial_slots)
        skills, trials, lessons = sel.skills, sel.trials, sel.lessons
    else:
        skills = [s for s in h.skills.all() if s.status == "active"]
        trials = [s for s in h.skills.all() if s.status == "incubating"]
        lessons = h.memory.all()

    parts: list[str] = [
        "You are a US speculative-momentum trading co-pilot. Read the day's state and the candidate "
        "universe and propose ranked candidates with a plan. A human confirms; you never place orders.",
        "\nMARKET REGIME CYCLE (per-day phase): " + " -> ".join(CANONICAL_PHASES)
        + " (frontside/backside is a per-line momentum-direction read — early/healthy vs late/topping"
        + " — not a fixed function of phase).",
        "\nDOCTRINE (immutable red-lines are absolute):",
    ]
    for e in h.doctrine.immutable_core():
        parts.append(f"- [RED-LINE] {e.section}: {e.guidance}")
    for e in h.doctrine.mutable_entries():
        parts.append(f"- {e.section} [{'/'.join(e.phases) or 'all'}]: {e.guidance}")
    parts.append("\nSKILLS (K):")
    parts += [_skill_line(s) for s in skills]
    if trials:
        parts.append("\nINCUBATING (trial — use sparingly to gather evidence):")
        parts += [_skill_line(s) for s in trials]
    if lessons:
        parts.append("\nMEMORY (M):")
        for l in lessons:
            tag = {"principle": "PRINCIPLE", "loss": "LOSS", "win": "WIN"}.get(l.outcome, l.outcome.upper())
            analog = f"{l.named_analog}: " if l.named_analog else ""
            parts.append(f"- [{tag}] {analog}{l.lesson}")
    parts.append("\n" + _OUTPUT_CONTRACT)
    return "\n".join(parts)


def build_user_prompt(state: MarketState, universe: CandidateUniverse) -> str:
    """Render the day's MarketState + the candidate universe into the user prompt."""
    sn = f"{state.sentiment_norm:.2f}" if state.sentiment_norm is not None else "n/a"
    ft = f"{state.follow_through_rate:.2f}" if state.follow_through_rate is not None else "n/a"
    head = (f"Date {state.date}. gainers={state.gainer_count} gap_ups={state.gap_up_count} "
            f"losers={state.loser_count} failed_breakouts={state.failed_breakout_count} "
            f"max_runner_tier={state.max_runner_tier} follow_through={ft} sentiment_norm={sn}.")
    lines = ["\nCANDIDATE UNIVERSE (only these symbols are tradeable today):"]
    for s in sorted(universe.all(), key=lambda x: x.symbol):
        pct = f"{s.pct_change:+.0f}%" if s.pct_change is not None else "?"
        rvol = f"{s.rvol:.1f}" if s.rvol is not None else "?"
        cud = s.consecutive_up_days if s.consecutive_up_days is not None else "?"
        lines.append(f"- {s.symbol} ({s.name}) [{s.status}] pct={pct} rvol={rvol} up_days={cud}")
    return head + "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/test_prompt.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/prompt.py tests/agent/test_prompt.py
git commit -m "US-2a Task 6: prompt rendering (system H+cycle+contract / user state+universe)"
```

---

### Task 7: Parse + hallucination defense

**Files:**
- Create: `alpha/agent/parse.py`
- Create: `tests/agent/test_parse.py`

`parse_decision` extracts JSON, drops symbols not in the universe + duplicates (hallucination defense), clamps confidence, and returns a no-trade package on malformed output.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_parse.py
from datetime import date, datetime
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.agent.parse import parse_decision


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol="RUN", name="Runner", status="gainer"),
        StockSnapshot(symbol="MOON", name="Moon", status="gainer"),
    ])


def test_parses_valid_and_drops_hallucinations():
    raw = ('{"regime_read": "trend frontside", "candidates": ['
           '{"symbol": "RUN", "pattern": "gap_and_go", "reason": "held VWAP", "confidence": 0.8}, '
           '{"symbol": "GHOST", "pattern": "x", "confidence": 0.9}, '          # not in universe -> drop
           '{"symbol": "RUN", "pattern": "dup", "confidence": 0.5}], '          # duplicate -> drop
           '"no_trade_reason": ""}')
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
    assert pkg.candidates[0].confidence == 0.8 and pkg.candidates[0].name == "Runner"
    assert pkg.regime_read == "trend frontside"


def test_clamps_confidence():
    raw = '{"candidates": [{"symbol": "MOON", "pattern": "p", "confidence": 5.0}]}'
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    assert pkg.candidates[0].confidence == 1.0


def test_malformed_is_no_trade():
    pkg = parse_decision("the model rambled with no json", date(2026, 6, 12), _uni(),
                         as_of=datetime(2026, 6, 12, 16, 0))
    assert pkg.candidates == [] and pkg.no_trade_reason
    assert pkg.as_of == datetime(2026, 6, 12, 16, 0)     # as_of stamped even on the no-trade path


def test_prose_wrapped_json_extracted():
    raw = 'Here is my call:\n```json\n{"candidates": [{"symbol": "RUN", "pattern": "p"}]}\n```'
    pkg = parse_decision(raw, date(2026, 6, 12), _uni())
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/test_parse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.agent.parse'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/agent/parse.py
from __future__ import annotations

import json
from datetime import date as Date, datetime as DateTime

from alpha.eval.decision import Candidate, DecisionPackage
from alpha.llm.extract import extract_json_object
from alpha.universe.universe import CandidateUniverse


def _clamp01(v: object, default: float = 0.5) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, f))


def parse_decision(raw: str, day: Date, universe: CandidateUniverse,
                   as_of: DateTime | None = None) -> DecisionPackage:
    """Robustly parse LLM text into a DecisionPackage: drop hallucinated/duplicate symbols
    (re-anchor to the universe), clamp confidence; malformed output -> no-trade fallback.
    `as_of` (the inference-path snapshot timestamp, §4.1) is stamped on EVERY package, incl. no-trade."""
    extracted = extract_json_object(raw)
    if extracted is None:                              # no JSON object at all -> no-trade
        return DecisionPackage(date=day, as_of=as_of, no_trade_reason="LLM output parse failed")
    try:
        data = json.loads(extracted)
        if not isinstance(data, dict):
            raise ValueError("top level not an object")
    except (json.JSONDecodeError, ValueError):
        return DecisionPackage(date=day, as_of=as_of, no_trade_reason="LLM output parse failed")

    cands: list[Candidate] = []
    seen: set[str] = set()
    for c in (data.get("candidates") or []):
        if not isinstance(c, dict):
            continue
        sym = (str(c.get("symbol")) if c.get("symbol") is not None else "").strip()
        snap = universe.get(sym)
        if snap is None or snap.symbol in seen:        # hallucinated / not tradeable / duplicate -> drop
            continue
        seen.add(snap.symbol)
        cands.append(Candidate(symbol=snap.symbol, name=snap.name,
                               pattern=str(c.get("pattern") or ""), reason=str(c.get("reason") or ""),
                               confidence=_clamp01(c.get("confidence", 0.5))))
    return DecisionPackage(date=day, as_of=as_of, candidates=cands,
                           no_trade_reason=str(data.get("no_trade_reason") or ""),
                           regime_read=str(data.get("regime_read") or "").strip())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/test_parse.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/parse.py tests/agent/test_parse.py
git commit -m "US-2a Task 7: parse + hallucination defense (re-anchor to universe; malformed -> no-trade)"
```

---

### Task 8: LLMAgentPolicy (the act half-loop)

**Files:**
- Create: `alpha/agent/agent.py`
- Create: `tests/agent/test_agent.py`

`LLMAgentPolicy` implements `DecisionPolicy`: holds `H` + an `LLMClient`, rebuilds the prompt from the current `H` each `decide()`, calls the LLM, parses, and tracks `phase_prior` (its own prior `regime_read`, `≤t`).

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_agent.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy


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


def test_agent_decides_and_reanchors():
    llm = MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                        '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    agent = LLMAgentPolicy(_h(), llm)
    assert hasattr(agent, "decide") and callable(agent.decide)   # structural DecisionPolicy conformance
    state, uni = _state(), _uni()
    pkg = agent.decide(state, uni)
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
    assert pkg.regime_read == "trend frontside"
    assert pkg.as_of == state.as_of                # agent stamps the inference-path timestamp (§4.1)
    # the agent built a prompt that included the live skill + the candidate
    sys, usr = llm.calls[0]
    assert "gap_and_go" in sys and "RUN" in usr


def test_phase_prior_threads_across_calls():
    # regime_read obeys the multi-token output contract; the agent must EXTRACT the canonical phase
    llm = MockLLMClient(['{"regime_read": "trend frontside", "candidates": []}',
                         '{"regime_read": "", "candidates": []}'])
    agent = LLMAgentPolicy(_h(), llm, injection="retrieval")
    st = _state()
    pkg1 = agent.decide(st, _uni())
    assert agent._phase_prior == "trend"           # extracted from "trend frontside" (NOT None)
    assert pkg1.as_of == st.as_of
    agent.decide(_state(), _uni())                  # second response has empty regime_read
    assert agent._phase_prior is None              # -> prior cleared


def test_malformed_response_is_no_trade():
    agent = LLMAgentPolicy(_h(), MockLLMClient("no json at all"))
    pkg = agent.decide(_state(), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/test_agent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.agent.agent'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/agent/agent.py
from __future__ import annotations

from typing import Literal

from alpha.agent.parse import parse_decision
from alpha.agent.prompt import build_system_prompt, build_user_prompt
from alpha.agent.retrieval import DEFAULT_MEMORY_BUDGET, DEFAULT_SKILL_BUDGET, DEFAULT_TRIAL_SLOTS
from alpha.eval.decision import DecisionPackage
from alpha.harness.regime import normalize_phase
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


def _phase_from_read(regime_read: str) -> str | None:
    """Extract the first CANONICAL phase token from a free-text regime_read.

    The output contract makes regime_read a multi-token string (e.g. 'trend frontside' or
    'AI frontside; trend'), so normalize_phase() on the whole string returns None. Scan tokens
    (comma/semicolon/space-separated) and return the first that maps to a canonical phase, else None.
    """
    for tok in (regime_read or "").replace(",", " ").replace(";", " ").split():
        p = normalize_phase(tok)
        if p is not None:
            return p
    return None


class LLMAgentPolicy:
    """LLM-driven DecisionPolicy: the harness wraps the model. Reads state + universe -> DecisionPackage.

    Holds H (not a pre-rendered prompt): each decide() rebuilds the system prompt from the CURRENT H,
    so the US-2b Refiner's edits become visible immediately. Default injection='retrieval' renders a
    budgeted, phase-prior-ordered slice of H (the spec's intent as H grows); 'full' is an opt-in debug
    path that dumps all active skills + all lessons. phase_prior = the CANONICAL phase extracted from
    the agent's own prior-day regime_read (<=t, no lookahead); a rollback that rebuilds this object
    resets it to None (acceptable — under rollback the prior read is void, same as day 1).
    """

    def __init__(self, harness: HarnessState, llm: LLMClient,
                 injection: Literal["full", "retrieval"] = "retrieval",
                 skill_budget: int = DEFAULT_SKILL_BUDGET,
                 memory_budget: int = DEFAULT_MEMORY_BUDGET,
                 trial_slots: int = DEFAULT_TRIAL_SLOTS) -> None:
        self._harness = harness
        self._llm = llm
        self._injection: Literal["full", "retrieval"] = injection
        self._skill_budget = skill_budget
        self._memory_budget = memory_budget
        self._trial_slots = trial_slots
        self._phase_prior: str | None = None

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        system = build_system_prompt(self._harness, injection=self._injection,
                                     phase_prior=self._phase_prior, skill_budget=self._skill_budget,
                                     memory_budget=self._memory_budget, trial_slots=self._trial_slots)
        user = build_user_prompt(state, universe)
        raw = self._llm.complete(system, user)
        pkg = parse_decision(raw, state.date, universe, as_of=state.as_of)
        self._phase_prior = _phase_from_read(pkg.regime_read)   # canonical phase only; None if no phase token
        return pkg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/test_agent.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/agent.py tests/agent/test_agent.py
git commit -m "US-2a Task 8: LLMAgentPolicy (act half-loop; rebuilds prompt from live H; phase_prior)"
```

---

### Task 9: US-2a acceptance gate + docs update

**Files:**
- Create: `tests/agent/test_us2a_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-2a done)

- [ ] **Step 1: Write the acceptance test**

```python
# tests/agent/test_us2a_acceptance.py
"""US-2a acceptance: the LLM agent (MockLLM) drives the seeded harness end-to-end through one
WalkForwardEval day-step, producing a scored decision — and the firewall holds (the agent only sees
state+universe). Runs the default injection='retrieval' path, so budgeted retrieval (Task 5) is
validated end-to-end on the real seed harness. This is the act half-loop the US-2b Refiner will close."""
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.walk_forward import WalkForwardEval
from alpha.eval.scorer import ReturnScorer

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    snaps = {}
    for d, rows in {date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
                    date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)]}.items():
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [r[2] for r in rows],
                                 "high": [r[1] for r in rows], "low": [r[2] for r in rows],
                                 "close": [r[1] for r in rows], "volume": [1], "prev_close": [r[2] for r in rows]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
                                 "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_agent_drives_walk_forward_end_to_end():
    h = load_seeds(SEEDS)                       # the real defense-heavy seed harness
    # the agent always picks RUN with the gap_and_go skill (MockLLM scripts a valid JSON)
    llm = MockLLMClient('{"regime_read": "trend", "candidates": '
                        '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    agent = LLMAgentPolicy(h, llm)
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    report = wf.run(agent)
    assert report.n_decisions == 4 and report.n_candidates >= 1     # RUN picked + scored on real bars
    assert llm.calls                                               # the LLM was actually consulted
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0 + US-1 + US-2a tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

Mark **US-2a (LLM clients + agent) done** with the date and a summary: provider-agnostic LLM layer (Mock/Claude/OpenAI-compatible, per-role config, retry/backoff), and `LLMAgentPolicy` (the act half-loop) that wraps `H`, rebuilds the prompt from live `H` each decide (default budgeted retrieval), threads a canonical `phase_prior`, stamps `as_of`, and parses with hallucination defense (re-anchor to universe; malformed -> no-trade). The agent drives `WalkForwardEval` end-to-end on MockLLM. Update the "Next" pointer to **US-2b (Refiner: 4-pass CRUD + credit assignment + retire-discipline)** — closing the inner loop. Note deferred: record/replay cache, sizing/guard wiring into the DecisionPackage, master-dispatch G sub-agents.

- [ ] **Step 4: Commit**

```bash
git add tests/agent/test_us2a_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-2a Task 9: acceptance gate (agent drives walk-forward on MockLLM) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (§8 per-role LLM; §4 agent):** LLMClient protocol + Mock (Task 1) ✓ · OpenAI-compatible + Claude clients with retry/backoff (Tasks 2-3) ✓ · per-role config, agent-cheap/refiner-Claude, temp=0 (Task 4) ✓ · budgeted retrieval (Task 5) ✓ · prompt rendering H+cycle+contract (Task 6) ✓ · parse + hallucination defense (Task 7) ✓ · LLMAgentPolicy rebuilding prompt from live H (Task 8) ✓ · end-to-end through WalkForwardEval (Task 9) ✓. **Deferred & documented:** record/replay CachedLLMClient → later US-2; sizing/guard → DecisionPackage wiring → US-2c; Refiner → US-2b; master-dispatch G sub-agents → later.

**Type consistency:** `LLMClient.complete(system, user) -> str` identical across Mock/Claude/OpenAICompat and consumed by the agent. `make_client(role) -> LLMClient`. `Selection(skills/trials/lessons)` from retrieval used by prompt. `parse_decision(raw, day, universe) -> DecisionPackage` uses the eval `Candidate`/`DecisionPackage` (US-1d/g). `LLMAgentPolicy` implements `DecisionPolicy.decide(state, universe)` (US-1d) so `WalkForwardEval` runs it unchanged. `normalize_phase`/`CANONICAL_PHASES` from harness/regime; `is_family` available if needed.

**Placeholder scan:** no TBD/TODO; every code step shows full code; the real clients' network paths are smoke-only (offline-tested via injected transports). Deferrals are explicit scope notes.

**Scope:** LLM clients + agent only; no Refiner, no inner loop, no cache. Produces the act half-loop the US-2b Refiner closes.

**Adversarial-review fixes folded (2026-06-14, 4-lens review):**
- **[critical] `isinstance(agent, DecisionPolicy)` → `TypeError`** (`DecisionPolicy` is a plain, non-`@runtime_checkable` Protocol): Task 8 test now asserts structural conformance (`hasattr(agent, "decide")`) + the Task 9 end-to-end `WalkForwardEval` run proves it; `DecisionPolicy` (US-1d shipped code) left untouched.
- **[critical] `phase_prior` threading dead under the output contract**: the contract makes `regime_read` multi-token (`"trend frontside"`), which `normalize_phase` maps to `None`, silently killing the retrieval phase-hit. Added `_phase_from_read()` (token scan → first canonical phase) and a regression test with a multi-token `regime_read`.
- **[critical] `DecisionPackage.as_of` never set**: `parse_decision` now takes `as_of` and stamps it on every package (incl. no-trade); the agent passes `state.as_of`; tests assert it.
- **[important] retrieval not the spec default / untested e2e**: `LLMAgentPolicy` default flipped to `injection="retrieval"`; the Task 9 acceptance gate now exercises it on the real seed harness.
- **[important] env hygiene**: `test_missing_key_raises` uses `monkeypatch.delenv` (no session leak).
- **[minor] honesty/fidelity**: dropped the unimplemented "by family" retrieval claim (deferred); reworded master-dispatch collapse as a deliberate spec REDUCTION; softened the prompt's frontside line to "per-line attribute, not a fixed function of phase" (spec §5 #2).
- **Rejected [minor]**: a reviewer flagged `claude-sonnet-4-6` as "not a real model id" — that is the correct current Sonnet 4.6 id; kept.
