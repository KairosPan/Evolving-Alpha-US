# Sonia — Standalone Meta-Agent Service — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorm). Next: implementation plan.
**Topic:** Split the teaching co-pilot out of the web console into **Sonia** — an independent
meta-agent running as its **own process on its own port**, talking to the live trading brain. The
console (`alpha_web`) becomes a thin conversational **chat UI client** that calls Sonia over HTTP.
Sonia runs on **`deepseek-v4-pro` (text-only)** and owns the whole gated brain-mutation path
(dry-run preview → accept/reject → snapshotted apply → rollback).

This **supersedes the v2 "conversational multimodal cockpit" spec** (`2026-06-23-conversational-
multimodal-cockpit-design.md`) on four points, recorded in §0. The v2 spec was approved but not yet
implemented; this design replaces its in-process / multimodal / Claude-copilot assumptions.

---

## 0. What this changes vs the v2 cockpit spec

| v2 cockpit spec said | This design says | Why |
|---|---|---|
| Copilot is a new **in-process** LLM role inside `alpha_web` | Sonia is a **standalone service** (own process + port); `alpha_web` is its HTTP client | User decision: "Sonia 是一个独立的 meta-agent，单独端口." |
| Copilot defaults to **anthropic/Claude** (vision) | Sonia runs on **`deepseek-v4-pro`, text-only** | Verified (DeepSeek API ref, V4 release notes, NVIDIA NIM card): `deepseek-v4-pro` accepts **text input only**; the "V4 multimodal" claims are SEO blogs, not first-party. Vision is web-chat-only, not on the API. |
| Full **multimodal** (text+URL+files+**images**), needs a vision model | **Text + URL + files (txt/md/csv/pdf)**; **image upload dropped for v1** | DeepSeek can't read images via API; a permanently-rejecting upload button is bad UX. Image vision → roadmap (re-add when a vision model is wired). |
| Gated apply lives in the **web layer** (`alpha_web`) | Gated apply lives in **Sonia** (it owns `MetaTools` + `LiveBrainStore`); `alpha_web` only reads the brain | User decision: Sonia owns the brain + gated apply. It is the sole writer. |

Everything else the v2 spec settled (full chat thread, inline reviewable edit cards, gated/auditable
core, per-turn apply/rollback, resume-latest-on-`GET /`, the 9-tool vocabulary, red-line immutability)
is **kept** — this design only relocates it across the process boundary and drops vision.

---

## 1. Goal & framing

Sonia is "an independent meta-agent." Concretely: a headless backend service that holds the live
trading brain and evolves it through a back-and-forth **chat thread**. You teach it (text, links,
pasted files, PDFs); it discusses, asks questions, and **when warranted** proposes brain edits as
**inline reviewable cards** (dry-run before/after). Nothing touches the live brain without a click;
every applied turn is snapshotted and individually rollback-able. The console renders the
conversation and reflects the live brain; Sonia does the reasoning and the mutation.

Two processes, one shared file-backed brain:
- **`sonia/`** — the meta-agent service. Owns: the `deepseek-v4-pro` chat client, the `SoniaAgent`
  reasoner, `MetaTools` + `LiveBrainStore` (dry-run, gated apply, snapshot, rollback), the
  conversation `SessionStore`, the `EditLog` audit. Sole writer of the brain.
- **`alpha_web/`** — the existing console + the new chat cockpit UI. Calls Sonia's HTTP API for all
  conversation/apply/rollback; ingests uploads (files/PDF/URL → text) at the web edge; reads the
  brain **read-only** (badge + dashboard/decisions/doctrine/evolution/memory/skills) from the same
  store. Never writes the brain.

---

## 2. Decisions locked (brainstorm)

| # | Decision |
|---|----------|
| Process model | **Standalone service.** `sonia/` (top-level, parallel to `alpha_web/`), entrypoint `python -m sonia`, **port 8810**. `alpha_web` on **8800**, finds Sonia via `ALPHA_SONIA_URL` (default `http://127.0.0.1:8810`). |
| Model | **`deepseek-v4-pro`, text-only.** New `sonia` LLM role; env `ALPHA_SONIA_PROVIDER`/`ALPHA_SONIA_MODEL`; `mock` for offline. |
| Brain ownership | **Sonia owns it.** `MetaTools` + `LiveBrainStore` live in Sonia; it is the **sole writer**. `alpha_web` + console read the same `ALPHA_LIVE_BRAIN_DIR` files (already side-effect-free reads). No DB, no brain-over-HTTP. |
| Conversation thread | **Owned by Sonia** (`SessionStore`), because apply/rollback are per-message and snapshots are keyed `{sid}-{mid}` — thread and brain writes must be co-located. `alpha_web` fetches the thread via Sonia's API to render. |
| Modalities (v1) | **text + URL + files (txt/md/csv/pdf).** **Image upload removed for v1** (no vision on DeepSeek). |
| Streaming | **No** (v1). `thinking…` indicator, then the complete reply. Streaming → roadmap. |
| Inter-service auth | **None (v1).** localhost-only, single-user. SSRF/IP-range + auth hardening is the precondition before any non-localhost serving. |
| Edits in chat | **Inline reviewable cards** — dry-run before/after, per-card accept/reject, per-turn snapshotted Apply, per-turn rollback. Gated/auditable core preserved. |
| `chat()` decoding | **No `response_format=json_object`** — the reply is prose + an OPTIONAL fenced JSON object, parsed with `extract_json_object`. (Differs from `complete()`, which forces JSON.) |
| `GET /` (console) | **Resume the latest open conversation** (or a fresh empty thread). |

---

## 3. Scope

**In (v1):**
- One composer in the console: type/paste text, attach files (txt/md/csv/pdf), URLs auto-detected.
- A persistent conversation thread with Sonia; non-streaming replies.
- Sonia discusses, asks questions, and **when warranted** proposes brain edits as inline cards
  (and/or higher-level directions).
- Per-card accept/reject (refining a proposed edit = chatting a follow-up turn); per-turn Apply
  (snapshotted, `{sid}-{mid}`) through the gated meta-tools into the live brain; per-turn rollback.
- Multiple teach-and-apply rounds per conversation; browse past conversations; new chat.
- The whole console still reflects the live brain (badge); Sonia-offline shows a friendly banner.

**Out (v1) → roadmap:**
- Image vision (re-add when a vision model is wired); token streaming; voice.
- Non-localhost / multi-user serving + inter-service auth + the SSRF IP-range hardening precondition.
- The self-learning channel (Sonia reflecting on its own task runs into this same thread).
- Long-thread context summarization/windowing beyond a simple char cap.

---

## 4. Reused vs replaced

**Reused unchanged (imported by Sonia from `alpha.*`):** `alpha/refine/apply.py::try_apply_op` +
`ALL_TOOLS`, the 9 `MetaTools`, `alpha/refine/ops.py::parse_ops`, `EditLog`/`EditRecord`,
`alpha/meta/prompts.py::render_brain_summary` + `parse_directions` + `_TOOLS_DOC`,
`alpha/llm/extract.py::extract_json_object`, `MetaAgent.apply`, `ProposedDirection`/`ProposedEdit`.
`LiveBrainStore` (file-backed `brain.json` + `history/` snapshots) reused, with `snapshot()`
generalized from one key to a `{sid}-{mid}` key. `SessionStore` reused (extended `Session` model).

**Reused unchanged (stays in `alpha_web`):** `data_access.load_brain` + `brain_badge` (read-only),
the console pages (dashboard/decisions/doctrine/evolution/memory/skills), base chrome.

**Extracted to share:** `MetaAgent._preview` → a module-level `preview_op(harness, op, *, retire_min,
promote_min) -> ProposedEdit` (deepcopy + `try_apply_op`), used by both `MetaAgent.apply`'s siblings
and the new `SoniaAgent`.

**Replaced/removed (v1 teaching-cockpit front, currently in `alpha_web`):**
`MetaAgent.propose_directions` / `expand_to_edits` / `repropose_edit`; the v1 ingest/direction/
edit-queue routes; templates `partials/directions.html`, `partials/edit_queue.html`,
`partials/edit_row.html`; their tests. The flat `Session.sources/directions/edits/
chosen_direction_id` fields fold into the message thread. The brain-mutation backend (apply/rollback/
snapshot) **moves out of `alpha_web` into Sonia**.

---

## 5. Data models (`alpha/meta/models.py`, pydantic — shared, Sonia owns the store)

```
Attachment
  kind: "file" | "url"           # no "image" in v1 (no vision)
  name: str
  mime: str = ""
  text: str = ""                 # extracted text (file/url)

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

`ProposedDirection`/`ProposedEdit` unchanged from v1 (the edit-card shape: dry-run `payload`,
`status`, `apply_reason`, `applied_seq`, etc.).

---

## 6. The LLM chat layer (`alpha/llm/`, text-only, additive)

The text-only `LLMClient.complete(system, user) -> str` is untouched (agent/refiner keep it).

```
ChatMessage    role: "user" | "assistant"; text: str = ""
ChatLLMClient (Protocol)   def chat(self, system: str, messages: list[ChatMessage]) -> str: ...
```

- **`make_client("sonia")`** — new role; default `("openai_compat", "deepseek-v4-pro")`; env
  `ALPHA_SONIA_PROVIDER`/`ALPHA_SONIA_MODEL`; `mock` provider for offline.
- `OpenAICompatClient.chat()` — maps `ChatMessage`s to a multi-message DeepSeek chat completion
  (`system` as the system message; each turn appended). **No `response_format=json_object`** (the
  reply is prose + optional fenced JSON; forcing JSON would break the conversation). Same
  retry/backoff/injectable-`sleep` as `complete()`.
- `MockLLMClient.chat()` — replays the scripted list and records `(system, messages)` calls (offline).
- **Graceful no-key:** building Sonia's client with a missing `DEEPSEEK_API_KEY` raises (as today);
  the service catches it and returns a structured error the console shows as "set DEEPSEEK_API_KEY,
  or `ALPHA_SONIA_PROVIDER=mock`."

(No `ImagePart`, no vision content blocks, no `VisionUnsupported` — dropped vs the v2 spec.)

---

## 7. The `SoniaAgent` (`alpha/meta/sonia_agent.py`)

`SoniaAgent(tools: MetaTools, copilot: ChatLLMClient, *, retire_min=5, promote_min=3)` — stateless per
request; holds the live brain (`tools.h`). (Imported and instantiated by the Sonia service.)

`respond(session: Session, user_message: Message) -> Message` (the assistant message):
1. **System prompt** = `render_brain_summary(h)` + chat instructions: *"You are Sonia, a US
   speculative-momentum trading co-pilot. Discuss freely, ask clarifying questions. When warranted,
   propose brain edits — output prose, plus an OPTIONAL fenced JSON object with `directions` and/or
   `ops` (the 9-tool vocabulary; never rewrite immutable [RED-LINE] doctrine)."* (Tool vocab reused
   from `prompts._TOOLS_DOC`.)
2. **History** → `list[ChatMessage]`: each prior `Message` → `ChatMessage(role, text=…)` (assistant
   prose; a one-line note of what it proposed/applied for context). The latest user turn's text =
   its prose with extracted file/URL text appended.
3. `copilot.chat(system, messages)` → one reply string.
4. **Parse** via `extract_json_object`: prose + an optional JSON object holding `directions`
   (→ `parse_directions`) and/or `ops` (→ each through `preview_op` = dry-run, live brain untouched).
   Prose = the reply with the JSON block stripped.
5. Build the assistant `Message{role:"assistant", text: prose, directions, edits}`.

The agent **decides per turn**: pure prose, a `directions` offer, or concrete `ops` edit cards.
Persistence/snapshot/apply are the service's job (§8). The live brain is never mutated here.

---

## 8. The Sonia service (`sonia/`, FastAPI, headless)

`sonia/app.py` builds the app; `sonia/__main__.py` runs uvicorn on port 8810. On startup it builds
`MetaTools` over the live brain (`ALPHA_LIVE_BRAIN_DIR`), a `SessionStore`
(`ALPHA_SESSIONS_DIR`), the `sonia` copilot client, and a module-level `_MUTATION_LOCK`.

| Route | Purpose |
|---|---|
| `POST /chat` `{session_id?, text, attachments: [{kind,name,mime,text}]}` | Create-or-resume the session; build the user `Message`; `SoniaAgent.respond` → assistant `Message`; append both; persist; return both new turns (+ the `session_id`). |
| `POST /sessions/{sid}/edit/{eid}` `{action: "accept"\|"reject"}` | Flip one card's state (pure state, no LLM); persist; return the card. Refining = a follow-up chat turn. |
| `POST /sessions/{sid}/messages/{mid}/apply` | Under `_MUTATION_LOCK`: snapshot (`{sid}-{mid}`) → apply that turn's **accepted** edits via `MetaAgent.apply` → persist; record `snapshot_before`/`applied_seqs`; return the apply result. |
| `POST /sessions/{sid}/messages/{mid}/rollback` | Under the lock: restore that message's `snapshot_before`; note it; persist. |
| `GET /sessions` · `GET /sessions/{sid}` · `POST /sessions/new` | List (newest-first) · load one · new empty session. |
| `GET /healthz` | `{ok, brain_live, edit_count}` — drives the console's "Sonia online/offline" state. |

Mutating routes serialize on `_MUTATION_LOCK`. `snapshot()` generalizes to a `{sid}-{mid}` key so a
conversation can have multiple snapshotted applies. The service is the **only writer** of `brain.json`.

---

## 9. The console as Sonia's client (`alpha_web/`)

`/` becomes the chat cockpit: a **thread** (message bubbles) + a sticky **composer** (textarea + `+`
attach for files + send) + a **session list** + **New chat**. It is a thin client over Sonia's API.

- A small `sonia_client.py` (httpx) wraps Sonia's routes. Each console action proxies to Sonia and
  renders the result (HTMX `beforeend` for new turns, swap for card/apply/rollback results).
- **Ingestion at the edge** (`alpha/meta/ingest.py::ingest_attachments(text, upload_files) ->
  (clean_text, attachments)`): `txt/md/csv` decoded (utf-8/replace); **PDF** via a lazy `pypdf`
  import (absent → friendly note); URLs regex-detected and fetched via the scheme-allowlisted
  `fetch_url`; per-file size cap + ~50k extracted-text cap with a truncation note; unknown type →
  friendly reject. **Images rejected with a note** ("image vision isn't available — describe it").
  The cleaned text + `Attachment`s are POSTed to Sonia's `/chat`.
- **Read-only brain:** `data_access.load_brain` + `brain_badge` unchanged (reads the shared store,
  picks up Sonia's writes on the next request). Other console pages unchanged.
- **Sonia-offline:** any Sonia call that fails/times out → a friendly banner ("Sonia service
  unavailable — start it with `python -m sonia`"); the user's typed input is preserved.

Templates: `cockpit.html` + partials `message_user`, `message_assistant` (prose + direction cards +
edit cards), `edit_card`, `apply_result`, `session_list`. Remove `partials/{directions,edit_queue,
edit_row}.html`. Chat CSS/JS: bubbles, composer, file chips, `thinking…` indicator.

---

## 10. Persistence, error handling, testing

**Persistence:** the brain is `LiveBrainStore` (`brain.json` + `history/<sid>-<mid>.json` snapshots)
under `ALPHA_LIVE_BRAIN_DIR`; the thread is `SessionStore` under `ALPHA_SESSIONS_DIR`; both under
gitignored `/state/`, both written **only by Sonia**. `title` from the first user message.

**Error handling — never a 500 on either side:**
- Console↔Sonia: unreachable/timeout/5xx → friendly banner; user input preserved.
- Sonia: copilot failure / missing key / timeout → friendly assistant note; the user turn is kept.
  Unparseable/malformed model JSON → render the prose, drop the block (no cards), never crash.
- Apply per-edit gated (immutable/[RED-LINE]/blocked → failed card + reason); partial apply fine;
  snapshot enables rollback. Mis-shaped persisted session → render what's valid.
- Ingestion (console): unsupported/oversized file, dead URL, image → each a friendly inline note;
  extracted text capped + noted.

**Testing (TDD, fully offline):**
- Models: `Attachment`/`Message`/`Session` round-trips.
- `chat()` clients: `MockLLMClient.chat` scripted + call recording; `OpenAICompatClient.chat`
  multi-message mapping (injected fake `openai` client) + **asserts no `json_object` forcing**.
- `preview_op` shared helper (the v1 preview assertions, now shared).
- `SoniaAgent.respond`: prose-only → no cards; `directions` → direction cards; `ops` → dry-run edit
  cards with the **live brain untouched**; red-line op → failed card; history threading asserted.
- Sonia service (`httpx`, `ALPHA_SONIA_PROVIDER=mock`, tmp `/state`): `POST /chat` → two turns;
  accept a card → apply → brain mutated + `{sid}-{mid}` snapshot written; rollback restores; sessions
  list/load/new; `healthz`; graceful no-key; red-line op → failed card.
- Console (Sonia mocked via an injected `sonia_client` / httpx mock transport): cockpit renders turns,
  proxies apply/rollback, shows the badge; Sonia-offline → friendly banner; ingestion parses
  txt/md/csv + pdf (tiny fixture / injected extractor) + URL (injected fetcher); image → reject note.
- Playwright: type + send → assistant turn with cards → accept → apply → badge flips (Sonia running
  on its port with a mock copilot).
- **Removed v1-front tests deleted with no dangling references; existing `tests/refine/*` stay green.**

---

## 11. Build order (vertical slices, each green before the next)
1. **Text chat LLM layer** (`ChatMessage`/`ChatLLMClient` + `chat()` on mock + DeepSeek + `sonia`
   role) + extract shared `preview_op`.
2. **`SoniaAgent.respond`** against the mock copilot (offline).
3. **Models** (Attachment/Message, Session→thread) + `SessionStore` reuse + `{sid}-{mid}` snapshot key.
4. **Sonia service skeleton** (`sonia/app.py` + `__main__`: `/chat`, sessions routes, `healthz`)
   against the mock copilot.
5. **Sonia gated apply/rollback** (`MetaTools` + `LiveBrainStore`, per-message snapshot, lock).
6. **Console ingestion** (`ingest_attachments`: files + pdf + URL; image-reject).
7. **Console chat cockpit** (`/` thread+composer + `sonia_client` proxying chat/apply/rollback,
   session list/new, Sonia-offline banner) — **and remove the v1 direction/edit-queue front + the
   three superseded `MetaAgent` methods + their routes/templates/tests** (apply/preview kept, moved
   into Sonia).
8. **Chat CSS/JS** (bubbles, composer, file chips, loading indicator).
9. **Playwright** verify + real-DeepSeek smoke once offline is green.

---

## 12. File map (new / changed)
```
sonia/__init__.py
sonia/__main__.py          # uvicorn on :8810
sonia/app.py               # FastAPI: /chat, /sessions, /edit, /apply, /rollback, /healthz; _MUTATION_LOCK
alpha/llm/chat.py          # ChatMessage, ChatLLMClient protocol
alpha/llm/openai_compat.py # + OpenAICompatClient.chat() (text-only multi-message, no json_object)
alpha/llm/client.py        # + MockLLMClient.chat()
alpha/llm/config.py        # + "sonia" role (default deepseek-v4-pro)
alpha/meta/models.py       # Attachment (file|url), Message; Session -> thread
alpha/meta/sonia_agent.py  # SoniaAgent.respond
alpha/meta/agent.py        # extract preview_op; drop propose_directions/expand_to_edits/repropose_edit
alpha/meta/ingest.py       # + ingest_attachments (files/pdf/url; image-reject)
alpha/meta/store.py        # LiveBrainStore.snapshot(key) generalization ({sid}-{mid})
alpha_web/app.py           # chat cockpit routes proxying Sonia; remove v1 ingest/direction routes; brain stays read-only
alpha_web/sonia_client.py  # httpx wrapper over Sonia's API
alpha_web/templates/       # cockpit.html + partials/{message_user,message_assistant,edit_card,apply_result,session_list}.html
                           #   remove partials/{directions,edit_queue,edit_row}.html
alpha_web/static/          # chat CSS/JS (bubbles, composer, chips, loading)
pyproject.toml             # [sonia] extra (fastapi, uvicorn, openai); pypdf stays in [web]
tests/meta/, tests/web/, tests/llm/, tests/sonia/   # new tests; remove v1-front tests
```

---

## 13. Roadmap follow-ups (deferred)
- **Image vision** — re-add image upload + a vision model for Sonia (composite/side-model or a future
  multimodal DeepSeek API), restoring the v2 spec's chart-analysis capability.
- **Token streaming** (SSE + async/streaming `chat()` + incremental console render).
- **Self-learning channel** — Sonia proposing evolutions from its own realized task runs into this
  same thread.
- **Inter-service auth + SSRF IP-range hardening** (private/loopback/link-local + `169.254.169.254`)
  — blocking precondition before any non-localhost / multi-user serving (scheme allowlist already done).
- **Long-thread context management** (summarization/windowing beyond a char cap); voice input.
