# Conversational Multimodal Cockpit — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorm). Next: implementation plan.
**Topic:** Replace the teaching cockpit's two-field input + structured propose panels with a single
ChatGPT-style **conversational, multimodal cockpit**: one composer (text + file + image upload, URLs
auto-detected), a back-and-forth **thread** with the meta-agent, and brain edits surfaced as **inline
reviewable cards** inside the agent's replies — committed through the *same* gated meta-tool path
(dry-run preview, accept/apply, rollback) the v1 cockpit already uses.

This is **v2 of the teaching cockpit** (the channel shipped 2026-06-23 at `main` @ 38f0879). It replaces
the v1 *front* (input + directions/edit-queue panels) and keeps the *back* (live brain, gated apply,
rollback, stores) intact.

---

## 1. Goal & framing

User feedback on v1: the separate "Paste text" textarea + "…or a URL" field is clunky and dated; it
should be "像 ChatGPT" — a single conversational composer with file/image/text upload. Decisions locked
during brainstorm:

| # | Decision |
|---|----------|
| Paradigm | **Full chat thread** — you and the meta-agent exchange messages; it proposes evolutions inline as chat turns. (Revises v1's "structured over chat" choice.) |
| Edits in chat | **Inline reviewable cards** — the agent chats freely and embeds structured edit cards (dry-run before/after, accept/reject, Apply) in its replies. Nothing touches the live brain without a click; the gated/auditable core is preserved. |
| Modalities (v1) | **text + URL + files + images** — full multimodal. Images need a vision model (Claude). |
| Streaming | **No** (v1) — `thinking…` indicator then the complete reply. Reuses the synchronous LLM layer; streaming deferred. |
| Architecture | **A: conversational front, reuse gated back.** New chat UI + multimodal/vision LLM layer; accepted edits flow through the existing `try_apply_op`/`LiveBrainStore`/rollback unchanged. |
| Copilot model | A new **independent `copilot` LLM role**, default **anthropic/Claude** (vision). Trading `agent` stays DeepSeek; `refiner` unchanged. |
| v1 front | **Removed** (superseded) — the direction/edit-queue routes/templates/tests + `MetaAgent.propose_directions`/`expand_to_edits`/`repropose_edit` go; `apply` + the dry-run preview are kept/shared. |
| PDF | supported via a small lazy **`pypdf`** dep in `[web]`. |
| `GET /` | **resumes the latest open conversation** (chat-native; reverses v1's fresh-on-GET). |
| Images | stored under the session dir, served via a **path-traversal-guarded** route for thumbnails. |

---

## 2. Scope

**In (v1):**
- One composer: type/paste text, attach files (txt/md/csv/pdf) + images, URLs auto-detected.
- A persistent conversation thread with the copilot; non-streaming replies.
- The agent discusses, asks questions, analyzes attached charts (vision), and **when warranted** proposes
  brain edits as inline cards (and/or higher-level directions).
- Per-card **accept/reject** (refining a proposed edit is done by chatting a follow-up turn — the
  conversation replaces v1's per-card comment→re-propose); **per-turn Apply** (snapshotted) through the
  gated meta-tools into the live brain; **per-turn rollback**.
- Multiple teach-and-apply rounds per conversation; browse past conversations; new chat.
- Whole console still reflects the live brain (badge).

**Out (v1) → roadmap:**
- Token streaming; voice; non-localhost/multi-user serving (+ the SSRF IP-range hardening precondition).
- The self-learning channel (agent reflecting on its own task runs) — separate roadmap arc.
- Long-thread context summarization/windowing beyond a simple cap.

---

## 3. Reused vs replaced

**Reused unchanged:** `LiveBrainStore` (+ a generalized snapshot key, §6), `SessionStore` (extended model),
`alpha/refine/apply.py::try_apply_op` + `ALL_TOOLS`, the 9 `MetaTools`, `EditLog`/`EditRecord`,
`alpha/meta/prompts.py::render_brain_summary` + `parse_directions`, `alpha/refine/ops.py::parse_ops`,
`alpha/llm/extract.py::extract_json_object`, `MetaAgent.apply`, `data_access.brain_badge`, base chrome.

**Extracted to share:** `MetaAgent._preview` → a module-level `preview_op(harness, op, *, retire_min,
promote_min) -> ProposedEdit` (deepcopy + `try_apply_op`), used by both `MetaAgent.apply`'s siblings and
the new `ChatAgent`.

**Replaced/removed (v1 front):** `MetaAgent.propose_directions` / `expand_to_edits` / `repropose_edit`;
routes `POST /evolve/ingest`, `/evolve/{sid}/direction[/regenerate]`; templates `partials/directions.html`,
`partials/edit_queue.html`; their tests. The flat `Session.sources/directions/edits/chosen_direction_id`
fields fold into the message thread.

---

## 4. Data models (`alpha/meta/models.py`, pydantic)

```
Attachment
  kind: "file" | "image" | "url"
  name: str
  mime: str = ""
  text: str = ""            # extracted text (file/url); "" for image
  image_path: str | None = None   # stored image (relative to the session dir), for vision

Message
  message_id: str
  role: "user" | "assistant"
  created_at: str
  text: str = ""                       # user prose, or assistant reply prose
  attachments: list[Attachment] = []   # user turns
  directions: list[ProposedDirection] = []   # assistant turns, optional
  edits: list[ProposedEdit] = []             # assistant turns, optional (inline cards)
  snapshot_before: str | None = None   # set when THIS turn's edits were applied
  applied_seqs: list[int] = []

Session
  session_id: str
  created_at: str
  title: str = ""                      # derived from the first user message
  channel: "teach"
  status: "open" | "discarded"         # 'open' the whole life; apply is per-message, not session-terminal
  messages: list[Message] = []
  notes: list[str] = []
```

`ProposedDirection`/`ProposedEdit` are unchanged from v1 (the edit-card shape, with the dry-run
`payload`, `status`, `apply_reason`, `applied_seq`, etc.).

---

## 5. The multimodal LLM layer (`alpha/llm/`)

Additive — the text-only `LLMClient.complete(system, user) -> str` is untouched (agent/refiner keep it).

```
ImagePart      media_type: str; data: bytes
ChatMessage    role: "user" | "assistant"; text: str = ""; images: list[ImagePart] = []
ChatLLMClient (Protocol)   def chat(self, system: str, messages: list[ChatMessage]) -> str: ...
```

- **`make_client("copilot")`** — new role; defaults `("anthropic", "claude-sonnet-4-6")` (the Claude 4.x
  family is vision-capable); env `ALPHA_COPILOT_PROVIDER`/`ALPHA_COPILOT_MODEL`; `mock` provider for offline.
- `ClaudeClient.chat()` — maps `ChatMessage`s to the Anthropic messages API; images → base64 image content
  blocks; `system` passed as the top-level system param.
- `MockLLMClient.chat()` — replays the scripted list and records `(system, messages)` calls (offline tests).
- `OpenAICompatClient.chat()` — text-only (DeepSeek); if any `ChatMessage` carries images, raise a typed
  `VisionUnsupported` the route turns into "this copilot can't read images — describe it or switch to Claude."
- **Graceful no-key:** building the copilot with a missing key raises (as today); the route catches it and
  shows "set your copilot key, or `ALPHA_COPILOT_PROVIDER=mock`."

---

## 6. The `ChatAgent` (`alpha/meta/chat_agent.py`)

`ChatAgent(tools: MetaTools, copilot: ChatLLMClient, *, retire_min=5, promote_min=3)` — stateless per
request; holds the live brain (`tools.h`).

`respond(session: Session, user_message: Message) -> Message` (the assistant message):
1. **System prompt** = `render_brain_summary(h)` + chat instructions: *"You are a US speculative-momentum
   trading co-pilot. Discuss freely, ask clarifying questions, analyze attached charts. When warranted,
   propose brain edits — output prose, plus an OPTIONAL fenced JSON object with `directions` and/or `ops`
   (the 9-tool vocabulary; never rewrite immutable [RED-LINE] doctrine)."* (Tool vocab reused from
   `prompts._TOOLS_DOC`.)
2. **History** → `list[ChatMessage]`: each prior `Message` → `ChatMessage(role, text=...)` (assistant
   prose; a one-line note of what it proposed/applied for context). The latest user turn's `ChatMessage`
   carries its `ImagePart`s (from image attachments) + its prose with extracted file/URL text appended.
3. `copilot.chat(system, messages)` → one reply string.
4. **Parse** via `extract_json_object`: the reply is prose + an optional JSON object that may hold
   `directions` (→ `parse_directions`) and/or `ops` (→ each through `preview_op` = dry-run, live brain
   untouched). Prose = the reply with the JSON block stripped.
5. Build the assistant `Message{role:"assistant", text: prose, directions, edits}`.

The agent **decides per turn**: pure prose (just discussing), a `directions` offer, or concrete `ops`
edit cards — driven by the conversation. Persistence/snapshot/apply are the route's job (§7).

---

## 7. Ingestion & web layer

### Ingestion (`alpha/meta/ingest.py`, extended)
`ingest_attachments(text, upload_files) -> (clean_text, list[Attachment])`:
- **Files by type:** `txt/md/csv` decoded (utf-8, errors=replace); **PDF** via a lazy `pypdf` import
  (absent → friendly "PDF support needs pypdf"); unknown → friendly reject. Extracted text capped (~50k
  chars + truncation note); per-file size cap.
- **Images:** png/jpeg/webp/gif saved under `<ALPHA_SESSIONS_DIR>/<session_id>/img-<id>.<ext>`, recorded
  as `Attachment(kind=image, image_path)`, loaded to `ImagePart` for the vision call; per-turn count + byte
  caps.
- **URLs:** regex-detected in `text`, fetched via the existing scheme-allowlisted `fetch_url`, attached as
  `url` text. (`from_text`/`fetch_url` reused.)

### Web layer (`alpha_web/`)
`/` = the chat cockpit: a **thread** (message bubbles) + a sticky **composer** (textarea + `+` attach for
files/images + send) + a **session list** + **New chat**.

| Route | Purpose |
|---|---|
| `GET /` | Resume the latest open conversation (or a fresh empty thread) + session list. |
| `POST /evolve/message` (multipart: `session_id?`, `text`, `files[]`) | Create-or-resume the session; `ingest_attachments` → user `Message`; `ChatAgent.respond` → assistant `Message`; append both; persist; return the two new turns (HTMX `beforeend` on the thread; echo the `session_id` for the composer). |
| `POST /evolve/{sid}/edit/{eid}` | accept / reject one card (pure state, no LLM); return the card. Refining a proposed edit = chatting a follow-up turn. |
| `POST /evolve/{sid}/message/{mid}/apply` | under `_MUTATION_LOCK`: snapshot (`{sid}-{mid}` key) → apply that turn's accepted edits via `MetaAgent.apply` → persist; record `snapshot_before`/`applied_seqs` on the message; return the apply result. |
| `POST /evolve/rollback/{sid}/{mid}` | under the lock: restore that message's `snapshot_before`; note it. |
| `GET /evolve/attachments/{sid}/{name}` | serve a stored image (resolve within the session dir; reject path traversal). |
| `POST /evolve/new` · `GET /evolve/sessions[/{id}]` | new chat · browse / load a conversation. |

HTMX appends turns + clears the composer; a `thinking…` indicator covers the LLM call; the attach button
shows file chips; images render as thumbnails (via the attachments route). Templates: `cockpit.html` +
partials `message_user`, `message_assistant` (prose + direction cards + edit cards), `edit_card`,
`apply_result`, `session_list`. `data_access.load_brain` + `brain_badge` unchanged. Mutating routes
serialize on the existing module-level `_MUTATION_LOCK`.

---

## 8. Persistence, error handling, testing

**Persistence:** the thread persists via `SessionStore` (extended model); images under the session dir
(gitignored `/state/`). `LiveBrainStore.snapshot(key)` generalizes from a session id to a `<sid>-<mid>`
key (multiple snapshotted applies per conversation); `restore` unchanged. `title` from the first user
message.

**Error handling — never a 500:**
- Copilot failure / missing key / timeout → friendly banner or assistant note; the user turn is preserved.
- Unparseable/malformed model JSON → render the prose, drop the block (no cards), never crash.
- Attachments: unsupported file / oversized / bad image / dead URL / image-with-non-vision-copilot → each a
  friendly inline note. Extracted text capped + noted.
- Apply per-edit gated (immutable/blocked → failed card + reason); partial apply fine; snapshot enables
  rollback. The attachment route rejects path traversal. Mis-shaped persisted session → render what's valid.

**Testing (TDD, fully offline via `MockLLMClient.chat` + injected fetcher/extractor):**
- Model round-trips (Attachment/Message/Session).
- `chat()` clients: mock scripted; `ClaudeClient.chat` content-block mapping (injected fake anthropic
  client); `OpenAICompatClient.chat` text-only + `VisionUnsupported` on image.
- Ingestion: txt/md/csv parse; pdf via pypdf (tiny fixture or injected extractor); unsupported-reject; size
  cap; image save; URL detect+fetch (injected fetcher).
- `ChatAgent.respond`: prose-only → no cards; `directions` → direction cards; `ops` → dry-run edit cards
  with the **live brain untouched**; red-line op → failed card; history threading asserted.
- `preview_op` shared helper (the v1 preview assertions, now shared).
- Web routes (`httpx`, mock copilot, tmp dirs): `POST /evolve/message` with a fake file + image → thread
  gains two turns; accept a card → apply → brain mutated + snapshot; rollback restores; new chat; resume;
  attachment serving returns the image + rejects traversal; graceful no-key.
- Playwright multimodal flow (type + attach an image + send → assistant turn with cards → accept → apply →
  badge flips).
- **Removed v1-front tests deleted with no dangling references; existing `tests/refine/*` stay green.**

---

## 9. Build order (vertical slices, each green before the next)
1. **Models** (Attachment/Message, Session→thread) + extract shared `preview_op` + per-message snapshot key.
2. **Multimodal LLM layer** (`ImagePart`/`ChatMessage`/`ChatLLMClient` + `chat()` on mock/Claude/DeepSeek +
   `copilot` role + `VisionUnsupported`).
3. **`ChatAgent.respond`** against the mock copilot (offline).
4. **Ingestion** (`ingest_attachments`: files + pdf + images + URL).
5. **Web chat layer** (`/` thread+composer, `POST /evolve/message`, card actions, per-turn apply/rollback,
   attachment serving, session list/new) — **and remove the v1 direction/edit-queue front + the three
   superseded `MetaAgent` methods + their routes/templates/tests** (apply + preview kept/shared).
6. **Chat CSS/JS** (bubbles, composer, file chips, thumbnails, loading indicator).
7. **Playwright** verify + real-Claude smoke once offline is green.

---

## 10. File map (new / changed)
```
alpha/llm/chat.py          # ImagePart, ChatMessage, ChatLLMClient protocol, VisionUnsupported
alpha/llm/anthropic.py     # + ClaudeClient.chat()
alpha/llm/openai_compat.py # + OpenAICompatClient.chat() (text-only)
alpha/llm/client.py        # + MockLLMClient.chat()
alpha/llm/config.py        # + "copilot" role
alpha/meta/models.py       # Attachment, Message; Session -> thread
alpha/meta/chat_agent.py   # ChatAgent.respond
alpha/meta/agent.py        # extract preview_op; drop propose_directions/expand_to_edits/repropose_edit
alpha/meta/ingest.py       # + ingest_attachments (files/pdf/images/url)
alpha/meta/store.py        # LiveBrainStore.snapshot(key) generalization
alpha_web/app.py           # chat routes; remove v1 ingest/direction routes
alpha_web/templates/       # cockpit.html + partials/{message_user,message_assistant,edit_card,apply_result,session_list}.html
                           #   remove partials/{directions,edit_queue}.html
alpha_web/static/          # chat CSS/JS (bubbles, composer, chips, thumbnails)
pyproject.toml             # pypdf in [web]
tests/meta/, tests/web/, tests/llm/   # new tests; remove v1-front tests
```

---

## 11. Roadmap follow-ups (deferred)
- **Token streaming** (SSE + async/streaming `chat()` + incremental client render).
- **Self-learning channel** — the agent proposing evolutions from its own realized task runs into this
  same thread.
- **Long-thread context management** (summarization/windowing beyond a char cap); voice input.
- **SSRF IP-range hardening** (private/loopback/link-local + `169.254.169.254`) — blocking precondition
  before any non-localhost/multi-user serving (scheme allowlist already done).
