# Teach → Modification: On-Demand Crystallization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a teaching conversation reliably and observably become a committed modification to the harness `H`, by splitting prose chat from an explicit, deterministic "Propose an edit" crystallization pass.

**Architecture:** The teach→apply write-waist (`try_apply_op` → `MetaTools` → one `EditRecord`) is already wired and stays untouched. The fragile hop is *upstream* of the gate: `SoniaAgent.respond` mines an **optional** ops block out of a text-only chat reply, and `parse_ops` swallows failures into `[]` (silent). This plan (a) makes chat prose-only, (b) adds an on-demand extractor that calls `LLMClient.complete()` in enforced-JSON mode, forced to return `{"ops":[...]}` **or** `{"no_edit":true,"reason":...}` — never silent, always parseable — and (c) renders every outcome. Everything downstream of `preview_op` is unchanged.

**Tech Stack:** Python 3, pydantic v2 (frozen value objects), FastAPI + Jinja2 + HTMX, pytest (offline via `MockLLMClient`, `temperature=0`).

**Design spec:** `docs/superpowers/specs/2026-07-01-teach-crystallize-design.md`

## Global Constraints

- **One write-waist (invariant §5.2):** every brain mutation flows through `refine/apply.try_apply_op` → `harness/metatools.MetaTools` → exactly one `EditRecord`. The extractor is strictly upstream of `preview_op`; **add no side channel that mutates `H`.**
- **Read-only propose:** the extractor calls `client.complete()` (read) and `preview_op` runs on a `deepcopy`; the propose pass writes only the *session*, never the brain.
- **All English** in code, comments, docs.
- **Frozen pydantic v2** for value objects (`model_config = ConfigDict(frozen=True)` or `class Config`); additive model fields default-empty so existing persisted sessions deserialize unchanged.
- **Tests are offline:** `MockLLMClient` replays a scripted string for both `.chat()` and `.complete()`; `ALPHA_SONIA_PROVIDER=mock` + `ALPHA_MOCK_RESPONSE=<json>` drives Sonia in-process. `temperature=0`.
- **Tests mirror `alpha/`**; add a test next to the code you change. Full suite: `python -m pytest -q`.
- **Scope fences (do NOT touch in this plan):** apply atomicity / batch transaction; two-face consolidation; `conflict_queue` on the teach path; per-direction crystallization. These are deferred (see spec §10).

---

## File Structure

**Created**
- `alpha/meta/extractor.py` — `ExtractionResult` + `extract_ops()` (the deterministic crystallization pass).
- `tests/meta/test_extractor.py` — extractor unit tests.
- `alpha_web/templates/partials/_propose_area.html` — the per-turn propose control (button / chip / no-edit note).
- `alpha_web/templates/partials/_propose_result.html` — the `/propose` HTMX response (propose-area swap + OOB `#pending`).

**Modified**
- `alpha/refine/ops.py` — extract `_parse_op_items()` helper (DRY); add `parse_extraction()`.
- `alpha/meta/prompts.py` — add `render_extraction_system()` + `render_conversation()`.
- `alpha/meta/models.py` — add `Message.proposal_note: str = ""`.
- `alpha/meta/sonia_agent.py` — `respond()` becomes prose-only; promote `_turn_text` → public `turn_text`; drop ops solicitation from `_INSTRUCTIONS`.
- `sonia/app.py` — add `POST /sessions/{sid}/messages/{mid}/propose`.
- `alpha_web/sonia_client.py` — add `propose()`.
- `alpha_web/app.py` — add `POST /evolve/{session_id}/message/{message_id}/propose`; (Task 6) thread `materialized` into `brain_view` call sites.
- `alpha_web/templates/partials/message_assistant.html` — replace the inline chip with a `propose-area` container.
- `alpha_web/drawer.py` — (Task 6) `brain_view(state, *, materialized=True)` + `BrainView.materialized`.
- `alpha_web/templates/partials/_brain_panel.html` — (Task 6) "seeds · no live edits yet" badge.

**Migrated tests** (existing tests that assume *chat* produces ops — each fixed in the task that breaks it)
- `tests/meta/test_sonia_agent.py` (Task 3)
- `tests/sonia/test_chat.py` (Task 4)
- `tests/web/test_drawer.py` (Task 5, Task 6)

---

## Task 1: `parse_extraction` — deterministic parse of the crystallization reply

**Files:**
- Modify: `alpha/refine/ops.py`
- Test: `tests/refine/test_ops.py`

**Interfaces:**
- Consumes: `extract_json_object(raw: str) -> str | None` (`alpha/llm/extract.py`); `RefineOp` (same file).
- Produces:
  - `alpha.refine.ops._parse_op_items(raw_ops: list) -> list[RefineOp]` — the per-item validation loop, extracted from `parse_ops` (DRY).
  - `alpha.refine.ops.parse_extraction(raw: str) -> tuple[list[RefineOp], bool, str]` — `(ops, no_edit, reason)`. Never raises; empty/unknown/malformed → `([], True, <reason>)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/refine/test_ops.py`:

```python
from alpha.refine.ops import parse_extraction


def test_parse_extraction_returns_ops_when_present():
    raw = '{"ops":[{"tool":"process_memory","args":{"lesson_id":"l1"},"rationale":"r"}]}'
    ops, no_edit, reason = parse_extraction(raw)
    assert no_edit is False and reason == ""
    assert [o.tool for o in ops] == ["process_memory"]


def test_parse_extraction_no_edit_carries_reason():
    ops, no_edit, reason = parse_extraction('{"no_edit": true, "reason": "still clarifying"}')
    assert ops == [] and no_edit is True and reason == "still clarifying"


def test_parse_extraction_empty_object_falls_back_never_silent():
    ops, no_edit, reason = parse_extraction("{}")
    assert ops == [] and no_edit is True and reason        # non-empty fallback reason


def test_parse_extraction_malformed_is_no_edit_not_crash():
    for raw in ("not json at all", '{"ops": 5}', '{"ops": []}', ""):
        ops, no_edit, reason = parse_extraction(raw)
        assert ops == [] and no_edit is True and reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/refine/test_ops.py -k parse_extraction -v`
Expected: FAIL with `ImportError: cannot import name 'parse_extraction'`.

- [ ] **Step 3: Refactor `parse_ops` to share `_parse_op_items`, add `parse_extraction`**

In `alpha/refine/ops.py`, replace the body of the item loop in `parse_ops` with a call to a new shared helper, and add `parse_extraction`. Final state of the two functions:

```python
def _parse_op_items(raw_ops: list) -> list[RefineOp]:
    """Validate a list of raw op dicts into RefineOps; drop malformed items (reject-don't-crash).
    Empty rationale is kept as '' (rejected later at apply time)."""
    ops: list[RefineOp] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            continue
        args = item.get("args")
        if args is None:
            args = {}
        elif not isinstance(args, dict):
            continue
        rationale = item.get("rationale")
        if not isinstance(rationale, str):
            rationale = ""
        ops.append(RefineOp(tool=tool, args=args, rationale=rationale))
    return ops


def parse_ops(raw: str) -> list[RefineOp]:
    """Pull {"ops": [...]} from prose/fenced/thinking-prefixed LLM text; drop malformed items.
    Any structural failure yields []. Empty rationale is kept as '' (rejected later at apply time)."""
    extracted = extract_json_object(raw)
    if extracted is None:
        return []
    try:
        data = json.loads(extracted)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw_ops = data.get("ops")
    if not isinstance(raw_ops, list):       # non-list ops (5, "x", {}) -> no edits (reject-don't-crash)
        return []
    return _parse_op_items(raw_ops)


def parse_extraction(raw: str) -> tuple[list[RefineOp], bool, str]:
    """Parse the enforced-JSON crystallization reply into (ops, no_edit, reason). NEVER silent:
    - dict with a non-empty valid 'ops' list  -> (ops, False, "")
    - dict with truthy 'no_edit'               -> ([], True, reason or "no edit proposed")
    - anything else (empty/unknown/malformed)  -> ([], True, "model proposed no ops")."""
    extracted = extract_json_object(raw)
    data = None
    if extracted is not None:
        try:
            data = json.loads(extracted)
        except (json.JSONDecodeError, ValueError):
            data = None
    if not isinstance(data, dict):
        return [], True, "model returned no parseable JSON"
    raw_ops = data.get("ops")
    if isinstance(raw_ops, list):
        ops = _parse_op_items(raw_ops)
        if ops:
            return ops, False, ""
    if data.get("no_edit"):
        reason = data.get("reason")
        return [], True, reason if isinstance(reason, str) and reason.strip() else "no edit proposed"
    return [], True, "model proposed no ops"
```

- [ ] **Step 4: Run tests to verify they pass (and `parse_ops` regressions still pass)**

Run: `python -m pytest tests/refine/test_ops.py -v`
Expected: PASS (all existing `parse_ops` tests + the four new `parse_extraction` tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/ops.py tests/refine/test_ops.py
git commit -m "feat(refine): parse_extraction for the crystallization reply (DRY _parse_op_items)"
```

---

## Task 2: `extract_ops` — the deterministic crystallization pass

**Files:**
- Create: `alpha/meta/extractor.py`
- Modify: `alpha/meta/prompts.py`
- Test: `tests/meta/test_extractor.py`

**Interfaces:**
- Consumes: `parse_extraction` (Task 1); `LLMClient` (`alpha/llm/client.py`, has `.complete(system, user) -> str`); `ChatMessage` (`alpha/llm/chat.py`); `HarnessState`; `render_brain_summary` + `_TOOLS_DOC` (`alpha/meta/prompts.py`).
- Produces:
  - `alpha.meta.prompts.render_extraction_system(h: HarnessState) -> str`
  - `alpha.meta.prompts.render_conversation(messages: list[ChatMessage]) -> str`
  - `alpha.meta.extractor.ExtractionResult` (frozen; `ops: list[RefineOp]`, `no_edit: bool`, `reason: str`)
  - `alpha.meta.extractor.extract_ops(client: LLMClient, h: HarnessState, conversation: list[ChatMessage]) -> ExtractionResult`

- [ ] **Step 1: Write the failing tests**

Create `tests/meta/test_extractor.py`:

```python
from alpha.harness.loader import load_seeds
from alpha.llm.chat import ChatMessage
from alpha.llm.client import MockLLMClient
from alpha.meta.extractor import ExtractionResult, extract_ops
from alpha.meta import prompts


def _convo():
    return [ChatMessage(role="user", text="make gap-fails taboo"),
            ChatMessage(role="assistant", text="noted — want me to record that?")]


def test_extract_ops_returns_ops_from_enforced_json():
    h = load_seeds("seeds")
    reply = '{"ops":[{"tool":"process_memory","args":{"lesson_id":"l1","lesson":"x","outcome":"principle"},"rationale":"the operator asked"}]}'
    res = extract_ops(MockLLMClient(reply), h, _convo())
    assert isinstance(res, ExtractionResult)
    assert res.no_edit is False and [o.tool for o in res.ops] == ["process_memory"]


def test_extract_ops_no_edit_is_explicit_not_silent():
    h = load_seeds("seeds")
    res = extract_ops(MockLLMClient('{"no_edit": true, "reason": "still clarifying the VWAP window"}'), h, _convo())
    assert res.ops == [] and res.no_edit is True and "VWAP" in res.reason


def test_extract_ops_uses_complete_with_brain_and_conversation():
    h = load_seeds("seeds")
    client = MockLLMClient('{"no_edit": true, "reason": "r"}')
    extract_ops(client, h, _convo())
    system, user = client.calls[0]                 # .complete records (system, user)
    assert "RED-LINE" in system                    # brain summary present
    assert "process_memory" in system              # the op vocabulary (_TOOLS_DOC) present
    assert "make gap-fails taboo" in user          # the conversation is in the user prompt


def test_render_conversation_serialises_roles_and_text():
    out = prompts.render_conversation([ChatMessage(role="user", text="hi"),
                                       ChatMessage(role="assistant", text="hello")])
    assert "hi" in out and "hello" in out and "user" in out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/meta/test_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha.meta.extractor'`.

- [ ] **Step 3: Add the prompt helpers**

Append to `alpha/meta/prompts.py`:

```python
from alpha.llm.chat import ChatMessage

_EXTRACTION_INSTRUCTION = (
    "\n\nYou are crystallizing the conversation above into brain edits. Output ONLY a single JSON "
    "object, no prose outside it. If the conversation warrants concrete, specific brain change(s), "
    'output {"ops": [{"tool":..., "args":..., "rationale":...}, ...]} using the EXACT tool vocabulary '
    "above, with a non-empty rationale on every op. If it does NOT yet warrant a concrete change "
    '(too vague, still clarifying, purely conversational), output '
    '{"no_edit": true, "reason": "<one sentence why>"}.'
)


def render_extraction_system(h: HarnessState) -> str:
    """System prompt for the deterministic crystallization pass: the live brain + the op vocabulary
    + the strict either-ops-or-no_edit instruction."""
    return render_brain_summary(h) + "\n\n" + _TOOLS_DOC + _EXTRACTION_INSTRUCTION


def render_conversation(messages: list[ChatMessage]) -> str:
    """Serialize the conversation (up to and including the target turn) into the user prompt."""
    return "\n\n".join(f"{m.role.upper()}: {m.text}" for m in messages)
```

- [ ] **Step 4: Create the extractor**

Create `alpha/meta/extractor.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.state import HarnessState
from alpha.llm.chat import ChatMessage
from alpha.llm.client import LLMClient
from alpha.meta import prompts
from alpha.refine.ops import RefineOp, parse_extraction


class ExtractionResult(BaseModel):
    """Outcome of one crystallization pass. `ops` is empty iff `no_edit`; `reason` is populated
    when `no_edit` (a one-sentence why, always non-empty)."""
    model_config = ConfigDict(frozen=True)
    ops: list[RefineOp] = Field(default_factory=list)
    no_edit: bool = False
    reason: str = ""


def extract_ops(client: LLMClient, h: HarnessState, conversation: list[ChatMessage]) -> ExtractionResult:
    """Deterministic crystallization: render (brain + op vocabulary) and (conversation), call
    client.complete() [enforced json_object on openai_compat], parse into ops-or-no_edit. Read-only
    on `h`. Never returns silently — parse_extraction guarantees a reason when no ops."""
    system = prompts.render_extraction_system(h)
    user = prompts.render_conversation(conversation)
    raw = client.complete(system, user)
    ops, no_edit, reason = parse_extraction(raw)
    return ExtractionResult(ops=ops, no_edit=no_edit, reason=reason)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/meta/test_extractor.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add alpha/meta/extractor.py alpha/meta/prompts.py tests/meta/test_extractor.py
git commit -m "feat(meta): extract_ops crystallization pass (complete() enforced-JSON, ops-or-no_edit)"
```

---

## Task 3: Chat becomes prose-only; add `Message.proposal_note`

**Files:**
- Modify: `alpha/meta/models.py`
- Modify: `alpha/meta/sonia_agent.py`
- Test: `tests/meta/test_sonia_agent.py` (migrate two tests)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `alpha.meta.models.Message.proposal_note: str = ""` (additive, default-empty).
  - `alpha.meta.sonia_agent.turn_text(m: Message) -> str` (public; was `_turn_text`).
  - `SoniaAgent.respond()` now always returns `edits == []` (chat no longer parses ops); `directions` still parsed.

- [ ] **Step 1: Migrate the two failing tests + add the prose-only guarantee**

In `tests/meta/test_sonia_agent.py`: **delete** `test_ops_become_dryrun_edit_cards_without_mutating_brain` and `test_redline_op_becomes_failed_card` (that behavior now belongs to the extractor / `/propose` path — covered in Task 2 and Task 4). **Add** this test in their place:

```python
def test_respond_is_prose_only_even_when_reply_contains_ops():
    # Chat must NOT crystallize ops anymore — even if the model volunteers an ops block, respond()
    # returns prose + zero edit cards. Crystallization happens only via the on-demand /propose pass.
    scripted = ('sure. {"ops": [{"tool": "patch_skill", "args": {"skill_id": "x"}, "rationale": "r"}]}')
    agent, _ = _agent(scripted)
    out = agent.respond(Session(session_id="s1"), _user())
    assert out.role == "assistant"
    assert out.edits == []                       # prose-only: no cards from chat
```

(Keep `test_prose_only_makes_no_cards`, `test_directions_become_direction_cards`, and `test_history_is_threaded_into_the_chat_call` unchanged — they already pass.)

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `python -m pytest tests/meta/test_sonia_agent.py::test_respond_is_prose_only_even_when_reply_contains_ops -v`
Expected: FAIL — `out.edits` currently has 1 item (respond still calls `parse_ops`).

- [ ] **Step 3: Add the `proposal_note` field**

In `alpha/meta/models.py`, add one line to `Message` (after `applied_seqs`):

```python
    applied_seqs: list[int] = Field(default_factory=list)
    proposal_note: str = ""          # set when a /propose pass yielded no edit (the visible reason)
```

- [ ] **Step 4: Make `respond` prose-only + promote `turn_text`**

In `alpha/meta/sonia_agent.py`:

1. Rename `_turn_text` → `turn_text` (public), and update its caller in `_history`.
2. In `respond`, delete the `edits = [...]` list-comprehension line and the `parse_ops` import; pass `edits=[]`.
3. Trim `_INSTRUCTIONS` so it no longer solicits an ops block.

Final state of the relevant pieces:

```python
from alpha.harness.metatools import MetaTools
from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.extract import extract_json_object
from alpha.meta import prompts
from alpha.meta.models import Message, Session, new_message_id, now_iso

_INSTRUCTIONS = (
    "\n\nYou are Sonia, a US speculative-momentum trading co-pilot. Discuss freely, ask clarifying "
    "questions, and think out loud with the operator. You may optionally append a SINGLE fenced JSON "
    "object with \"directions\" (each {\"title\":..., \"summary\":...}) to surface candidate changes — "
    "but do NOT emit brain edits here; the operator crystallizes edits explicitly on demand."
)


def turn_text(m: Message) -> str:
    extra = "\n\n".join(a.text for a in m.attachments if a.text)
    return (m.text + ("\n\n" + extra if extra else "")).strip()
```

```python
    def _history(self, session: Session, user_message: Message) -> list[ChatMessage]:
        msgs = [ChatMessage(role=m.role, text=turn_text(m)) for m in session.messages]
        msgs.append(ChatMessage(role="user", text=turn_text(user_message)))
        return msgs

    def respond(self, session: Session, user_message: Message) -> Message:
        reply = self.copilot.chat(self._system(), self._history(session, user_message))
        block = extract_json_object(reply)
        prose = reply.replace(block, "").strip() if block else reply.strip()
        directions = prompts.parse_directions(reply)
        return Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                       text=prose, directions=directions, edits=[])
```

(Remove the now-unused imports `from alpha.meta.agent import preview_op` and `from alpha.refine.ops import parse_ops`.)

- [ ] **Step 5: Run the meta suite**

Run: `python -m pytest tests/meta/test_sonia_agent.py tests/meta/test_models.py -v`
Expected: PASS (the new prose-only test passes; the two deleted tests are gone; models test unaffected by the additive field).

- [ ] **Step 6: Commit**

```bash
git add alpha/meta/models.py alpha/meta/sonia_agent.py tests/meta/test_sonia_agent.py
git commit -m "feat(meta): chat is prose-only; add Message.proposal_note; promote turn_text"
```

---

## Task 4: Sonia `POST /sessions/{sid}/messages/{mid}/propose`

**Files:**
- Modify: `sonia/app.py`
- Test: `tests/sonia/test_chat.py` (migrate one test + add propose coverage)

**Interfaces:**
- Consumes: `extract_ops` (Task 2); `preview_op` (`alpha/meta/agent.py`); `turn_text` (Task 3); `Message.proposal_note` (Task 3); `make_client` (`alpha/llm/config.py`); `ChatMessage`.
- Produces: `POST /sessions/{sid}/messages/{mid}/propose` → `200 {"session_id", "message": <msg dict>}`; `404` if session/message missing; `409` if the turn is already applied; `502` if the extractor call fails.

- [ ] **Step 1: Migrate the chat-ops test + add propose tests**

In `tests/sonia/test_chat.py`: **replace** `test_chat_with_ops_returns_edit_cards` with a prose-only assertion, and **add** the propose tests:

```python
def test_chat_never_returns_edit_cards_now(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s"}, "rationale": "r"}]}' % sid)
    body = client.post("/chat", json={"text": "patch it"}).json()
    assert body["assistant_message"]["edits"] == []      # chat is prose-only; edits come from /propose


def _seed_turn(client, mock, monkeypatch):
    """Create a session with one user+assistant turn; return (sid, assistant message_id)."""
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", mock)
    body = client.post("/chat", json={"text": "teach me"}).json()
    return body["session_id"], body["assistant_message"]["message_id"]


def test_propose_crystallizes_ops_into_edit_cards(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    skid = load_seeds("seeds").skills.all()[0].skill_id
    sid, mid = _seed_turn(client, "let's discuss", monkeypatch)
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"%s","notes":"n"},"rationale":"r"}]}' % skid)
    body = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()
    edits = body["message"]["edits"]
    assert len(edits) == 1 and edits[0]["status"] == "proposed" and edits[0]["tool"] == "patch_skill"
    assert body["message"]["proposal_note"] == ""
    # read-only: proposing does not mutate the live brain
    assert client.get("/healthz").json()["edit_count"] == 0


def test_propose_no_edit_sets_a_visible_note(client, monkeypatch):
    sid, mid = _seed_turn(client, "let's discuss", monkeypatch)
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"no_edit": true, "reason": "still clarifying the window"}')
    body = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()
    assert body["message"]["edits"] == []
    assert body["message"]["proposal_note"] == "still clarifying the window"


def test_propose_redline_op_becomes_a_failed_card(client, monkeypatch):
    sid, mid = _seed_turn(client, "let's discuss", monkeypatch)
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"missing"},"rationale":"r"}]}')
    body = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()
    assert body["message"]["edits"][0]["status"] == "failed" and body["message"]["edits"][0]["apply_reason"]


def test_propose_on_missing_message_is_404(client):
    sid = client.post("/sessions/new").json()["session_id"]
    assert client.post(f"/sessions/{sid}/messages/nope/propose").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/sonia/test_chat.py -k "propose or never_returns" -v`
Expected: FAIL — `/propose` returns 404 (route not defined) / chat still returns edits.

- [ ] **Step 3: Implement the `/propose` route**

In `sonia/app.py`: add imports at the top (with the other `alpha.meta` imports):

```python
from alpha.llm.chat import ChatMessage
from alpha.meta.agent import MetaAgent, preview_op
from alpha.meta.extractor import extract_ops
from alpha.meta.sonia_agent import SoniaAgent, turn_text
```

(Update the existing `from alpha.meta.agent import MetaAgent` and `from alpha.meta.sonia_agent import SoniaAgent` lines to the above forms.)

Add the route inside `create_app()`, right after `edit_action` (uses the existing `_find` helper):

```python
    @app.post("/sessions/{sid}/messages/{mid}/propose")
    def propose(sid: str, mid: str):
        sstore = _session_store()
        sess = sstore.get(sid)
        msg = _find(sess, mid) if sess else None
        if msg is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if msg.applied_seqs:
            return JSONResponse({"error": "already applied"}, status_code=409)
        idx = sess.messages.index(msg)
        convo = [ChatMessage(role=m.role, text=turn_text(m)) for m in sess.messages[: idx + 1]]
        h, _ = _brain_store().load()                                   # read-only
        try:
            res = extract_ops(make_client("sonia"), h, convo)
        except Exception as e:                                         # extractor unavailable — visible, never silent
            return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=502)
        if res.ops:
            msg.edits = [preview_op(h, op) for op in res.ops]
            msg.proposal_note = ""
        else:
            msg.edits = []
            msg.proposal_note = res.reason
        sstore.put(sess)
        return {"session_id": sid, "message": msg.model_dump()}
```

- [ ] **Step 4: Run the Sonia suite**

Run: `python -m pytest tests/sonia/ -v`
Expected: PASS (migrated + new propose tests; existing apply/rollback/conflict tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add sonia/app.py tests/sonia/test_chat.py
git commit -m "feat(sonia): on-demand /propose route (crystallize -> preview cards or no-edit note)"
```

---

## Task 5: Web propose route + client + templates

**Files:**
- Modify: `alpha_web/sonia_client.py`
- Modify: `alpha_web/app.py`
- Modify: `alpha_web/templates/partials/message_assistant.html`
- Create: `alpha_web/templates/partials/_propose_area.html`
- Create: `alpha_web/templates/partials/_propose_result.html`
- Test: `tests/web/test_drawer.py` (migrate two tests + add propose coverage)

**Interfaces:**
- Consumes: Sonia `/propose` (Task 4); `drawer.pending_view` (`alpha_web/drawer.py`); the `render(request, template, ctx)` helper + `_sonia()` + `da` already in `alpha_web/app.py`.
- Produces:
  - `SoniaClient.propose(sid: str, mid: str) -> dict`
  - `POST /evolve/{session_id}/message/{message_id}/propose` → renders `_propose_result.html` (propose-area innerHTML + OOB `#pending`).
  - `_propose_area.html`: shows the change-chip (has edits) / no-edit note (`proposal_note`) / "Propose an edit" button (neither, and not yet applied).

- [ ] **Step 1: Write the failing tests (migrate + add)**

In `tests/web/test_drawer.py`: **replace** `test_message_lands_edits_in_the_drawer_with_a_chip_not_inline` and `test_apply_reflects_in_brain_panel_and_rollback_reverts` with the versions below (they now route through `/propose`), and **add** the no-edit test. `re` is imported inside the existing apply test; add `import re` at module top if not present.

```python
def test_chat_is_prose_only_then_propose_lands_edits_in_the_drawer(client, monkeypatch):
    import re
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"%s","notes":"n"},"rationale":"r"}]}' % sid_skill)
    m = client.post("/evolve/message", data={"text": "patch it"})
    assert m.status_code == 200
    assert "change-chip" not in m.text and "edit-card" not in m.text     # chat produced no edits
    assert "Propose an edit" in m.text                                   # the on-demand control is offered
    sid = re.search(r'id="composer-session"[^>]*value="([^"]+)"', m.text).group(1)
    mid = re.search(r"/message/([\w-]+)/propose", m.text).group(1)       # the assistant turn's propose button
    p = client.post(f"/evolve/{sid}/message/{mid}/propose")
    assert p.status_code == 200
    assert "change-chip" in p.text                                       # chip now points at the drawer
    assert 'id="pending"' in p.text and 'hx-swap-oob="true"' in p.text   # #pending refreshes OOB
    assert "edit-card" in p.text and "patch_skill" in p.text             # the edit lives in the drawer


def test_propose_with_no_edit_shows_a_visible_note(client, monkeypatch):
    import re
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "let's keep clarifying")
    m = client.post("/evolve/message", data={"text": "hmm"})
    sid = re.search(r'id="composer-session"[^>]*value="([^"]+)"', m.text).group(1)
    mid = re.search(r"/message/([\w-]+)/propose", m.text).group(1)
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"no_edit": true, "reason": "still clarifying the window"}')
    p = client.post(f"/evolve/{sid}/message/{mid}/propose")
    assert "no edit proposed" in p.text and "still clarifying the window" in p.text
    assert "change-chip" not in p.text


def test_propose_then_apply_reflects_in_brain_panel_and_rollback_reverts(client, monkeypatch):
    import re
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"process_memory",'
        '"args":{"lesson_id":"les-test-1","lesson":"NEW-TEST-LESSON","outcome":"principle"},'
        '"rationale":"teach test"}]}')
    m = client.post("/evolve/message", data={"text": "remember this"})
    sid = re.search(r'id="composer-session"[^>]*value="([^"]+)"', m.text).group(1)
    mid = re.search(r"/message/([\w-]+)/propose", m.text).group(1)
    p = client.post(f"/evolve/{sid}/message/{mid}/propose")
    eid = re.search(r"/edit/([\w-]+)", p.text).group(1)
    acc = client.post(f"/evolve/{sid}/edit/{eid}", data={"action": "accept"})
    assert re.search(r"/message/([\w-]+)/apply", acc.text).group(1) == mid   # same turn
    ap = client.post(f"/evolve/{sid}/message/{mid}/apply")
    assert 'id="brain-panel"' in ap.text and 'hx-swap-oob="true"' in ap.text
    assert "NEW-TEST-LESSON" in ap.text.split('id="brain-panel"', 1)[1]       # mirror reflects the applied lesson
    rb = client.post(f"/evolve/rollback/{sid}/{mid}")
    assert "NEW-TEST-LESSON" not in rb.text.split('id="brain-panel"', 1)[1]   # gone from the live brain
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/web/test_drawer.py -k "propose" -v`
Expected: FAIL — `/evolve/.../propose` route missing; "Propose an edit" not in template.

- [ ] **Step 3: Add the client method**

In `alpha_web/sonia_client.py`, add after `apply`:

```python
    def propose(self, sid: str, mid: str) -> dict:
        return self._request("POST", f"/sessions/{sid}/messages/{mid}/propose")
```

- [ ] **Step 4: Create the two partials**

Create `alpha_web/templates/partials/_propose_area.html` (the per-turn control; `m` is a message dict, `session_id` in scope):

```html
{% if m.edits %}
<a class="change-chip" href="#agent-drawer" data-flash="agent-drawer">&#8629; {{ m.edits|length }} proposed change{{ "" if m.edits|length == 1 else "s" }} &rarr;</a>
{% elif m.proposal_note %}
<div class="no-edit-note">&#8629; no edit proposed: {{ m.proposal_note }}</div>
{% elif not m.applied_seqs %}
<button class="propose-btn" hx-post="/evolve/{{ session_id }}/message/{{ m.message_id }}/propose"
        hx-target="#propose-{{ m.message_id }}" hx-swap="innerHTML">Propose an edit</button>
{% endif %}
```

Create `alpha_web/templates/partials/_propose_result.html` (the `/propose` HTMX response: swap the propose-area, refresh `#pending` OOB):

```html
{% include "partials/_propose_area.html" %}
{% with pending_oob = true %}{% include "partials/_pending.html" %}{% endwith %}
```

- [ ] **Step 5: Wire the propose-area into the assistant bubble**

Replace `alpha_web/templates/partials/message_assistant.html` entirely with:

```html
<div class="bubble assistant" id="msg-{{ m.message_id }}">
  <div class="prose">{{ m.text | md }}</div>
  {% for d in m.directions %}<div class="direction">▸ {{ d.title }}{% if d.summary %} — {{ d.summary }}{% endif %}</div>{% endfor %}
  <div class="propose-area" id="propose-{{ m.message_id }}">
    {% include "partials/_propose_area.html" %}
  </div>
</div>
```

- [ ] **Step 6: Add the web propose route**

In `alpha_web/app.py`, add after the `edit` route (uses the existing `_sonia()`, `drawer`, `_unavailable`):

```python
    @app.post("/evolve/{session_id}/message/{message_id}/propose")
    def propose(request: Request, session_id: str, message_id: str):
        try:
            out = _sonia().propose(session_id, message_id)
            session = _sonia().get_session(session_id)
        except httpx.HTTPError:
            return _unavailable(request)
        return render(request, "partials/_propose_result.html",
                      {"session_id": session_id, "m": out["message"],
                       "pending": drawer.pending_view(session)})
```

- [ ] **Step 7: Run the web drawer suite**

Run: `python -m pytest tests/web/test_drawer.py -v`
Expected: PASS (migrated + new propose tests; the view-model unit tests and the unavailable test unchanged).

- [ ] **Step 8: Commit**

```bash
git add alpha_web/sonia_client.py alpha_web/app.py \
  alpha_web/templates/partials/message_assistant.html \
  alpha_web/templates/partials/_propose_area.html \
  alpha_web/templates/partials/_propose_result.html \
  tests/web/test_drawer.py
git commit -m "feat(web): on-demand 'Propose an edit' control + /propose route (prose chat -> explicit crystallize)"
```

---

## Task 6: Honest brain mirror — "seeds · no live edits yet" badge

**Files:**
- Modify: `alpha_web/drawer.py`
- Modify: `alpha_web/app.py`
- Modify: `alpha_web/templates/partials/_brain_panel.html`
- Test: `tests/web/test_drawer.py`

**Interfaces:**
- Consumes: `da.brain_badge()` (`alpha_web/data_access.py`, returns `{"is_live": bool, "edit_count": int}`).
- Produces: `drawer.brain_view(state, *, materialized: bool = True) -> BrainView` with new field `BrainView.materialized: bool`. Default `True` keeps existing callers/tests working; routes pass the real liveness.

- [ ] **Step 1: Write the failing tests**

Add to `tests/web/test_drawer.py`:

```python
def test_brain_view_carries_materialized_flag():
    state = load_seeds("seeds")
    assert drawer.brain_view(state).materialized is True                  # default
    assert drawer.brain_view(state, materialized=False).materialized is False


def test_brain_panel_badges_pre_materialization(client, monkeypatch):
    # A fresh session before any apply: the live store isn't materialized, so the mirror says so.
    body = client.get("/").text
    panel = body.split('id="brain-panel"', 1)[1]
    assert "no live edits yet" in panel
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/web/test_drawer.py -k "materialized or badges" -v`
Expected: FAIL — `brain_view()` has no `materialized` kwarg; badge text absent.

- [ ] **Step 3: Add the flag to the view-model**

In `alpha_web/drawer.py`: add the field to `BrainView` and the kwarg to `brain_view`:

```python
@dataclass(frozen=True)
class BrainView:
    components: list[Component]
    materialized: bool = True          # False → live store not yet written (mirror shows frozen seeds)


def brain_view(state: HarnessState, *, materialized: bool = True) -> BrainView:
    """Mirror the six brain components in the left-rail order: three live (doctrine/memory/skills,
    with item lists) and three read-only stubs (workflow/connector/subagent). `materialized` reflects
    whether the LiveBrainStore has been written yet (drives the 'no live edits yet' badge)."""
    doctrine = list(state.doctrine.entries)
    lessons = state.memory.all()
    skills = state.skills.all()
    blurb = {k: b for k, _, b in _STUBS}
    return BrainView(materialized=materialized, components=[
        Component("doctrine",  "Doctrine",  "/doctrine", len(doctrine), doctrine, False),
        Component("memory",    "Memory",    "/memory",   len(lessons),  lessons,  False),
        Component("workflow",  "Workflow",  "", None, [], True, blurb["workflow"]),
        Component("skills",    "Skill",     "/skills",   len(skills),   skills,   False),
        Component("connector", "Connector", "", None, [], True, blurb["connector"]),
        Component("subagent",  "Subagent",  "", None, [], True, blurb["subagent"]),
    ])
```

- [ ] **Step 4: Thread real liveness at the brain-panel call sites**

In `alpha_web/app.py`, update the three brain-panel render sites to pass the real flag. Change each `drawer.brain_view(da.load_brain())` to `drawer.brain_view(da.load_brain(), materialized=da.brain_badge()["is_live"])` at:
- `_cockpit_ctx` (the `"brain": ...` key)
- the `message` route (the `_two_turns.html` render `"brain": ...`)
- the `apply` route (the `_drawer_update.html` render `"brain": ...`)
- the `rollback` route (the `_drawer_update.html` render `"brain": ...`)

(The `propose` route from Task 5 does not render the brain panel — leave it.)

- [ ] **Step 5: Add the badge to the template**

In `alpha_web/templates/partials/_brain_panel.html`, add the badge just inside `.acc-body`, before the components loop (line 5 `<div class="acc-body">`):

```html
  <div class="acc-body">
    {% if not brain.materialized %}<div class="brain-badge">seeds · no live edits yet</div>{% endif %}
    {% for c in brain.components %}
```

- [ ] **Step 6: Run the web suite**

Run: `python -m pytest tests/web/ -v`
Expected: PASS (badge tests pass; existing `test_home_*` / drawer tests unaffected — default `materialized=True` and the seed-state home now shows the badge because the live store isn't materialized).

- [ ] **Step 7: Commit**

```bash
git add alpha_web/drawer.py alpha_web/app.py alpha_web/templates/partials/_brain_panel.html tests/web/test_drawer.py
git commit -m "feat(web): honest brain mirror — 'no live edits yet' badge before first apply"
```

---

## Task 7: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole offline suite**

Run: `python -m pytest -q`
Expected: PASS, 0 failures (record the baseline count with `python -m pytest -q --co -q | tail -1` before Task 1 so you can confirm the delta = net new tests). If anything in `tests/web/test_cockpit.py`, `tests/web/test_app.py`, or `tests/sonia/` references the old chat-produces-ops behavior or the old `message_assistant.html` chip, fix it to route through `/propose` (same pattern as Task 5's migrations) — show the diff in the commit.

- [ ] **Step 2: Run the four PIT firewall acceptance tests (untouched, must stay green)**

Run:
```bash
python -m pytest tests/data/test_source.py::test_guarded_source_blocks_future_snapshot \
  tests/data/test_corp_actions.py::test_has_reverse_split_pending_pit \
  tests/data/test_snapshot_source.py::test_bars_are_raw_not_future_adjusted \
  tests/universe/test_build_universe.py::test_rvol_uses_only_trailing_bars -q
```
Expected: PASS (this change never touches the perception/PIT layer).

- [ ] **Step 3: Commit any fallout fixes from Step 1**

```bash
git add -A && git commit -m "test: route residual chat-ops assertions through /propose (crystallize split)"
```

---

## Self-Review

**Spec coverage** (spec §3–§9 → task):
- §3 chosen approach B, turn-level, prose-only chat → Task 3; on-demand extractor → Tasks 1–2; explicit Propose control → Task 5. ✓
- §5.1 `extractor.py` (`ExtractionResult`, `extract_ops`) → Task 2. ✓
- §5.2 prompt helpers (`render_extraction_system`, `render_conversation`) → Task 2. ✓
- §5.3 `parse_extraction` (+ shared item helper) → Task 1. ✓
- §5.4 `Message.proposal_note` → Task 3. ✓
- §5.5 `respond` prose-only + `_INSTRUCTIONS` trim → Task 3. ✓
- §5.6 Sonia `/propose` (409 when applied, 404 missing, 502 on extractor failure, re-propose replaces edits) → Task 4. ✓
- §5.7 `SoniaClient.propose` + web route → Task 5. ✓
- §5.8 "Propose an edit" button, inline no-edit note, `edit_card.html:3` failed-reason already present (unchanged), brain-mirror badge → Task 5 (button/note) + Task 6 (badge). ✓
- §7 error handling (extractor unavailable → 502 → web `_unavailable`; `{}` → no_edit fallback; already-applied → 409/button hidden) → Tasks 1/4/5. ✓
- §8 testing (extractor branches, `/propose` attach vs note, `respond` migration, web render, apply unchanged) → Tasks 1–6. ✓
- §9 invariants (write-waist untouched, read-only propose, human confirmation strengthened, temp=0) → Global Constraints + Task 7 firewall check. ✓

**Placeholder scan:** no TBD/TODO/"handle edge cases"; every code step shows complete code; every test step shows the assertions and the exact `pytest` command + expected result. ✓

**Type consistency:** `parse_extraction -> (list[RefineOp], bool, str)` (Task 1) consumed by `extract_ops` (Task 2) unchanged. `ExtractionResult.ops/no_edit/reason` (Task 2) consumed in Sonia `/propose` (Task 4) as `res.ops`/`res.reason`. `turn_text` (Task 3) imported in Task 4. `Message.proposal_note` (Task 3) set in Task 4, read in `_propose_area.html` (Task 5). `SoniaClient.propose(sid, mid)` (Task 5) matches the Sonia route path (Task 4). `brain_view(state, *, materialized=True)` + `BrainView.materialized` (Task 6) match the `_brain_panel.html` read and the app.py call sites. ✓
