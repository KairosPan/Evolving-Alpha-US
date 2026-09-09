# The Charter and the Documents — Implementation Plan (plan 4 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The documents describe what shipped: the charter's §7.1 amendment with its collateral edits (D11 closed, D12 and D13 added, the §8 trigger), `CLAUDE.md`'s one-line mirror and map row, `AGENTS.md`'s rooms paragraph, `DEVELOPMENT.md`'s mechanism rows, drill rows, residual updates and forward list, `ROADMAP.md`'s built log, and the spec's §16 blocks for plans 3 and 4 — written last, so every sentence is a fact of the tree.

**Architecture:** Documentation only. Each task is one file, edited with the exact text below; nothing here changes code. The authority chain is the charter (intent) > `DEVELOPMENT.md` (as-built mechanism) > the specs (decision history); `face/README.md` keeps the face's operational depth (plan 3 wrote it). Descriptive, present tense, files and symbols cited, never line numbers.

**Tech Stack:** Markdown. `python -m pytest` and `cd face && npm test && npm run typecheck` still pass (nothing here touches code); `FACE_SMOKE=1 npm test` was run at the end of plan 2 and plan 3 — cite their counts.

**Spec:** `docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md` — §10 (the amendment's agreed wording, verbatim), §12 (residuals), §14 item 4, §16 (the plan-1 and plan-2 blocks). This plan is §14 item 4. The amendment's wording was agreed 2026-09-07 and is copied, not rewritten; the collateral edits are §10's list.

## Global Constraints

- The charter's **§7.1 wording is the spec's §10 text verbatim** (agreed 2026-09-07). Do not improve it.
- Charter scale discipline: no section grows past a page; mechanism goes to `DEVELOPMENT.md`.
- `CLAUDE.md` stays ~55 lines, present-tense facts, no prescriptions, one file (the operator's policy).
- `DEVELOPMENT.md` citation rule: files and named symbols, never line numbers. Its header's "Last full pass" line carries the real counts from the last `FACE_SMOKE=1 npm test` and `python -m pytest` runs — run them in Task 3 and write what they print.
- `AGENTS.md` is what Kairos itself reads (dsh's instruction loader hands it `CLAUDE.md` too): write for the model, in the register the file already uses.
- The residual ledger (`DEVELOPMENT.md` §9) records what holds and what does not (charter Rule 3): every plan-2/3 residual named in the spec's §12 and §16 blocks gets a row or an update; nothing is marked resolved without naming the mechanism that resolved it.
- Every date is absolute (2026-09-08 / 2026-09-09).
- Commit per task (`git commit -F <file>` when the message carries backticks or parentheses). Never commit the operator's untracked files (`strategies/*`, `bots/buffet/`, `docs/research/*`, `tests/strategies/`, `face/probe4.ts`, `.claude/launch.json`, `docs/storage-industry-chain-2026.md`, `.bots-smoke-*`).
- Do not push. The operator merges and pushes.

## File Structure

| File | Edits |
|---|---|
| `Kairos-Design.md` | header status line; §1 (`one principal agent`, the bots sentence); §5 D11 → resolved, D12 and D13 added; §7.1 replaced by the agreed wording; §8 new trigger row |
| `CLAUDE.md` | "What this is" mirror line; Map row for `bots/` and the room engine; Gotchas: one line on no custom session-event types |
| `AGENTS.md` | a rooms paragraph: what Kairos is told about `dispatch`, the bots on a channel's roster, the operator's `@`, and that a voice is evidence, never a verdict |
| `DEVELOPMENT.md` | header counts; §3.7 rooms state; §4.2 module rows; §4.3 the cache row; §4.4 the three routes; §4.5 state; §5.1 `room.js` + the room views; §5.2 the room frames and the `@` route; §5.3 pipeline; §6.8 a room round end to end; §7.3 suite; §7.4 drill rows; §8 conventions; §9 R6 resolved, R13 resolved, R14–R17 new; §10 item 9 done, item 3 done |
| `ROADMAP.md` | built log line |
| `docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md` | §16 blocks for plans 3 and 4 |

---

### Task 1: The charter — `Kairos-Design.md`

**Files:**
- Modify: `Kairos-Design.md`

- [ ] **Step 1: The header**

Change `**Status:** living charter, written 2026-08-30, revised 2026-09-04, §9 added 2026-09-08` to `**Status:** living charter, written 2026-08-30, revised 2026-09-04, §9 added 2026-09-08, §7.1 amended and D11–D13 revised 2026-09-09 (the bots-and-rooms arc)`.

- [ ] **Step 2: §1**

Replace `for **one operator, one machine, one agent**. The agent, also called Kairos, runs on DeepSeek Harness (dsh) inside the operator's chat face and works three layers:` with:

```markdown
for **one operator, one machine, one principal agent**. The agent, also called Kairos, runs on
DeepSeek Harness (dsh) inside the operator's chat face and works three layers. The operator may
author further agents — bots — as discussants (§7.1); they are voices on Kairos's substrate, not
hands.
```

(keep the three-layer list that follows). In the STRATEGY bullet, after `its roster of helper agents.` add: `A channel with bots on its roster is a **room**: Kairos dispatches the voices, the operator argues with them, and the conclusion stays Kairos's.`

- [ ] **Step 3: §5 — D11 resolved, D12 and D13 added**

Replace the D11 row with:

```markdown
| D11 | *Resolved 2026-09-07.* The model is told it is Kairos: `dsh/profile/persona.md` is the `system-prompt` row's `persona`, set by the face at compose time; a bot's preset shadows it for that bot's sessions | — | — |
| D12 | Bot tool masks are visibility, not authority. dsh scopes and `tools.restrict` are "live visibility composition, not an authority boundary"; a bot with a shell writes whatever its session's sandbox mode allows and reaches whatever the network allows | held by: the `read-only` permission preset logged into every bot room session inside its creation (file effects, subject to an operator-granted escalation card), the `journal/`-scoped `cwd` of every bot home session, Gate 2 tree-wide (the account), and the room transcript naming every dispatch and every member not called. Not held by the mask, and not held for the network | if a bot's composition is ever given the account tools, or a room session is created other than read-only (§8) |
| D13 | Kairos's sessions may have a picked `cwd` at the repository root, which includes `bots/`; "Kairos never edits a bot" is a Rule-7 commitment carried by `AGENTS.md`'s never-edit list and review, not by the sandbox | single operator; every edit reviewed; git is the ledger | the first bot edit that is not the operator's |
```

- [ ] **Step 4: §7 — the amendment, verbatim from the spec's §10**

Replace the `**No second agent.**` bullet with:

```markdown
- **No privileged second agent.** Teaching, review, and adjudication belong to the operator. One
  hand, many voices: Kairos is the one agent whose composition carries the account tools and the
  write to a strategy directory; the operator may roster other agents on a channel — local CLIs as
  callable tools, operator-authored dsh bots as **discussants** that speak in the room — but a bot
  is a voice, not a reviewer: what it says is evidence the operator and Kairos weigh, never a
  verdict, and the conclusion is written by Kairos. Bots run on Kairos's substrate with their tool
  sets masked by configuration; the mask is a menu (a bot with a shell writes whatever its sandbox
  mode allows — D12), and the fence around the account is Gate 2, tree-wide, the same for every
  agent. Kairos's `dispatch` orders the room but grants nothing, and the operator's `@` bypasses
  it. Bots are authored by the operator, never by Kairos (Rule 7). A voice need not run on this
  machine: an agent reached over A2A is a voice too — untrusted text in the room log, never a hand
  in this tree; the moment anything outside this machine can call *in*, §8's last row applies. A
  reviewer entity with authority would add a plane of machinery to buy safety that already comes
  from P1.
```

- [ ] **Step 5: §8 — the trigger**

Add a row before the interface-migration row:

```markdown
| A bot's composition is given the account tools, a bot room session is created other than read-only, or a bot home session's cwd widens past its `journal/` | §7.1 · D8 · D12 · run the order drill under that bot's preset |
```

- [ ] **Step 6: Commit**

```bash
git add Kairos-Design.md
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
docs(charter): section 7.1 reads no privileged second agent (the agreed 2026-09-07 wording); D11 resolved, D12 masks are visibility and D13 Kairos never edits a bot added; the bot-capability trigger
```

---

### Task 2: `CLAUDE.md` and `AGENTS.md`

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: `CLAUDE.md`**

In "What this is", change `for one operator and one agent (Kairos)` to `for one operator, one principal agent (Kairos), and operator-authored bots`. Change `Last reviewed 2026-09-04` to `Last reviewed 2026-09-09`. In the Map table add a row after the `face/` row:

```markdown
| `bots/` | one directory per bot (`_template` is the copy source, `kairos` the inert default): a dsh agent preset — persona + allow-list mask via `face/plugins/bot.js`; a bot's home session writes only `bots/<id>/journal/`; in a room (a channel session with bots rostered) `face/src/room.ts` creates one `read-only` member session per bot and Kairos calls `dispatch` |
```

In Gotchas add one bullet after the `face/client/*` one:

```markdown
- **No custom session-event types.** dsh's persistence refuses to reload a log carrying an event
  type outside its generated catalog, and `Session.append` cannot mark one ignorable — the room
  engine records every room fact on a known event (`user/message` with `source.kind: 'room'`).
```

Keep the file under ~60 lines; if it grows past, fold the bots row's second sentence.

- [ ] **Step 2: `AGENTS.md`**

Before the `Never edit:` paragraph add:

```markdown
- Rooms. A channel whose roster has bots is a room, and you organize it. `dispatch({to, mode,
  brief, reason})` starts a round: `to` are bot ids from this channel's roster (the refusal names
  the roster), `parallel` lets every voice answer independently — use it first on a fresh question —
  and `serial` lets each later voice see the earlier answers. The call returns at once; END YOUR
  TURN after it. You are woken once when the round ends, with who answered and who passed; every
  answer is in this conversation, attributed to its voice. Then name the disagreements before you
  conclude; the conclusion is yours, and a voice is evidence, never a verdict. Caps per operator
  message: 3 rounds, 10 bot messages, 2 peer continuations per round. The operator's `@<bot>`
  reaches a voice without you and you see it on your next wake. Dispatch grants a voice nothing:
  its tools are its mask, its writes are refused by its sandbox, its orders meet the same gate you do.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md AGENTS.md
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
docs: CLAUDE.md names the principal agent and the bots directory; AGENTS.md tells Kairos how a room works - dispatch, the caps, the operator's @, and that a voice is evidence
```

---

### Task 3: `DEVELOPMENT.md`

**Files:**
- Modify: `DEVELOPMENT.md`

- [ ] **Step 1: Run the suites and take the counts**

```bash
python -m pytest 2>&1 | tail -3
cd face && npm test 2>&1 | tail -6 && FACE_SMOKE=1 npm test 2>&1 | tail -6 && npm run typecheck && cd ..
git rev-parse --short HEAD
```

Write the counts into the header: `**Last full pass:** 2026-09-09 on \`feat/rooms\` @ \`<sha>\` (<N> pytest; <M> face tests, <P> pass + <S> skipped without \`FACE_SMOKE\`; <Q> under \`FACE_SMOKE=1\`; typecheck clean).`

- [ ] **Step 2: §3.7 — the state line**

Replace `State on 2026-09-07: no bot exists. …` with a paragraph stating what is true: which bots exist in the tree (`kairos`, `_template`; `bots/buffet/` untracked, the operator's), that a bot's `preset.yml` may carry a face-only `model:` route, and that a bot in a room gets a member session per room (`parentSession` = the room, `cwd` = the channel, `read-only`), created and resumed by `face/src/room.ts`, never by hand.

- [ ] **Step 3: §4.2 — module rows**

Add after the `bots.ts` row:

```markdown
| `room-rules.ts` | the room's pure rules: `ROOM_CAPS`, `resolveMentions` (by id, by one-token name), `finalTextOf` + `isPass`, `validateDispatch` (names the roster), `dispatchResultText` (names who was not called), `roomLinesOf` + `formatDelta` + `memberPrompt` (the attributed delta and the four standing rules), `roundEndText`, `parseModelRoute`; the `room` message-source vocabulary |
| `room-projection.ts` | the `room` projection unit: a pure fold of the known events that carry room facts (`dispatch` calls, room-sourced messages, turn boundaries) into `{kind, round, members, organizing}`; zod schemas; `stateVersion` |
| `room.ts` | the engine on the root context: `installRoom` (the `dispatch` tool, the unit, the bus); `RoomEngine` — members created with `ctx.agents.create` (`parentSession`, `agentPreset`, the model ref, `read-only` inside `setup`) or resumed; `driveTurn` with the extending deadline and the hard-cap cancel (`keepInbox`); rounds parallel/serial, peer continuations, the three caps, `settled`/`capped`/`superseded`; answers appended to a quiet room log, the round-end `followup`; `say` (the operator's `@`), `describe`; two routes |
```

Update the `main.ts` row: `entry: chdir, signal handlers, boot, mount every route family (the room engine included), print the URL`. Update `roster.ts`: `… the per-channel agent AND bot rosters …`; `channels.ts`: `… five routes` and mention `bots`/`allBots` on the overview; `panels.ts`: `channelFor` returns `dir`.

- [ ] **Step 4: §4.3 — the cache row**

Append to the row list: `session-projection-cache` (`writeEveryEvents: 200`, `writeIntervalMs: 5000` — the persisted projection checkpoints `session.list` reads for cold sessions; R13 closed by it) — so the overlay is **twelve** rows; fix the count wherever the section says eleven.

- [ ] **Step 5: §4.4 — the routes**

Add rows:

```markdown
| `POST /data/channels/bots` `{workspaceId, bots[]}` | `channels.ts` | `setBots` → `channels.json` (`bots[]` beside `agents[]`; 400 an id outside the bot grammar or more than `ROOM_CAPS.maxMembers` ids, 404 no such channel, 409 a corrupt file), then a dated `bots` line to `roster.log`. The overview answers `bots` (the roster) and `allBots` (every preset dsh reports, `broken` reasons included) |
| `POST /data/rooms/say` `{sessionId, text}` | `room.ts` | the operator's `@`: mentions resolved against the roster (by id, by one-token display name); nobody named → `addressed: []` and the client sends an ordinary prompt; else the message is appended to the room as the operator's own (never a prompt), a cold room is resumed through the gateway's own composition (`apiProxy.sessions.models`), and each named member turns. 400 a bad id or empty text, 404 not in a channel, 409 a corrupt roster |
| `POST /data/rooms/state` `{sessionId}` | `room.ts` | the roster, the members the engine drove this boot, the caps left; never resumes |
```

- [ ] **Step 6: §4.5 — state**

Change the `channels.json` row to `{version:1, channels:{<wsId>:{agents[], bots[]}}}`; add `$DSH_HOME/storages/session_projcache.json | dsh's projection cache (the face's overlay row) | one checkpoint record per session, written at every turn/end and at detach; what session.list reads for a cold session's projections`. Add a row `bots/<id>/journal/ | a bot's HOME session | workspace-write, cwd = the journal; the only directory a bot writes (the write to ../SOUL.md is refused, proven in room-smoke)`.

- [ ] **Step 7: §5.1, §5.2, §5.3 — the client**

§5.1 table: add `room.js` (the pure room rules: `foldMembers`, `stripChips`, `avatarGlyph`, `isMentionText`, `roundEndLine`, `gateSpeaker`); extend `mapper.js`'s row with the four room views (`bot` bubbles, `room-line`, `turn`, `mention`); extend `chat.js`'s row (the strip, inline member gates, the fold, the `@` path); `channels.js` (the bots chips). §5.2 wire: the event stream list gains `turn/start`, `turn/end` (surfaced for every session), the `room` projection key; the RPC list is unchanged; add "**Room routes** — `/data/rooms/say` before `session.prompt` when the text carries `(^|\s)@`; `/data/rooms/state` on session open." §5.3: after the pulses sentence add "pulses and turn boundaries of the room's MEMBER sessions feed the strip's fine states; a `user/message` whose source is `room`/`answer` renders in the bot's own voice, `room`/`round-end` as a room line, `room`/`delta` (in a member's own session) as a `context · room` row".

- [ ] **Step 8: §6.8 — a room round, end to end**

Append:

```markdown
**6.8 A room round.** Operator checks two bots into a channel (`POST /data/channels/bots` →
`channels.json` `bots[]`) → asks a question in a channel session → Kairos calls `dispatch`
(`tool/call`) → the engine validates against the roster, starts the round and returns at once
(`tool/result` naming who was not called) → per bot: find or create the member session
(`ctx.agents.create`, `parentSession` = the room, `agentPreset` = the bot, `read-only` pinned
inside `setup`, attached to the channel workspace) → `followup` the delta prompt (its
`messageIds` are the member's cursor, in its own log) → await that turn's `turn/end` under the
extending deadline → final text after the last tool result; empty or `(pass)` → `passed`; an
error → `failed` → an answer is appended to the room log while no Kairos turn is open (else held
until its `turn/end`) → peer `@`s queue continuations (≤ 2) → round end: every held answer
flushed, then ONE `followup` naming who answered and who passed → Kairos's synthesis turn. Every
step is a known event; the `room` projection folds them; the client renders each answer in the
bot's voice as it lands and the strip from the projection plus the members' own pulses.
```

- [ ] **Step 9: §7.3, §7.4**

§7.3: add the new suites — `room-rules`, `room-projection`, `room-engine` (the fake tree: a scriptable agent per member, a manual clock; parallel isolation, serial accumulation, continuations bounded, the three caps, `settled`/`capped`/`superseded`, deadlines with extension and the hard-cap cancel, resume-not-recreate, the `@` queued behind a running turn, the cold-room resume through the gateway), `room-client` (the fold, the strip, the glyph, the mention anchor, the line, the gate speaker), the mapper's five room frames, and the sixth FACE_SMOKE boot `room-smoke.test.ts` (what plan 2's Task 10 proves — copy the README's Step 0 sentence).

§7.4: add two rows:

```markdown
| **Room** — automated (`room-smoke`) | a real round on a stub model: dispatch → three members (answered / passed / failed) → answers on the log before one wake → synthesis in one turn; members parented, preset-joined, `read-only` first, `AGENTS.md` chain, no `dispatch`; the projection on the row and in the cache; the `@` route with a member's write refused in content; a home refused on `../SOUL.md` | that a human can read the strip; a real model's behaviour on the four standing rules | passes as of 2026-09-08 |
| **Room** — manual (`face/README.md`, eight parts) | check-in → dispatch line → attributed bubbles and the strip → the fold → `@` → an inline member question with the needs-you mark → a member's write refused → `left` and re-check → a restart keeps states and titles | per-message attribution across a mux reconnect; convergence of four voices on one model (R3) | <the PASS line plan 3's drill wrote> |
```

- [ ] **Step 10: §8, §9, §10**

§8 add: `- **No custom session-event types.** dsh's persistence refuses to reload a log carrying an unknown type; a room fact rides a known event with a room \`source\`.`

§9: R6 → `*Resolved 2026-09-09.* The charter's D11 now names the persona mechanism (plan 4).` R13 → `*Resolved 2026-09-08.* The face mounts \`dsh-session-projection-cache\` (overlay row); a cold session lists with its cached projections once it has completed a turn under the row — sessions cold before it stay \`untitled\` until resumed.` Add:

```markdown
- **R14 — A room's answers are appended to Kairos's log by the face, not spoken by Kairos's
  driver.** Honest and necessary (plan 2, deviation 2), but it means a room log can gain user-role
  messages while no client watches and while Kairos is idle; the persistence write path records
  them like any event. The `quiet` rule (no open turn) is what keeps a running request intact.
- **R15 — Fine states are presence, not truth.** `thinking` / `writing` / `tool` on the strip come
  from the members' own `assistant/chunk` block starts, held in the client's memory and cleared at
  turn boundaries; a reload loses them; the log never held them.
- **R16 — The membership rule is a header rule.** A session is a member of `P` when its header
  names `P`, has no `origin`, and a bot preset, and `P` runs the host. A fork of a room keeps the
  host preset and a subagent child carries `origin`, so both stay out; a blank session re-linked
  to another preset through `agentPreset.select` (an RPC the face never calls) could masquerade.
- **R17 — `superseded` is a third outcome.** The spec named two; a round the operator's next
  message cut short is neither settled nor capped, and the log says so.
```

§10: item 3 → done (D11 named in the charter); item 9 → `**Rooms** — built 2026-09-08/09 (plans 2–4); the live room drill passed <date>. Remaining from the spec's §11: nothing planned.` Add item 10: `**A2A voices** — the charter's §7.1 admits an agent reached over A2A as a voice; no spec, nothing built; the day anything outside this machine can call in, §8's last row applies.`

- [ ] **Step 11: Commit**

```bash
git add DEVELOPMENT.md
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
docs(reference): DEVELOPMENT records the room engine and its client as built - modules, the cache row, the three routes, the state files, the wire, a room round end to end, the suites and drills, R6 and R13 resolved, R14-R17 recorded, the forward list moved
```

---

### Task 4: `ROADMAP.md` and the spec's §16 blocks for plans 3 and 4

**Files:**
- Modify: `ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md`

- [ ] **Step 1: `ROADMAP.md`**

Append to Part II: `; 2026-09-07..09 bots and rooms (spec \`docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md\`, plans 1–4): bots as dsh presets with a home, rooms with \`dispatch\`, member sessions, the strip, the live drill; charter §7.1 amended.`

- [ ] **Step 2: The spec's §16**

Append after the plan-2 block:

```markdown
### Plan 3 — the room in the client, and the drills

Built 2026-09-09 on `feat/rooms` (<N> face tests; the live drill passed <date>, recorded in
`face/README.md`). Deviations, each decided by the wire plan 2 left: (1) the dispatch line is the
`dispatch` tool card's own collapsed row — the result text plan 2 wrote is the spec's line
verbatim; (2) fine states are derived from the member sessions' own `assistant/chunk` block starts
and `turn/*` boundaries, which the mux forwards for every live session — the unit carries coarse
state only; (3) the fold rule is the header rule (plan 2, deviation 7); (4) a member's gate renders
inline when its room is on screen, headed with the bot's name, answered against the member's own
session — the wire already required that. §6's "no with-whom column" holds. The drill's eight parts
and the PASS line are in the README.

### Plan 4 — the charter and the documents

Written 2026-09-09 after plans 2–3 shipped: §10's amendment landed in `Kairos-Design.md` §7.1
verbatim; D11 marked resolved, D12 and D13 added, the §8 trigger added; `CLAUDE.md`, `AGENTS.md`,
`DEVELOPMENT.md` (§3.7, §4.2–4.5, §5.1–5.3, §6.8, §7.3–7.4, §8, §9 R6/R13/R14–R17, §10) and
`ROADMAP.md` describe the tree as built. This document is frozen: its Status line stays as written
and its truth now lives where §16's blocks point.
```

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
docs: the roadmap's built log carries the bots-and-rooms arc; the spec's section 16 records plans 3 and 4 and freezes the document
```

---

## Self-review

**Spec §10 coverage.** The §7.1 wording → Task 1 Step 4 verbatim; §1's two collateral edits → Task 1 Step 2; `CLAUDE.md` mirror → Task 2; D12 and D13 → Task 1 Step 3; the §8 trigger → Task 1 Step 5. §14 item 4 lists `AGENTS.md` (Task 2), `DEVELOPMENT.md` (Task 3), `CLAUDE.md` (Task 2). §12's residuals R1–R8 were recorded in plan 1's docs; the plan-2/3 residuals (R14–R17) → Task 3 Step 10; §16's plan-3/4 blocks → Task 4.

**Placeholder scan.** The `<…>` in Task 3 (counts, the drill's PASS line) and Task 4 (dates, counts) are measurements the executor reads off the suite runs and the README — each says where the value comes from.

**Consistency.** The overlay row count (twelve) is stated in one place and the instruction says to fix every other mention; the residual numbering continues from R13; the forward list's item numbers are unchanged except 3 and 9 (done) and the new 10.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-08-rooms-4-charter-and-docs.md`. Execute with **superpowers:subagent-driven-development** after plan 3's live drill has its PASS line: one subagent per task (Tasks 1–4), a documentation reviewer between tasks checking every sentence against the tree (a claim the code does not bear out is a finding). Then the operator's call: merge `feat/rooms` into `main` and push.
