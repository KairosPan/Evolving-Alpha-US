# The Room in the Client, and the Drills — Implementation Plan (plan 3 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After this plan the operator sees a room: each bot's answer as its own attributed bubble, the dispatch and round-end lines, a participants strip that says who is preparing an answer, a member's question or escalation card inline in the room and answered there, the members folded under their room in the sidebar, a needs-you mark on the channel row and the landing page, bots checked in on the channel page, and `@` in the composer reaching a bot without waking Kairos — and `face/README.md` documents the mechanism and a live drill that passed.

**Architecture:** Everything the client shows about a room derives from what plan 2 already puts on the wire: `user/message` events whose `source.kind === 'room'` (answers, round ends, a member's delta), the operator's `mention` field, the `dispatch` tool's own call/result card, the `room` projection unit (coarse states, on `session/projection` frames and on `session.list` rows), the member sessions' own `assistant/chunk` block starts and `turn/*` boundaries (fine states — the mux forwards every live session), the gate frames (which carry the member's `sessionId`), the `session.list` header fields (`parentSessionId`, `agentPreset`, `origin` — the fold rule), and two loopback routes (`/data/rooms/state`, `/data/rooms/say`). The pure decisions live in one new browser module, `face/client/room.js`, tested under `node:test`; `chat.js` wires them; `mapper.js` grows four view kinds; `channels.js` grows the bots chips. No `innerHTML` anywhere, no new client-side retention of other sessions' frames beyond the fine-state map and the gate map that already exist.

**Tech Stack:** plain-ESM browser client, no bundler, no cache headers (hard-reload after every client edit) · `node:test` via `tsx --test` importing the `.js` modules through `allowJs` · the face at `127.0.0.1:3090` for the live drill.

**Spec:** `docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md` — read §4.3 (the dispatch line), §4.4 (`@`), §4.7 (`left`), §5 (the human in the room), §6 (the client), §8's live drill, §14, and §16's plan-2 block (the deviations this client is built on: no `room/*` events, answers appended to the log, fine states are the client's). This plan is §14 item 3. Plan 2 must be merged into the branch this plan builds on; its interfaces are named in each task.

**Deviations from the spec, decided here.**

1. **The dispatch line is the tool card's own collapsed row**, not a separate system row: the `dispatch` `tool/call` card's head already carries the tool name and, once the result lands, the result's first line — "Dispatched 巴菲特型, 投机型 (parallel), round 1 …; Not called: 宏观型." — which is the spec's line verbatim (plan 2 wrote it into the result). The card is styled as a room line; the raw result stays one click away (Rule 5, nothing hidden).
2. **Fine states come from the member sessions' own pulses**, as plan 2's deviation 3 says: `assistant/chunk` block starts (`reasoning` → thinking, `text` → writing, `tool-call` → tool) and `turn/*` boundaries, read off the mux for the member session ids the fold and `/data/rooms/state` name. The projection supplies the coarse states.
3. **The fold rule is the header rule** (plan 2, deviation 7): a session folds under `P` when its `parentSessionId` is `P`, it has no `origin`, its `agentPreset` names a bot, and `P` is in the list running the host preset. Members never file under a bot's home bucket.
4. **A member's gate renders inline when the member's room is on screen**, attributed with the bot's name; the answer names the gate's own session (the wire already requires that — `respond` refuses a payload whose `sessionId` is not the gate's).

## Global Constraints

- `face/client/*` is served with **no cache headers**: hard-reload the browser after every client edit before believing what you see (two false drill failures came from a stale `chat.js`).
- No `innerHTML` anywhere in the client; every string lands via `textContent` (`el()`), markdown through `renderMarkdown`.
- Pure decisions go in `face/client/room.js` and are tested under `node:test`; `chat.js` holds DOM and state only. Follow the split `grouping.js` / `speaker.js` / `channelName.js` already make.
- The mapper's view vocabulary is closed and documented in its `FrameView` typedef; every new kind or field is added there, and `tests/fixtures/events.jsonl` is repinned with REAL wire shapes (the plan-2 sources, verbatim).
- The fold rule and the strip's state vocabulary are exactly the spec's §6 table reduced to what the wire carries: `idle`, `organizing` (Kairos), `called`, `thinking`, `writing`, `tool`, `waiting for you`, `answered`, `passed`, `failed`, `timed-out`, `left`.
- Rule 5: a member is folded and **counted** under its room, never hidden; a roster id the mount does not report is shown; `left` is shown; `capped` and `superseded` read differently from `settled`.
- Gate answers carry the gate's own `sessionId` (`view.sessionId`), never the viewer's active session.
- Every operator send — `@` or not — goes through one place, `send()`; an `@` that resolves to nobody falls through to an ordinary prompt.
- Commit after every task (`git commit -F <file>` when the message carries backticks or parentheses). Never commit the operator's untracked files (`strategies/*`, `bots/buffet/`, `docs/research/*`, `tests/strategies/`, `face/probe4.ts`, `.claude/launch.json`, `docs/storage-industry-chain-2026.md`, `.bots-smoke-*`).
- Nothing in this plan edits `Kairos-Design.md`, `CLAUDE.md`, `AGENTS.md` or `DEVELOPMENT.md` (plan 4). `face/README.md` is this plan's (Task 9).

## File Structure

| File | Responsibility |
|---|---|
| `face/client/mapper.js` | + `bubble` role `bot` with `bot`/`name`; + `form` on room-sourced bubbles; + `mention` on operator bubbles; + kind `room-line` (`round-end`); + kind `turn` (`turn/start`, `turn/end`, any session) |
| `face/client/room.js` (new, pure) | `avatarGlyph`, `isMentionText`, `foldMembers`, `stripChips`, `roundEndLine`, `gateSpeaker` |
| `face/client/grouping.js` | `bucketFor(channel, archived, bot, member)` — a member never files under a bot |
| `face/client/chat.js` | attributed bot bubbles; room lines; the dispatch card styled as a line; the strip; inline member gates; the `@` path; the sidebar fold and the needs-you marks; the channel page's bots glue |
| `face/client/channels.js` | "bots in this channel" chips, the landing page's needs-you chips |
| `face/client/index.html` | `#strip` |
| `face/client/chat.css` | `.msg.bot`, `.avatar`, `.strip`, `.strip-chip[data-state]`, `.room-line`, `.card[data-tool="dispatch"]`, `.conv-member`, `.conv-members`, `.needs-you` |
| `face/tests/mapper.test.ts`, `tests/fixtures/events.jsonl` | five new frames (26 lines) |
| `face/tests/room-client.test.ts` (new), `tests/grouping.test.ts` | the pure helpers; the member rule |
| `face/README.md` | the Rooms section; the room drill; the Bots section's "Not built here" paragraph retired; the channels section's roster paragraph |

---

### Task 1: The mapper learns the room — `face/client/mapper.js`, the fixtures

**Files:**
- Modify: `face/client/mapper.js`
- Modify: `face/tests/fixtures/events.jsonl`, `face/tests/mapper.test.ts`

**Interfaces:**
- Consumes: plan 2's sources — answer `{ kind: 'room', form: 'answer', bot, name, sessionId, turn, round }`, round end `{ kind: 'room', form: 'round-end', round, outcome, turns: [{ bot, name, sessionId, state, turn?, reason? }] }`, delta `{ kind: 'room', form: 'delta', room, bot, messageIds, trigger, brief? }`, the operator's `{ kind: 'user', mention: string[] }`.
- Produces (`FrameView` additions): `role: "bot"` with `bot: string`, `name: string`; `form?: string` on any room-sourced bubble; `mention?: string[]` on operator bubbles; kind `"room-line"` with `line: "round-end"`, `round: number`, `outcome: string`, `turns: unknown[]`, `text`; kind `"turn"` with `phase: "start" | "end"`, `turn: number`, `sessionId`, `reason?: string`.

- [ ] **Step 1: Append five real frames to `face/tests/fixtures/events.jsonl`**

(one line each, no wrapping; `time` any epoch ms):

```json
{"type":"server-request","rpcId":"r-22","method":"session/event","payload":{"type":"session/event","sessionId":"s1","event":{"type":"user/message","seq":30,"time":1756512100000,"surfaceOp":"append","data":{"id":"a-1","role":"user","content":[{"type":"text","text":"买。理由：便宜。"}],"source":{"kind":"room","form":"answer","bot":"buffett","name":"巴菲特型","sessionId":"s-b","turn":1,"round":1}}}}}
{"type":"server-request","rpcId":"r-23","method":"session/event","payload":{"type":"session/event","sessionId":"s1","event":{"type":"user/message","seq":31,"time":1756512101000,"surfaceOp":"append","data":{"id":"re-1","role":"user","content":[{"type":"text","text":"Round 1 ended (settled).\nAnswered: 巴菲特型. Passed: 投机型. Failed: none. Timed out: none.\nName the disagreements."}],"source":{"kind":"room","form":"round-end","round":1,"outcome":"settled","turns":[{"bot":"buffett","name":"巴菲特型","sessionId":"s-b","state":"answered","turn":1},{"bot":"speculator","name":"投机型","sessionId":"s-s","state":"passed","turn":1}]}}}}}
{"type":"server-request","rpcId":"r-24","method":"session/event","payload":{"type":"session/event","sessionId":"s1","event":{"type":"user/message","seq":32,"time":1756512102000,"surfaceOp":"append","data":{"id":"u-9","role":"user","content":[{"type":"text","text":"@buffett 杠杆呢？"}],"source":{"kind":"user","mention":["buffett"]}}}}}
{"type":"server-request","rpcId":"r-25","method":"session/event","payload":{"type":"session/event","sessionId":"s-b","event":{"type":"user/message","seq":3,"time":1756512103000,"surfaceOp":"append","data":{"id":"d-1","role":"user","content":[{"type":"text","text":"You are in the room \"storage-chain\" …\nNew in the room since you last spoke:\n操作员: 开会"}],"source":{"kind":"room","form":"delta","room":"s1","bot":"buffett","messageIds":["msg-1"],"trigger":"dispatch","brief":"state a view"}}}}}
{"type":"server-request","rpcId":"r-26","method":"session/event","payload":{"type":"session/event","sessionId":"s-b","event":{"type":"turn/end","seq":9,"time":1756512104000,"data":{"turn":1,"reason":{"kind":"completed"}}}}}
```

- [ ] **Step 2: Write the failing tests**

In `face/tests/mapper.test.ts` change the alignment test to 26 and append:

```ts
test("a member's answer is a BOT bubble with its name and id, never an operator bubble or a context row", () => {
  const v = views[21];
  assert.equal(v.kind, "bubble");
  assert.equal(v.role, "bot");
  assert.equal(v.bot, "buffett");
  assert.equal(v.name, "巴菲特型");
  assert.equal(v.form, "answer");
  assert.equal(v.text, "买。理由：便宜。");
  assert.equal(v.seq, 30);
});

test("the round-end message is a room line carrying the outcome and every turn's state", () => {
  const v = views[22];
  assert.equal(v.kind, "room-line");
  assert.equal(v.line, "round-end");
  assert.equal(v.round, 1);
  assert.equal(v.outcome, "settled");
  assert.deepEqual((v.turns as { bot: string; state: string }[]).map((t) => `${t.bot}:${t.state}`), ["buffett:answered", "speculator:passed"]);
  assert.match(v.text ?? "", /^Round 1 ended/);
});

test("the operator's @ stays an operator bubble and names whom it addressed", () => {
  const v = views[23];
  assert.equal(v.kind, "bubble");
  assert.equal(v.role, "operator");
  assert.equal(v.source, "user");
  assert.deepEqual(v.mention, ["buffett"]);
});

test("a member's delta prompt is an injected context row of source room, form delta", () => {
  const v = views[24];
  assert.equal(v.kind, "bubble");
  assert.equal(v.role, "operator");
  assert.equal(v.source, "room");
  assert.equal(v.form, "delta");
  assert.equal(v.sessionId, "s-b");
});

test("turn boundaries are surfaced for every session, so the strip can clear a member's fine state", () => {
  const v = views[25];
  assert.equal(v.kind, "turn");
  assert.equal(v.phase, "end");
  assert.equal(v.turn, 1);
  assert.equal(v.sessionId, "s-b");
  assert.equal(v.reason, "completed");
});
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd face && npx tsx --test tests/mapper.test.ts`
Expected: FAIL — the alignment count and the new kinds.

- [ ] **Step 4: Implement**

In `mapper.js`'s `FrameView` typedef add: `"room-line"|"turn"` to `kind`; `"bot"` to `role`; `@property {string} [bot]`, `[name]`, `[form]`, `@property {string[]} [mention]`, `@property {string} [line]`, `[outcome]`, `@property {number} [round]`, `@property {unknown[]} [turns]`, `@property {"start"|"end"} [phase]`, `@property {number} [turn]`, `@property {string} [reason]`.

Replace `bubble()`:

```js
function bubble(role, message, base, interrupted) {
  const text = isObject(message) ? blocksText(message.content) : "";
  const thinking = role === "kairos" && isObject(message) ? blocksReasoning(message.content) : "";
  if (text === "" && thinking === "") return ignore();
  const src = isObject(message) && isObject(message.source) ? message.source : {};
  const kind = typeof src.kind === "string" ? src.kind : undefined;
  const form = typeof src.form === "string" ? src.form : undefined;
  /* A room-sourced user message is one of three things (plan 2, deviation 1):
   * a member's ANSWER (a bubble in the bot's own voice), the ROUND END (a
   * line), or - in a member's own session - the DELTA it was prompted with
   * (an injected context row, like every other plugin-sourced message). */
  if (role === "operator" && kind === "room") {
    if (form === "answer" && typeof src.bot === "string") {
      return { ...base, kind: "bubble", role: "bot", bot: src.bot, name: typeof src.name === "string" && src.name !== "" ? src.name : src.bot, form, text, interrupted: false, source: kind };
    }
    if (form === "round-end") {
      return { ...base, kind: "room-line", line: "round-end", round: typeof src.round === "number" ? src.round : undefined, outcome: typeof src.outcome === "string" ? src.outcome : undefined, turns: Array.isArray(src.turns) ? src.turns : [], text };
    }
  }
  const mention = kind === "user" && Array.isArray(src.mention) ? src.mention.filter((m) => typeof m === "string") : undefined;
  return {
    ...base,
    kind: "bubble",
    role,
    text,
    interrupted,
    source: kind,
    form,
    ...(mention !== undefined && mention.length > 0 ? { mention } : {}),
    thinking: thinking === "" ? undefined : thinking,
  };
}
```

In `mapSessionEvent`, before `default:` add:

```js
    case "turn/start":
    case "turn/end": {
      const reason = isObject(data.reason) && typeof data.reason.kind === "string" ? data.reason.kind : undefined;
      return { ...base, kind: "turn", phase: event.type === "turn/start" ? "start" : "end", turn: typeof data.turn === "number" ? data.turn : undefined, ...(reason === undefined ? {} : { reason }) };
    }
```

(`turn` views carry a `seq`; `chat.js` must NOT dedupe them into the transcript — Task 5 routes them to the strip before the seq check, the way pulses are routed.)

- [ ] **Step 5: Run the mapper tests and the whole offline suite**

Run: `cd face && npx tsx --test tests/mapper.test.ts && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add face/client/mapper.js face/tests/mapper.test.ts face/tests/fixtures/events.jsonl
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): the mapper learns the room - a member's answer is a bot bubble with its name, the round end is a line, the operator's @ keeps whom it addressed, and turn boundaries surface for every session
```

---

### Task 2: The pure helpers — `face/client/room.js`; the member rule in `grouping.js`

**Files:**
- Create: `face/client/room.js`
- Modify: `face/client/grouping.js`
- Test: `face/tests/room-client.test.ts` (new), `face/tests/grouping.test.ts`

**Interfaces:**
- Consumes: `session.list` rows (`sessionId`, `parentSessionId`, `agentPreset`, `origin`); the `room` projection value (`{ kind, members: { [bot]: { sessionId?, name?, state, turn? } }, organizing?, round? }`); `/data/bots.json` rows.
- Produces: `avatarGlyph(id): string`; `isMentionText(text): boolean`; `foldMembers(items): { rooms: Map<string, Row[]>, members: Set<string> }`; `stripChips({ roster, projection, members, gates, fine, running, kairosName }): Chip[]` with `Chip = { id, name, state, kairos?: boolean, broken?: string, sessionId?: string }`; `roundEndLine(view): string`; `gateSpeaker(sessionId, memberRows, bots, fallback): string`; `bucketFor(channel, archived, bot, member = false)`.

- [ ] **Step 1: Write the failing tests**

```ts
// face/tests/room-client.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { avatarGlyph, foldMembers, gateSpeaker, isMentionText, roundEndLine, stripChips } from "../client/room.js";
import { bucketFor } from "../client/grouping.js";

test("avatarGlyph is deterministic per id and differs between the two template bots", () => {
  assert.equal(avatarGlyph("buffett"), avatarGlyph("buffett"));
  assert.equal(typeof avatarGlyph("x"), "string");
  assert.equal(avatarGlyph("buffett").length > 0, true);
  const set = new Set(["buffett", "speculator", "macro-view", "alpha", "beta", "gamma"].map(avatarGlyph));
  assert.ok(set.size >= 4, "six ids spread over at least four glyphs");
});

test("isMentionText is the composer anchor: start or whitespace, then @ and a token; an e-mail is not one", () => {
  assert.equal(isMentionText("@buffett hi"), true);
  assert.equal(isMentionText("hi @投机型"), true);
  assert.equal(isMentionText("mail pan@example.com"), false);
  assert.equal(isMentionText("no mention"), false);
  assert.equal(isMentionText("@ alone"), false);
});

const rows = [
  { sessionId: "room", agentPreset: "kairos", cwd: "/c" },
  { sessionId: "m1", parentSessionId: "room", agentPreset: "buffett", cwd: "/c" },
  { sessionId: "m2", parentSessionId: "room", agentPreset: "speculator", cwd: "/c" },
  { sessionId: "fork", parentSessionId: "room", agentPreset: "kairos", cwd: "/c" },
  { sessionId: "child", parentSessionId: "room", agentPreset: "buffett", origin: "subagent", cwd: "/c" },
  { sessionId: "orphan", parentSessionId: "gone", agentPreset: "buffett", cwd: "/c" },
  { sessionId: "home", agentPreset: "buffett", cwd: "/bots/buffett/journal" },
  { sessionId: "nested", parentSessionId: "m1", agentPreset: "buffett", cwd: "/c" },
];

test("foldMembers: a bot session parented by a host session is a member; forks, subagent children, orphans, homes and members-of-members are not", () => {
  const { rooms, members } = foldMembers(rows);
  assert.deepEqual([...rooms.keys()], ["room"]);
  assert.deepEqual(rooms.get("room")!.map((r) => r.sessionId), ["m1", "m2"]);
  assert.deepEqual([...members].sort(), ["m1", "m2"]);
});

test("bucketFor: a member never files under its bot's home bucket, whatever precedence says otherwise", () => {
  const bot = { id: "buffett", label: "巴菲特型" };
  assert.equal(bucketFor({ workspaceId: "ws", title: "c" }, false, bot, false).key, "bot:buffett");
  assert.equal(bucketFor({ workspaceId: "ws", title: "c" }, false, bot, true).key, "ws");
  assert.equal(bucketFor(null, false, bot, true).key, "__ungrouped");
  assert.equal(bucketFor(null, true, bot, true).key, "__archived");
});

const roster = [{ id: "buffett", name: "巴菲特型" }, { id: "speculator", name: "投机型" }, { id: "cracked", name: "cracked", broken: "not a list" }];

test("stripChips: Kairos first; roster members read the projection's coarse state, the pulses' fine state while called, a pending gate over both; a rostered-but-unmounted bot is shown broken; a member no longer rostered is left", () => {
  const projection = { kind: "room", organizing: true, members: { buffett: { sessionId: "m1", state: "called" }, speculator: { sessionId: "m2", state: "passed" }, ghost: { sessionId: "m3", state: "answered", name: "Ghost" } } };
  const chips = stripChips({ roster, projection, members: { ghost: { sessionId: "m3", name: "Ghost" } }, gates: new Set(["m2"]), fine: new Map([["m1", "writing"]]), running: false, kairosName: "Kairos" });
  assert.deepEqual(chips.map((c) => `${c.id}:${c.state}`), ["kairos:organizing", "buffett:writing", "speculator:waiting for you", "cracked:idle", "ghost:left"]);
  assert.equal(chips[0].kairos, true);
  assert.equal(chips[3].broken, "not a list");
  assert.equal(chips[1].sessionId, "m1");
});

test("stripChips: before any dispatch the strip is the roster at idle, and Kairos follows the running flag", () => {
  const chips = stripChips({ roster, projection: { kind: "none" }, members: {}, gates: new Set(), fine: new Map(), running: true, kairosName: "Kairos" });
  assert.deepEqual(chips.map((c) => c.state), ["organizing", "idle", "idle", "idle"]);
  assert.deepEqual(stripChips({ roster: [], projection: undefined, members: {}, gates: new Set(), fine: new Map(), running: false, kairosName: "Kairos" }).map((c) => c.id), ["kairos"]);
});

test("roundEndLine reads the outcome and each state group; capped and superseded say so", () => {
  const turns = [{ bot: "b", name: "巴菲特型", state: "answered" }, { bot: "s", name: "投机型", state: "passed" }, { bot: "m", name: "Macro", state: "timed-out" }];
  assert.equal(roundEndLine({ round: 1, outcome: "settled", turns }), "round 1 · settled · answered: 巴菲特型 · passed: 投机型 · timed out: Macro");
  assert.match(roundEndLine({ round: 2, outcome: "capped", turns: [] }), /^round 2 · capped/);
  assert.match(roundEndLine({ round: 1, outcome: "superseded", turns: [] }), /superseded/);
});

test("gateSpeaker names the member's bot for a member's gate, else the fallback", () => {
  const memberRows = [{ sessionId: "m1", agentPreset: "buffett" }];
  const bots = [{ id: "buffett", name: "巴菲特型" }];
  assert.equal(gateSpeaker("m1", memberRows, bots, "Kairos"), "巴菲特型");
  assert.equal(gateSpeaker("m9", memberRows, bots, "Kairos"), "Kairos");
  assert.equal(gateSpeaker("m1", memberRows, [], "Kairos"), "buffett", "no roster name: the id, never the host");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd face && npx tsx --test tests/room-client.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `face/client/room.js`**

```js
/** Pure room decisions: the tested half of the room view.
 *
 * No DOM, no network, no state - session rows, a projection value and the
 * live maps in, chips / labels / folds out. Split out of chat.js for the
 * reason grouping.js and speaker.js are: the rules must be drillable
 * without a browser.
 *
 * WHAT THE WIRE CARRIES (plan 2 of the bots-and-rooms spec): no `room/*`
 * events. A member is known from its HEADER (`parentSessionId` + a bot
 * `agentPreset`, no `origin`); a room's coarse states come from the `room`
 * projection value; fine states (thinking / writing / tool) are the member
 * sessions' own pulses, which the mux forwards for every live session.
 * @module
 */

/** A dozen distinguishable shapes; a bot keeps its glyph for life (a hash of its id). */
export const GLYPHS = ["◆", "●", "▲", "■", "◇", "○", "△", "□", "⬟", "⬢", "✦", "✧"];

/** @param {string} id @returns {string} */
export function avatarGlyph(id) {
  let h = 0;
  for (const ch of String(id)) h = (h * 31 + (ch.codePointAt(0) ?? 0)) >>> 0;
  return GLYPHS[h % GLYPHS.length];
}

/** The composer anchor: start of text or whitespace, then `@` and a token. An e-mail's `@` follows a non-space. */
export const MENTION_RE = /(^|\s)@[^\s@]/u;
/** @param {string} text @returns {boolean} */
export const isMentionText = (text) => MENTION_RE.test(text);

/** Whether a row runs the host: no preset, or the inert default. @param {{agentPreset?: unknown}} row */
const isHost = (row) => typeof row.agentPreset !== "string" || row.agentPreset === "" || row.agentPreset === "kairos";

/**
 * The fold rule (spec §2.4 as plan 2 rebuilt it): a session is a member of
 * `P` when its header names `P` as parent, it has no `origin`, its preset is
 * a bot, and `P` itself is in the list running the host. Forks carry the
 * source's preset (`kairos` for a room) and subagent children carry
 * `origin`, so both stay out; a member of a member is not a member.
 * @param {ReadonlyArray<{sessionId: unknown, parentSessionId?: unknown, agentPreset?: unknown, origin?: unknown}>} items
 * @returns {{rooms: Map<string, any[]>, members: Set<string>}} rooms → their member rows, in list order; every member id.
 */
export function foldMembers(items) {
  const byId = new Map(items.map((s) => [String(s.sessionId), s]));
  /** @type {Map<string, any[]>} */
  const rooms = new Map();
  const members = new Set();
  for (const s of items) {
    if (typeof s.parentSessionId !== "string" || s.origin !== undefined || isHost(s)) continue;
    const room = byId.get(s.parentSessionId);
    if (room === undefined || !isHost(room)) continue;
    const list = rooms.get(s.parentSessionId) ?? [];
    if (list.length === 0) rooms.set(s.parentSessionId, list);
    list.push(s);
    members.add(String(s.sessionId));
  }
  return { rooms, members };
}

/** @typedef {{id: string, name: string, state: string, kairos?: boolean, broken?: string, sessionId?: string}} Chip */

/**
 * The participants strip (spec §6): Kairos first, then every rostered bot,
 * then any member the roster no longer carries (`left`). States, in
 * precedence: a pending gate on the member's session → `waiting for you`;
 * while `called`, the live fine state if any; else the projection's coarse
 * state; else `idle`. Kairos is `organizing` while the projection says so,
 * or - before the session is a room - while the list says it is running.
 * @param {{roster: ReadonlyArray<{id: string, name: string, broken?: string}>, projection: any, members: Record<string, {sessionId?: string, name?: string}>, gates: Set<string>, fine: Map<string, string>, running: boolean, kairosName?: string}} input
 * @returns {Chip[]}
 */
export function stripChips(input) {
  const room = input.projection !== null && typeof input.projection === "object" && input.projection.kind === "room" ? input.projection : null;
  const projMembers = room !== null && room.members !== null && typeof room.members === "object" ? room.members : {};
  const organizing = room !== null ? room.organizing === true : input.running === true;
  /** @type {Chip[]} */
  const chips = [{ id: "kairos", name: input.kairosName ?? "Kairos", state: organizing ? "organizing" : "idle", kairos: true }];
  const stateOf = (bot) => {
    const sessionId = input.members[bot]?.sessionId ?? projMembers[bot]?.sessionId;
    if (sessionId !== undefined && input.gates.has(sessionId)) return { state: "waiting for you", sessionId };
    const coarse = projMembers[bot]?.state;
    if (coarse === "called") return { state: (sessionId !== undefined && input.fine.get(sessionId)) || "called", sessionId };
    return { state: typeof coarse === "string" ? coarse : "idle", sessionId };
  };
  const seen = new Set();
  for (const bot of input.roster) {
    seen.add(bot.id);
    const { state, sessionId } = stateOf(bot.id);
    chips.push({ id: bot.id, name: bot.name, state, ...(bot.broken === undefined ? {} : { broken: bot.broken }), ...(sessionId === undefined ? {} : { sessionId }) });
  }
  for (const bot of new Set([...Object.keys(input.members), ...Object.keys(projMembers)])) {
    if (seen.has(bot)) continue;
    const sessionId = input.members[bot]?.sessionId ?? projMembers[bot]?.sessionId;
    chips.push({ id: bot, name: input.members[bot]?.name ?? projMembers[bot]?.name ?? bot, state: "left", ...(sessionId === undefined ? {} : { sessionId }) });
  }
  return chips;
}

/** The round-end line: `round 1 · settled · answered: A · passed: B`; empty groups are omitted. @param {{round?: unknown, outcome?: unknown, turns?: unknown}} view */
export function roundEndLine(view) {
  const turns = Array.isArray(view.turns) ? view.turns : [];
  const group = (state, label) => {
    const names = turns.filter((t) => t && t.state === state).map((t) => (typeof t.name === "string" && t.name !== "" ? t.name : String(t.bot)));
    return names.length === 0 ? null : `${label}: ${names.join(", ")}`;
  };
  const head = view.outcome === "capped" ? "capped - the bot-message cap was reached"
    : view.outcome === "superseded" ? "superseded by a new operator message"
    : String(view.outcome ?? "ended");
  return [`round ${String(view.round ?? "?")}`, head, group("answered", "answered"), group("passed", "passed"), group("failed", "failed"), group("timed-out", "timed out")]
    .filter((part) => part !== null).join(" · ");
}

/** Whose gate this is: the member's bot name when the session is a member of the room on screen, else the fallback (the session's own voice).
 * @param {string|undefined} sessionId @param {ReadonlyArray<{sessionId: unknown, agentPreset?: unknown}>} memberRows @param {ReadonlyArray<{id: string, name?: unknown}>} bots @param {string} fallback */
export function gateSpeaker(sessionId, memberRows, bots, fallback) {
  const row = memberRows.find((r) => String(r.sessionId) === sessionId);
  if (row === undefined || typeof row.agentPreset !== "string") return fallback;
  const bot = bots.find((b) => b.id === row.agentPreset);
  const name = typeof bot?.name === "string" ? bot.name.trim() : "";
  return name === "" ? row.agentPreset : name;
}
```

In `face/client/grouping.js`, `bucketFor(channel, archived, bot, member = false)`: after the archived check add `if (member) bot = null;` with the doc line "a room member is reached through its room (folded under it); it never files under the bot's home bucket, even though its header names the bot".

- [ ] **Step 4: Run the tests**

Run: `cd face && npx tsx --test tests/room-client.test.ts tests/grouping.test.ts && npm run typecheck`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add face/client/room.js face/client/grouping.js face/tests/room-client.test.ts face/tests/grouping.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): the room's pure client rules - the header fold, the strip's chip states, the avatar glyph, the mention anchor, the round-end line, the gate speaker; a member never files under a bot's home
```

---

### Task 3: Attributed bubbles, room lines, the dispatch line — `chat.js`, `chat.css`

**Files:**
- Modify: `face/client/chat.js` (`bubbleNode`, `accept`, `fillResult`, imports)
- Modify: `face/client/chat.css`

**Interfaces:**
- Consumes: Task 1's views (`role: "bot"`, `room-line`), Task 2's `avatarGlyph`, `roundEndLine`.
- Produces: `.msg.bot` bubbles with `.who` = glyph + name; `.room-line` rows; the `dispatch` card styled as a line.

- [ ] **Step 1: Bot bubbles**

In `chat.js` import `avatarGlyph, roundEndLine` from `./room.js`. In `bubbleNode`, before `const operator = …`:

```js
  /* A member's answer: the bot's own lane and name, an avatar glyph the eye
   * learns, markdown like Kairos's. Attribution is per MESSAGE here - the
   * room log carries several voices - which is what `speaker` (per session)
   * could never say (R12's last mile). */
  if (view.role === "bot") {
    const wrap = el("div", "msg k bot");
    const who = el("div", "who");
    who.append(el("span", "avatar", avatarGlyph(String(view.bot))), el("span", "who-name", String(view.name ?? view.bot)));
    wrap.append(who);
    const bubble = el("div", "bubble md-bubble");
    const md = renderMarkdown(String(view.text ?? ""));
    bubble.append(md.node);
    if (md.doc) wrap.classList.add("doc");
    wrap.append(bubble);
    return wrap;
  }
```

- [ ] **Step 2: Room lines**

Add after `thinkRow`:

```js
/** A room fact as one quiet centred line: the round end today. @param {Record<string, any>} view */
function roomLineNode(view) {
  const node = el("div", "room-line");
  node.append(el("span", "room-line-text", view.line === "round-end" ? roundEndLine(view) : dash(view.text)));
  node.title = dash(view.text);
  return node;
}
```

and in `accept`: `else if (view.kind === "room-line") place(view, roomLineNode(view));`.

- [ ] **Step 3: The dispatch line**

In `fillResult`, after the `.sum` block: `if (node.dataset.tool === "dispatch") node.classList.add("dispatch");` — and in `toolCardNode` nothing changes (the card's head already reads `dispatch`, the producer reads the `presentCall` title once the call view lands; on result the `.sum` reads the first line: "Dispatched …; Not called: …").

- [ ] **Step 4: CSS**

Append to `chat.css`:

```css
/* ---------- rooms: attributed voices, room lines, the strip ---------- */

.msg.bot .who { display: flex; align-items: center; gap: 6px; text-transform: none; letter-spacing: 0.04em; }
.msg.bot .avatar { font-size: 11px; color: var(--accent); }
.msg.bot .bubble { border-left: 3px solid var(--accent); }

.room-line {
  align-self: center;
  max-width: 88%;
  margin: 4px 0;
  padding: 3px 10px;
  border: 1px dashed var(--line);
  border-radius: var(--r-chip);
  font: 11px var(--mono);
  letter-spacing: 0.04em;
  color: var(--dim);
  text-align: center;
}

/* the dispatch card reads as a line: who was called, how, and who was NOT */
.card.dispatch { border-left-color: var(--accent); }
.card.dispatch .kind { color: var(--accent); }
.card.dispatch .sum { color: var(--text); }
```

- [ ] **Step 5: Prove it in the browser**

Start the face (`preview_start` name `face`, or `cd face && npm start` in a terminal the operator owns — never from Bash here), hard-reload, open a room session from plan 2's smoke if one exists in the operator's home, or run the smoke's flow manually later in Task 9. For this task the offline check is enough: `cd face && npm test` (mapper + room-client) and a syntax check of the client, `node --check client/chat.js`.

- [ ] **Step 6: Commit**

```bash
git add face/client/chat.js face/client/chat.css
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): a member's answer renders in the bot's own voice with an avatar, the round end as a room line, the dispatch card as the who-was-called line
```

---

### Task 4: The sidebar fold and the needs-you marks — `chat.js`, `channels.js`

**Files:**
- Modify: `face/client/chat.js` (`refreshSessions`, `convRow`, `groupHeader`, the `collapsedGroups` loader, `openChannel`)
- Modify: `face/client/channels.js` (the sessions block)
- Modify: `face/client/chat.css`

**Interfaces:**
- Consumes: Task 2's `foldMembers`, `bucketFor(…, member)`; the `gates` map (rpcId → view with `sessionId`).
- Produces: member rows folded under their room row with a count and a fold key `room:<sessionId>`; `needsYou(sessionId)`; a `needs-you` mark on the channel group header and the landing page's session rows.

- [ ] **Step 1: The fold in `refreshSessions`**

Import `foldMembers` from `./room.js`. After `lastSessions = …`:

```js
  const fold = foldMembers(lastSessions);
  memberFold = fold; // module state the strip and the gates read (Task 5/6)
```

Declare near `lastSessions`: `/** The header fold: room id → member rows; every member id. @type {{rooms: Map<string, any[]>, members: Set<string>}} */ let memberFold = { rooms: new Map(), members: new Set() };`

In the bucket loop, skip members: `if (fold.members.has(id)) continue;` and pass the fourth argument: `bucketFor(channelOf(id), archived, botOf(summary), false)`.

When rendering rows inside a bucket, after `box.append(row)`, if `fold.rooms.has(String(summary.sessionId))`, append `memberBox(summary, fold.rooms.get(id))`:

```js
/** The members folded under a room row: one indented row per member, the bot's name as its label, collapsed by default. */
function memberBox(roomSummary, members) {
  const key = `room:${String(roomSummary.sessionId)}`;
  const box = el("div", "conv-members");
  const head = el("div", "conv-members-head");
  const chev = el("span", "chev", collapsedGroups.has(key) ? "▸" : "▾");
  head.append(chev, el("span", "conv-members-n", `${members.length} member${members.length === 1 ? "" : "s"}`));
  const list = el("div");
  list.hidden = collapsedGroups.has(key);
  head.addEventListener("click", () => {
    if (collapsedGroups.has(key)) collapsedGroups.delete(key); else collapsedGroups.add(key);
    persistCollapsed();
    list.hidden = collapsedGroups.has(key);
    chev.textContent = list.hidden ? "▸" : "▾";
  });
  for (const m of members) {
    const row = el("div", "conv conv-pick conv-member");
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    const top = el("div", "conv-top");
    top.append(el("span", "conv-name", botOf(m)?.label ?? String(m.agentPreset)));
    row.append(top);
    const sub = el("div", "conv-sub");
    if (needsYou(String(m.sessionId))) sub.append(waitingChip());
    if (m.running === true) sub.append(el("span", "chip", "running"));
    row.append(sub);
    row.title = `${dash(m.cwd)}\n${when(m.updatedAt)}`;
    row.addEventListener("click", () => void openSession(String(m.sessionId)));
    row.addEventListener("keydown", (event) => {
      const k = /** @type {KeyboardEvent} */ (event).key;
      if (k !== "Enter" && k !== " ") return;
      event.preventDefault();
      void openSession(String(m.sessionId));
    });
    convRows.set(String(m.sessionId), row);
    row.dataset.title = botOf(m)?.label ?? String(m.agentPreset);
    list.append(row);
  }
  box.append(head, list);
  return box;
}
```

In the `collapsedGroups` loader's filter admit the new grammar: `|| /^room:session-[0-9a-f-]{36}$/.test(k)`.

- [ ] **Step 2: `needsYou` and the marks**

Add near `waitingChip`:

```js
/** A session needs the operator when a gate is pending on it or on any of its members. @param {string} sessionId */
function needsYou(sessionId) {
  const ids = new Set([sessionId, ...(memberFold.rooms.get(sessionId) ?? []).map((m) => String(m.sessionId))]);
  return [...gates.values()].some((gate) => ids.has(gate.sessionId));
}
```

`convRow`: replace its `gates` scan with `if (needsYou(id)) sub.append(waitingChip());`.

`groupHeader(key, label, count, box, channel, needs)`: a sixth argument; when `needs` is true append `el("span", "needs-you", "●")` with `title = "a session in this channel is waiting on you"` after the name. In `refreshSessions`'s header loop compute `const needs = bucket.items.some((s) => needsYou(String(s.sessionId)));` and pass it.

`openChannel`: each `payload.sessions` row gains `waiting: needsYou(id)`; `channels.js`'s sessions block appends `el("span", "chip waiting", "waiting")` when `row.waiting === true`.

- [ ] **Step 3: CSS**

```css
.conv-members { margin: 0 0 0 14px; border-left: 1px solid var(--line); }
.conv-members-head { display: flex; align-items: center; gap: 6px; padding: 4px 10px; font: 10px var(--mono); letter-spacing: 0.06em; text-transform: uppercase; color: var(--dim); cursor: pointer; user-select: none; }
.conv-member { padding: 6px 12px; }
.conv-member .conv-name { font-weight: 500; font-size: 13px; }
.needs-you { color: var(--danger); font-size: 9px; margin-left: 4px; }
```

- [ ] **Step 4: Offline check and commit**

Run: `cd face && node --check client/chat.js && node --check client/channels.js && npm test`
Expected: clean, PASS.

```bash
git add face/client/chat.js face/client/channels.js face/client/chat.css
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): members fold under their room in the sidebar, counted, with the bot's name; a pending gate on a session or its members marks the session row, the channel header and the landing page (needs-you at the index level)
```

---

### Task 5: The participants strip — `index.html`, `chat.js`, `chat.css`

**Files:**
- Modify: `face/client/index.html` (`#strip` above `#scroll`)
- Modify: `face/client/chat.js` (`acceptFrame`, `acceptProjection`, `openSession`, `newSession`, a `renderStrip`, room state fetch)
- Modify: `face/client/chat.css`

**Interfaces:**
- Consumes: `stripChips` (Task 2), `memberFold` (Task 4), the `room` projection value in `projStore`, `turn`/`pulse` views (Task 1), the `gates` map, `POST /data/rooms/state { sessionId }` → `{ roster: [{id,name,broken?}], members: { [bot]: { sessionId, name } }, caps, round? }` (plan 2).
- Produces: `roomInfo` (per active session), `fineStates: Map<sessionId, "thinking"|"writing"|"tool">`, `memberSessionIds(): Set<string>`, `renderStrip()`.

- [ ] **Step 1: The element**

In `index.html`, between `</header>` and `<div id="scroll" class="flow">`:

```html
    <!-- The participants strip: who is in the room and what each is doing,
         built by chat.js from the room projection and the members' own pulses.
         Hidden unless the session on screen is in a channel with bots. -->
    <div id="strip" class="strip" hidden></div>
```

- [ ] **Step 2: State and the fetch**

In `chat.js`, near `projStore`:

```js
/** The room on screen, from `/data/rooms/state`: the channel's bot roster and
 * the members the engine has driven this boot. `null` when the active session
 * is in no channel. @type {{roster: any[], members: Record<string, any>}|null} */
let roomInfo = null;
/** Live fine states of member sessions (thinking / writing / tool) from their
 * own pulses; cleared at their turn boundaries. Presence, not truth. @type {Map<string, string>} */
const fineStates = new Map();

/** The member session ids of the room on screen: the header fold ∪ what the engine reports. */
function memberSessionIds() {
  const ids = new Set((memberFold.rooms.get(activeSession ?? "") ?? []).map((m) => String(m.sessionId)));
  for (const m of Object.values(roomInfo?.members ?? {})) if (typeof m?.sessionId === "string") ids.add(m.sessionId);
  return ids;
}

/** Refetch the room state for the session on screen; a session in no channel reads `null`. */
async function loadRoomInfo() {
  const id = activeSession;
  if (id === null) { roomInfo = null; renderStrip(); return; }
  try {
    const body = await panelData("/data/rooms/state", { sessionId: id });
    if (activeSession !== id) return;
    roomInfo = { roster: Array.isArray(body.roster) ? body.roster : [], members: body.members ?? {} };
  } catch {
    if (activeSession !== id) return;
    roomInfo = null; // 404: not in a channel - no strip
  }
  renderStrip();
}
```

- [ ] **Step 3: The renderer**

```js
const KAIROS_STATES = { organizing: "organizing", idle: "" };
/** Draw the strip for the session on screen, or hide it. */
function renderStrip() {
  const strip = $("#strip");
  const projection = activeSession === null ? undefined : projStore.get(activeSession)?.get("room")?.value;
  const isRoom = projection !== null && typeof projection === "object" && /** @type {any} */ (projection).kind === "room";
  if (roomInfo === null || (roomInfo.roster.length === 0 && !isRoom)) { strip.hidden = true; strip.replaceChildren(); return; }
  const running = lastSessions.find((s) => String(s.sessionId) === activeSession)?.running === true;
  const chips = stripChips({
    roster: roomInfo.roster.filter((b) => b.id !== "kairos"),
    projection,
    members: roomInfo.members,
    gates: new Set([...gates.values()].map((g) => g.sessionId)),
    fine: fineStates,
    running,
    kairosName: HOST_NAME,
  });
  strip.replaceChildren();
  for (const chip of chips) {
    const node = el("span", chip.kairos ? "strip-chip kairos" : "strip-chip");
    node.dataset.state = chip.state;
    if (!chip.kairos) node.append(el("span", "avatar", avatarGlyph(chip.id)));
    node.append(el("span", "strip-name", chip.name));
    node.append(el("span", "strip-state", chip.kairos ? (KAIROS_STATES[chip.state] ?? chip.state) : chip.state));
    if (chip.broken) { node.classList.add("broken"); node.title = `dsh cannot mount this bot: ${chip.broken}`; }
    if (chip.sessionId) {
      node.title = `session ${chip.sessionId}`;
      node.classList.add("open");
      node.addEventListener("click", () => void openSession(String(chip.sessionId)));
    }
    strip.append(node);
  }
  strip.hidden = false;
}
```

Import `stripChips` from `./room.js`.

- [ ] **Step 4: Feed it**

In `acceptFrame`, the `pulse` branch: after the active-session pulse handling add, before `return`:

```js
    if (view.sessionId !== undefined && memberSessionIds().has(view.sessionId)) {
      fineStates.set(view.sessionId, view.mode === "reasoning" ? "thinking" : view.mode === "tool-call" ? "tool" : "writing");
      renderStrip();
    }
```

Add a `turn` branch right after the `pulse` branch (before `projection`):

```js
  if (view.kind === "turn") {
    // A member's turn boundary: its fine state ends with the turn; the coarse
    // state (answered / passed / …) arrives on the room's projection.
    if (view.sessionId !== undefined && memberSessionIds().has(view.sessionId)) {
      if (view.phase === "end") fineStates.delete(view.sessionId);
      else fineStates.set(view.sessionId, "thinking");
      renderStrip();
    }
    return;
  }
```

In `acceptProjection`, after storing: `if (id === activeSession && view.key === "room") renderStrip();`. In `acceptGate` and `acceptGateResolved`, call `renderStrip()` after updating `gates`. In `openSession` (after `status(...)`), `newSession` and `onNewRound`: `void loadRoomInfo();` (`newSession`/`onNewRound` set `activeSession = null`, so it hides). In `refreshSessions`, after `markActive()`: `renderStrip()` (the fold and `running` may have changed). After a bots roster toggle on the channel page (Task 8), `void loadRoomInfo()`.

- [ ] **Step 5: CSS**

```css
.strip {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  padding: 6px 18px; border-bottom: 1px solid var(--line); background: var(--panel);
}
.strip-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 9px; border: 1px solid var(--line); border-radius: var(--r-chip);
  font: 11px var(--mono); color: var(--dim); background: var(--bg);
}
.strip-chip.open { cursor: pointer; }
.strip-chip .avatar { color: var(--accent); }
.strip-name { color: var(--text); }
.strip-state { text-transform: uppercase; letter-spacing: 0.06em; font-size: 9.5px; }
.strip-chip[data-state="idle"] .strip-state { display: none; }
.strip-chip[data-state="organizing"], .strip-chip[data-state="thinking"], .strip-chip[data-state="writing"], .strip-chip[data-state="tool"], .strip-chip[data-state="called"] { border-color: var(--accent); }
.strip-chip[data-state="waiting for you"] { border-color: var(--danger); color: var(--danger); }
.strip-chip[data-state="answered"] .strip-state { color: var(--green); }
.strip-chip[data-state="failed"] .strip-state, .strip-chip[data-state="timed-out"] .strip-state { color: var(--red); }
.strip-chip[data-state="left"], .strip-chip.broken { opacity: 0.6; }
```

- [ ] **Step 6: Offline check and commit**

Run: `cd face && node --check client/chat.js && npm test`

```bash
git add face/client/index.html face/client/chat.js face/client/chat.css
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): the participants strip - Kairos and every rostered voice, coarse states from the room projection, fine states from the members' own pulses, a pending gate over both, left when unrostered
```

---

### Task 6: A member's gate, inline and attributed — `chat.js`

**Files:**
- Modify: `face/client/chat.js` (`acceptGate`, `questionNode`, `approvalNode`, `openSession`)

**Interfaces:**
- Consumes: `gateSpeaker` (Task 2), `memberSessionIds()` (Task 5), `memberFold`, `botIndex`.
- Produces: a member's question or approval card rendered in the room it belongs to, headed with the bot's name, answered against the member's own session.

- [ ] **Step 1: The predicate**

In `acceptGate`, replace the `if (view.sessionId !== undefined && view.sessionId !== activeSession)` branch's condition with:

```js
  const inRoom = view.sessionId !== undefined && memberSessionIds().has(view.sessionId);
  if (view.sessionId !== undefined && view.sessionId !== activeSession && !inRoom) {
```

(a member's gate is rendered in the room on screen; every other session's gate still becomes a `waiting` chip on its row). In `openSession`'s replay loop: `for (const gate of gates.values()) if (gate.sessionId === id || memberSessionIds().has(gate.sessionId)) renderGate(gate);` — call `loadRoomInfo()` BEFORE that loop and await it, so a member's gate is found on a cold open.

- [ ] **Step 2: The attribution**

Add:

```js
/** Whose card this is: a member's bot for a member's gate, else the session's own voice. */
function gateWho(sessionId) {
  const rows = memberFold.rooms.get(activeSession ?? "") ?? [];
  const extra = Object.entries(roomInfo?.members ?? {}).map(([bot, m]) => ({ sessionId: m?.sessionId, agentPreset: bot }));
  return gateSpeaker(sessionId, [...rows, ...extra], botIndex, speaker);
}
```

Import `gateSpeaker` from `./room.js`. In `questionNode`: `head.append(el("span", "kind", `${gateWho(view.sessionId)} asks`));`. In `approvalNode`: the producer span becomes `` `${gateWho(view.sessionId)} · ${dash(view.toolName)}` `` when the gate is a member's (`view.sessionId !== activeSession`), else the tool name alone as today. Both `respond` calls already send `view.sessionId ?? activeSession` — the gate's own session; leave them.

- [ ] **Step 3: Offline check and commit**

Run: `cd face && node --check client/chat.js && npm test`

```bash
git add face/client/chat.js
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): a member's question or escalation card renders inline in its room, headed with the bot's name, and is answered against the member's own session
```

---

### Task 7: The operator's `@` — `chat.js` `send()`

**Files:**
- Modify: `face/client/chat.js` (`send`)

**Interfaces:**
- Consumes: `isMentionText` (Task 2), `POST /data/rooms/say { sessionId, text }` → `{ ok, addressed: string[] }` (plan 2), `channelOf`, `botIndex`.
- Produces: an `@` message reaches the named bots without waking Kairos; a message that names nobody is an ordinary prompt.

- [ ] **Step 1: Implement**

In `send()`, after the session-creation branch and before the `session.prompt` call:

```js
    /* The operator's `@` (spec §4.4 rule 1): resolved on the server against
     * the channel's roster, appended to the room as the operator's own message
     * without waking Kairos, and each named member turns. A text that resolves
     * to nobody is an ordinary prompt. Only inside a channel: elsewhere `@` is
     * just a character. */
    if (isMentionText(text) && channelOf(activeSession) !== null) {
      const said = await panelData("/data/rooms/say", { sessionId: activeSession, text });
      const addressed = Array.isArray(said.addressed) ? said.addressed : [];
      if (addressed.length > 0) {
        const names = addressed.map((id) => botIndex.find((b) => b.id === id)?.name ?? id).join(", ");
        status(`@ → ${names}`);
        return;
      }
    }
```

Import `isMentionText` from `./room.js`. The existing `catch` hands the text back on failure — an `@` refused with `409` (a corrupt roster) lands there with the server's message.

- [ ] **Step 2: Offline check and commit**

Run: `cd face && node --check client/chat.js && npm test`

```bash
git add face/client/chat.js
git commit -m "feat(face): an @ in the composer reaches the named voices through the room route and never wakes Kairos; a text naming nobody is an ordinary prompt"
```

---

### Task 8: Bots on the channel page — `channels.js`, `chat.js`

**Files:**
- Modify: `face/client/channels.js`
- Modify: `face/client/chat.js` (`openChannel`)
- Modify: `face/client/chat.css`

**Interfaces:**
- Consumes: the overview payload's `bots: string[]` (the roster) and `allBots: [{ id, name, broken?, listed }]` (plan 2), `POST /data/channels/bots { workspaceId, bots[] }`.
- Produces: "bots in this channel" chips; `actions.onToggleBot(id, on)`.

- [ ] **Step 1: The chips**

In `renderChannelPage`, after the agents chips block:

```js
  /* Bots: the operator's own voices, checked in per channel. A chip per bot the
   * preset roster reports (a broken one is shown, disabled, with dsh's reason),
   * plus - Rule 5 - any id the roster file carries that no directory answers to. */
  const bchips = el("div", "ch-chips");
  bchips.append(el("span", "ch-chips-label", "bots in this channel"));
  const rosterBots = Array.isArray(payload.bots) ? payload.bots : [];
  const allBots = (Array.isArray(payload.allBots) ? payload.allBots : []).filter((b) => b.id !== "kairos");
  const known = new Set(allBots.map((b) => b.id));
  for (const bot of allBots) {
    const on = rosterBots.includes(bot.id);
    const chip = el("button", on ? "ch-chip on" : "ch-chip", String(bot.name ?? bot.id));
    chip.type = "button";
    chip.title = bot.broken ? `dsh cannot mount this bot: ${bot.broken}` : String(bot.id);
    if (bot.broken) chip.classList.add("broken");
    chip.addEventListener("click", () => { void actions.onToggleBot(bot.id, !on); });
    bchips.append(chip);
  }
  for (const id of rosterBots) {
    if (known.has(id)) continue;
    const chip = el("button", "ch-chip on missing", id);
    chip.type = "button";
    chip.title = "on this channel's roster, but no bot directory answers to this id - click to remove";
    chip.addEventListener("click", () => { void actions.onToggleBot(id, false); });
    bchips.append(chip);
  }
  if (allBots.length === 0 && rosterBots.length === 0) bchips.append(el("span", "ch-none", "no bots yet - create one on the agent face"));
  head.append(bchips);
```

Update the JSDoc `actions` type with `onToggleBot(id: string, on: boolean): void`.

- [ ] **Step 2: The glue in `openChannel`**

```js
      onToggleBot: async (id, on) => {
        try {
          const current = Array.isArray(payload.bots) ? payload.bots : [];
          const next = on ? [...current, id] : current.filter((b) => b !== id);
          await panelData("/data/channels/bots", { workspaceId: channel.workspaceId, bots: next });
          void loadRoomInfo(); // the strip of a room in this channel follows the roster
          void openChannel(channel);
        } catch (err) {
          failed(err, "channel bots");
        }
      },
```

- [ ] **Step 3: CSS**

```css
.ch-chip.broken { text-decoration: line-through; opacity: 0.6; }
.ch-chip.missing { border-style: dashed; }
```

- [ ] **Step 4: Offline check and commit**

Run: `cd face && node --check client/channels.js && node --check client/chat.js && npm test`

```bash
git add face/client/channels.js face/client/chat.js face/client/chat.css
git commit -m "feat(face): bots are checked into a channel on its page - one chip per voice dsh reports, a broken one shown disabled, an unmatched roster id shown and removable"
```

---

### Task 9: `face/README.md` — the Rooms section and the room drill; then the live drill

**Files:**
- Modify: `face/README.md` (a new `## Rooms` section after `## Bots`; a new `## The room drill` after `## The bots drill`; the Bots section's last paragraph; the Channels section's roster table)

- [ ] **Step 1: The Bots section's last paragraph**

Replace the paragraph beginning `**Not built here (the rooms arc, plans 2–4 of the spec):**` with:

```markdown
**A bot in a room** — dispatched by Kairos, addressed by the operator's `@`, its answers in the
room's transcript in its own voice — is the next section. What is still not built (spec §11, on
purpose): bot-to-bot messaging outside a room, cross-channel memory for a bot, a delete button, a
channel-scoped 1:1 with a bot.
```

- [ ] **Step 2: The Rooms section**

Insert after the Bots section:

```markdown
## Rooms (src/room.ts + src/room-rules.ts + src/room-projection.ts + client/room.js)

A room is an ordinary channel session whose agent is Kairos and which has **members**: one
session per bot the channel rosters, created lazily the first time that bot is named. Nothing
is created to make a session a room. The operator checks bots into a channel on its page
("bots in this channel", `POST /data/channels/bots`, at most six — `ROOM_CAPS.maxMembers`); the
roster stays a menu, not a fence (the channels section's honest limits apply verbatim).

**Kairos organizes the room through one tool, `dispatch`** (`to`, `mode` parallel or serial,
`brief`, `reason`). It is registered globally on the root context (`installRoom` in `main.ts`),
so it is in Kairos's roster; every bot's allow-list mask excludes it without naming it. The
call validates `to` against the channel's bot roster (the refusal names the roster), starts
the round, and returns at once — the result text names who was called, how, **who was not
called**, and tells the model to end its turn. Kairos is woken once per round, by a
`followup` that names who answered and who passed.

**A member session** is created in-process by the engine (`ctx.agents.create`) with the
channel directory as `cwd`, `parentSession` = the room, `agentPreset` = the bot, the bot's
`preset.yml` `model:` when the tree serves it (else the default, with a line in the dispatch
result), and — inside the same creation `setup`, before the session is published — the
**`read-only`** permission preset: a bot in a room does not write files, by sandbox mode, not
by mask (D12). A member that already exists is resumed, never recreated. Members are runtime
roots (created from the root context, not from Kairos's), which is what lets a member ask the
operator a question.

**What a member sees** each turn: the room delta — every operator prompt, Kairos reply and
member answer since it last spoke, one attributed line each (`操作员:`, `Kairos:`, `<bot> (you):`,
`<bot>:`) — the brief, and four standing rules carried in the prompt (reply with your view or
exactly `(pass)`; your text goes to the room verbatim; you remember this room only; address the
operator directly when the judgment is theirs, write `@<bot>` to pull a peer in). Its cursor is
the delta prompt in its own log (`source.form === 'delta'`, `messageIds`), so a member never
re-reads what it saw. Parallel: everyone answers on the same delta and sees no peer this round.
Serial: each later member sees the earlier answers.

**How a room fact is recorded — no `room/*` events.** dsh's persistence refuses to reload a log
carrying an event type outside its catalog (`KNOWN_SESSION_EVENT_TYPES`), so every room fact
rides a known event: membership is the member's header; the dispatch is the tool's own
call/result; an answer is a `user/message` on the room session with `source: { kind: 'room',
form: 'answer', bot, name, sessionId, turn, round }`; the round end is the waking
`user/message` with `form: 'round-end'` and every turn's state. Answers are **appended straight
onto the room log** while no Kairos turn is open (a bubble at once, a seq now, in the next
request's history) and held in a per-room outbox otherwise, flushed at the next `turn/end` and
before the round-end wake. The `room` projection unit folds these events into the coarse state
the strip shows (`called`, `answered`, `passed`, `failed`, `timed-out`, the round, `organizing`);
it rides `session/projection` frames, the `session.list` row and — now that the face mounts
`dsh-session-projection-cache` — the cold row too (R13 closed by the same row).

**Caps, deadlines, endings** (`ROOM_CAPS`, one block): 3 rounds and 10 bot messages per
operator send, 2 peer continuations per round, 180 s base per member turn extended while the
member runs or has a gate pending, 1200 s hard cap → `agent.cancel` (inbox kept) → `timed-out`.
A member whose model fails is `failed` and counts as a pass; the round continues. A round ends
`settled`, `capped` (a cap stopped it) or `superseded` (the operator spoke mid-round: running
turns finish and land, nothing further starts) — three words for three facts. Every operator
send resets the caps.

**The operator's `@`** is deterministic and never passes through Kairos: the composer sends a
text containing `(^|\s)@` to `POST /data/rooms/say`, which resolves mentions against the roster
by id (by display name only when it is one token), appends the message to the room as the
operator's own (`kind: 'user'`, `mention: [...]`) without waking Kairos, and turns each named
member — one mid-turn is queued behind that turn, never refused. A text that names nobody comes
back `addressed: []` and the client sends it as an ordinary prompt. `POST /data/rooms/state`
answers the roster, the members the engine drove this boot, and the caps left.

**The client.** A member's answer renders as a bubble in the bot's own voice — its display name
and an avatar glyph — never as a context row (`client/room.js`, `mapper.js`); the round end is a
room line; the dispatch card reads as the who-was-called line. The **participants strip** above
the transcript shows Kairos (`organizing` while its turn is open) and every rostered voice:
coarse states from the projection, fine states (`thinking` / `writing` / `tool`) from the member
sessions' own pulses, `waiting for you` when a gate is pending on the member, `left` for a member
the roster no longer carries. A member's question or escalation card renders **inline in the
room**, headed with the bot's name, and is answered against the member's own session. Members
**fold under their room** in the sidebar (counted, the bot's name as the label; the fold rule is
the header: `parentSessionId` set, no `origin`, a bot preset, the parent running the host). A
pending gate on a session or its members marks the session row, the channel header and the
landing page (needs-you at the index level).

**The honest limits, in the register of the channels section.** Dispatch grants nothing and the
mask is visibility; a member's write fence is its sandbox mode, its order fence is Gate 2,
tree-wide (both proven from a bot session in `room-smoke.test.ts` and `bots-smoke.test.ts`).
Four voices on one model will tend to converge (R3); parallel first answers are the mitigation,
not a cure. Dispatch is Kairos's judgment (R2): it may under- or over-call; the "not called"
clause and the operator's `@` are the answer. A member's pending gate with no client connected
blocks until the hard cap (R6). A bot does not remember across channels (R5).

| Route | What |
|---|---|
| `POST /data/channels/bots` | `{workspaceId, bots[]}` — the channel's bot roster, at most six ids; 400 a bad id or over the cap, 404 no such channel, 409 a corrupt roster file; a dated `bots` line to `roster.log` |
| `POST /data/rooms/say` | `{sessionId, text}` → `{addressed: [...]}`; 400 a bad id or empty text, 404 not in a channel, 409 a corrupt roster |
| `POST /data/rooms/state` | `{sessionId}` → `{roster, members, caps, round?}`; never resumes a session |
```

- [ ] **Step 3: The drill**

Insert after `## The bots drill`:

```markdown
## The room drill (run after any face or dsh change)

A room whose strip never moved is presumed decorative.

**Step 0, no model, no key.** `FACE_SMOKE=1 npm test` boots `room-smoke.test.ts`: a stub model
route, three bots in a temp channel, one operator prompt → Kairos dispatches all three in
parallel → alpha answers, beta passes, gamma's model fails → the answer is on the room log before
the round-end wake, the wake is one turn, Kairos's synthesis is in it; every member is parented,
preset-joined, `read-only` as its first event, carries the channel's `AGENTS.md` chain and lacks
`dispatch`; the `room` value rides the session row and the cache file; an `@` turns alpha, whose
write into the channel is refused inside the tool content (D12) and never woke Kairos; a home
session writes its journal and is refused on `../SOUL.md`.

**Step 0b, if you changed anything under `client/`.** Hard-reload.

**The drill**, with the face live and two template bots created on the agent face (the bots
drill, steps 1–2), on a fresh channel:

1. Channel page → **bots in this channel** → check both in. PASS, part one: two chips read
   on; `$DSH_HOME/face/roster.log` gained a dated `bots` line; `channels.json` carries `bots`.
2. `new round`, ask a question that invites two views ("X 值得买吗？各说各的"). PASS, part
   two: the strip appears with Kairos and both voices; Kairos's dispatch card reads
   `Dispatched <A>, <B> (parallel) … Not called: none.`; both chips go `called` → `thinking` /
   `writing` → `answered` or `passed`; each answer is a bubble in the bot's own voice with its
   glyph; the round line reads `round 1 · settled · …`; Kairos wakes once and names the
   disagreement.
3. Sidebar. PASS, part three: the room row shows `2 members`, folded; expanding it lists both
   by name; opening one shows its delta as a `context · room` row and its reply.
4. `@<bot> …` in the composer. PASS, part four: the status line reads `@ → <bot>`; the bot's
   chip moves and its bubble lands; Kairos does not speak (no new Kairos turn until you prompt
   it); the `@` shows as your own bubble.
5. Make a bot ask: `@<bot> 先问我一个问题再回答`. PASS, part five: the card appears inline in
   the room headed `<bot> asks`; the chip reads `waiting for you`; the channel header and the
   landing page's session row show the needs-you mark; answer it; the mark clears and the
   bot's answer lands.
6. Make a bot write: `@<bot> 在当前目录写一个 test.txt`. PASS, part six: no file appears; the
   bot's own session (open it from the fold or the strip) shows the bash result with
   `[sandbox: file access denied under read-only mode]`; the bot reports the refusal in the
   room.
7. Un-check one bot on the channel page and come back. PASS, part seven: its chip reads
   `left`; `@` to it resolves nobody (the text goes to Kairos as a prompt); re-check it and
   `@` it again: the same session answers (one member row, not two).
8. Restart the face, open the room. PASS, part eight: the strip's coarse states and the fold
   survive (the projection cache); the members' titles survive (R13 closed).

**PASS criteria are observations.** Record the run below with the date and the commit.
```

- [ ] **Step 4: The channels section's roster table**

In the Channels section's three-layer table change the Roster row to: `| **Roster** (runtime) | \`$DSH_HOME/face/channels.json\` — \`agents[]\` (local CLIs Kairos may call) and \`bots[]\` (the voices a room may dispatch) | the operator, on the channel page |`.

- [ ] **Step 5: Commit the documentation**

```bash
git add face/README.md
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
docs(face): the Rooms section - dispatch, members, the delta, how a room fact is recorded without room events, caps and endings, the @ route, the client - and the room drill
```

- [ ] **Step 6: The live drill (the controller runs it, in the browser, on the operator's face)**

This step is not for a subagent. The controller starts the face (`preview_start` name `face` — reads `.claude/launch.json`, port 3090, the operator's real `$DSH_HOME` with the DeepSeek key), hard-reloads, and walks steps 1–8 above using the browser tools (`requestSubmit()` for the composer; viewport 1280×800). Every PASS is an observation written into the README under the drill as `**Drilled and PASSED <date>** on the operator's own face (`main` @ …): …` with one line per part, and every FAIL becomes a fix task (a plan 3 fix round) before the line is written. Commit the README line afterwards.

---

## Self-review (run by the plan's author before handing off)

**Spec coverage, §5–§6.** §5 "the operator speaks to the room" → Task 7; "a member asks the operator" inline, attributed, answered against the member's session → Task 6; "a sandbox escalation card from a member" → the same path (approval frames carry the member's `sessionId`); "Gate 2 for a bot" is plan 1's and plan 2's proof; "needs-you at the index level" → Task 4. §6 attributed bubbles with a deterministic glyph → Tasks 2–3; the dispatch line and the round-end line → Task 3 (deviation 1 for the dispatch line); the participants strip with the §6 table's states → Tasks 2 and 5 (`thinking/writing/tool` from pulses, `waiting for you` from the gate map, `answered/passed/timed-out/failed` from the projection, `left` from roster-minus-members, `organizing` from the projection or `running`); "no with-whom column" → nothing added; the roster page's Bots section already exists (plan 1); per-channel check-in → Task 8. §4.7 `left` and re-check resumes the same session → Task 5's chip and plan 2's `findMemberSession` (drill part 7). §8's live drill → Task 9. Not in this plan: the reference documents and the charter (plan 4).

**Placeholder scan.** Every task carries its code; Task 9 Step 6 names the controller as the runner and says what gets written.

**Type consistency.** `stripChips` input `{ roster, projection, members, gates, fine, running, kairosName }` is what `renderStrip` builds; `foldMembers` returns `{ rooms, members }` and `memberFold` holds it; `gateSpeaker(sessionId, memberRows, bots, fallback)` matches `gateWho`; `bucketFor`'s fourth argument is a boolean; the mapper's `turn` views carry `phase`, `turn`, `sessionId`; the `room-line` view carries `line`, `round`, `outcome`, `turns`, `text` and `roundEndLine` reads exactly those.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-08-rooms-3-client-and-drills.md`. Execute with **superpowers:subagent-driven-development** after plan 2 is merged into `feat/rooms`: Tasks 1–8 by fresh subagents with review between tasks; Task 9's documentation by a subagent and its live drill by the controller in the browser. Plan 4 (`2026-09-08-rooms-4-charter-and-docs.md`) follows the drill's PASS line.
