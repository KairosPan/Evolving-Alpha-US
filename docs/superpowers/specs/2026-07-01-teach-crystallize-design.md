# Teach → Modification: On-Demand Crystallization

**Status:** design approved 2026-07-01 · awaiting spec review
**Layer touched:** `meta` / `sonia` / `alpha_web` (faces over `H`) — write-waist untouched
**Related:** [[meta-agent-teaching-cockpit]], [[hermes-rebase-design]], the "one write-waist" invariant (§5.2 of `CLAUDE.md`)

---

## 1. Problem

A teaching conversation with Sonia already lands as a committed modification to the harness `H`
on the happy path — the plumbing is fully wired and tested:

```
teach message → Sonia /chat → SoniaAgent.respond: parse_ops(reply) → preview_op(deepcopy(h))
  → ProposedEdit cards → Accept → Apply → MetaAgent.apply → try_apply_op   [THE ONE WRITE-WAIST]
  → MetaTools.* mutates H + appends 1 EditRecord → bstore.save → live brain mirror refresh
  → rollback via msg.snapshot_before
```
(`test_apply.py` proves `edit_count` 0→1; `test_drawer.py` proves a taught lesson appears in the
brain panel.)

The difficulty ("现在的难题") is **not** the apply/gate/persist chain — it is one hop **upstream** of
the gate: the **propose** hop at `alpha/meta/sonia_agent.py:48-49`:

```python
edits = [preview_op(h, op, ...) for op in parse_ops(reply)]
```

This hop silently evaporates for three reasons, all confirmed against the code:

1. **The chat path cannot force structure.** `ChatLLMClient.chat()` returns a plain `str`
   (`llm/chat.py:17`); `OpenAICompatClient.chat()` does **not** set
   `response_format={"type":"json_object"}` — only `complete()` does (`openai_compat.py:45` vs `:67`).
   So Sonia's conversational turn returns free prose that *might* contain a fenced JSON block.
2. **Ops are solicited by a soft instruction.** The system prompt says "*When (and only when) a
   concrete brain change is warranted* … append a SINGLE fenced JSON object with … ops"
   (`sonia_agent.py:11-16`). Mid-conversation the model usually just chats and emits nothing.
3. **`parse_ops` swallows every failure into `[]`.** Malformed JSON, missing `"ops"` key, non-list
   `ops` → all return `[]` with no diagnostic (`refine/ops.py:33-44`). Zero cards, no signal — which
   reads to the operator as "教了没反应 / 看不出变化."

The lever we already own: `complete()` **has** enforced `json_object` mode (the Refiner uses it). The
`chat` path can't use it because that turn also needs prose. That asymmetry is the whole design opening.

**Correction to an earlier assumption:** a *failed-preview* reason is **not** invisible today —
`edit_card.html:3` already renders `apply_reason` on failed cards. The only genuinely-missing
observability piece is the **no-edit** signal, plus a minor brain-mirror honesty badge.

## 2. Goal / non-goals

**Goal.** Make the propose hop **reliable and observable**: a teach turn, on explicit operator
request, always produces a visible outcome — either concrete edit cards or an explicit
"no edit proposed: `<reason>`" — never silent evaporation.

**Non-goals (out of scope for this spec).**
- No change to `try_apply_op`, `MetaTools`, `EditLog`, the 10 gates, or rollback. The write-waist is
  a hard invariant and stays byte-identical.
- No change to apply atomicity (brain/session transaction, multi-edit batching). That is a separate,
  real gap (tracked in `ROADMAP.md`), deliberately deferred here to keep this change bounded.
- No consolidation of the two teach faces (Sonia drawer = `ALL_TOOLS` vs workbench `/converse` =
  memory-only). Also deferred. This spec touches **only the Sonia/drawer face** (the active one per
  the recent git log, "teaching lands in the drawer").
- No `conflict_queue` threading into the teach path (teach edits remain always-final per the
  modification-ladder asymmetry).

## 3. Chosen approach

**B · On-demand crystallization (turn-level).** Split the two jobs currently fused into one chat call:

- **Converse** — the chat turn stays **prose-only**; Sonia discusses and asks clarifying questions.
- **Crystallize** — an explicit **"Propose an edit"** button on an assistant turn fires a *second*,
  deterministic call: `client.complete(system, user)` with enforced `json_object` mode over the
  conversation up to that turn, forced to return **either** `{"ops":[...]}` **or**
  `{"no_edit": true, "reason": "..."}`. Enforced JSON + a required verdict makes it never silent and
  always parseable. Extracted ops flow through the **existing** `preview_op` → cards → Accept → Apply.

Rejected alternatives (recorded for context):
- **A · signals-only** — cheapest, but doesn't raise the landing rate; the model still volunteers ops
  or not. It only stops the silence.
- **C · re-prompt/repair** — still prose-mined on the chat path, so it can still fail; adds a
  conditional round-trip without removing the root cause.

Chosen granularity: **turn-level** (crystallize the conversation *up to and including* the clicked
assistant turn; edits attach to that message). This reuses the existing per-`message_id`
`pending_view` / apply grouping unchanged. Per-direction crystallization (a button per suggested
direction) is a possible later refinement, out of scope for v1.

**Why on-demand fits this system:** teaching is exploratory (clarify → align → commit). A deliberate
"crystallize now" step matches the co-pilot doctrine — every persisted change is an explicit human
act. Propose + Accept + Apply = three explicit human steps.

## 4. Architecture — the cut

```
Chat:    POST /evolve/message → Sonia POST /chat
           → SoniaAgent.respond: prose reply (+ soft directions), NO edits
           → drawer shows the turn + [Propose an edit] button

Propose: POST /evolve/{sid}/message/{mid}/propose → Sonia POST /sessions/{sid}/messages/{mid}/propose
           → extract_ops(client.complete, h_live, conversation_upto_mid) → ExtractionResult
                • ops present:  preview_op each → msg.edits (proposed|failed cards); msg.proposal_note = ""
                • no_edit:      msg.edits = [] ; msg.proposal_note = reason
           → SessionStore.put(sess) ; return updated session
           → web renders inline turn note + OOB refresh of #pending

Apply:   (UNCHANGED) Accept → Apply → MetaAgent.apply → try_apply_op → 1 EditRecord → bstore.save
```

The propose pass is **read-only on `H`** — it loads the live brain to preview against, calls
`complete()` (read-only), and `preview_op` runs on a deepcopy. It writes only the **session**
(proposed edits + note), never the brain. The brain is mutated exclusively by the unchanged Apply path.

## 5. Components

All additions are small and mirror existing patterns. Files:

### 5.1 `alpha/meta/extractor.py` (new)
```python
class ExtractionResult(BaseModel):   # frozen (ConfigDict(frozen=True))
    ops: list[RefineOp] = Field(default_factory=list)   # empty iff no_edit
    no_edit: bool = False
    reason: str = ""                 # populated when no_edit (one-sentence why)

def extract_ops(client: LLMClient, h: HarnessState, conversation: list[ChatMessage]) -> ExtractionResult:
    """Deterministic crystallization. Renders (system, user) from the brain + conversation,
    calls client.complete(system, user) [enforced json_object on openai_compat], parses via
    parse_extraction. Never returns silently: an empty/unknown object → no_edit with a generic
    reason. Read-only on h."""
```
- Uses `client.complete` (the `LLMClient` face), **not** `.chat`. The concrete Sonia client
  (`OpenAICompatClient` / `MockLLMClient`) satisfies both Protocols.
- Does **not** call `preview_op` — it returns raw `RefineOp`s; the endpoint previews them (keeps the
  extractor pure and unit-testable without a brain deepcopy).

### 5.2 `alpha/meta/prompts.py` (edit — additive)
```python
def render_extraction_system(h: HarnessState) -> str:
    """render_brain_summary(h) + _TOOLS_DOC + the crystallization instruction:
    'Output ONLY a JSON object. If the conversation warrants concrete brain change(s), output
    {"ops":[{tool,args,rationale}, ...]} using the exact tool vocabulary above, non-empty rationale
    on every op. Otherwise output {"no_edit": true, "reason": "<one sentence>"}. No prose outside JSON.'"""

def render_conversation(msgs: list[ChatMessage]) -> str:
    """Serialize the conversation up to and including the target turn into the user prompt."""
```
`_TOOLS_DOC` and `render_brain_summary` are reused verbatim (no drift in the op vocabulary).

### 5.3 `alpha/refine/ops.py` (edit — additive)
```python
def parse_extraction(raw: str) -> tuple[list[RefineOp], bool, str]:
    """For the enforced-JSON extraction reply. Defensive: uses extract_json_object as a fallback.
    - dict has list 'ops' with >=1 valid item → (ops, False, "")   [reuses parse_ops item logic]
    - dict has truthy 'no_edit'              → ([], True, reason)
    - empty/unknown/malformed                → ([], True, "model returned no ops")  [never silent]"""
```
The existing `parse_ops` is unchanged and remains the Refiner's ops parser; only the Sonia chat path
stops calling it (see 5.5), so it does **not** become dead code. `parse_extraction` may share the
per-item validation helper with `parse_ops`.

### 5.4 `alpha/meta/models.py` (edit — additive)
- Add `Message.proposal_note: str = ""` — carries the no-edit reason for inline rendering. Additive,
  default-empty (existing sessions deserialize unchanged).

### 5.5 `alpha/meta/sonia_agent.py` (edit)
- `respond()` becomes **prose-only for ops**: drop the `parse_ops`/`preview_op` line (`:48-49`); the
  returned `Message.edits` is always `[]` from chat. `directions` (via `parse_directions`) are kept —
  they don't mutate `H`.
- `_INSTRUCTIONS` (`:11-16`) stops soliciting an ops block; it may still invite `directions` as soft
  conversational hints.
- Add a thin helper `propose(session, upto_message) -> ExtractionResult` (or the endpoint calls
  `extract_ops` directly with the sliced history — either is fine; keep one call site).

### 5.6 `sonia/app.py` (edit)
- New `POST /sessions/{sid}/messages/{mid}/propose`:
  - `sess = sstore.get(sid)`; locate `mid`; build `conversation` = messages up to and including `mid`.
  - `h, _ = bstore.load()` (read-only).
  - `res = extract_ops(copilot, h, conversation)`.
  - if `res.ops`: `msg.edits = [preview_op(h, op) for op in res.ops]`; `msg.proposal_note = ""`.
  - else: `msg.edits = []`; `msg.proposal_note = res.reason`.
  - `sstore.put(sess)`; return `sess.model_dump()`.
  - **Re-propose semantics:** replaces `msg.edits` wholesale on each call. Returns **409 Conflict**
    if `msg.applied_seqs` is non-empty (can't re-crystallize an already-committed turn); the web
    "Propose an edit" button is also hidden in that state as defense-in-depth.
- `/chat` is unchanged in shape but now yields prose-only edits (a consequence of 5.5).

### 5.7 `alpha_web/app.py` + `alpha_web/sonia_client.py` (edit)
- `sonia_client.propose(session_id, message_id)` → POST to the Sonia route above.
- New `POST /evolve/{sid}/message/{mid}/propose`: calls `sonia_client.propose`, fetches the session,
  renders the assistant turn's inline propose-area **plus** an OOB `#pending` refresh (same dual-update
  pattern as `/evolve/message` returning `_two_turns.html`). On `httpx` error → the existing
  "Sonia unavailable" fallback (visible, never silent).

### 5.8 Templates
- **"Propose an edit" button** on each assistant turn (in the message partial). `hx-post` to
  `/evolve/{sid}/message/{mid}/propose`. Hidden/disabled when `msg.applied_seqs` is non-empty.
- **Inline no-edit note** — render `msg.proposal_note` under the turn as "↳ no edit proposed:
  `<reason>`" when present.
- **Failed-preview reason** — already rendered at `edit_card.html:3`; no change (confirming coverage).
- **Brain-mirror badge** (minor) — "seeds · no live edits yet" while `LiveBrainStore` is not
  materialized (`data_access.py:58-64`), so a pre-first-apply state doesn't read as "nothing happened."

## 6. Data flow (worked example)

1. Operator: "runners that gap >20% and fail to hold VWAP by 10:30 are taboo." → `/chat` → Sonia
   replies in prose, maybe a `direction`. No cards. The turn shows a **[Propose an edit]** button.
2. Operator clicks **Propose an edit** → `/propose` → `extract_ops` → enforced-JSON reply
   `{"ops":[{"tool":"process_memory","args":{...},"rationale":"..."}]}` → `preview_op` → one
   `proposed` card in `#pending`.
3. Operator **Accept** → **Apply** → `try_apply_op` (unchanged) → one `EditRecord`, brain mirror
   refreshes, rollback available.
4. Counter-case: operator clicks Propose after an ambiguous turn → `{"no_edit": true, "reason":
   "still clarifying which VWAP window"}` → inline "↳ no edit proposed: still clarifying …". No silent
   evaporation.

## 7. Error handling

- **Extractor call fails** (network/rate/5xx) → `OpenAICompatClient.complete` retries (`max_retries`)
  then raises → `/propose` surfaces it → web shows a visible "extraction unavailable, try again."
- **Model returns `{}`** or a non-conforming object → `parse_extraction` returns
  `no_edit=True, reason="model returned no ops"`. Never silent.
- **`mid` already applied** → `/propose` returns 404/no-op; the button is disabled anyway.
- **Read-only guarantee** — the propose pass never mutates `H`; a failure leaves the brain untouched
  and only the session unchanged.

## 8. Testing (offline, `MockLLMClient` scripted, `temperature=0`)

- `extractor`: scripted `{"ops":[...]}` → `ops` non-empty, `no_edit False`; `{"no_edit":true,
  "reason":"x"}` → `no_edit True, reason "x"`; `{}` → `no_edit True` fallback reason.
- `parse_extraction`: ops / no_edit / empty / malformed branches.
- Sonia `/propose`: attaches previewed edits on ops; sets `proposal_note` on no_edit; 404 when the
  turn is already applied; leaves the brain untouched (edit_count unchanged after propose).
- `respond` **regression / migration:** chat no longer emits ops — assert `respond(...).edits == []`
  even when a scripted reply contains an ops block. **Existing tests that assert `respond` produces
  edits from a scripted ops reply are repurposed to exercise the new `/propose` extractor path.**
- Web: `/evolve/.../propose` renders cards into `#pending` and the inline note; unavailable fallback
  on `httpx` error.
- Template: no-edit note renders from `proposal_note`; brain-mirror badge shows pre-materialization.
- **Apply path unchanged** — the existing `test_apply.py` / `test_drawer.py` apply+rollback tests keep
  passing byte-for-byte (they Accept/Apply pre-seeded edits, independent of how edits were proposed).

## 9. Invariants preserved

1. **One write-waist** — every mutation still flows through `try_apply_op` → `MetaTools` → one
   `EditRecord`. The extractor is strictly upstream of `preview_op`; it adds no side channel.
2. **Read-only propose** — `complete()` + `preview_op` (deepcopy) never touch live `H`.
3. **Immutable doctrine** — unchanged; still enforced at the gate/dispatch.
4. **Human confirmation** — strengthened: Propose + Accept + Apply are three explicit human steps.
5. **Eval determinism** — extractor uses `temperature=0`; offline tests use `MockLLMClient`.

## 10. Deferred (explicitly not in this change)

- Apply atomicity (brain/session transaction; all-or-nothing multi-edit batch; auto-rollback on
  partial failure).
- Canonical teach surface / two-face consolidation + unified write scope.
- `conflict_queue` threading into the teach path.
- Per-direction crystallization button.
- Re-preview when `ProposedEdit.args` is edited between propose and apply.
