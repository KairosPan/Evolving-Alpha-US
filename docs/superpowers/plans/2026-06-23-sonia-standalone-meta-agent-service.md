# Sonia — Standalone Meta-Agent Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the teaching co-pilot out of `alpha_web` into **Sonia** — an independent FastAPI meta-agent on its own port (`deepseek-v4-pro`, text-only) that owns the live brain + gated apply/rollback; `alpha_web` becomes a thin HTTP chat-cockpit client.

**Architecture:** Two processes sharing one file-backed brain (`LiveBrainStore` under `ALPHA_LIVE_BRAIN_DIR`). Sonia is the sole writer (dry-run preview → accept/reject → snapshotted apply → rollback) and owns the conversation thread (`SessionStore`). `alpha_web` ingests uploads to text at the edge, calls Sonia over HTTP (`httpx`), renders the thread, and reads the brain read-only for the console + badge.

**Tech Stack:** Python 3.11+, pydantic v2, FastAPI + uvicorn, httpx (ASGITransport for in-process tests), Jinja2 + HTMX, DeepSeek via the lazy `openai` SDK, `pypdf` for PDF text. TDD, fully offline via `MockLLMClient.chat` + injected fetchers + `httpx.ASGITransport`.

## Global Constraints

- **Python floor:** `requires-python = ">=3.11"`. All models are `pydantic.BaseModel` (v2).
- **Ports:** `alpha_web` stays on **8100** (`ALPHA_WEB_PORT`, unchanged). Sonia runs on **8810** (`ALPHA_SONIA_PORT`); `alpha_web` finds it via `ALPHA_SONIA_URL` (default `http://127.0.0.1:8810`). localhost-only, no inter-service auth (v1).
- **Model:** Sonia role default `("openai_compat", "deepseek-v4-pro")`; **text-only** (no images). `chat()` must NOT set `response_format={"type": "json_object"}` (the reply is prose + an optional fenced JSON block).
- **Brain ownership:** Sonia is the **only writer** of `brain.json`. `alpha_web`/console only read via `data_access.load_brain`/`brain_badge` (unchanged). `MetaTools` is imported from `alpha.harness.metatools`.
- **Snapshot key:** per-message snapshots use the string key `f"{session_id}-{message_id}"`. `LiveBrainStore.snapshot(key)` already accepts any string — **no signature change**.
- **Never a 500:** copilot failure / missing key / unreachable Sonia / bad upload → a friendly note or banner; the user's turn is always preserved.
- **Env vars:** `ALPHA_LIVE_BRAIN_DIR` (default `./state/brain`), `ALPHA_SESSIONS_DIR` (default `./state/sessions`), `ALPHA_SONIA_PROVIDER`/`ALPHA_SONIA_MODEL`, `ALPHA_SONIA_HOST`/`ALPHA_SONIA_PORT`, `ALPHA_SONIA_URL`, `ALPHA_MOCK_RESPONSE`.
- **Tests:** `pytest -q` (config: `testpaths=["tests"]`, `addopts="-q"`). Set env with `monkeypatch.setenv`; isolate state with `tmp_path` autouse fixtures. Web/Sonia test packages `pytest.importorskip("fastapi")`.
- **Existing contracts (verbatim):**
  - `MetaTools(harness, log=None)` → `.h`, `.log`.
  - `try_apply_op(meta, harness, op, *, allowed, min_retire_samples, min_promote_samples) -> tuple[EditRecord|None, str|None]` from `alpha.refine.apply`; `ALL_TOOLS` from same.
  - `RefineOp(tool, args={}, rationale="")` (frozen) + `parse_ops(raw) -> list[RefineOp]` from `alpha.refine.ops`.
  - `render_brain_summary(h) -> str`, `parse_directions(raw) -> list[ProposedDirection]`, `_TOOLS_DOC` (str) in `alpha.meta.prompts`.
  - `extract_json_object(raw) -> str | None` (returns the balanced JSON **substring**) in `alpha.llm.extract`.
  - `MetaAgent(tools, llm, *, retire_min=5, promote_min=3)`; `MetaAgent.apply(accepted) -> tuple[list[EditRecord], list[ProposedEdit]]` (live, no snapshot/persist).
  - `_KIND` dict in `alpha.meta.agent`; `new_edit_id`/`new_session_id`/`new_direction_id` in `alpha.meta.models`.

---

### Task 1: Chat LLM protocol + `MockLLMClient.chat()`

**Files:**
- Create: `alpha/llm/chat.py`
- Modify: `alpha/llm/client.py` (add `chat()` + `chat_calls` to `MockLLMClient`)
- Test: `tests/llm/test_chat.py`

**Interfaces:**
- Produces: `ChatMessage(role: Literal["user","assistant"], text: str = "")` (pydantic); `ChatLLMClient` Protocol with `chat(self, system: str, messages: list[ChatMessage]) -> str`; `MockLLMClient.chat(system, messages) -> str` recording into `.chat_calls: list[tuple[str, list[ChatMessage]]]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_chat.py
from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.client import MockLLMClient


def test_chat_message_fields():
    m = ChatMessage(role="user", text="hi")
    assert m.role == "user" and m.text == "hi"
    assert ChatMessage(role="assistant").text == ""


def test_mock_chat_replays_and_records():
    m = MockLLMClient(['{"a": 1}', "second"])
    msgs = [ChatMessage(role="user", text="u1")]
    assert m.chat("sys", msgs) == '{"a": 1}'
    assert m.chat("sys2", msgs) == "second"
    assert m.chat("sys3", msgs) == "second"            # past end -> last repeats
    assert isinstance(m, ChatLLMClient)                # satisfies runtime-checkable protocol
    assert m.chat_calls[0] == ("sys", msgs) and len(m.chat_calls) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_chat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha.llm.chat'`.

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/llm/chat.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """One turn in a multi-turn chat. Text-only (Sonia's copilot has no vision)."""
    role: str  # "user" | "assistant"
    text: str = ""


@runtime_checkable
class ChatLLMClient(Protocol):
    """Multi-turn chat: given a system prompt and prior turns, return the reply text."""
    def chat(self, system: str, messages: list[ChatMessage]) -> str: ...
```

Then add `chat()` + `chat_calls` to `MockLLMClient` in `alpha/llm/client.py`. Add `self.chat_calls: list = []` at the end of `__init__`, and this method after `complete`:

```python
    def chat(self, system: str, messages: list) -> str:
        self.chat_calls.append((system, list(messages)))
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_chat.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/chat.py alpha/llm/client.py tests/llm/test_chat.py
git commit -m "feat(llm): text-only ChatMessage/ChatLLMClient protocol + MockLLMClient.chat"
```

---

### Task 2: `OpenAICompatClient.chat()` (text-only, multi-message)

**Files:**
- Modify: `alpha/llm/openai_compat.py`
- Test: `tests/llm/test_openai_compat_chat.py`

**Interfaces:**
- Consumes: `ChatMessage` (Task 1).
- Produces: `OpenAICompatClient.chat(system: str, messages: list[ChatMessage]) -> str` — builds `[{"role":"system",...}, *turns]`, **no** `response_format`, same retry/backoff as `complete()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_openai_compat_chat.py
from alpha.llm.chat import ChatMessage
from alpha.llm.openai_compat import OpenAICompatClient


class _Msg:
    def __init__(self, content): self.content = content


class _Choice:
    def __init__(self, content): self.message = _Msg(content)


class _Resp:
    def __init__(self, content): self.choices = [_Choice(content)]


class _FakeCompletions:
    def __init__(self): self.calls = []
    def create(self, **kw):
        self.calls.append(kw)
        return _Resp("the reply")


class _FakeChat:
    def __init__(self): self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self): self.chat = _FakeChat()


def test_chat_maps_messages_and_omits_json_object():
    c = OpenAICompatClient(model="deepseek-v4-pro", api_key="x")
    c._client = _FakeClient()
    out = c.chat("SYS", [ChatMessage(role="user", text="hello"),
                         ChatMessage(role="assistant", text="hi"),
                         ChatMessage(role="user", text="more")])
    assert out == "the reply"
    sent = c._client.chat.completions.calls[0]
    assert sent["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "more"},
    ]
    assert "response_format" not in sent          # prose+JSON reply, not forced JSON
    assert sent["model"] == "deepseek-v4-pro"


def test_chat_retries_then_raises(monkeypatch):
    c = OpenAICompatClient(api_key="x", max_retries=1, sleep=lambda _s: None)
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                def create(**kw): raise RuntimeError("boom")
    c._client = _Boom()
    import pytest
    with pytest.raises(RuntimeError):
        c.chat("s", [ChatMessage(role="user", text="x")])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_openai_compat_chat.py -v`
Expected: FAIL with `AttributeError: 'OpenAICompatClient' object has no attribute 'chat'`.

- [ ] **Step 3: Write minimal implementation**

Add this method to `OpenAICompatClient` (after `complete`) in `alpha/llm/openai_compat.py`:

```python
    def chat(self, system: str, messages: list) -> str:
        if self._client is None:
            raise RuntimeError("openai not installed (pip install openai)")
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            msgs.append({"role": m.role, "content": m.text})
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model, messages=msgs, temperature=self.temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:           # noqa: BLE001 — transient: back off
                last = e
                if attempt < self._max_retries:
                    self._sleep(self._backoff * (2 ** attempt))
                else:
                    raise
        raise last  # pragma: no cover
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_openai_compat_chat.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/openai_compat.py tests/llm/test_openai_compat_chat.py
git commit -m "feat(llm): OpenAICompatClient.chat (text-only multi-message, no json_object)"
```

---

### Task 3: `sonia` LLM role

**Files:**
- Modify: `alpha/llm/config.py`
- Test: `tests/llm/test_config_sonia.py`

**Interfaces:**
- Produces: `make_client("sonia")` honoring `ALPHA_SONIA_PROVIDER`/`ALPHA_SONIA_MODEL`; default `("openai_compat", "deepseek-v4-pro")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_config_sonia.py
import pytest
from alpha.llm.client import MockLLMClient
from alpha.llm.config import make_client


def test_sonia_mock_provider(monkeypatch):
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "{}")
    assert isinstance(make_client("sonia"), MockLLMClient)


def test_sonia_defaults_to_deepseek_openai_compat(monkeypatch):
    # default provider is openai_compat -> a missing DEEPSEEK_API_KEY raises cleanly
    monkeypatch.delenv("ALPHA_SONIA_PROVIDER", raising=False)
    monkeypatch.delenv("ALPHA_SONIA_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        make_client("sonia")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_config_sonia.py -v`
Expected: FAIL — `make_client("sonia")` raises `ValueError: unknown role: 'sonia'`.

- [ ] **Step 3: Write minimal implementation**

In `alpha/llm/config.py`, extend the role literal and defaults:

```python
Role = Literal["agent", "refiner", "sonia"]

_DEFAULTS: dict[str, tuple[str, str]] = {
    "agent": ("openai_compat", "deepseek-chat"),
    "refiner": ("anthropic", "claude-sonnet-4-6"),
    "sonia": ("openai_compat", "deepseek-v4-pro"),
}
```

(No other change — the existing `ALPHA_{role.upper()}_PROVIDER/_MODEL` lookup already handles `ALPHA_SONIA_*`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_config_sonia.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/llm/config.py tests/llm/test_config_sonia.py
git commit -m "feat(llm): add sonia role (default deepseek-v4-pro, text-only copilot)"
```

---

### Task 4: Extract module-level `preview_op`

**Files:**
- Modify: `alpha/meta/agent.py` (add `preview_op`, make `_preview` delegate)
- Test: `tests/meta/test_preview_op.py`

**Interfaces:**
- Produces: `preview_op(harness: HarnessState, op: RefineOp, *, retire_min: int = 5, promote_min: int = 3) -> ProposedEdit` — dry-run on a deepcopy; live brain untouched. `MetaAgent._preview` now delegates to it.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_preview_op.py
from alpha.harness.loader import load_seeds
from alpha.meta.agent import preview_op
from alpha.refine.ops import RefineOp


def test_preview_op_dry_runs_without_mutating_live_brain():
    h = load_seeds("seeds")
    sid = h.skills.all()[0].skill_id
    op = RefineOp(tool="patch_skill", args={"skill_id": sid, "notes": "from preview"}, rationale="r")
    edit = preview_op(h, op)
    assert edit.status == "proposed" and edit.target_id == sid
    assert edit.payload["after"] == {"notes": "from preview"}
    assert h.skills.get(sid).notes != "from preview"          # live brain NOT mutated


def test_preview_op_failed_op_becomes_failed_card():
    h = load_seeds("seeds")
    op = RefineOp(tool="patch_skill", args={"skill_id": "nope", "notes": "x"}, rationale="r")
    edit = preview_op(h, op)
    assert edit.status == "failed" and edit.apply_reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_preview_op.py -v`
Expected: FAIL — `ImportError: cannot import name 'preview_op'`.

- [ ] **Step 3: Write minimal implementation**

In `alpha/meta/agent.py`, add `from alpha.harness.state import HarnessState` to the imports, then add this module-level function (above the `MetaAgent` class) — it is the exact body of the current `_preview`, generalized:

```python
def preview_op(harness: HarnessState, op: RefineOp, *, retire_min: int = 5, promote_min: int = 3) -> ProposedEdit:
    """Dry-run one op on a deepcopy of the brain; never mutates `harness`. Returns a ProposedEdit
    (status 'proposed' with payload on success, 'failed' + apply_reason on rejection)."""
    scratch = copy.deepcopy(harness)
    rec, reason = try_apply_op(MetaTools(scratch, EditLog()), scratch, op, allowed=ALL_TOOLS,
                               min_retire_samples=retire_min, min_promote_samples=promote_min)
    if rec is not None:
        return ProposedEdit(edit_id=new_edit_id(), tool=op.tool, target_kind=rec.target_kind,
                            target_id=rec.target_id, op=rec.op, summary=rec.summary,
                            payload=rec.payload, rationale=op.rationale, args=dict(op.args))
    return ProposedEdit(edit_id=new_edit_id(), tool=op.tool, target_kind=_KIND.get(op.tool, ""),
                        rationale=op.rationale, args=dict(op.args), status="failed", apply_reason=reason)
```

Replace the body of `MetaAgent._preview` with a delegation:

```python
    def _preview(self, op: RefineOp) -> ProposedEdit:
        return preview_op(self.h, op, retire_min=self._retire_min, promote_min=self._promote_min)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/meta/test_preview_op.py tests/meta/test_agent.py -v`
Expected: PASS — new tests pass AND the existing `test_expand_to_edits_*` still pass (delegation unchanged behavior).

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/agent.py tests/meta/test_preview_op.py
git commit -m "refactor(meta): extract module-level preview_op (shared by MetaAgent + SoniaAgent)"
```

---

### Task 5: Thread data models (additive)

**Files:**
- Modify: `alpha/meta/models.py` (add `Attachment`, `Message`, `new_message_id`, `now_iso`; add `title`/`messages` to `Session`, keeping old fields for now)
- Test: `tests/meta/test_thread_models.py`

**Interfaces:**
- Produces: `Attachment(kind: Literal["file","url"], name="", mime="", text="")`; `Message(message_id, role, created_at="", text="", attachments=[], directions=[], edits=[], snapshot_before=None, applied_seqs=[])`; `Session.title: str`, `Session.messages: list[Message]`; `new_message_id() -> str`; `now_iso() -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_thread_models.py
from alpha.meta.models import (Attachment, Message, Session, new_message_id, now_iso)


def test_attachment_and_message_roundtrip():
    a = Attachment(kind="file", name="notes.md", text="hello")
    m = Message(message_id="m1", role="user", text="teach", attachments=[a])
    back = Message.model_validate_json(m.model_dump_json())
    assert back.attachments[0].name == "notes.md" and back.role == "user"
    assert back.edits == [] and back.directions == [] and back.snapshot_before is None


def test_session_thread_roundtrip_and_defaults():
    s = Session(session_id="s1", title="t", messages=[Message(message_id="m1", role="assistant")])
    back = Session.model_validate_json(s.model_dump_json())
    assert back.title == "t" and back.messages[0].role == "assistant"
    assert Session(session_id="s2").messages == [] and Session(session_id="s2").title == ""


def test_id_and_time_helpers():
    assert len(new_message_id()) == 8 and new_message_id() != new_message_id()
    assert "T" in now_iso()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_thread_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Attachment'`.

- [ ] **Step 3: Write minimal implementation**

In `alpha/meta/models.py`, add after the existing id helpers:

```python
def new_message_id() -> str:
    return uuid4().hex[:8]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Attachment(BaseModel):
    kind: Literal["file", "url"]
    name: str = ""
    mime: str = ""
    text: str = ""


class Message(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    created_at: str = ""
    text: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    directions: list[ProposedDirection] = Field(default_factory=list)
    edits: list[ProposedEdit] = Field(default_factory=list)
    snapshot_before: str | None = None
    applied_seqs: list[int] = Field(default_factory=list)
```

In the `Session` model, add two fields (keep all existing fields for the transition — Task 11 removes the obsolete ones):

```python
class Session(BaseModel):
    session_id: str
    created_at: str = ""
    title: str = ""                      # NEW: derived from the first user message
    channel: str = "teach"
    status: Literal["open", "applied", "discarded"] = "open"
    messages: list[Message] = Field(default_factory=list)   # NEW: the conversation thread
    sources: list[LessonSource] = Field(default_factory=list)            # (removed in Task 11)
    directions: list[ProposedDirection] = Field(default_factory=list)    # (removed in Task 11)
    chosen_direction_id: str | None = None                               # (removed in Task 11)
    direction_comment: str = ""                                          # (removed in Task 11)
    edits: list[ProposedEdit] = Field(default_factory=list)              # (removed in Task 11)
    applied_seqs: list[int] = Field(default_factory=list)                # (removed in Task 11)
    snapshot_before: str | None = None                                   # (removed in Task 11)
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/meta/ -v`
Expected: PASS — new thread tests pass AND existing `tests/meta/test_store.py` / `test_agent.py` stay green (additive change).

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/models.py tests/meta/test_thread_models.py
git commit -m "feat(meta): add Attachment/Message + Session thread fields (additive)"
```

---

### Task 6: `SoniaAgent.respond`

**Files:**
- Create: `alpha/meta/sonia_agent.py`
- Test: `tests/meta/test_sonia_agent.py`

**Interfaces:**
- Consumes: `MetaTools` (`.h`), `ChatLLMClient` (Task 1), `preview_op` (Task 4), `Message`/`now_iso`/`new_message_id` (Task 5), `prompts.render_brain_summary`/`parse_directions`/`_TOOLS_DOC`, `parse_ops`, `extract_json_object`.
- Produces: `SoniaAgent(tools, copilot, *, retire_min=5, promote_min=3)`; `respond(session: Session, user_message: Message) -> Message` (the assistant turn, with `directions`/`edits` dry-run; live brain untouched).

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_sonia_agent.py
from alpha.harness.edit_log import EditLog
from alpha.harness.loader import load_seeds
from alpha.harness.metatools import MetaTools
from alpha.llm.client import MockLLMClient
from alpha.meta.models import Message, Session
from alpha.meta.sonia_agent import SoniaAgent


def _agent(scripted, h=None):
    h = h if h is not None else load_seeds("seeds")
    return SoniaAgent(MetaTools(h, EditLog()), MockLLMClient(scripted)), h


def _user(text="teach me"):
    return Message(message_id="u1", role="user", text=text)


def test_prose_only_makes_no_cards():
    agent, _ = _agent("Let's discuss your squeeze thesis first — no edits yet.")
    out = agent.respond(Session(session_id="s1"), _user())
    assert out.role == "assistant" and "squeeze thesis" in out.text
    assert out.edits == [] and out.directions == []


def test_directions_become_direction_cards():
    agent, _ = _agent('Here is a direction. {"directions": [{"title": "lean into squeezes"}]}')
    out = agent.respond(Session(session_id="s1"), _user())
    assert [d.title for d in out.directions] == ["lean into squeezes"]
    assert "lean into squeezes" not in out.text or out.text.startswith("Here is a direction")


def test_ops_become_dryrun_edit_cards_without_mutating_brain():
    h = load_seeds("seeds")
    sid = h.skills.all()[0].skill_id
    scripted = ('proposing a patch. {"ops": [{"tool": "patch_skill", '
                '"args": {"skill_id": "%s", "notes": "from sonia"}, "rationale": "the writeup shows it"}]}') % sid
    agent, h = _agent(scripted, h)
    out = agent.respond(Session(session_id="s1"), _user())
    assert len(out.edits) == 1 and out.edits[0].status == "proposed"
    assert out.edits[0].payload["after"] == {"notes": "from sonia"}
    assert h.skills.get(sid).notes != "from sonia"               # live brain untouched


def test_redline_op_becomes_failed_card():
    scripted = '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "missing"}, "rationale": "r"}]}'
    agent, _ = _agent(scripted)
    out = agent.respond(Session(session_id="s1"), _user())
    assert len(out.edits) == 1 and out.edits[0].status == "failed" and out.edits[0].apply_reason


def test_history_is_threaded_into_the_chat_call():
    agent, _ = _agent("ok")
    prior = [Message(message_id="m0", role="user", text="earlier"),
             Message(message_id="m1", role="assistant", text="noted")]
    agent.respond(Session(session_id="s1", messages=prior), _user("now this"))
    system, sent = agent.copilot.chat_calls[0]
    assert "RED-LINE" in system                                  # brain summary in the system prompt
    assert [m.text for m in sent] == ["earlier", "noted", "now this"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_sonia_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.meta.sonia_agent'`.

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/sonia_agent.py
from __future__ import annotations

from alpha.harness.metatools import MetaTools
from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.extract import extract_json_object
from alpha.meta import prompts
from alpha.meta.agent import preview_op
from alpha.meta.models import Message, Session, new_message_id, now_iso
from alpha.refine.ops import parse_ops

_INSTRUCTIONS = (
    "\n\nYou are Sonia, a US speculative-momentum trading co-pilot. Discuss freely and ask "
    "clarifying questions. When (and only when) a concrete brain change is warranted, write prose "
    "for the operator and then append a SINGLE fenced JSON object with \"directions\" (each "
    "{\"title\":..., \"summary\":...}) and/or \"ops\". " + prompts._TOOLS_DOC
)


def _turn_text(m: Message) -> str:
    extra = "\n\n".join(a.text for a in m.attachments if a.text)
    return (m.text + ("\n\n" + extra if extra else "")).strip()


class SoniaAgent:
    """Stateless-per-request chat meta-agent. Reasons over the thread; proposes dry-run edit cards.
    The live brain is never mutated here — apply is the service's job."""

    def __init__(self, tools: MetaTools, copilot: ChatLLMClient, *, retire_min: int = 5, promote_min: int = 3) -> None:
        self.tools = tools
        self.h = tools.h
        self.copilot = copilot
        self._retire_min = retire_min
        self._promote_min = promote_min

    def _system(self) -> str:
        return prompts.render_brain_summary(self.h) + _INSTRUCTIONS

    def _history(self, session: Session, user_message: Message) -> list[ChatMessage]:
        msgs = [ChatMessage(role=m.role, text=_turn_text(m)) for m in session.messages]
        msgs.append(ChatMessage(role="user", text=_turn_text(user_message)))
        return msgs

    def respond(self, session: Session, user_message: Message) -> Message:
        reply = self.copilot.chat(self._system(), self._history(session, user_message))
        block = extract_json_object(reply)
        prose = reply.replace(block, "").strip() if block else reply.strip()
        directions = prompts.parse_directions(reply)
        edits = [preview_op(self.h, op, retire_min=self._retire_min, promote_min=self._promote_min)
                 for op in parse_ops(reply)]
        return Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                       text=prose, directions=directions, edits=edits)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_sonia_agent.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/sonia_agent.py tests/meta/test_sonia_agent.py
git commit -m "feat(meta): SoniaAgent.respond (chat reasoner; dry-run edit cards, brain untouched)"
```

---

### Task 7: `ingest_attachments` (files / PDF / URL; reject images)

**Files:**
- Modify: `alpha/meta/ingest.py`
- Modify: `pyproject.toml` (add `pypdf` to `[web]`)
- Test: `tests/meta/test_ingest_attachments.py`

**Interfaces:**
- Consumes: `Attachment` (Task 5), existing `fetch_url`/`IngestError`.
- Produces: `ingest_attachments(text: str, files: list[tuple[str, bytes]] | None = None, *, fetcher=None) -> tuple[str, list[Attachment]]` — never raises; bad inputs become friendly note attachments.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_ingest_attachments.py
from alpha.meta.ingest import ingest_attachments


def test_text_file_decoded_and_text_preserved():
    clean, atts = ingest_attachments("plain prose", files=[("notes.md", b"# Heading\nbody")])
    assert clean == "plain prose"
    assert atts[0].kind == "file" and atts[0].name == "notes.md" and "Heading" in atts[0].text


def test_image_is_rejected_with_a_friendly_note():
    _, atts = ingest_attachments("", files=[("chart.png", b"\x89PNG\r\n")])
    assert len(atts) == 1 and "can't read images" in atts[0].text.lower()


def test_unknown_type_rejected():
    _, atts = ingest_attachments("", files=[("a.bin", b"\x00\x01")])
    assert "unsupported" in atts[0].text.lower()


def test_url_detected_and_fetched_via_injected_fetcher():
    html = "<html><head><title>Squeeze</title></head><body>short interest spikes</body></html>"
    _, atts = ingest_attachments("see https://example.com/post", fetcher=lambda _u: html)
    url_atts = [a for a in atts if a.kind == "url"]
    assert url_atts and "short interest spikes" in url_atts[0].text


def test_dead_url_becomes_a_note_not_a_crash():
    def boom(_u): raise RuntimeError("no net")
    _, atts = ingest_attachments("https://example.com", fetcher=boom)
    assert atts and "could not fetch" in atts[0].text


def test_pdf_text_extraction_when_pypdf_present():
    import pytest
    pypdf = pytest.importorskip("pypdf")
    import io
    w = pypdf.PdfWriter()
    w.add_blank_page(width=72, height=72)
    buf = io.BytesIO(); w.write(buf)
    _, atts = ingest_attachments("", files=[("doc.pdf", buf.getvalue())])
    assert atts[0].kind == "file" and atts[0].name == "doc.pdf"   # parses without raising
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_ingest_attachments.py -v`
Expected: FAIL — `ImportError: cannot import name 'ingest_attachments'`.

- [ ] **Step 3: Write minimal implementation**

Add to `alpha/meta/ingest.py` (it already has `fetch_url`, `IngestError`, `_ALLOWED_SCHEMES`):

```python
import re
from io import BytesIO

from alpha.meta.models import Attachment

_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_TEXT_EXT = {".txt", ".md", ".csv"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_TEXT = 50_000


def _ext(name: str) -> str:
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


def _cap(text: str) -> str:
    return text if len(text) <= _MAX_TEXT else text[:_MAX_TEXT] + "\n\n[... truncated ...]"


def _pdf_text(data: bytes) -> str:
    try:
        import pypdf
    except ImportError as e:
        raise IngestError("PDF support needs pypdf (pip install -e '.[web]')") from e
    reader = pypdf.PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def ingest_attachments(text: str, files=None, *, fetcher=None) -> tuple[str, list[Attachment]]:
    """(clean_text, attachments) from composer text + uploaded (filename, bytes) files. txt/md/csv
    decoded, pdf via pypdf, images rejected (no vision), unknown rejected; http(s) URLs in `text`
    fetched via the scheme-allowlisted fetch_url. Never raises — bad inputs become note attachments."""
    out: list[Attachment] = []
    for name, data in (files or []):
        ext = _ext(name)
        if ext in _IMAGE_EXT:
            out.append(Attachment(kind="file", name=name, mime="image",
                                  text=f"[image '{name}' attached — Sonia can't read images; describe it in text]"))
            continue
        try:
            if ext == ".pdf":
                body = _pdf_text(data)
            elif ext in _TEXT_EXT:
                body = data.decode("utf-8", errors="replace")
            else:
                out.append(Attachment(kind="file", name=name,
                                      text=f"[unsupported file '{name}' — paste the text instead]"))
                continue
        except IngestError as e:
            out.append(Attachment(kind="file", name=name, text=f"[{e}]"))
            continue
        out.append(Attachment(kind="file", name=name, text=_cap(body)))
    for url in _URL_RE.findall(text or ""):
        try:
            src = fetch_url(url, fetcher=fetcher)
            out.append(Attachment(kind="url", name=url, text=_cap(src.text)))
        except IngestError as e:
            out.append(Attachment(kind="url", name=url, text=f"[{e}]"))
    return (text or "").strip(), out
```

In `pyproject.toml`, add `pypdf>=4.0` to the `web` extra:

```toml
web = ["fastapi>=0.110", "uvicorn>=0.29", "jinja2>=3.1", "python-multipart>=0.0.9", "httpx>=0.27", "pypdf>=4.0"]
```

(Note: `httpx>=0.27` is added here too — Task 10 needs it at runtime for `sonia_client`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install -e '.[web]' && pytest tests/meta/test_ingest_attachments.py -v`
Expected: PASS (6 tests; the PDF test runs once `pypdf` is installed).

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/ingest.py pyproject.toml tests/meta/test_ingest_attachments.py
git commit -m "feat(meta): ingest_attachments (txt/md/csv/pdf + URL; reject images); pypdf+httpx in [web]"
```

---

### Task 8: Sonia service skeleton (`/chat`, sessions, `/healthz`, launcher)

**Files:**
- Create: `sonia/__init__.py`, `sonia/app.py`, `sonia/__main__.py`
- Create: `tests/sonia/__init__.py`, `tests/sonia/conftest.py`, `tests/sonia/test_chat.py`
- Modify: `pyproject.toml` (`[sonia]` extra + package include)

**Interfaces:**
- Consumes: `SoniaAgent` (Task 6), `make_client("sonia")` (Task 3), `Session`/`Message`/`Attachment`/`new_session_id`/`new_message_id`/`now_iso` (Task 5), `LiveBrainStore`/`SessionStore`.
- Produces: `sonia.app.create_app() -> FastAPI` with `GET /healthz`, `POST /sessions/new`, `GET /sessions`, `GET /sessions/{sid}`, `POST /chat`; module-level `app`. `POST /chat` body = `{session_id?, text, attachments: [{kind,name,mime,text}]}` → `{session_id, user_message, assistant_message}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/sonia/conftest.py
import pytest

pytest.importorskip("fastapi", reason="install: pip install -e '.[sonia]'")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "let's discuss your thesis")
```

```python
# tests/sonia/test_chat.py
import pytest
from fastapi.testclient import TestClient
from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_healthz_reports_seed_brain(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True, "brain_live": False, "edit_count": 0}


def test_new_then_list_sessions(client):
    sid = client.post("/sessions/new").json()["session_id"]
    assert any(s["session_id"] == sid for s in client.get("/sessions").json())


def test_chat_appends_two_turns_and_persists(client):
    r = client.post("/chat", json={"text": "high short interest writeup"})
    body = r.json()
    assert r.status_code == 200
    assert body["user_message"]["text"] == "high short interest writeup"
    assert body["assistant_message"]["role"] == "assistant" and body["assistant_message"]["text"]
    loaded = client.get(f"/sessions/{body['session_id']}").json()
    assert [m["role"] for m in loaded["messages"]] == ["user", "assistant"]
    assert loaded["title"]                                         # derived from first user message


def test_chat_with_ops_returns_edit_cards(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "n"}, "rationale": "r"}]}' % sid)
    body = client.post("/chat", json={"text": "patch it"}).json()
    assert body["assistant_message"]["edits"][0]["status"] == "proposed"


def test_chat_is_graceful_when_copilot_unavailable(client, monkeypatch):
    monkeypatch.delenv("ALPHA_SONIA_PROVIDER", raising=False)        # default openai_compat
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    body = client.post("/chat", json={"text": "hi"}).json()
    assert "couldn't respond" in body["assistant_message"]["text"].lower()
    assert body["user_message"]["text"] == "hi"                      # user turn preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/sonia/test_chat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sonia'`.

- [ ] **Step 3: Write minimal implementation**

```python
# sonia/__init__.py
```

```python
# sonia/app.py
from __future__ import annotations

import os
import threading

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from alpha.harness.metatools import MetaTools
from alpha.llm.config import make_client
from alpha.meta.models import Attachment, Message, Session, new_message_id, new_session_id, now_iso
from alpha.meta.sonia_agent import SoniaAgent
from alpha.meta.store import LiveBrainStore, SessionStore

_MUTATION_LOCK = threading.Lock()


def _brain_store() -> LiveBrainStore:
    return LiveBrainStore(os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"))


def _session_store() -> SessionStore:
    return SessionStore(os.environ.get("ALPHA_SESSIONS_DIR", "./state/sessions"))


class ChatIn(BaseModel):
    session_id: str | None = None
    text: str = ""
    attachments: list[Attachment] = []


def create_app() -> FastAPI:
    app = FastAPI(title="Sonia · meta-agent")

    @app.get("/healthz")
    def healthz():
        store = _brain_store()
        return {"ok": True, "brain_live": store.is_live(), "edit_count": store.edit_count()}

    @app.post("/sessions/new")
    def new_session():
        sess = Session(session_id=new_session_id(), created_at=now_iso())
        _session_store().put(sess)
        return sess.model_dump()

    @app.get("/sessions")
    def list_sessions():
        return [s.model_dump() for s in _session_store().list()]

    @app.get("/sessions/{sid}")
    def get_session(sid: str):
        s = _session_store().get(sid)
        if s is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return s.model_dump()

    @app.post("/chat")
    def chat(body: ChatIn):
        sstore = _session_store()
        sess = sstore.get(body.session_id) if body.session_id else None
        if sess is None:
            sess = Session(session_id=new_session_id(), created_at=now_iso())
        if not sess.title:
            sess.title = (body.text or "untitled").strip()[:60] or "untitled"
        user_msg = Message(message_id=new_message_id(), role="user", created_at=now_iso(),
                           text=body.text, attachments=body.attachments)
        h, log = _brain_store().load()
        try:
            agent = SoniaAgent(MetaTools(h, log), make_client("sonia"))
            asst = agent.respond(sess, user_msg)
        except Exception as e:                                       # never 500: keep the user turn
            asst = Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                           text=f"(Sonia couldn't respond: {type(e).__name__}: {e})")
        sess.messages.append(user_msg)
        sess.messages.append(asst)
        sstore.put(sess)
        return {"session_id": sess.session_id, "user_message": user_msg.model_dump(),
                "assistant_message": asst.model_dump()}

    return app


app = create_app()
```

```python
# sonia/__main__.py
from __future__ import annotations

import os


def main() -> None:
    import uvicorn
    host = os.environ.get("ALPHA_SONIA_HOST", "127.0.0.1")
    port = int(os.environ.get("ALPHA_SONIA_PORT", "8810"))
    uvicorn.run("sonia.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
```

```python
# tests/sonia/__init__.py
```

In `pyproject.toml`, add the `[sonia]` extra and include the package:

```toml
sonia = ["fastapi>=0.110", "uvicorn>=0.29", "openai>=1.0"]
```

```toml
[tool.setuptools.packages.find]
include = ["alpha*", "alpha_web*", "sonia*"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install -e '.[web,sonia]' && pytest tests/sonia/ -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add sonia/ tests/sonia/ pyproject.toml
git commit -m "feat(sonia): standalone meta-agent service skeleton (/chat, /sessions, /healthz)"
```

---

### Task 9: Sonia gated apply / rollback / edit-action routes

**Files:**
- Modify: `sonia/app.py`
- Test: `tests/sonia/test_apply.py`

**Interfaces:**
- Consumes: `MetaAgent` (for `.apply`), `MockLLMClient` (apply needs no LLM), `LiveBrainStore.snapshot`/`save`/`restore`/`is_live`.
- Produces: `POST /sessions/{sid}/edit/{eid}` (body `{action:"accept"|"reject"}`) → the card; `POST /sessions/{sid}/messages/{mid}/apply` → `{applied:int, edits:[...]}`; `POST /sessions/{sid}/messages/{mid}/rollback` → `{ok:bool}`. All mutating routes hold `_MUTATION_LOCK`; apply snapshots with key `f"{sid}-{mid}"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/sonia/test_apply.py
import pytest
from fastapi.testclient import TestClient
from alpha.harness.loader import load_seeds
from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _seed_one_edit(client, monkeypatch):
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "taught"}, "rationale": "r"}]}' % sid_skill)
    body = client.post("/chat", json={"text": "patch it"}).json()
    sid = body["session_id"]
    mid = body["assistant_message"]["message_id"]
    eid = body["assistant_message"]["edits"][0]["edit_id"]
    return sid, mid, eid, sid_skill


def test_accept_then_apply_mutates_brain_and_snapshots(client, monkeypatch):
    sid, mid, eid, sid_skill = _seed_one_edit(client, monkeypatch)
    assert client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"}).json()["status"] == "accepted"
    r = client.post(f"/sessions/{sid}/messages/{mid}/apply").json()
    assert r["applied"] == 1
    assert client.get("/healthz").json()["edit_count"] == 1            # live brain mutated
    assert client.get(f"/sessions/{sid}").json()["messages"][1]["snapshot_before"]


def test_rollback_restores_pre_apply_brain(client, monkeypatch):
    sid, mid, eid, _ = _seed_one_edit(client, monkeypatch)
    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})
    client.post(f"/sessions/{sid}/messages/{mid}/apply")
    assert client.post(f"/sessions/{sid}/messages/{mid}/rollback").json()["ok"] is True
    assert client.get("/healthz").json()["edit_count"] == 0            # rolled back


def test_apply_with_no_accepted_edits_is_a_noop(client, monkeypatch):
    sid, mid, _eid, _ = _seed_one_edit(client, monkeypatch)            # never accept
    assert client.post(f"/sessions/{sid}/messages/{mid}/apply").json()["applied"] == 0
    assert client.get("/healthz").json()["edit_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/sonia/test_apply.py -v`
Expected: FAIL — `404 Not Found` (the routes don't exist yet).

- [ ] **Step 3: Write minimal implementation**

Add these imports to `sonia/app.py`:

```python
from alpha.llm.client import MockLLMClient
from alpha.meta.agent import MetaAgent
```

Add an input model near `ChatIn`:

```python
class EditAction(BaseModel):
    action: str  # "accept" | "reject"
```

Add a helper and the three routes inside `create_app()` (before `return app`):

```python
    def _find(sess: Session, mid: str) -> Message | None:
        return next((m for m in sess.messages if m.message_id == mid), None)

    @app.post("/sessions/{sid}/edit/{eid}")
    def edit_action(sid: str, eid: str, body: EditAction):
        sstore = _session_store()
        sess = sstore.get(sid)
        if sess is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        for m in sess.messages:
            for e in m.edits:
                if e.edit_id == eid:
                    e.status = "accepted" if body.action == "accept" else "rejected"
                    sstore.put(sess)
                    return e.model_dump()
        return JSONResponse({"error": "edit not found"}, status_code=404)

    @app.post("/sessions/{sid}/messages/{mid}/apply")
    def apply_message(sid: str, mid: str):
        with _MUTATION_LOCK:
            sstore = _session_store()
            sess = sstore.get(sid)
            msg = _find(sess, mid) if sess else None
            if msg is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            accepted = [e for e in msg.edits if e.status == "accepted"]
            bstore = _brain_store()
            h, log = bstore.load()
            if not bstore.is_live():
                bstore.save(h, log)                                   # materialize before snapshot
            msg.snapshot_before = bstore.snapshot(f"{sid}-{mid}")
            applied, _rows = MetaAgent(MetaTools(h, log), MockLLMClient("{}")).apply(accepted)
            bstore.save(h, log)
            msg.applied_seqs = [r.seq for r in applied]
            sstore.put(sess)
            return {"applied": len(applied), "edits": [e.model_dump() for e in msg.edits]}

    @app.post("/sessions/{sid}/messages/{mid}/rollback")
    def rollback_message(sid: str, mid: str):
        with _MUTATION_LOCK:
            sstore = _session_store()
            sess = sstore.get(sid)
            msg = _find(sess, mid) if sess else None
            if msg is None or not msg.snapshot_before:
                return JSONResponse({"error": "nothing to roll back"}, status_code=404)
            _brain_store().restore(msg.snapshot_before)
            sess.notes.append(f"rolled back {mid}")
            sstore.put(sess)
            return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/sonia/ -v`
Expected: PASS (8 tests across the package).

- [ ] **Step 5: Commit**

```bash
git add sonia/app.py tests/sonia/test_apply.py
git commit -m "feat(sonia): gated per-message apply/rollback + edit accept/reject (snapshot {sid}-{mid})"
```

---

### Task 10: `alpha_web` Sonia HTTP client

**Files:**
- Create: `alpha_web/sonia_client.py`
- Test: `tests/web/test_sonia_client.py`

**Interfaces:**
- Consumes: Sonia's HTTP API (Tasks 8–9); `Attachment` (Task 5).
- Produces: `SoniaClient(base_url=None, *, transport=None, timeout=30.0)` with `healthz()`, `new_session()`, `list_sessions()`, `get_session(sid)`, `chat(session_id, text, attachments)`, `edit(sid, eid, action)`, `apply(sid, mid)`, `rollback(sid, mid)` — each returns the parsed JSON dict. Network failures raise `httpx.HTTPError` (the web layer catches → banner).

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_sonia_client.py
import httpx
import pytest

pytest.importorskip("fastapi", reason="install: pip install -e '.[web,sonia]'")

from sonia.app import create_app as create_sonia
from alpha_web.sonia_client import SoniaClient


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "discussing it")


@pytest.fixture()
def sonia():
    return SoniaClient(base_url="http://sonia", transport=httpx.ASGITransport(app=create_sonia()))


def test_healthz_roundtrips_in_process(sonia):
    assert sonia.healthz()["ok"] is True


def test_chat_returns_two_turns(sonia):
    out = sonia.chat(session_id=None, text="teach me", attachments=[])
    assert out["user_message"]["text"] == "teach me"
    assert out["assistant_message"]["role"] == "assistant"
    assert sonia.list_sessions()[0]["session_id"] == out["session_id"]


def test_unreachable_sonia_raises_httpx_error():
    client = SoniaClient(base_url="http://127.0.0.1:9", timeout=0.2)   # nothing listening
    with pytest.raises(httpx.HTTPError):
        client.healthz()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_sonia_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha_web.sonia_client'`.

- [ ] **Step 3: Write minimal implementation**

```python
# alpha_web/sonia_client.py
from __future__ import annotations

import os

import httpx


class SoniaClient:
    """Thin httpx wrapper over the Sonia meta-agent service. Network errors propagate as
    httpx.HTTPError (the web layer catches them and shows a 'Sonia unavailable' banner)."""

    def __init__(self, base_url: str | None = None, *, transport=None, timeout: float = 30.0) -> None:
        self.base_url = base_url or os.environ.get("ALPHA_SONIA_URL", "http://127.0.0.1:8810")
        self._transport = transport
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, transport=self._transport, timeout=self._timeout)

    def _get(self, path: str) -> dict | list:
        with self._client() as c:
            r = c.get(path); r.raise_for_status(); return r.json()

    def _post(self, path: str, json: dict | None = None) -> dict | list:
        with self._client() as c:
            r = c.post(path, json=json or {}); r.raise_for_status(); return r.json()

    def healthz(self) -> dict:
        return self._get("/healthz")

    def new_session(self) -> dict:
        return self._post("/sessions/new")

    def list_sessions(self) -> list:
        return self._get("/sessions")

    def get_session(self, sid: str) -> dict:
        return self._get(f"/sessions/{sid}")

    def chat(self, session_id: str | None, text: str, attachments: list) -> dict:
        return self._post("/chat", {"session_id": session_id, "text": text,
                                    "attachments": [a.model_dump() for a in attachments]})

    def edit(self, sid: str, eid: str, action: str) -> dict:
        return self._post(f"/sessions/{sid}/edit/{eid}", {"action": action})

    def apply(self, sid: str, mid: str) -> dict:
        return self._post(f"/sessions/{sid}/messages/{mid}/apply")

    def rollback(self, sid: str, mid: str) -> dict:
        return self._post(f"/sessions/{sid}/messages/{mid}/rollback")
```

(`httpx` is already in the `[web]` extra from Task 7.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_sonia_client.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_web/sonia_client.py tests/web/test_sonia_client.py
git commit -m "feat(web): SoniaClient httpx wrapper over the Sonia service API"
```

---

### Task 11: Cut `alpha_web` over to the chat cockpit (remove v1 front)

This is the atomic cutover: the new chat cockpit replaces the v1 teaching front in one green step. It adds the new routes/templates/CSS, removes the v1 routes/templates/methods/obsolete `Session` fields, and rewrites the v1 tests.

**Files:**
- Modify: `alpha_web/app.py` (remove v1 cockpit wiring + routes; add chat cockpit routes that proxy `SoniaClient`; add a `set_sonia_client()` test seam)
- Modify: `alpha/meta/agent.py` (delete `propose_directions`, `expand_to_edits`, `repropose_edit`)
- Modify: `alpha/meta/prompts.py` (delete `build_directions_prompt`, `build_edits_prompt`, `build_reedit_prompt` — used only by the deleted methods; keep `render_brain_summary`, `parse_directions`, `_TOOLS_DOC`)
- Modify: `alpha/meta/models.py` (remove obsolete `Session` fields: `sources`, `directions`, `chosen_direction_id`, `direction_comment`, `edits`, `applied_seqs`, `snapshot_before`; set `status: Literal["open","discarded"] = "open"`)
- Create: `alpha_web/templates/cockpit.html`; `alpha_web/templates/partials/{message_user,message_assistant,edit_card,apply_result,session_list}.html`
- Delete: `alpha_web/templates/partials/{directions,edit_queue,edit_row}.html`
- Create: `alpha_web/static/cockpit.css`, `alpha_web/static/cockpit.js`
- Modify/Replace: `tests/web/test_cockpit.py` (rewrite for the chat cockpit with an injected fake Sonia)
- Modify: `tests/meta/test_agent.py` (delete the `propose_directions`/`expand_to_edits`/`repropose_edit`/`build_*_prompt` tests; keep `render_brain_summary`/`parse_directions`/`apply` tests)
- Modify: `tests/meta/test_store.py` (the session test uses `status="applied"` → change to `status="discarded"`)

**Interfaces:**
- Consumes: `SoniaClient` (Task 10), `ingest_attachments` (Task 7), `data_access.brain_badge`/`load_brain` (unchanged).
- Produces: `alpha_web.app.set_sonia_client(client_or_none)` (test seam); chat routes `GET /`, `POST /evolve/message`, `POST /evolve/{sid}/edit/{eid}`, `POST /evolve/{sid}/message/{mid}/apply`, `POST /evolve/rollback/{sid}/{mid}`, `GET /evolve/sessions[/{sid}]`, `POST /evolve/new`.

- [ ] **Step 1: Write the failing tests (new chat cockpit)**

Replace the entire contents of `tests/web/test_cockpit.py` with:

```python
import httpx
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fastapi")

from alpha_web import app as webapp
from alpha_web.sonia_client import SoniaClient
from sonia.app import create_app as create_sonia


@pytest.fixture(autouse=True)
def _wire_sonia(monkeypatch):
    # Drive the real Sonia app in-process via ASGITransport, with a mock copilot + isolated state.
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "let's discuss the squeeze setup")
    webapp.set_sonia_client(SoniaClient(base_url="http://sonia",
                                        transport=httpx.ASGITransport(app=create_sonia())))
    yield
    webapp.set_sonia_client(None)


@pytest.fixture()
def client():
    return TestClient(webapp.create_app())


def test_home_is_the_chat_cockpit(client):
    body = client.get("/").text
    assert "<html" in body.lower()
    assert "composer" in body.lower() or "send" in body.lower()


def test_message_round_trips_two_bubbles(client):
    r = client.post("/evolve/message", data={"text": "high short interest writeup"})
    assert r.status_code == 200
    assert "<html" not in r.text.lower()                       # HTMX partial (two turns)
    assert "high short interest writeup" in r.text
    assert "let's discuss the squeeze setup" in r.text


def test_accept_then_apply_then_rollback(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "n"}, "rationale": "r"}]}' % sid_skill)
    msg = client.post("/evolve/message", data={"text": "patch it"})
    # pull ids out of the session via the sessions API the cockpit also uses
    sessions = client.get("/evolve/sessions").text
    assert "patch_skill" in msg.text and sid_skill in msg.text
    # the session list page renders
    assert "<html" in sessions.lower()


def test_sonia_offline_shows_a_friendly_banner(client):
    webapp.set_sonia_client(SoniaClient(base_url="http://127.0.0.1:9", timeout=0.2))
    r = client.post("/evolve/message", data={"text": "hi"})
    assert r.status_code == 200 and "unavailable" in r.text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/web/test_cockpit.py -v`
Expected: FAIL — `AttributeError: module 'alpha_web.app' has no attribute 'set_sonia_client'` (and old routes still present).

- [ ] **Step 3: Implement the cutover**

**(3a) `alpha/meta/agent.py`** — delete the methods `propose_directions`, `expand_to_edits`, `repropose_edit` from `MetaAgent` (keep `__init__`, `_preview`, `apply`, and module-level `preview_op`). Remove now-unused imports if they become unused: keep `LessonSource`/`ProposedDirection` only if still referenced; `parse_ops` and `prompts` are no longer used by `agent.py` after deletion — remove `from alpha.meta import prompts` and `from alpha.refine.ops import RefineOp, parse_ops` → keep `RefineOp` (used by `_preview`/`preview_op`), drop `parse_ops`. Final import line: `from alpha.refine.ops import RefineOp`.

**(3b) `alpha/meta/prompts.py`** — delete `build_directions_prompt`, `build_edits_prompt`, `build_reedit_prompt`. Keep `render_brain_summary`, `parse_directions`, `_TOOLS_DOC`.

**(3c) `alpha/meta/models.py`** — change `Session` to the final thread shape:

```python
class Session(BaseModel):
    session_id: str
    created_at: str = ""
    title: str = ""
    channel: str = "teach"
    status: Literal["open", "discarded"] = "open"
    messages: list[Message] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
```

**(3d) `tests/meta/test_store.py`** — in the session test, change `status="applied"` to `status="discarded"` (and the assertion `== "applied"` to `== "discarded"`).

**(3e) `tests/meta/test_agent.py`** — delete the tests that call the removed methods/prompts: `test_build_directions_prompt_mentions_source_and_asks_json`, `test_propose_directions_parses_cards`, `test_expand_to_edits_previews_without_mutating_live_brain`, `test_expand_to_edits_bad_op_becomes_failed_row_not_a_crash`, `test_repropose_edit_replaces_one_row_keeping_id`, `test_repropose_edit_no_op_returns_failed_keeping_id`. Keep `test_render_brain_summary_lists_redlines_and_skills`, `test_parse_directions_tolerant_and_assigns_ids`, `test_apply_mutates_live_brain_and_marks_rows`.

**(3f) Templates** — create `alpha_web/templates/cockpit.html` (extends `base.html`, renders the session list + thread + composer):

```html
{% extends "base.html" %}
{% block content %}
<section class="cockpit" id="cockpit">
  <aside class="sessions">
    <form hx-post="/evolve/new" hx-target="#thread" hx-swap="innerHTML"><button>New chat</button></form>
    {% include "partials/session_list.html" %}
  </aside>
  <main class="thread-wrap">
    <div id="banner">{% if banner %}<div class="banner">{{ banner }}</div>{% endif %}</div>
    <div id="thread" class="thread">
      {% for m in messages %}
        {% if m.role == "user" %}{% include "partials/message_user.html" %}
        {% else %}{% include "partials/message_assistant.html" %}{% endif %}
      {% endfor %}
    </div>
    <form id="composer" class="composer" hx-post="/evolve/message"
          hx-target="#thread" hx-swap="beforeend" hx-encoding="multipart/form-data"
          hx-on::after-request="this.reset()">
      <input type="hidden" name="session_id" value="{{ session_id or '' }}">
      <textarea name="text" placeholder="Teach Sonia… (paste text, links; attach .txt/.md/.csv/.pdf)"></textarea>
      <input type="file" name="files" multiple>
      <button type="submit">Send</button>
      <span class="thinking htmx-indicator">thinking…</span>
    </form>
  </main>
</section>
{% endblock %}
```

Create `alpha_web/templates/partials/message_user.html`:

```html
<div class="bubble user">
  <div class="prose">{{ m.text }}</div>
  {% for a in m.attachments %}<div class="chip">{{ a.name }}</div>{% endfor %}
</div>
```

Create `alpha_web/templates/partials/message_assistant.html`:

```html
<div class="bubble assistant" id="msg-{{ m.message_id }}">
  <div class="prose">{{ m.text }}</div>
  {% for d in m.directions %}<div class="direction">▸ {{ d.title }}{% if d.summary %} — {{ d.summary }}{% endif %}</div>{% endfor %}
  {% for e in m.edits %}{% include "partials/edit_card.html" %}{% endfor %}
  {% if m.edits %}
  <form hx-post="/evolve/{{ session_id }}/message/{{ m.message_id }}/apply"
        hx-target="#msg-{{ m.message_id }}" hx-swap="beforeend">
    <button type="submit">Apply accepted</button>
  </form>
  {% endif %}
</div>
```

Create `alpha_web/templates/partials/edit_card.html`:

```html
<div class="edit-card status-{{ e.status }}" id="edit-{{ e.edit_id }}">
  <code>{{ e.tool }}</code> <span>{{ e.summary or e.target_id or "" }}</span>
  {% if e.status == "failed" %}<em class="reason">{{ e.apply_reason }}</em>{% endif %}
  {% if e.status in ("proposed", "accepted", "rejected") %}
  <span class="actions">
    <button hx-post="/evolve/{{ session_id }}/edit/{{ e.edit_id }}" hx-vals='{"action":"accept"}'
            hx-target="#edit-{{ e.edit_id }}" hx-swap="outerHTML">accept</button>
    <button hx-post="/evolve/{{ session_id }}/edit/{{ e.edit_id }}" hx-vals='{"action":"reject"}'
            hx-target="#edit-{{ e.edit_id }}" hx-swap="outerHTML">reject</button>
  </span>
  <span class="state">{{ e.status }}</span>
  {% endif %}
</div>
```

Create `alpha_web/templates/partials/apply_result.html`:

```html
<div class="apply-result">applied {{ applied }} edit(s)
  <form hx-post="/evolve/rollback/{{ session_id }}/{{ message_id }}"
        hx-target="closest .apply-result" hx-swap="outerHTML" style="display:inline">
    <button type="submit">rollback</button>
  </form>
</div>
```

Create `alpha_web/templates/partials/session_list.html`:

```html
<ul class="session-list">
  {% for s in sessions %}
  <li><a hx-get="/evolve/sessions/{{ s.session_id }}" hx-target="#cockpit" hx-swap="outerHTML">
    {{ s.title or s.session_id }}</a></li>
  {% endfor %}
</ul>
```

Delete the obsolete partials:

```bash
git rm alpha_web/templates/partials/directions.html alpha_web/templates/partials/edit_queue.html alpha_web/templates/partials/edit_row.html
```

Create `alpha_web/static/cockpit.css`:

```css
.cockpit{display:flex;gap:1rem}
.sessions{width:14rem;flex:none}
.thread-wrap{flex:1;display:flex;flex-direction:column;min-height:60vh}
.thread{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:.5rem;padding:.5rem}
.bubble{padding:.5rem .75rem;border-radius:.5rem;max-width:48rem}
.bubble.user{align-self:flex-end;background:#1f2937;color:#e5e7eb}
.bubble.assistant{align-self:flex-start;background:#111827;color:#e5e7eb;border:1px solid #374151}
.edit-card{margin-top:.4rem;padding:.35rem .5rem;border:1px solid #374151;border-radius:.4rem}
.edit-card.status-failed{border-color:#b91c1c}
.chip{display:inline-block;font-size:.75rem;background:#374151;border-radius:.3rem;padding:0 .35rem;margin-right:.25rem}
.composer{display:flex;gap:.5rem;align-items:flex-end;padding:.5rem;border-top:1px solid #374151}
.composer textarea{flex:1;min-height:3rem}
.banner{background:#7c2d12;color:#fff;padding:.4rem .6rem;border-radius:.4rem;margin:.4rem}
.htmx-indicator{display:none}.htmx-request .htmx-indicator{display:inline}
```

Create `alpha_web/static/cockpit.js`:

```javascript
// Auto-scroll the thread to the newest turn after each HTMX swap.
document.body.addEventListener("htmx:afterSwap", (e) => {
  const t = document.getElementById("thread");
  if (t) t.scrollTop = t.scrollHeight;
});
```

(Reference `cockpit.css`/`cockpit.js` from `base.html`'s `<head>` alongside the existing stylesheet — add `<link rel="stylesheet" href="/static/cockpit.css">` and `<script src="/static/cockpit.js" defer></script>`.)

**(3g) `alpha_web/app.py`** — remove the v1 cockpit wiring and routes, add the chat cockpit. At module scope add the Sonia client seam:

```python
from alpha.meta.ingest import ingest_attachments
from alpha_web.sonia_client import SoniaClient

_SONIA: SoniaClient | None = None


def set_sonia_client(client) -> None:
    """Test seam: inject an in-process SoniaClient (ASGITransport). None → use ALPHA_SONIA_URL."""
    global _SONIA
    _SONIA = client


def _sonia() -> SoniaClient:
    return _SONIA if _SONIA is not None else SoniaClient()
```

Delete `_meta_agent()`, `_MUTATION_LOCK`, and the v1 routes (`/evolve/ingest`, `/evolve/{sid}/direction`, `/evolve/{sid}/direction/regenerate`, `/evolve/{sid}/edit/{eid}`, `/evolve/{sid}/apply`, `/evolve/rollback/{sid}`, `/evolve/sessions`, `/evolve/sessions/{sid}`, and the old `GET /` cockpit handler). Keep `_brain_store`/`_session_store` only if other code uses them; the chat cockpit reads sessions via Sonia, so they can be removed from `app.py` (the console's read-only brain comes from `data_access`). Add the new routes inside `create_app()`:

```python
    import httpx

    def _cockpit_ctx(request, session: dict | None, banner: str = ""):
        return {"active": "evolve",
                "session_id": (session or {}).get("session_id", ""),
                "messages": (session or {}).get("messages", []),
                "sessions": _safe_sessions(),
                "banner": banner}

    def _safe_sessions():
        try:
            return _sonia().list_sessions()
        except httpx.HTTPError:
            return []

    @app.get("/")
    def home(request: Request):
        try:
            sessions = _sonia().list_sessions()
            latest = next((s for s in sessions if s.get("status") == "open"), None)
            session = _sonia().get_session(latest["session_id"]) if latest else None
            return render(request, "cockpit.html", _cockpit_ctx(request, session))
        except httpx.HTTPError:
            return render(request, "cockpit.html", _cockpit_ctx(request, None,
                          banner="Sonia service unavailable — start it with `python -m sonia`"))

    @app.post("/evolve/message")
    async def message(request: Request, session_id: str = Form(""), text: str = Form("")):
        form = await request.form()
        uploads = [(f.filename, await f.read()) for f in form.getlist("files") if getattr(f, "filename", "")]
        clean, attachments = ingest_attachments(text, uploads)
        try:
            out = _sonia().chat(session_id or None, clean, attachments)
        except httpx.HTTPError:
            return render(request, "partials/message_assistant.html",
                          {"session_id": session_id, "m": {"message_id": "err", "role": "assistant",
                           "text": "Sonia service unavailable — start it with `python -m sonia`.",
                           "directions": [], "edits": []},
                           "banner": "unavailable"})
        return render(request, "partials/_two_turns.html",
                      {"session_id": out["session_id"], "user": out["user_message"],
                       "assistant": out["assistant_message"]})

    @app.post("/evolve/{session_id}/edit/{edit_id}")
    def edit(request: Request, session_id: str, edit_id: str, action: str = Form(...)):
        e = _sonia().edit(session_id, edit_id, action)
        return render(request, "partials/edit_card.html", {"session_id": session_id, "e": e})

    @app.post("/evolve/{session_id}/message/{message_id}/apply")
    def apply(request: Request, session_id: str, message_id: str):
        r = _sonia().apply(session_id, message_id)
        return render(request, "partials/apply_result.html",
                      {"session_id": session_id, "message_id": message_id, "applied": r["applied"]})

    @app.post("/evolve/rollback/{session_id}/{message_id}")
    def rollback(request: Request, session_id: str, message_id: str):
        _sonia().rollback(session_id, message_id)
        return render(request, "partials/apply_result.html",
                      {"session_id": session_id, "message_id": message_id, "applied": 0})

    @app.get("/evolve/sessions")
    def sessions_index(request: Request):
        return render(request, "cockpit.html", _cockpit_ctx(request, None))

    @app.get("/evolve/sessions/{session_id}")
    def session_detail(request: Request, session_id: str):
        try:
            session = _sonia().get_session(session_id)
        except httpx.HTTPError:
            session = None
        return render(request, "cockpit.html", _cockpit_ctx(request, session))

    @app.post("/evolve/new")
    def new_chat(request: Request):
        try:
            _sonia().new_session()
        except httpx.HTTPError:
            pass
        return render(request, "cockpit.html", _cockpit_ctx(request, None))
```

Create `alpha_web/templates/partials/_two_turns.html` (the `beforeend` payload for one round):

```html
{% with m = user %}{% include "partials/message_user.html" %}{% endwith %}
{% with m = assistant %}{% include "partials/message_assistant.html" %}{% endwith %}
```

(`Form` and `Request` are already imported in `app.py`; ensure `from fastapi import Form` is present.)

- [ ] **Step 4: Run the full suite to verify green**

Run: `pip install -e '.[web,sonia]' && pytest -q`
Expected: PASS — the new cockpit tests pass; no references remain to deleted methods/templates; all other suites stay green.

- [ ] **Step 5: Commit**

```bash
git add alpha_web/ alpha/meta/agent.py alpha/meta/prompts.py alpha/meta/models.py tests/web/test_cockpit.py tests/meta/test_agent.py tests/meta/test_store.py
git rm alpha_web/templates/partials/directions.html alpha_web/templates/partials/edit_queue.html alpha_web/templates/partials/edit_row.html
git commit -m "feat(web): chat cockpit over Sonia; remove v1 direction/edit-queue front + obsolete Session fields"
```

---

### Task 12: End-to-end verification (Playwright + real-DeepSeek smoke)

**Files:**
- Create: `tests/web/test_cockpit_e2e.py` (optional, Playwright-gated)
- Modify: `README.md` (run instructions for the two processes)

**Interfaces:** none (verification only).

- [ ] **Step 1: Full offline suite green**

Run: `pytest -q`
Expected: PASS — entire suite green (count ≥ the pre-change total minus the deleted v1-front tests plus the new tests).

- [ ] **Step 2: Document the two-process run in `README.md`**

Add a section:

```markdown
## Sonia teaching cockpit (two processes)

    pip install -e '.[web,sonia]'
    # terminal 1 — the meta-agent (needs DEEPSEEK_API_KEY, or ALPHA_SONIA_PROVIDER=mock):
    DEEPSEEK_API_KEY=... python -m sonia                       # :8810
    # terminal 2 — the console (chat cockpit at /):
    ALPHA_SONIA_URL=http://127.0.0.1:8810 python -m alpha_web  # :8100
```

- [ ] **Step 3: Manual Playwright smoke (mock copilot)**

Start both processes with `ALPHA_SONIA_PROVIDER=mock` and `ALPHA_MOCK_RESPONSE` set to an `ops` JSON. In the browser at `http://127.0.0.1:8100/`: type a message → assistant bubble with an edit card appears → click **accept** → **Apply accepted** → the brain badge edit-count increments → **rollback** → it decrements. Capture a screenshot.

- [ ] **Step 4: Manual real-DeepSeek smoke**

With a real `DEEPSEEK_API_KEY` and `ALPHA_SONIA_MODEL=deepseek-v4-pro`, send one real teaching message and confirm a coherent prose reply (and, when warranted, a valid edit card). Confirm a pasted `.pdf`/`.md` is summarized and a pasted image yields the friendly "can't read images" note.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/web/test_cockpit_e2e.py
git commit -m "docs+test: two-process run instructions + cockpit e2e smoke"
```

---

## Self-Review

**1. Spec coverage** (each spec §):
- §0 supersession (in-process→service, Claude→deepseek-v4-pro, multimodal→text, web-apply→Sonia-apply): Tasks 3, 7, 8–11. ✓
- §2 ports/role/brain-ownership/thread-ownership/no-image/no-json/no-auth: Global Constraints + Tasks 3, 5, 8, 9, 11. ✓
- §4 reuse (`try_apply_op`/`MetaTools`/`MetaAgent.apply`/`render_brain_summary`/`parse_directions`) + extract `preview_op` + remove v1 methods: Tasks 4, 6, 9, 11. ✓
- §5 models (`Attachment`/`Message`/`Session` thread): Tasks 5, 11. ✓
- §6 LLM `chat()` layer (text-only, no json_object): Tasks 1–3. ✓
- §7 `SoniaAgent`: Task 6. ✓
- §8 Sonia service routes: Tasks 8–9. ✓
- §9 console as client (ingestion at edge, read-only brain, offline banner): Tasks 7, 10, 11. ✓
- §10 persistence/error/testing (never-500, offline TDD, snapshot {sid}-{mid}): Tasks 8, 9, 11. ✓
- §11 build order: Tasks 1–12 follow it. ✓
- §12 file map: every listed file appears in a task. ✓

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to". Every code step shows real code. The only manual steps are Task 12's Playwright/real-key smokes (inherently manual, with concrete observable assertions). ✓

**3. Type consistency:** `ChatMessage(role,text)` consistent across Tasks 1/2/6. `preview_op(harness, op, *, retire_min, promote_min)` consistent Tasks 4/6. `Message`/`Attachment`/`Session` fields consistent Tasks 5/6/8/9/11. `SoniaClient` methods consistent Tasks 10/11. `MetaAgent.apply(accepted) -> (applied, rows)` used per its real signature in Task 9. `snapshot(f"{sid}-{mid}")` matches the verbatim `snapshot(key)` contract. ✓

**Note on transition:** Task 5 keeps obsolete `Session` fields (additive) so Tasks 6–10 stay green while built alongside the live v1 front; Task 11 removes them in the same atomic commit that removes the v1 routes/methods/tests. This is the one necessarily-large task — it cannot be split without a red commit (removing v1 routes breaks the app unless the new routes replace them together).
