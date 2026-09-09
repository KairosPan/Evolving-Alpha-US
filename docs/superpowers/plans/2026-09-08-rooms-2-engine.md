# The Room Engine (server) — Implementation Plan (plan 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After this plan Kairos can call `dispatch` from a channel session, the face creates or resumes one `read-only` member session per named bot, runs their turns in parallel or serially with an attributed room delta, feeds every answer back into Kairos's session as an attributed user-role message, wakes Kairos once per round with who spoke and who passed, and a `room` projection unit tells any client the coarse state of the room — all provable in-process with a stub model and no key.

**Architecture:** One face module, `face/src/room.ts`, installed on the booted root context by `main.ts` (the same way Gate 2 and the `agent_<bin>` tools are installed — on `ctx`, not as a cordis row). It registers the global `dispatch` tool, a root-level `session/event` listener, the `room` projection unit, and two loopback routes. Member sessions are created in-process through `ctx.agents.create` with `meta: { cwd: <channel dir>, parentSession: <room id>, agentPreset: <bot> }` and a face-owned `setup` that mirrors the gateway's (`installModelSelection` + `agentPresets.mount`), and pinned `read-only` with `permissionPresets.set` inside that same `setup`, before publication — `pinInitialPermission` fills only missing knobs, so the pin is the session's first permission fact and there is no window to close. Pure rules (mentions, validation, deltas, final text, caps, the dispatch line) live in `face/src/room-rules.ts`; the projection fold lives in `face/src/room-projection.ts`. **No custom session-event types**: every room fact rides a known dsh event (see Deviation 1).

**Tech Stack:** Node 22 · TypeScript (`tsc --noEmit`, `tsx` runs sources) · `node:test` via `tsx --test tests/*.test.ts` · dsh `0.1.1-rc.2` exact · cordis `4.0.2` · zod `4.5.4` (the version dsh's own projection registry installs) · js-yaml `4.3.2`.

**Spec:** `docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md` — read §2.4, §3, §4 (all of it), §5, §6 (for what the client will need), §7, §8, §12, §13, §14, §16 before Task 1. This plan is §14 item 2. The client (bubbles, strip, inline gates, `@` composer path, roster check-in UI, the live drill, `face/README.md`) is plan 3; the charter and the reference documents are plan 4.

**Deviations from the spec, decided by substrate facts measured while planning (2026-09-08). Each is recorded in the spec's §16 by Task 11.**

1. **No `room/*` session events.** The spec's `room/member`, `room/dispatch`, `room/turn` and `room/round-end` cannot be appended: `Session.append` accepts any type, but every persistence *read* (`readFrom`, `inspect`, `prepare`/resume) runs the log through the generated closed set `KNOWN_SESSION_EVENT_TYPES` and throws `SessionFormatUnsupportedError` for an unknown type unless the event carries `ignorable: true` — and `append` has no way to set it (`dsh-session-persistence/lib/index.js:1119-1120`; `dsh-session/lib/index.js:1444-1463`). One custom event would make the room session unresumable and unlistable after the next boot. So every room fact rides a **known** event: membership = the member's own header (`parentSession` + `agentPreset`) plus the room-sourced messages that name it; the dispatch = the `dispatch` tool's own `tool/call` + `tool/result` (the result text names who was *not* called); a member's answer = a `user/message` in Kairos's session with `source: { kind: 'room', form: 'answer', bot, name, sessionId, turn, round }`; the round end = the waking `user/message` with `source: { kind: 'room', form: 'round-end', … }`; the member's cursor = the delta message in the member's own log, `source: { kind: 'room', form: 'delta', room, bot, messageIds }`. The `room` projection unit folds exactly these.
2. **Answers are appended to the room log directly, and only while no Kairos turn is open — never `inject`ed.** `inject` splices the inbox only: the `user/message` the client renders lands when Kairos's next step *claims* it, so §4.3's "the operator sees bubbles appear while Kairos sleeps" is false on the substrate, the answer's seq is unknown until the claim, and an inject on a *running* driver forces an extra model step or opens a stray turn whose only input is the injected text (`dsh-agent-loop/lib/index.js:554, 564-571, 600-604`). `Session.append('user/message', msg, { surfaceOp: 'append' })` on the room session is the honest carrier: a known event, visible on the mux at once, seq assigned now, persisted, and in `deriveMessages()` for Kairos's next request. It is safe only while the room log is **quiet** (its last `turn/start` is closed by a `turn/end`) — a user message dropped between an assistant tool-call message and its `tool/result` would break the running request — so the engine keeps a per-room outbox and flushes it on every `turn/end` and before the round-end `followup`, in one synchronous block. Kairos is woken only by `followup` (the round-end); every answer is already in the log above it.
3. **Fine states are the client's.** The projection registry has no out-of-fold write (`dsh-session-projection/lib/index.js`: `drive`/cells private, the change feed fires only inside `drive`), so the spec's "thinking / writing / tool" states cannot be folded into the unit by the plugin. The mux already forwards every live session's `assistant/chunk` block starts to every client, so plan 3 derives fine states from the member sessions' own pulses. The unit carries coarse state only.
4. **`session.selectModel` is not used for `preset.yml`'s `model:`.** It saves the selection as the host-wide default (`dsh-host-apiproxy/lib/index.js` `selectModel` → `saveDefaultModelSelection`). The engine installs a per-member `ModelSelectionRef` through `installModelSelection` (exported by `@deepseek-ai/dsh-agent`) inside the creation `setup`, exactly as the gateway does for its own sessions, and validates the route with `ctx.llm.resolveCallConfig` first — falling back to `ctx.agentDefaultModel.currentSelection()` with a visible line in the dispatch result.
5. **The hard-cap cancel keeps the inbox.** `agent.cancel(cause)` clears the inbox by default (logging canceled splices); the engine passes `{ keepInbox: true }` so a member's queued work survives the cancellation of one runaway turn.
6. **A superseded round has its own outcome.** `settled` and `capped` are the spec's; a round cut short by a new operator message ends with outcome `superseded` (Rule 5: a third fact deserves a third word).
7. **The membership fold is a header rule.** The spec folds a child under a room only when the parent's log names it; with no `room/member` event the rule becomes: a session is a member of `P` when its header has `parentSession = P`, no `origin`, and an `agentPreset` naming a bot, and `P` itself runs the host preset. Forks carry the source's preset (`kairos` for a room) and subagent children carry `origin: 'subagent'`, so both stay out.
8. **The gate that pends is read from the log.** `ask_user_question` leaves no session event (questions live only in the gateway's memory and on the mux), so "a pending gate" for the deadline extension is an open `tool/call` named `ask_user_question` with no `tool/result` yet, or an `approval/asked` with no `approval/decided`.

## Global Constraints

- Every `@deepseek-ai/dsh-*` dependency is pinned **exactly** `0.1.1-rc.2`; `face/tests/version.test.ts` sweeps both dependency blocks. Run `npm install` in `face/` after editing `package.json` (the lockfile is tracked).
- **One `bootFace` per test process**: every FACE_SMOKE test is its own `face/tests/<name>.test.ts`, gated `skip: gated && "set FACE_SMOKE=1"`, booting into a `mkdtempSync` home via `setupFaceProfile(home)`; never `~/.dsh`.
- **No custom session-event types, ever** (Deviation 1). If you find yourself calling `session.append`, stop: the engine speaks to agents only through `followup` / `inject` / `cancel`.
- **Never call `inject`/`followup` synchronously inside a `session/event` listener for the same session**: `Session.append` rejects reentrancy. The engine's listener only resolves promises and records state; every action runs in a promise continuation.
- Member sessions are created from the **root** context (`booted.ctx`), never through Kairos's `agent.ctx`: a runtime-owned child cannot ask the operator anything (`userQuestions.ask` refuses `DELEGATED_CALLER`) and the gateway would refuse its gates as subagent-owned.
- `meta.cwd` must be an absolute path; session ids are `session-<uuid>` (the face's `SESSION_ID_RE`).
- Constants live in one block, `ROOM_CAPS` in `room-rules.ts`: `maxRounds 3`, `maxContinuations 2`, `maxBotMessages 10`, `maxMembers 6`, `turnTimeoutMs 180_000`, `turnHardCapMs 1_200_000` (spec §4.6 verbatim).
- Rule 5: the dispatch result names who was **not** called; `capped`, `superseded`, `passed`, `failed`, `timed-out` are all distinct words on the wire; a member whose preset is gone is reported `failed` with its reason, never skipped.
- Rule 2 / D12: a member's write fence is the `read-only` permission preset logged into its session before its first prompt, verified with `permissionPresets.current(events)`; the mask is visibility.
- Every log line is `${BIN}: …` with `const BIN = "kairos-face"` declared per module. Docs cite files and symbols, never line numbers.
- Commit after every task (`git commit -F <file>` when the message carries backticks or parentheses). Never commit the operator's untracked files (`strategies/*`, `bots/buffet/`, `docs/research/*`, `tests/strategies/`, `face/probe4.ts`, `.claude/launch.json`).
- Nothing in this plan edits `Kairos-Design.md`, `CLAUDE.md`, `AGENTS.md`, `DEVELOPMENT.md` or `face/README.md` (plans 3–4). Two exceptions: `dsh/profile/persona.md` (Task 9, the room default Kairos carries) and the spec's §16 (Task 11).

## File Structure

| File | Responsibility |
|---|---|
| `face/src/room-rules.ts` (new) | pure rules: `ROOM_CAPS`, `resolveMentions`, `isPass`, `finalTextOf`, `validateDispatch`, `dispatchResultText`, `roomLinesOf`, `formatDelta`, `memberPrompt`, `roundEndText`, `parseModelRoute`, the `RoomMessageSource` types and their `MessageSourceMap` augmentation |
| `face/src/room-projection.ts` (new) | the `room` projection unit: `RoomState`, `initRoomState`, `applyRoomEvent` (pure, same-reference on unrelated events), `roomStateSchema` (zod), `registerRoomProjection` |
| `face/src/room.ts` (new) | the engine: `installRoom(deps)` → `RoomEngine` (`dispatch`, `say`, `describe`, `dispose`); member create/resume; turn driving with deadlines; the outbox; rounds, continuations, caps; `registerRoomRoutes` (`POST /data/rooms/say`, `POST /data/rooms/state`) |
| `face/src/roster.ts` | `bots: string[]` beside `agents` in `channels.json`; `botsFor`, `setBots`, `logBotsWrite`; `readRosters` keeps `bots` |
| `face/src/channels.ts` | overview carries `bots` (the roster) and `allBots` (what the preset roster reports); `POST /data/channels/bots` with the `maxMembers` cap |
| `face/src/bots.ts` | `preset.yml` gains optional `model:`; `BotRow.model`; `createBot` accepts `model` |
| `face/src/panels.ts` | `PanelDeps.channelFor` also returns `dir` |
| `face/src/overlay.ts` | + the `session-projection-cache` row (closes R13) |
| `face/src/setup.ts` | the patch header names the new face-owned row id |
| `face/src/main.ts` | wires `installRoom` and `registerRoomRoutes` |
| `face/package.json` | + `@deepseek-ai/dsh-agent`, `dsh-llm`, `dsh-session`, `dsh-session-projection`, `dsh-session-projection-cache` at the pin; + `zod` |
| `bots/_template/preset.yml` | documents `model:` |
| `dsh/profile/persona.md` | the room default: dispatch independently first, then name the disagreements |
| `face/tests/room-rules.test.ts`, `room-projection.test.ts`, `room-engine.test.ts`, `room-fake.ts` (new); `roster.test.ts`, `channels.test.ts`, `bots.test.ts`, `overlay.test.ts`, `setup.test.ts` (modified) | offline |
| `face/tests/stub-llm.ts`, `room-smoke.test.ts` (new) | FACE_SMOKE, one boot: the whole round in-process on a stub model route (S5, S6, the read-only pin, the home-scope sandbox, the cache row) |

**Shared test doubles.** Task 5 writes `face/tests/room-fake.ts` (a fake dsh tree with scriptable agents and a manual clock); Task 10 writes `face/tests/stub-llm.ts` (a scripted `LlmAdapter`). Every later test imports them; do not re-implement them inline.

---

### Task 1: Dependencies, the projection-cache row (R13), and `preset.yml`'s `model:`

**Files:**
- Modify: `face/package.json`
- Modify: `face/src/overlay.ts`
- Modify: `face/src/setup.ts` (the `PATCH_HEADER` comment)
- Modify: `face/src/bots.ts`
- Modify: `bots/_template/preset.yml`
- Test: `face/tests/overlay.test.ts`, `face/tests/bots.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `BotRow.model?: string` (the raw `provider/model` string from `preset.yml`); `createBot(root, body)` honours `body.model`; `renderPresetMeta(name, description, model?)`; the overlay row `session-projection-cache` with `{ writeEveryEvents: 200, writeIntervalMs: 5000 }`.

- [ ] **Step 1: Add the dependencies**

In `face/package.json` `dependencies`, add (keep the block alphabetical):

```json
    "@deepseek-ai/dsh-agent": "0.1.1-rc.2",
    "@deepseek-ai/dsh-llm": "0.1.1-rc.2",
    "@deepseek-ai/dsh-session": "0.1.1-rc.2",
    "@deepseek-ai/dsh-session-projection": "0.1.1-rc.2",
    "@deepseek-ai/dsh-session-projection-cache": "0.1.1-rc.2",
```

and after `"js-yaml": "4.3.2",`:

```json
    "zod": "4.5.4"
```

Run `cd face && npm install`. Expected: the lockfile changes, no new download (every package is already in `node_modules`), `npm ls zod` shows `zod@4.5.4` at the top level.

- [ ] **Step 2: Write the failing overlay test**

In `face/tests/overlay.test.ts` change the first test's expected id list and add the cache assertion:

```ts
test("overlay inserts exactly the twelve rows with loopback config", () => {
  const patches = faceOverlay(3090, HOME, BOTS);
  assert.equal(patches.length, 1);
  const rows = patches[0].insert!;
  const byId = new Map(rows.map(r => [r.id, r]));
  assert.deepEqual(
    [...byId.keys()].sort(),
    ["agent-presets", "api-gateway", "connection", "cordis-host-runner", "directory-picker",
      "session-projection-cache", "storage", "storage-domain", "storage-json", "tool-ask-user", "webserver", "workspace"],
  );
  /* … the existing agent-presets / webserver / api-gateway / connection / directory-picker / cordis-host-runner assertions stay verbatim … */
});

/* R13: a cold session listed with no `projections` column because dsh-base
 * composes `session-projection` and not the persisted cache. `session.list`
 * reads `sessionProjectionCache.cachedSnapshot(meta)` for every session not
 * attached in this boot, so without this row every restart resets the whole
 * sidebar to `untitled`. Both config keys are REQUIRED by the plugin (no
 * defaults); the values are dsh-web-app's own. */
test("the persisted projection cache is mounted so cold sessions keep their titles", () => {
  const byId = new Map(faceOverlay(3090, HOME, BOTS)[0].insert!.map(r => [r.id, r]));
  assert.equal(byId.get("session-projection-cache")!.name, "@deepseek-ai/dsh-session-projection-cache");
  assert.deepEqual(byId.get("session-projection-cache")!.config, { writeEveryEvents: 200, writeIntervalMs: 5000 });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/overlay.test.ts`
Expected: FAIL — the id list has eleven entries and no `session-projection-cache`.

- [ ] **Step 4: Add the row**

In `face/src/overlay.ts` add the import beside the other config types:

```ts
import type { Config as ProjectionCacheConfig } from "@deepseek-ai/dsh-session-projection-cache";
```

and, after the `tool-ask-user` row and before the `agent-presets` row, insert:

```ts
      /* R13. `session.list` fills a session's `projections` column from
       * `sessionProjections.snapshot` when the session is attached in this
       * boot and from `sessionProjectionCache.cachedSnapshot` when it is cold
       * (dsh-host-apiproxy `listProjectionsFor`). dsh-base composes the
       * registry and NOT the cache, so every cold session listed with no
       * column at all and the sidebar read `untitled` after every restart
       * (measured 2026-09-08: 24 sessions, none with a block). The cache
       * writes a whole-record checkpoint at every `turn/end` and at session
       * disposal, throttled between by these two REQUIRED keys - the values
       * are dsh-web-app's own. It fills forward only: a session cold before
       * this row existed stays `untitled` until it is resumed and completes a
       * turn. The `room` projection unit (src/room-projection.ts) rides the
       * same cache, which is what lets a cold room keep its member states. */
      { id: PROJECTION_CACHE_ROW_ID, name: "@deepseek-ai/dsh-session-projection-cache",
        config: { writeEveryEvents: 200, writeIntervalMs: 5000 } satisfies ProjectionCacheConfig },
```

with the constant exported beside `AGENT_PRESETS_ROW_ID`:

```ts
export const PROJECTION_CACHE_ROW_ID = "session-projection-cache";
```

In `face/src/setup.ts` `PATCH_HEADER`, change `tool-ask-user, agent-presets, the system-prompt persona,` to `tool-ask-user, agent-presets, session-projection-cache, the system-prompt persona,`.

- [ ] **Step 5: Run the overlay, setup and boot tests**

Run: `cd face && npx tsx --test tests/overlay.test.ts tests/setup.test.ts tests/boot.test.ts`
Expected: PASS (boot.test.ts's "every face row lands in the composed tree exactly once" now counts twelve; if it hard-codes eleven, update the number and nothing else).

- [ ] **Step 6: Write the failing bots test for `model:`**

Append to `face/tests/bots.test.ts`:

```ts
test("preset.yml may carry a face-only model route; createBot writes it and listBots reads it", async () => {
  const root = await makeBotsRoot();
  const made = await createBot(root, { id: "router", name: "Router", model: "stub/echo" });
  assert.equal(made.model, "stub/echo");
  const meta = load(await readFile(join(root, "router", "preset.yml"), "utf8")) as Record<string, unknown>;
  assert.equal(meta.model, "stub/echo");
  const listed = (await listBots(root, async () => [{ id: "router" }])).find((b) => b.id === "router");
  assert.equal(listed?.model, "stub/echo");
  const plain = await createBot(root, { id: "plain", name: "Plain" });
  assert.equal(plain.model, undefined, "absent stays absent - the default route serves it");
});

test("createBot refuses a model that is not one provider/model pair", async () => {
  const root = await makeBotsRoot();
  await assert.rejects(createBot(root, { id: "bad", name: "Bad", model: "deepseek-v4-flash" }), (err: HttpError) => err.status === 400 && /provider\/model/.test(err.message));
  await assert.rejects(createBot(root, { id: "bad2", name: "Bad", model: "a/b/c" }), (err: HttpError) => err.status === 400);
});
```

(`makeBotsRoot` is `./bots-fixture.ts`'s; `load` is js-yaml's; import `HttpError` from `../src/http.ts` if the file does not already.)

- [ ] **Step 7: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/bots.test.ts`
Expected: FAIL — `made.model` is undefined / TypeScript complains about `model` on `BotRow`.

- [ ] **Step 8: Implement `model:`**

In `face/src/bots.ts`:

```ts
/** `preset.yml`'s face-only `model:` - `<provider>/<model>`, the route a bot's
 *  sessions select when the tree serves it (spec §2.5). dsh's reader keeps only
 *  name/description/order and drops it, so it is harmless to dsh. Exactly two
 *  non-empty segments: a bare model id is refused rather than guessed at. */
export const MODEL_ROUTE_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_.:-]*$/;

export function renderPresetMeta(name: string, description: string, model?: string): string {
  return dump({ name, description, ...(model === undefined ? {} : { model }) }, { lineWidth: -1 });
}
```

Add `model?: string` to `BotRow` (doc: `preset.yml`'s `model:` verbatim, absent when the default route serves the bot). In `readMeta`, also read `model` when it is a string. In `rowFor`, spread `...(meta.model === undefined ? {} : { model: meta.model })`. In `createBot`, before the template check:

```ts
  const model = body.model === undefined ? undefined : body.model;
  if (model !== undefined && (typeof model !== "string" || !MODEL_ROUTE_RE.test(model))) {
    throw new HttpError(400, "model must be one provider/model route, e.g. deepseek-official/deepseek-v4-flash");
  }
```

and write `renderPresetMeta(name ?? id, description, model)`.

In `bots/_template/preset.yml` append:

```yaml
# model: deepseek-official/deepseek-v4-flash   # face-only, optional: the provider/model route this voice
#                                              # runs on when the tree serves it; the default route otherwise
```

- [ ] **Step 9: Run the bots tests and typecheck**

Run: `cd face && npx tsx --test tests/bots.test.ts && npm run typecheck`
Expected: PASS, typecheck clean.

- [ ] **Step 10: Commit**

```bash
git add face/package.json face/package-lock.json face/src/overlay.ts face/src/setup.ts face/src/bots.ts bots/_template/preset.yml face/tests/overlay.test.ts face/tests/bots.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): mount the projection cache so cold sessions keep their titles (R13); preset.yml carries a model route; the room engine's dependencies at the pin
```

---

### Task 2: The roster's `bots[]` and the channel check-in route

**Files:**
- Modify: `face/src/roster.ts`
- Modify: `face/src/channels.ts`
- Modify: `face/src/panels.ts` (`channelFor` returns `dir`)
- Modify: `face/src/main.ts` (pass `listBots` to the channel routes)
- Test: `face/tests/roster.test.ts`, `face/tests/channels.test.ts`

**Interfaces:**
- Consumes: `listBots` from `bots.ts` (Task 1's `BotRow`).
- Produces: `RosterFile.channels[id] = { agents: string[]; bots: string[] }`; `readRosters` returns both arrays (a file without `bots` reads as `[]`); `setRoster` keeps `bots`; `botsFor(home, ws): Promise<string[] | null>`; `setBots(home, ws, ids)` (refuses over a corrupt file, keeps `agents`); `logBotsWrite(home, ws, ids)`; `ChannelRouteDeps.listBots(): Promise<{ id: string; name: string; broken?: string; listed: boolean }[]>`; overview payload `bots: string[]`, `allBots: BotSummary[]`; `POST /data/channels/bots { workspaceId, bots[] }` → `{ ok, bots }`; `PanelDeps.channelFor` returns `{ workspaceId, name, dir }`.

- [ ] **Step 1: Write the failing roster tests**

Append to `face/tests/roster.test.ts`:

```ts
test("bots ride beside agents: seeded empty, set independently, and a legacy file reads bots as []", async () => {
  const h = await home();
  await seedRoster(h, "ws-1", ["claude"]);
  assert.deepEqual(await botsFor(h, "ws-1"), []);
  await setBots(h, "ws-1", ["buffett", "speculator", "buffett"]);
  assert.deepEqual(await botsFor(h, "ws-1"), ["buffett", "speculator"], "deduplicated, order kept");
  assert.deepEqual(await rosterFor(h, "ws-1"), ["claude"], "setBots leaves agents alone");
  await setRoster(h, "ws-1", ["codex"]);
  assert.deepEqual(await botsFor(h, "ws-1"), ["buffett", "speculator"], "setRoster leaves bots alone");
  assert.equal(await botsFor(h, "ws-nope"), null);
  // a file written before bots existed
  await mkdir(join(h, "face"), { recursive: true });
  await writeFile(join(h, "face", "channels.json"), JSON.stringify({ version: 1, channels: { "ws-old": { agents: ["claude"] } } }));
  assert.deepEqual((await readRosters(h)).rosters["ws-old"], { agents: ["claude"], bots: [] });
});

test("setBots refuses over a corrupt file and refuses non-id junk", async () => {
  const h = await home();
  await corrupt(h);
  await assert.rejects(setBots(h, "ws-1", ["buffett"]), /corrupt/i);
  const clean = await home();
  await assert.rejects(setBots(clean, "ws-1", ["Not An Id"]), (err: Error) => /bot id/.test(err.message));
});

test("logBotsWrite appends its own dated line kind", async () => {
  const h = await home();
  await logBotsWrite(h, "ws-1", ["buffett"]);
  const log = await readFile(join(h, "face", "roster.log"), "utf8");
  assert.match(log, /^\d{4}-\d{2}-\d{2}T[^ ]+ bots ws-1 = \[buffett\]\n$/);
});
```

Import `botsFor, setBots, logBotsWrite` from `../src/roster.ts` at the top.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/roster.test.ts`
Expected: FAIL — `botsFor` is not exported.

- [ ] **Step 3: Implement the roster half**

In `face/src/roster.ts`:

- `RosterFile.channels: Record<string, { agents: string[]; bots: string[] }>`.
- In `readRosters`, after the `agents` loop, read `bots` the same way (`typeof id === "string" && isBotId(id)`, deduplicated; a missing or non-array `bots` reads as `[]`) and set `rosters[id] = { agents: bins, bots: ids }`. Import `isBotId` from `./bots.ts`.
- `seedRoster`: `{ agents: [...bins], bots: [] }`.
- `setRoster`: `{ ...rosters, [workspaceId]: { agents: [...new Set(bins)], bots: rosters[workspaceId]?.bots ?? [] } }`.
- New:

```ts
/** The operator's explicit write of a channel's BOT roster: exactly `ids`,
 * deduplicated in order. Refuses a corrupt file for the reason `setRoster`
 * gives, and refuses any id outside the bot grammar before it can reach the
 * file - the ids become directory names under `bots/` when the engine mounts
 * them. Agents are left as they were. The cap on members (ROOM_CAPS) is the
 * route's to apply, not this store's: the store records what it is told. */
export async function setBots(home: string, workspaceId: string, ids: readonly string[]): Promise<void> {
  const bad = ids.filter((id) => !isBotId(id));
  if (bad.length > 0) throw new HttpError(400, `not a bot id: ${bad.join(", ")}`);
  await update(home, ({ rosters, corrupt }) => {
    if (corrupt) {
      throw new HttpError(409, `${pathOf(home)} is corrupt and cannot be safely merged into - repair or remove it by hand, then set the roster again`);
    }
    return { ...rosters, [workspaceId]: { agents: rosters[workspaceId]?.agents ?? [], bots: [...new Set(ids)] } };
  });
}

/** This channel's bot roster, or `null` when the channel has no entry (or the file is corrupt). */
export async function botsFor(home: string, workspaceId: string): Promise<string[] | null> {
  const { rosters } = await readRosters(home);
  return Object.hasOwn(rosters, workspaceId) ? [...rosters[workspaceId].bots] : null;
}

/** The bots twin of {@link logRosterWrite}: its own line kind, same file, same never-throws contract. */
export async function logBotsWrite(home: string, workspaceId: string, bots: readonly string[]): Promise<void> {
  const line = `${new Date().toISOString()} bots ${workspaceId} = [${bots.join(", ")}]`;
  console.log(`${BIN}: ${line}`);
  try {
    await mkdir(join(home, ROSTER_LOG_FILE[0]), { recursive: true });
    await appendFile(join(home, ...ROSTER_LOG_FILE), `${line}\n`, { encoding: "utf8", mode: 0o600 });
  } catch (err) {
    console.error(`${BIN}: failed to append to ${join(home, ...ROSTER_LOG_FILE)} - the bots write itself still stands:`, err);
  }
}
```

Note `roster.ts` now imports `bots.ts` and `bots.ts` imports nothing from `roster.ts` — no cycle.

- [ ] **Step 4: Run the roster tests**

Run: `cd face && npx tsx --test tests/roster.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing channels tests**

In `face/tests/channels.test.ts` find the test that pins "exactly four paths" on `registerChannelRoutes` and change it to five, adding `/data/channels/bots`. Every existing `registerChannelRoutes(recorder, deps)` call gets `listBots: async () => []` in its deps. Then append:

```ts
test("the overview carries the bot roster and every preset the roster reports; POST /data/channels/bots writes it under the members cap", async () => {
  const root = await makeRoot();
  const h = await mkdtemp(join(tmpdir(), "face-home-"));
  const registry = fakeRegistry();   // the same fake the overview test above uses
  const routes = recorder();
  registerChannelRoutes(routes, {
    registry, root, home: h, listSessions: async () => [], connectedBins: async () => [],
    listBots: async () => [
      { id: "buffett", name: "巴菲特型", listed: true },
      { id: "cracked", name: "cracked", broken: "not a list", listed: true },
    ],
  });
  const { channels } = JSON.parse(await routes.call("/data/channels.json", { method: "GET" })).body as { channels: { workspaceId: string }[] };
  const ws = channels[0].workspaceId;

  const ok = JSON.parse(await routes.call("/data/channels/bots", { method: "POST", json: { workspaceId: ws, bots: ["buffett", "ghost"] } }));
  assert.equal(ok.status, 200);
  assert.deepEqual(ok.body.bots, ["buffett", "ghost"], "an id the mount does not report is kept and shown (Rule 5), not dropped");

  const over = JSON.parse(await routes.call("/data/channels/overview", { method: "POST", json: { workspaceId: ws } }));
  assert.deepEqual(over.body.bots, ["buffett", "ghost"]);
  assert.deepEqual(over.body.allBots.map((b: { id: string }) => b.id), ["buffett", "cracked"]);
  assert.equal(over.body.allBots[1].broken, "not a list");

  const tooMany = JSON.parse(await routes.call("/data/channels/bots", { method: "POST", json: { workspaceId: ws, bots: ["a1", "a2", "a3", "a4", "a5", "a6", "a7"] } }));
  assert.equal(tooMany.status, 400);
  assert.match(tooMany.body.error, /6/);
  const junk = JSON.parse(await routes.call("/data/channels/bots", { method: "POST", json: { workspaceId: ws, bots: ["Not Valid"] } }));
  assert.equal(junk.status, 400);
  const nowhere = JSON.parse(await routes.call("/data/channels/bots", { method: "POST", json: { workspaceId: "ws-none", bots: [] } }));
  assert.equal(nowhere.status, 404);
  await rm(h, { recursive: true, force: true });
});
```

Adapt `recorder()` / `routes.call` / `fakeRegistry()` to whatever helper names the existing channels route tests already use — read them first; do not invent a second recorder.

- [ ] **Step 6: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/channels.test.ts`
Expected: FAIL — `listBots` is not a known dep / four paths.

- [ ] **Step 7: Implement the channels half**

In `face/src/channels.ts`:

- Import `ROOM_CAPS` from `./room-rules.ts` — **not yet written**: until Task 3 lands, declare a local `const MAX_MEMBERS = 6;` and replace it with `ROOM_CAPS.maxMembers` in Task 3 Step 9. Import `botsFor, setBots, logBotsWrite` from `./roster.ts` and `isBotId` from `./bots.ts`.
- `ChannelRouteDeps` gains:

```ts
  /** Every bot directory with dsh's view merged in (`listBots` in bots.ts, narrowed). */
  listBots(): Promise<{ id: string; name: string; broken?: string; listed: boolean }[]>;
```

- The overview handler answers `bots: await botsFor(deps.home, channel.workspaceId) ?? []` and `allBots: await deps.listBots()` beside `agents`.
- The new route, registered after `/data/channels/agents`:

```ts
  webServer.register({
    kind: "exact",
    path: "/data/channels/bots",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!guardPost(req, res)) return;
      try {
        const { workspaceId, bots } = await bodyOf(req);
        const { channels } = await reconcile();
        if (!channels.some((c) => c.workspaceId === workspaceId)) return send(res, 404, { ok: false, error: "no such channel" });
        if (!Array.isArray(bots) || bots.some((b) => !isBotId(b))) {
          return send(res, 400, { ok: false, error: "bots must be an array of bot ids" });
        }
        const ids = [...new Set(bots as string[])];
        /* The cap is the room's, not the store's: six members is what one
         * operator message may cost (spec §4.6, P5). Refused here, before the
         * write, so the file never holds a roster the engine would refuse. */
        if (ids.length > MAX_MEMBERS) {
          return send(res, 400, { ok: false, error: `a channel rosters at most ${MAX_MEMBERS} bots` });
        }
        const id = workspaceId as string;
        await setBots(deps.home, id, ids);
        await logBotsWrite(deps.home, id, ids);
        return send(res, 200, { ok: true, bots: await botsFor(deps.home, id) ?? [] });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "roster write failed" });
      }
    },
  });
```

In `face/src/panels.ts`, `PanelDeps.channelFor` returns `Promise<{ workspaceId: string; name: string; dir: string } | null>` and `panelDeps` fills `dir: ws.path`. `agents.ts` reads only `workspaceId`/`name`; leave it.

In `face/src/main.ts`, pass `listBots: () => listBots(BOTS_ROOT, () => agentPresets.list())` to `registerChannelRoutes` — move the `agentPresets` lookup above the channel routes so it is in scope, and import `listBots` from `./bots.ts`.

- [ ] **Step 8: Run the channels, panels and agents tests; typecheck**

Run: `cd face && npx tsx --test tests/channels.test.ts tests/panels.test.ts tests/agents.test.ts && npm run typecheck`
Expected: PASS, clean.

- [ ] **Step 9: Commit**

```bash
git add face/src/roster.ts face/src/channels.ts face/src/panels.ts face/src/main.ts face/tests/roster.test.ts face/tests/channels.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): a channel rosters bots beside agents - bots[] in channels.json, POST /data/channels/bots capped at six, the overview names the roster and every preset dsh reports
```

---

### Task 3: The pure rules — `face/src/room-rules.ts`

**Files:**
- Create: `face/src/room-rules.ts`
- Modify: `face/src/channels.ts` (replace the local `MAX_MEMBERS` with `ROOM_CAPS.maxMembers`)
- Modify: `face/src/sessions.ts` (export `SESSION_ID_RE`)
- Test: `face/tests/room-rules.test.ts`

**Interfaces:**
- Consumes: nothing (pure; the only import is the `MessageSourceMap` augmentation target `@deepseek-ai/dsh-llm`).
- Produces (every later task imports these by name): `ROOM_CAPS: RoomCaps`, `RosterBot { id; name; model?; broken? }`, `EventLike { type; seq; data? }`, `MessageLike { id; role: "user"; content; source }`, `resolveMentions(text, roster): string[]`, `PASS_RE`, `isPass(text)`, `finalTextOf(events, turn): string`, `DispatchArgs`, `validateDispatch(args, roster)`, `dispatchResultText(args, roster, round, remainingRounds, notes)`, `RoomLine`, `roomLinesOf(events, pending, roster): RoomLine[]`, `formatDelta(lines, self): string`, `memberPrompt(opts): string`, `MEMBER_RULES`, `RoomTurnRecord`, `RoundOutcome`, `roundEndText(round, outcome, turns, remainingRounds)`, `parseModelRoute(route)`, the source types `RoomAnswerSource`, `RoomRoundEndSource`, `RoomDeltaSource`, `OperatorMentionSource`.

- [ ] **Step 1: Write the failing tests**

```ts
// face/tests/room-rules.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import {
  ROOM_CAPS, dispatchResultText, finalTextOf, formatDelta, isPass, memberPrompt, parseModelRoute,
  resolveMentions, roomLinesOf, roundEndText, validateDispatch, type EventLike, type MessageLike, type RosterBot,
} from "../src/room-rules.ts";

const roster: RosterBot[] = [
  { id: "buffett", name: "巴菲特型" },
  { id: "speculator", name: "投机型" },
  { id: "macro-view", name: "Macro View" }, // a multi-word display name: reached by id only
];

test("ROOM_CAPS is the spec's block, verbatim", () => {
  assert.deepEqual(ROOM_CAPS, {
    maxRounds: 3, maxContinuations: 2, maxBotMessages: 10, maxMembers: 6,
    turnTimeoutMs: 180_000, turnHardCapMs: 1_200_000,
  });
});

test("resolveMentions: by id always, by display name only when it is one token; anchored; unknown and e-mail pass through", () => {
  assert.deepEqual(resolveMentions("@buffett what about leverage?", roster), ["buffett"]);
  assert.deepEqual(resolveMentions("我想听 @投机型 的看法", roster), ["speculator"]);
  assert.deepEqual(resolveMentions("@投机型，你呢？", roster), ["speculator"], "trailing punctuation is not part of the token");
  assert.deepEqual(resolveMentions("@Macro View please", roster), [], "a multi-word name is not matched by its first word");
  assert.deepEqual(resolveMentions("@macro-view please", roster), ["macro-view"]);
  assert.deepEqual(resolveMentions("mail me at pan@buffett.example", roster), [], "an e-mail address is not a mention");
  assert.deepEqual(resolveMentions("@nobody and @buffett and @speculator and @buffett", roster), ["buffett", "speculator"], "unknown dropped, duplicates folded, order kept");
  assert.deepEqual(resolveMentions("no mentions here", roster), []);
  assert.deepEqual(resolveMentions("@buffett", []), [], "an empty roster resolves nothing");
});

test("isPass: the Hermes regex, whole-text only", () => {
  for (const text of ["(pass)", "pass", "(pass).", " ( pass ) ", "PASS"]) assert.equal(isPass(text), true, text);
  for (const text of ["I pass on this one", "pass, but note X", ""]) assert.equal(isPass(text), false, text);
});

const msg = (turn: number, text: string, seq: number): EventLike => ({
  type: "assistant/message", seq, data: { turn, step: 1, message: { id: `m${seq}`, role: "assistant", content: [{ type: "text", text }], source: { kind: "model", provider: "p", model: "m" } } },
});
const tool = (turn: number, seq: number): EventLike => ({ type: "tool/result", seq, data: { turn, step: 1, message: { id: `t${seq}`, role: "user", content: [{ type: "tool-result", toolCallId: "c1", content: [] }], source: { kind: "tool", callId: "c1" } } } });

test("finalTextOf: a text-only turn is its text; a tool-using turn is the text after the last tool result; a tool-only turn is empty", () => {
  assert.equal(finalTextOf([msg(1, "hello", 3)], 1), "hello");
  assert.equal(finalTextOf([msg(1, "let me check", 3), tool(1, 4), msg(1, "checked: yes", 5)], 1), "checked: yes");
  assert.equal(finalTextOf([msg(1, "a", 3), tool(1, 4), msg(1, "b", 5), msg(1, "c", 6)], 1), "b\n\nc");
  assert.equal(finalTextOf([msg(1, "running tool", 3), tool(1, 4)], 1), "");
  assert.equal(finalTextOf([msg(1, "other turn", 3), msg(2, "mine", 4)], 2), "mine", "only this turn's events count");
});

test("validateDispatch: empty to, duplicates, roster miss naming the roster, unknown mode, empty brief/reason", () => {
  const ok = validateDispatch({ to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" }, roster);
  assert.deepEqual(ok, { ok: true, value: { to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" } });
  const miss = validateDispatch({ to: ["ghost"], mode: "parallel", brief: "q", reason: "r" }, roster);
  assert.equal(miss.ok, false);
  assert.match((miss as { message: string }).message, /ghost/);
  assert.match((miss as { message: string }).message, /buffett, speculator, macro-view/, "the refusal names the roster - that is how the model learns it");
  assert.equal(validateDispatch({ to: [], mode: "parallel", brief: "q", reason: "r" }, roster).ok, false);
  assert.equal(validateDispatch({ to: ["buffett", "buffett"], mode: "serial", brief: "q", reason: "r" }, roster).ok, false);
  assert.equal(validateDispatch({ to: ["buffett"], mode: "round-robin", brief: "q", reason: "r" }, roster).ok, false);
  assert.equal(validateDispatch({ to: ["buffett"], mode: "serial", brief: " ", reason: "r" }, roster).ok, false);
  assert.equal(validateDispatch({ to: ["buffett"], mode: "serial", brief: "q" }, roster).ok, false);
  assert.equal(validateDispatch(null, roster).ok, false);
});

test("dispatchResultText names who was called, the mode, and who was NOT called (Rule 5), and tells the model to end its turn", () => {
  const args = { to: ["buffett", "speculator"], mode: "parallel" as const, brief: "q", reason: "two views first" };
  const text = dispatchResultText(args, roster, 1, 2, []);
  assert.match(text, /巴菲特型, 投机型 \(parallel\)/);
  assert.match(text, /Not called: Macro View\./);
  assert.match(text, /round 1/);
  assert.match(text, /2 rounds? left/i);
  assert.match(text, /end your turn/i);
  const all = dispatchResultText({ ...args, to: roster.map((b) => b.id) }, roster, 3, 0, ["投机型: model stub/x is not served; using the default route."]);
  assert.match(all, /Not called: none\./);
  assert.match(all, /stub\/x is not served/);
  assert.match(all, /0 rounds left/);
});

const user = (id: string, text: string, seq: number, source: Record<string, unknown> = { kind: "user" }): EventLike => ({
  type: "user/message", seq, data: { id, role: "user", content: [{ type: "text", text }], source },
});
const answer = (id: string, bot: string, name: string, text: string, seq: number): EventLike =>
  user(id, text, seq, { kind: "room", form: "answer", bot, name, sessionId: "s-b", turn: 1, round: 1 });

test("roomLinesOf: operator prompts, Kairos replies and member answers, in order; room events, plugin context and tool results are not lines", () => {
  const events: EventLike[] = [
    user("u1", "开个会", 1),
    user("ctx", "Instructions from AGENTS.md", 2, { kind: "plugin", plugin: "agent-instructions", form: "instructions" }),
    msg(1, "让大家先说", 3),
    tool(1, 4),
    answer("a1", "buffett", "巴菲特型", "买", 5),
    user("re", "Round 1 ended (settled)", 6, { kind: "room", form: "round-end", round: 1, outcome: "settled", turns: [] }),
    user("u2", "@speculator 你呢", 7, { kind: "user", mention: ["speculator"] }),
  ];
  const pending: MessageLike[] = [
    { id: "a2", role: "user", content: [{ type: "text", text: "卖" }], source: { kind: "room", form: "answer", bot: "speculator", name: "投机型", sessionId: "s-s", turn: 1, round: 1 } },
    { id: "a1", role: "user", content: [{ type: "text", text: "dup" }], source: { kind: "room", form: "answer", bot: "buffett", name: "巴菲特型", sessionId: "s-b", turn: 1, round: 1 } },
  ];
  const lines = roomLinesOf(events, pending, roster);
  assert.deepEqual(lines.map((l) => l.id), ["u1", "m3", "a1", "u2", "a2"], "pending lines follow the log; an id already in the log is not repeated");
  assert.deepEqual(lines[0].speaker, { kind: "operator" });
  assert.deepEqual(lines[1].speaker, { kind: "kairos" });
  assert.deepEqual(lines[2].speaker, { kind: "bot", bot: "buffett", name: "巴菲特型" });
  assert.deepEqual(lines[4].speaker, { kind: "bot", bot: "speculator", name: "投机型" });
});

test("formatDelta attributes every line and marks the reader's own", () => {
  const lines = roomLinesOf([user("u1", "开个会", 1), msg(1, "先各说各的", 3), answer("a1", "buffett", "巴菲特型", "买\n理由：便宜", 5), answer("a2", "speculator", "投机型", "卖", 6)], [], roster);
  assert.equal(formatDelta(lines, "buffett"), "操作员: 开个会\nKairos: 先各说各的\n巴菲特型 (you): 买\n  理由：便宜\n投机型: 卖");
  assert.equal(formatDelta([], "buffett"), "(nothing new)");
});

test("memberPrompt carries the delta, the brief when given, the trigger, and the four standing rules", () => {
  const text = memberPrompt({ roomName: "storage-chain", roster, self: "buffett", delta: "操作员: 开个会", brief: "state your view on SanDisk", trigger: "dispatch" });
  assert.match(text, /storage-chain/);
  assert.match(text, /操作员: 开个会/);
  assert.match(text, /state your view on SanDisk/);
  assert.match(text, /exactly \(pass\)/);
  assert.match(text, /verbatim/);
  assert.match(text, /this room only/);
  assert.match(text, /@<bot>/);
  assert.match(text, /投机型/, "the other voices are named so a peer mention can be spelled");
  const mention = memberPrompt({ roomName: "x", roster, self: "buffett", delta: "(nothing new)", trigger: "mention" });
  assert.match(mention, /operator addressed you directly/i);
  assert.doesNotMatch(mention, /Kairos asks this batch/);
  const cont = memberPrompt({ roomName: "x", roster, self: "buffett", delta: "(nothing new)", trigger: "continuation" });
  assert.match(cont, /continuation/i);
});

test("roundEndText: outcome word, each state group, rounds left; superseded and capped say why", () => {
  const turns = [
    { bot: "buffett", name: "巴菲特型", sessionId: "s1", state: "answered" as const, turn: 2 },
    { bot: "speculator", name: "投机型", sessionId: "s2", state: "passed" as const, turn: 1 },
    { bot: "macro-view", name: "Macro View", sessionId: "s3", state: "failed" as const, reason: "preset missing" },
  ];
  const settled = roundEndText(1, "settled", turns, 2);
  assert.match(settled, /^Round 1 ended \(settled\)/);
  assert.match(settled, /Answered: 巴菲特型\./);
  assert.match(settled, /Passed: 投机型\./);
  assert.match(settled, /Failed: Macro View \(preset missing\)\./);
  assert.match(settled, /Timed out: none\./);
  assert.match(settled, /2 rounds left/);
  assert.match(settled, /name the disagreements/i);
  assert.match(roundEndText(3, "capped", turns, 0), /capped/);
  assert.match(roundEndText(3, "capped", turns, 0), /0 rounds left/);
  assert.match(roundEndText(1, "superseded", turns, 2), /superseded by a new operator message/i);
});

test("parseModelRoute splits provider/model once and refuses anything else", () => {
  assert.deepEqual(parseModelRoute("deepseek-official/deepseek-v4-flash"), { provider: "deepseek-official", model: "deepseek-v4-flash" });
  assert.deepEqual(parseModelRoute("stub/echo:v2"), { provider: "stub", model: "echo:v2" });
  assert.equal(parseModelRoute("deepseek-v4-flash"), undefined);
  assert.equal(parseModelRoute("a/b/c"), undefined);
  assert.equal(parseModelRoute(""), undefined);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/room-rules.test.ts`
Expected: FAIL — cannot find `../src/room-rules.ts`.

- [ ] **Step 3: Write the module**

```ts
// face/src/room-rules.ts
/** The room's rules that are not Kairos's (spec §4.2, §4.3, §4.4, §4.6) —
 * pure functions and the constants block, so every rule is drillable without
 * a harness and the engine (room.ts) is orchestration only.
 *
 * Every room fact rides a KNOWN dsh event type (plan 2, deviation 1): dsh's
 * persistence read path refuses a log carrying any event type outside its
 * generated catalog, so the vocabulary here is a `source` vocabulary on
 * ordinary `user/message` events, never a new event type. The four sources:
 *   `answer`    a member's final text, injected into Kairos's session;
 *   `round-end` the one waking message per round;
 *   `delta`     the prompt a member turn received, in the MEMBER's own log -
 *               its `messageIds` are the member's durable cursor;
 *   the operator's `@`, an ordinary `kind: 'user'` message carrying `mention`.
 * @module
 */

/** Spec §4.6, verbatim. One block, one seam for later per-room overrides. */
export interface RoomCaps {
  /** dispatch rounds per operator send */
  maxRounds: number;
  /** peer-`@` continuation turns per round */
  maxContinuations: number;
  /** member turns (dispatched, continuation, or operator-`@`) per operator send */
  maxBotMessages: number;
  /** bots on one channel's roster */
  maxMembers: number;
  /** base per member turn */
  turnTimeoutMs: number;
  /** the deadline extends while the member runs or has a pending gate, up to this */
  turnHardCapMs: number;
}
export const ROOM_CAPS: RoomCaps = {
  maxRounds: 3, maxContinuations: 2, maxBotMessages: 10, maxMembers: 6,
  turnTimeoutMs: 180_000, turnHardCapMs: 1_200_000,
};

/** One bot as the room sees it: the roster id, the display name, the optional route. */
export interface RosterBot {
  id: string;
  name: string;
  model?: string;
  /** dsh's reason when the composition cannot mount - a member that will fail visibly. */
  broken?: string;
}

/** A session event as these rules read it (dsh-session's `SessionEvent`, structurally). */
export interface EventLike { type: string; seq: number; data?: unknown }
/** A user-role message as these rules read it (dsh-llm's `UserMessage`, structurally). */
export interface MessageLike {
  readonly id: string;
  readonly role: "user";
  readonly content: readonly { type: string; text?: string }[];
  readonly source: { readonly kind: string } & Record<string, unknown>;
}

export type MemberTurnState = "answered" | "passed" | "failed" | "timed-out";
export type RoundOutcome = "settled" | "capped" | "superseded";
export type TurnTrigger = "dispatch" | "mention" | "continuation";

export interface RoomTurnRecord {
  bot: string;
  name: string;
  sessionId: string;
  state: MemberTurnState;
  turn?: number;
  /** why it failed or timed out, one line */
  reason?: string;
}

/* ---------- the source vocabulary (plan 2, deviation 1) ---------- */

/* `type`, not `interface`: an interface is not assignable to `Record<string, unknown>`
 * (no implicit index signature), and the engine's `MessageLike.source` is one. */
export type RoomAnswerSource = {
  kind: "room"; form: "answer"; bot: string; name: string; sessionId: string; turn: number; round: number;
};
export type RoomRoundEndSource = {
  kind: "room"; form: "round-end"; round: number; outcome: RoundOutcome; turns: RoomTurnRecord[];
};
export type RoomDeltaSource = {
  kind: "room"; form: "delta"; room: string; bot: string; messageIds: string[]; trigger: TurnTrigger; brief?: string;
};
export type RoomMessageSource = RoomAnswerSource | RoomRoundEndSource | RoomDeltaSource;
/** The operator's `@`: still the operator's message (`kind: 'user'`), with whom it addressed. */
export type OperatorMentionSource = { kind: "user"; mention: string[] };

declare module "@deepseek-ai/dsh-llm" {
  interface MessageSourceMap {
    room: RoomMessageSource;
    "user-mention": OperatorMentionSource;
  }
}

/* ---------- `@` (spec §4.4 rule 1) ---------- */

/** `(^|\s)@token` - the composer anchor; an e-mail's `@` follows a non-space. */
const MENTION_RE = /(^|\s)@([^\s@]+)/gu;
/** Punctuation a mention may end on without being part of the name. */
const TRAILING_PUNCT_RE = /[.,;:!?)\]}"'，。；：！？）】」』]+$/u;

/**
 * Resolve the bots a message addresses: by id always, by display name only
 * when the name is one token (a multi-word name is reached by id). Unknown
 * tokens pass through; duplicates fold; order is first mention.
 */
export function resolveMentions(text: string, roster: readonly RosterBot[]): string[] {
  const byId = new Set(roster.map((b) => b.id));
  const byName = new Map<string, string>();
  for (const b of roster) {
    const name = b.name.trim();
    if (name !== "" && !/\s/u.test(name)) byName.set(name, b.id);
  }
  const out: string[] = [];
  for (const match of text.matchAll(MENTION_RE)) {
    const token = match[2].replace(TRAILING_PUNCT_RE, "");
    const id = byId.has(token) ? token : byName.get(token);
    if (id !== undefined && !out.includes(id)) out.push(id);
  }
  return out;
}

/* ---------- final text and `(pass)` (spec §4.6) ---------- */

/** Hermes's pass regex, applied to the whole final text. */
export const PASS_RE = /^\(?\s*pass\s*\)?\.?$/i;
export const isPass = (text: string): boolean => PASS_RE.test(text.trim());

function textBlocks(content: unknown): string {
  if (!Array.isArray(content)) return "";
  return content
    .filter((b): b is { type: "text"; text: string } => b !== null && typeof b === "object" && (b as { type?: unknown }).type === "text" && typeof (b as { text?: unknown }).text === "string")
    .map((b) => b.text).join("\n").trim();
}

/**
 * A member turn's final text: the assistant text after the turn's last tool
 * result, or the whole turn's text when it used no tools. Empty when the
 * turn ended on a tool (the caller reads that as `passed`).
 */
export function finalTextOf(events: readonly EventLike[], turn: number): string {
  const segments: string[] = [];
  for (const event of events) {
    const data = event.data as { turn?: unknown; message?: { content?: unknown } } | undefined;
    if (data === undefined || data.turn !== turn) continue;
    if (event.type === "tool/result") { segments.length = 0; continue; }
    if (event.type === "assistant/message") {
      const text = textBlocks(data.message?.content);
      if (text !== "") segments.push(text);
    }
  }
  return segments.join("\n\n").trim();
}

/* ---------- dispatch (spec §4.3) ---------- */

export interface DispatchArgs { to: string[]; mode: "parallel" | "serial"; brief: string; reason: string }

const rosterText = (roster: readonly RosterBot[]): string =>
  roster.length === 0 ? "(no bots on this channel's roster)" : roster.map((b) => b.id).join(", ");

/** Validate the model's arguments against the roster. The refusal names the
 * roster - that is how the model learns it without a prompt that could drift. */
export function validateDispatch(args: unknown, roster: readonly RosterBot[]): { ok: true; value: DispatchArgs } | { ok: false; message: string } {
  const a = (args !== null && typeof args === "object" ? args : {}) as Record<string, unknown>;
  const to = a.to;
  if (!Array.isArray(to) || to.length === 0 || to.some((x) => typeof x !== "string" || x === "")) {
    return { ok: false, message: `dispatch needs a non-empty "to" list of bot ids. This channel's roster: ${rosterText(roster)}.` };
  }
  const ids = to as string[];
  const dup = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
  if (dup.length > 0) return { ok: false, message: `"to" names a bot twice: ${dup.join(", ")}.` };
  const missing = ids.filter((id) => !roster.some((b) => b.id === id));
  if (missing.length > 0) {
    return { ok: false, message: `${missing.join(", ")} ${missing.length === 1 ? "is" : "are"} not on this channel's roster. It currently offers: ${rosterText(roster)}. The operator checks bots in on the channel page.` };
  }
  if (a.mode !== "parallel" && a.mode !== "serial") return { ok: false, message: `mode must be "parallel" or "serial".` };
  if (typeof a.brief !== "string" || a.brief.trim() === "") return { ok: false, message: "brief must be a non-empty string - the question or task for this batch." };
  if (typeof a.reason !== "string" || a.reason.trim() === "") return { ok: false, message: "reason must be a non-empty string - why these bots and why this mode; it lands in the transcript." };
  return { ok: true, value: { to: ids, mode: a.mode, brief: a.brief.trim(), reason: a.reason.trim() } };
}

const nameOf = (roster: readonly RosterBot[], id: string): string => roster.find((b) => b.id === id)?.name ?? id;
const names = (roster: readonly RosterBot[], ids: readonly string[]): string => ids.map((id) => nameOf(roster, id)).join(", ");

/** The tool result: who was called, how, who was NOT (Rule 5), and what to do now. */
export function dispatchResultText(args: DispatchArgs, roster: readonly RosterBot[], round: number, remainingRounds: number, notes: readonly string[]): string {
  const notCalled = roster.filter((b) => !args.to.includes(b.id)).map((b) => b.name);
  const lines = [
    `Dispatched ${names(roster, args.to)} (${args.mode}), round ${round} of this operator message; ${remainingRounds} ${remainingRounds === 1 ? "round" : "rounds"} left after it. Not called: ${notCalled.length === 0 ? "none" : notCalled.join(", ")}.`,
    "The batch is running. End your turn now: you will be woken once when the round ends, with who answered and who passed, and every answer will be in this conversation, attributed to its voice.",
    ...notes,
  ];
  return lines.join("\n");
}

/* ---------- the delta (spec §4.2) ---------- */

export interface RoomLine {
  id: string;
  speaker: { kind: "operator" } | { kind: "kairos" } | { kind: "bot"; bot: string; name: string };
  text: string;
}

function lineOfUserMessage(message: MessageLike | undefined, roster: readonly RosterBot[]): RoomLine | undefined {
  if (message === undefined || typeof message.id !== "string") return undefined;
  const source = message.source;
  const text = textBlocks(message.content);
  if (text === "") return undefined;
  if (source.kind === "user") return { id: message.id, speaker: { kind: "operator" }, text };
  if (source.kind === "room" && source.form === "answer" && typeof source.bot === "string") {
    return { id: message.id, speaker: { kind: "bot", bot: source.bot, name: typeof source.name === "string" ? source.name : nameOf(roster, source.bot) }, text };
  }
  return undefined; // round-end and delta are room facts, plugin/tool context is not conversation
}

/**
 * The room as a member reads it: operator prompts, Kairos replies and member
 * answers, in log order, then the messages still pending in Kairos's inbox
 * (answers and `@`s that have not been claimed yet), deduplicated by id.
 */
export function roomLinesOf(events: readonly EventLike[], pending: readonly MessageLike[], roster: readonly RosterBot[]): RoomLine[] {
  const lines: RoomLine[] = [];
  const seen = new Set<string>();
  const push = (line: RoomLine | undefined): void => {
    if (line === undefined || seen.has(line.id)) return;
    seen.add(line.id);
    lines.push(line);
  };
  for (const event of events) {
    if (event.type === "user/message") push(lineOfUserMessage(event.data as MessageLike | undefined, roster));
    else if (event.type === "assistant/message") {
      const message = (event.data as { message?: { id?: unknown; content?: unknown } } | undefined)?.message;
      const text = textBlocks(message?.content);
      if (typeof message?.id === "string" && text !== "") push({ id: message.id, speaker: { kind: "kairos" }, text });
    }
  }
  for (const message of pending) push(lineOfUserMessage(message, roster));
  return lines;
}

/** One line per entry, attributed; continuation lines of a multi-line text are indented. */
export function formatDelta(lines: readonly RoomLine[], self: string): string {
  if (lines.length === 0) return "(nothing new)";
  return lines.map((line) => {
    const label = line.speaker.kind === "operator" ? "操作员"
      : line.speaker.kind === "kairos" ? "Kairos"
      : line.speaker.bot === self ? `${line.speaker.name} (you)` : line.speaker.name;
    return `${label}: ${line.text.replace(/\n/g, "\n  ")}`;
  }).join("\n");
}

/** Spec §4.2: carried in every member turn rather than in SOUL.md, so any bot joins without a profile edit. */
export const MEMBER_RULES: readonly string[] = [
  "Reply with your view; reply with exactly (pass) if you have nothing to add.",
  "Your reply text goes to the room verbatim — no preamble, no meta-commentary.",
  "You remember this room only; do not claim knowledge of other channels.",
  "Address the operator directly when a judgment is theirs to make; write @<bot> to pull a peer in.",
];

export function memberPrompt(opts: { roomName: string; roster: readonly RosterBot[]; self: string; delta: string; trigger: TurnTrigger; brief?: string }): string {
  const others = opts.roster.filter((b) => b.id !== opts.self).map((b) => `${b.name} (@${b.id})`);
  const parts = [
    `You are in the room "${opts.roomName}" with the operator, Kairos (the organizer)${others.length === 0 ? "" : ` and the other voices on this channel's roster: ${others.join(", ")}`}.`,
    "",
    "New in the room since you last spoke:",
    opts.delta,
    "",
  ];
  if (opts.brief !== undefined) parts.push(`Kairos asks this batch: ${opts.brief}`, "");
  if (opts.trigger === "mention") parts.push("The operator addressed you directly.", "");
  if (opts.trigger === "continuation") parts.push("A peer addressed you; this is your one continuation turn this round.", "");
  parts.push("Rules for this turn:", ...MEMBER_RULES.map((rule, i) => `${i + 1}. ${rule}`));
  return parts.join("\n");
}

/* ---------- round end (spec §4.3, §4.6) ---------- */

export function roundEndText(round: number, outcome: RoundOutcome, turns: readonly RoomTurnRecord[], remainingRounds: number): string {
  const group = (state: MemberTurnState): string => {
    const rows = turns.filter((t) => t.state === state).map((t) => t.reason === undefined ? t.name : `${t.name} (${t.reason})`);
    return rows.length === 0 ? "none" : rows.join(", ");
  };
  const head = outcome === "settled" ? `Round ${round} ended (settled).`
    : outcome === "capped" ? `Round ${round} ended (capped: the bot-message cap for this operator message was reached before every voice spoke).`
    : `Round ${round} was superseded by a new operator message; no further voice was called for it.`;
  return [
    head,
    `Answered: ${group("answered")}. Passed: ${group("passed")}. Failed: ${group("failed")}. Timed out: ${group("timed-out")}.`,
    `The answers that landed are above in this conversation, attributed to each voice. Name the disagreements between them, then either dispatch again (${remainingRounds} ${remainingRounds === 1 ? "round" : "rounds"} left before the operator must speak) or reply to the operator.`,
  ].join("\n");
}

/* ---------- preset.yml `model:` ---------- */

/** `<provider>/<model>`, split once; anything else is undefined. */
export function parseModelRoute(route: string): { provider: string; model: string } | undefined {
  const at = route.indexOf("/");
  if (at <= 0 || at === route.length - 1) return undefined;
  const provider = route.slice(0, at);
  const model = route.slice(at + 1);
  if (model.includes("/")) return undefined;
  return { provider, model };
}
```

In `face/src/channels.ts`, replace the Task-2 `MAX_MEMBERS` constant with `import { ROOM_CAPS } from "./room-rules.ts";` and `ROOM_CAPS.maxMembers` (the channels test's `/6/` still passes). In `face/src/sessions.ts`, change `const SESSION_ID_RE` to `export const SESSION_ID_RE` (the room routes reuse it in Task 9).

- [ ] **Step 4: Run the tests and typecheck**

Run: `cd face && npx tsx --test tests/room-rules.test.ts tests/channels.test.ts && npm run typecheck`
Expected: PASS, clean. If `formatDelta`'s expected string in the test differs by a space, fix the TEST only if the difference is cosmetic and the rule (label, `(you)`, two-space continuation) holds — otherwise fix the code.

- [ ] **Step 5: Commit**

```bash
git add face/src/room-rules.ts face/src/channels.ts face/src/sessions.ts face/tests/room-rules.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): the room's pure rules - caps, mentions by id or one-token name, the final-text and pass rules, dispatch validation naming the roster, the attributed delta, the member prompt, the round-end text
```

---

### Task 4: The `room` projection unit — `face/src/room-projection.ts`

**Files:**
- Create: `face/src/room-projection.ts`
- Test: `face/tests/room-projection.test.ts`

**Interfaces:**
- Consumes: Task 3's `EventLike`, `MemberTurnState`, `RoundOutcome`.
- Produces: `ROOM_PROJECTION_KEY = "room"`, `ROOM_STATE_VERSION = 1`, `RoomState`, `RoomMemberState`, `initRoomState()`, `applyRoomEvent(state, event)`, `roomStateSchema`, `registerRoomProjection(registry): () => void` where `registry` is `{ register(definition: ProjectionDefinitionLike): () => void }`.

- [ ] **Step 1: Write the failing tests**

```ts
// face/tests/room-projection.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { ROOM_PROJECTION_KEY, ROOM_STATE_VERSION, applyRoomEvent, initRoomState, registerRoomProjection, roomStateSchema, type RoomState } from "../src/room-projection.ts";
import type { EventLike } from "../src/room-rules.ts";

let seq = 0;
const ev = (type: string, data: unknown): EventLike => ({ type, seq: seq++, data });
const user = (id: string, text: string, source: Record<string, unknown>): EventLike =>
  ev("user/message", { id, role: "user", content: [{ type: "text", text }], source });
const dispatchCall = (to: string[], mode: string): EventLike =>
  ev("tool/call", { turn: 1, step: 1, callId: "c1", name: "dispatch", arguments: JSON.stringify({ to, mode, brief: "b", reason: "r" }) });
const answerMsg = (id: string, bot: string, sessionId: string, turn: number) => ({
  id, role: "user", content: [{ type: "text", text: "view" }], source: { kind: "room", form: "answer", bot, name: bot, sessionId, turn, round: 1 },
});
const fold = (events: EventLike[]): RoomState => events.reduce(applyRoomEvent, initRoomState());

test("a session that is not a room stays `none`, by the same reference, through ordinary traffic", () => {
  const s0 = initRoomState();
  const s1 = applyRoomEvent(s0, user("u1", "hi", { kind: "user" }));
  const s2 = applyRoomEvent(s1, ev("turn/start", { turn: 1 }));
  const s3 = applyRoomEvent(s2, ev("assistant/message", { turn: 1, step: 1, message: { id: "m", role: "assistant", content: [], source: { kind: "model", provider: "p", model: "m" } } }));
  assert.equal(s3, s0, "unrelated events return the same reference (the registry's change gate)");
  assert.deepEqual(s0, { kind: "none" });
});

test("a dispatch call makes the session a room: members called, round open, mode kept", () => {
  const s = fold([user("u1", "q", { kind: "user" }), dispatchCall(["buffett", "speculator"], "parallel")]);
  assert.equal(s.kind, "room");
  assert.deepEqual(s.round, { n: 1, mode: "parallel", open: true });
  assert.deepEqual(s.members, { buffett: { state: "called" }, speculator: { state: "called" } });
});

test("answers - pending in the inbox or claimed into the log - mark the member answered with its session", () => {
  const spliced = ev("agent/inbox/spliced", { target: "next-step", start: 0, inserted: [answerMsg("a1", "buffett", "s-b", 3)] });
  const s = fold([dispatchCall(["buffett", "speculator"], "serial"), spliced]);
  assert.deepEqual(s.members?.buffett, { sessionId: "s-b", name: "buffett", state: "answered", turn: 3 });
  assert.deepEqual(s.members?.speculator, { state: "called" });
  const s2 = applyRoomEvent(s, ev("user/message", answerMsg("a1", "buffett", "s-b", 3)));
  assert.deepEqual(s2.members?.buffett, s.members?.buffett, "the claim repeats the fact, idempotently");
});

test("the round-end message closes the round with its outcome and every turn's state", () => {
  const s = fold([
    dispatchCall(["buffett", "speculator", "macro-view"], "parallel"),
    user("re", "Round 1 ended", { kind: "room", form: "round-end", round: 1, outcome: "settled", turns: [
      { bot: "buffett", name: "巴菲特型", sessionId: "s-b", state: "answered", turn: 1 },
      { bot: "speculator", name: "投机型", sessionId: "s-s", state: "passed", turn: 1 },
      { bot: "macro-view", name: "Macro View", sessionId: "s-m", state: "timed-out", turn: 1 },
    ] }),
  ]);
  assert.deepEqual(s.round, { n: 1, mode: "parallel", open: false, outcome: "settled" });
  assert.equal(s.members?.buffett.state, "answered");
  assert.equal(s.members?.speculator.state, "passed");
  assert.equal(s.members?.["macro-view"].state, "timed-out");
  assert.equal(s.members?.["macro-view"].sessionId, "s-m");
});

test("a new operator message resets the members to idle and closes the round; an `@` calls whom it names", () => {
  const before = fold([dispatchCall(["buffett"], "parallel")]);
  const plain = applyRoomEvent(before, user("u2", "new topic", { kind: "user" }));
  assert.deepEqual(plain.members, {});
  assert.equal(plain.round?.open, false);
  const mention = applyRoomEvent(plain, user("u3", "@speculator 你呢", { kind: "user", mention: ["speculator"] }));
  assert.deepEqual(mention.members, { speculator: { state: "called" } });
  assert.deepEqual(mention.round, { n: 1, mode: "mention", open: true });
  const fromNone = applyRoomEvent(initRoomState(), user("u4", "@buffett hi", { kind: "user", mention: ["buffett"] }));
  assert.equal(fromNone.kind, "room", "an `@` on a plain channel session makes it a room too");
});

test("a second dispatch bumps the round and forgets who was in the last one", () => {
  const s = fold([dispatchCall(["buffett"], "parallel"), dispatchCall(["speculator"], "serial")]);
  assert.deepEqual(s.round, { n: 2, mode: "serial", open: true });
  assert.deepEqual(s.members, { speculator: { state: "called" } });
});

test("Kairos's own turn boundaries drive `organizing` only once the session is a room", () => {
  const room = fold([dispatchCall(["buffett"], "parallel"), ev("turn/end", { turn: 1, reason: { kind: "completed" } })]);
  assert.equal(room.organizing, false);
  const again = applyRoomEvent(room, ev("turn/start", { turn: 2 }));
  assert.equal(again.organizing, true);
});

test("a member session folds to `member` from its first delta prompt and ignores everything else", () => {
  const s = fold([
    ev("turn/start", { turn: 1 }),
    user("d1", "You are in the room …", { kind: "room", form: "delta", room: "session-room", bot: "buffett", messageIds: ["u1"], trigger: "dispatch" }),
    dispatchCall(["x"], "parallel"), // cannot happen (masked), and must not turn a member into a room
  ]);
  assert.deepEqual(s, { kind: "member", room: "session-room", bot: "buffett" });
});

test("the state schema accepts every state the fold produces and the unit registers with the key and version", () => {
  for (const s of [initRoomState(), fold([dispatchCall(["a"], "parallel")]), fold([user("d", "x", { kind: "room", form: "delta", room: "r", bot: "b", messageIds: [], trigger: "mention" })])]) {
    assert.deepEqual(roomStateSchema.parse(s), s);
  }
  const seen: unknown[] = [];
  const dispose = registerRoomProjection({ register(definition) { seen.push(definition); return () => { seen.length = 0; }; } });
  const def = seen[0] as { key: string; stateVersion: number; init(): unknown; apply: unknown; wire: { view(s: unknown): unknown } };
  assert.equal(def.key, ROOM_PROJECTION_KEY);
  assert.equal(def.stateVersion, ROOM_STATE_VERSION);
  assert.deepEqual(def.init(), { kind: "none" });
  assert.equal(def.wire.view({ kind: "none" }).kind, "none");
  dispose();
  assert.equal(seen.length, 0);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/room-projection.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the module**

```ts
// face/src/room-projection.ts
/** The `room` projection unit: the coarse state of a room, folded from the
 * KNOWN events that carry room facts (plan 2, deviation 1), served to clients
 * as one whole value per session through dsh's own carriers - the
 * `session/projection` push frame, the history tail page and, for a cold
 * session, the persisted cache row the face now mounts.
 *
 * Registered process-wide (dsh-session-projection: the unit table is not
 * per-session), so the key is in EVERY session's snapshot; its `none` value
 * means "not a room" and a client reads the VALUE, never the key's presence.
 *
 * Coarse only: `called`, `answered`, `passed`, `failed`, `timed-out` are log
 * facts. "Thinking / writing / calling a tool" are live pulses on the member
 * sessions' own feeds and the client's to read - the registry has no
 * out-of-fold write (plan 2, deviation 3).
 * @module
 */
import { z } from "zod";
import type { EventLike, MemberTurnState, RoundOutcome } from "./room-rules.ts";

export const ROOM_PROJECTION_KEY = "room";
/** Bump when the state fields or the fold change: the persisted cache
 * discards rows of another version instead of forward-applying garbage. */
export const ROOM_STATE_VERSION = 1;

export type MemberCoarseState = "called" | MemberTurnState;

export interface RoomMemberState {
  sessionId?: string;
  name?: string;
  state: MemberCoarseState;
  turn?: number;
}

export interface RoomState {
  kind: "none" | "room" | "member";
  /** room: the current or last round */
  round?: { n: number; mode: "parallel" | "serial" | "mention"; open: boolean; outcome?: RoundOutcome };
  /** room: the members of the current round, by bot id */
  members?: Record<string, RoomMemberState>;
  /** room: Kairos's turn is open */
  organizing?: boolean;
  /** member: the room session this member belongs to */
  room?: string;
  /** member: the bot */
  bot?: string;
}

const memberSchema = z.object({
  sessionId: z.string().optional(),
  name: z.string().optional(),
  state: z.enum(["called", "answered", "passed", "failed", "timed-out"]),
  turn: z.number().optional(),
});
export const roomStateSchema: z.ZodType<RoomState> = z.object({
  kind: z.enum(["none", "room", "member"]),
  round: z.object({
    n: z.number(),
    mode: z.enum(["parallel", "serial", "mention"]),
    open: z.boolean(),
    outcome: z.enum(["settled", "capped", "superseded"]).optional(),
  }).optional(),
  members: z.record(z.string(), memberSchema).optional(),
  organizing: z.boolean().optional(),
  room: z.string().optional(),
  bot: z.string().optional(),
});

export const initRoomState = (): RoomState => ({ kind: "none" });

type Source = { kind?: unknown; form?: unknown } & Record<string, unknown>;
const sourceOf = (message: unknown): Source | undefined => {
  const source = (message as { source?: unknown } | undefined)?.source;
  return source !== null && typeof source === "object" ? source as Source : undefined;
};

/** `none` becomes `room`; `room` stays; `member` is never promoted (a masked voice cannot dispatch). */
const asRoom = (state: RoomState): RoomState | undefined =>
  state.kind === "room" ? state : state.kind === "none" ? { kind: "room", members: {}, organizing: false } : undefined;

function withMember(state: RoomState, bot: string, patch: Partial<RoomMemberState> & { state: MemberCoarseState }): RoomState {
  const current = state.members?.[bot] ?? { state: "called" as const };
  return { ...state, members: { ...state.members, [bot]: { ...current, ...patch } } };
}

function applyAnswer(state: RoomState, message: unknown): RoomState {
  const source = sourceOf(message);
  if (source?.kind !== "room" || source.form !== "answer" || typeof source.bot !== "string") return state;
  const room = asRoom(state);
  if (room === undefined) return state;
  return withMember(room, source.bot, {
    state: "answered",
    ...(typeof source.sessionId === "string" ? { sessionId: source.sessionId } : {}),
    ...(typeof source.name === "string" ? { name: source.name } : {}),
    ...(typeof source.turn === "number" ? { turn: source.turn } : {}),
  });
}

function applyOperator(state: RoomState, source: Source): RoomState {
  const mention = Array.isArray(source.mention) ? source.mention.filter((m): m is string => typeof m === "string") : [];
  if (state.kind === "member") return state;
  if (state.kind === "none" && mention.length === 0) return state;
  const room = asRoom(state) as RoomState;
  const reset: RoomState = { ...room, members: {}, ...(room.round === undefined ? {} : { round: { ...room.round, open: false } }) };
  if (mention.length === 0) return reset;
  let next = reset;
  for (const bot of mention) next = withMember(next, bot, { state: "called" });
  return { ...next, round: { n: room.round?.n ?? 1, mode: "mention", open: true } };
}

/**
 * The pure transition. Returns the SAME reference for every event that is not
 * the unit's (the registry gates its change feed on `Object.is`).
 */
export function applyRoomEvent(state: RoomState, event: EventLike): RoomState {
  const data = event.data as Record<string, unknown> | undefined;
  switch (event.type) {
    case "user/message": {
      const source = sourceOf(data);
      if (source?.kind === "room") {
        if (source.form === "delta") {
          if (state.kind === "member") return state;
          return { kind: "member", ...(typeof source.room === "string" ? { room: source.room } : {}), ...(typeof source.bot === "string" ? { bot: source.bot } : {}) };
        }
        if (source.form === "answer") return applyAnswer(state, data);
        if (source.form === "round-end") {
          const room = asRoom(state);
          if (room === undefined) return state;
          let next = room;
          const turns = Array.isArray(source.turns) ? source.turns : [];
          for (const t of turns as Array<Record<string, unknown>>) {
            if (typeof t.bot !== "string" || typeof t.state !== "string") continue;
            next = withMember(next, t.bot, {
              state: t.state as MemberCoarseState,
              ...(typeof t.sessionId === "string" ? { sessionId: t.sessionId } : {}),
              ...(typeof t.name === "string" ? { name: t.name } : {}),
              ...(typeof t.turn === "number" ? { turn: t.turn } : {}),
            });
          }
          const n = typeof source.round === "number" ? source.round : next.round?.n ?? 1;
          const outcome = source.outcome === "settled" || source.outcome === "capped" || source.outcome === "superseded" ? source.outcome : undefined;
          return { ...next, round: { n, mode: next.round?.mode ?? "parallel", open: false, ...(outcome === undefined ? {} : { outcome }) } };
        }
        return state;
      }
      if (source?.kind === "user") return applyOperator(state, source);
      return state;
    }
    case "agent/inbox/spliced": {
      const inserted = Array.isArray(data?.inserted) ? data.inserted : [];
      let next = state;
      for (const message of inserted) {
        const source = sourceOf(message);
        if (source?.kind === "room") next = applyAnswer(next, message);
        else if (source?.kind === "user" && Array.isArray(source.mention) && source.mention.length > 0) next = applyOperator(next, source);
      }
      return next;
    }
    case "tool/call": {
      if (data?.name !== "dispatch" || typeof data.arguments !== "string") return state;
      let args: { to?: unknown; mode?: unknown };
      try { args = JSON.parse(data.arguments) as { to?: unknown; mode?: unknown }; } catch { return state; }
      const room = asRoom(state);
      if (room === undefined) return state;
      const to = Array.isArray(args.to) ? args.to.filter((x): x is string => typeof x === "string") : [];
      const members: Record<string, RoomMemberState> = {};
      for (const bot of to) members[bot] = { state: "called" };
      const mode = args.mode === "serial" ? "serial" : "parallel";
      return { ...room, members, round: { n: (room.round?.n ?? 0) + 1, mode, open: true } };
    }
    case "turn/start":
      return state.kind === "room" && state.organizing !== true ? { ...state, organizing: true } : state;
    case "turn/end":
      return state.kind === "room" && state.organizing !== false ? { ...state, organizing: false } : state;
    default:
      return state;
  }
}

/** What `ctx.sessionProjections.register` takes, stated structurally (dsh-session-projection `ProjectionDefinition`). */
export interface ProjectionDefinitionLike {
  key: string;
  stateSchema: z.ZodType<RoomState>;
  init(): RoomState;
  apply(state: RoomState, event: EventLike): RoomState;
  wire: { viewSchema: z.ZodType<RoomState>; view(state: RoomState): RoomState };
  stateVersion: number;
}

/** Register the unit; returns the registry's own disposer. */
export function registerRoomProjection(registry: { register(definition: ProjectionDefinitionLike): () => void }): () => void {
  return registry.register({
    key: ROOM_PROJECTION_KEY,
    stateSchema: roomStateSchema,
    init: initRoomState,
    apply: applyRoomEvent,
    wire: { viewSchema: roomStateSchema, view: (state) => state },
    stateVersion: ROOM_STATE_VERSION,
  });
}
```

The `turn/start`/`turn/end` branches guard on the current value so a room already `organizing` returns the same reference (the mention `round.n` uses `?? 1` so a room born from an `@` reads round 1).

- [ ] **Step 4: Run the tests and typecheck**

Run: `cd face && npx tsx --test tests/room-projection.test.ts && npm run typecheck`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add face/src/room-projection.ts face/tests/room-projection.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): the room projection unit - a pure fold of the known events that carry room facts, whole-value, same-reference on everything else
```

---

### Task 5: The fake tree for engine tests — `face/tests/room-fake.ts`

**Files:**
- Create: `face/tests/room-fake.ts`

**Interfaces:**
- Consumes: Task 3's `EventLike`, `MessageLike`.
- Produces: `makeFakeTree(): FakeTree` with `tree.ctx` (satisfies the engine's `RoomContextLike` of Task 6), `tree.clock` (`now`, `setTimeout`, `clearTimeout`, `advance(ms)`, `flush()`), `tree.newRoom(id, cwd)` (a Kairos agent whose inbox is inspectable and whose `wake()` simulates a turn claiming its inbox), `tree.script(bot, fn)` (what a member does when prompted), `tree.agentsCreated`, `tree.mounts`, `tree.selections`, `tree.registeredTools`, `tree.attached`, `tree.persisted`. Script kinds: `{ kind: "answer", text, afterMs?, toolFirst? }`, `{ kind: "error", message }`, `{ kind: "hang" }` (never ends until cancelled), `{ kind: "gate" }` (opens an `ask_user_question` call and hangs), `{ kind: "throw" }` (followup itself throws).

- [ ] **Step 1: Write the fake**

```ts
// face/tests/room-fake.ts
/** A fake dsh tree for the room engine's offline tests: scriptable agents, a
 * manual clock, and a root `session/event` bus. Structural twins of exactly
 * the members `RoomContextLike` (src/room.ts) reads - nothing more. */
import type { EventLike, MessageLike } from "../src/room-rules.ts";

export type Script =
  | { kind: "answer"; text: string; afterMs?: number; toolFirst?: boolean }
  | { kind: "error"; message: string }
  | { kind: "hang" }
  | { kind: "gate" }
  | { kind: "throw" };

type Listener = (session: FakeSession, event: EventLike) => void;

export class FakeSession {
  readonly events: EventLike[] = [];
  tree?: FakeTree;
  constructor(readonly id: string, readonly header: { cwd?: string; parentSession?: string; agentPreset?: string; origin?: string; createdAt: number }) {}
  get seq(): number { return this.events.length; }
  /** The engine's direct append (plan 2, deviation 2): a known event, published on the bus. */
  append(type: "user/message", data: MessageLike, _opts: { surfaceOp: "append" }): EventLike {
    const event = { type, seq: this.seq, data };
    this.tree!.emit(this, event);
    return event;
  }
}

export class FakeAgent {
  status: "idle" | "running" = "idle";
  readonly inbox = { nextStep: [] as MessageLike[], nextTurn: [] as MessageLike[] };
  turn = 0;
  cancelled: { cause: unknown; options: unknown }[] = [];
  private idleWaiters: (() => void)[] = [];
  constructor(readonly tree: FakeTree, readonly session: FakeSession, readonly script?: (message: MessageLike, turn: number) => Script) {}
  get id(): string { return this.session.id; }
  private emit(type: string, data: unknown): void { this.tree.emit(this.session, { type, seq: this.session.seq, data }); }
  private splice(target: "next-step" | "next-turn", message: MessageLike): void {
    const list = target === "next-step" ? this.inbox.nextStep : this.inbox.nextTurn;
    if ([...this.inbox.nextStep, ...this.inbox.nextTurn].some((m) => m.id === message.id)) throw new Error(`message "${message.id}" is already pending`);
    this.emit("agent/inbox/spliced", { target, start: list.length, inserted: [message] });
    list.push(message);
  }
  inject(message: MessageLike): void { this.splice("next-step", message); }
  followup(message: MessageLike): void {
    this.splice("next-turn", message);
    if (this.script !== undefined) this.drive();
  }
  /** A member: claim the queued prompt and play the script. */
  private drive(): void {
    const claimed = [...this.inbox.nextStep.splice(0), ...this.inbox.nextTurn.splice(0, 1)];
    const prompt = claimed[claimed.length - 1];
    const turn = ++this.turn;
    this.status = "running";
    this.emit("turn/start", { turn });
    for (const m of claimed) this.emit("user/message", m);
    let script: Script;
    try { script = this.script!(prompt, turn); } catch (err) { script = { kind: "error", message: String(err) }; }
    const finish = (reason: unknown): void => {
      this.emit("turn/end", { turn, reason });
      this.status = "idle";
      for (const w of this.idleWaiters.splice(0)) w();
    };
    const say = (text: string): void => this.emit("assistant/message", { turn, step: 1, message: { id: `${this.id}-m${this.session.seq}`, role: "assistant", content: [{ type: "text", text }], source: { kind: "model", provider: "fake", model: "fake" } } });
    if (script.kind === "throw") throw new Error("followup exploded");
    if (script.kind === "error") { this.tree.clock.setTimeout(() => finish({ kind: "error", error: { message: (script as { message: string }).message, code: "FAKE" } }), 1); return; }
    if (script.kind === "hang") { this.pendingFinish = finish; return; }
    if (script.kind === "gate") {
      this.emit("tool/call", { turn, step: 1, callId: `${this.id}-ask`, name: "ask_user_question", arguments: "{}" });
      this.pendingFinish = finish;
      return;
    }
    const answer = script;
    this.tree.clock.setTimeout(() => {
      if (answer.toolFirst) {
        say("let me check");
        this.emit("tool/call", { turn, step: 1, callId: `${this.id}-c1`, name: "bash", arguments: "{}" });
        this.emit("tool/result", { turn, step: 1, message: { id: `${this.id}-t${this.session.seq}`, role: "user", content: [{ type: "tool-result", toolCallId: `${this.id}-c1`, content: [] }], source: { kind: "tool", callId: `${this.id}-c1` } } });
      }
      if (answer.text !== "") say(answer.text);
      finish({ kind: "completed" });
    }, answer.afterMs ?? 10);
  }
  private pendingFinish?: (reason: unknown) => void;
  cancel(cause: unknown, options?: unknown): void {
    this.cancelled.push({ cause, options });
    const finish = this.pendingFinish;
    this.pendingFinish = undefined;
    if (finish !== undefined) this.tree.clock.setTimeout(() => finish({ kind: "aborted", reason: cause }), 1);
  }
  /** A Kairos fake: settle when the test says the driver went idle. */
  whenIdle(): Promise<void> {
    return this.status === "idle" ? Promise.resolve() : new Promise((resolve) => { this.idleWaiters.push(resolve); });
  }
  /** A Kairos fake: the driver wakes and claims every pending message into one turn. */
  wake(): MessageLike[] {
    const claimed = [...this.inbox.nextStep.splice(0), ...this.inbox.nextTurn.splice(0, 1)];
    const turn = ++this.turn;
    this.emit("turn/start", { turn });
    for (const m of claimed) this.emit("user/message", m);
    return claimed;
  }
  /** A Kairos fake: end the open turn. */
  sleep(): void {
    this.emit("turn/end", { turn: this.turn, reason: { kind: "completed" } });
    this.status = "idle";
    for (const w of this.idleWaiters.splice(0)) w();
  }
}

export class FakeClock {
  private t = 1_000_000;
  private timers: { at: number; fn: () => void; id: number }[] = [];
  private nextId = 1;
  now(): number { return this.t; }
  setTimeout(fn: () => void, ms: number): number {
    const id = this.nextId++;
    this.timers.push({ at: this.t + ms, fn, id });
    return id;
  }
  clearTimeout(handle: unknown): void { this.timers = this.timers.filter((x) => x.id !== handle); }
  /** Let every pending promise continuation run. */
  async flush(): Promise<void> { for (let i = 0; i < 20; i++) await new Promise<void>((r) => setImmediate(r)); }
  /** Advance the clock, firing due timers in order and flushing between them. */
  async advance(ms: number): Promise<void> {
    const until = this.t + ms;
    await this.flush();
    for (;;) {
      const due = this.timers.filter((x) => x.at <= until).sort((a, b) => a.at - b.at)[0];
      if (due === undefined) break;
      this.timers = this.timers.filter((x) => x.id !== due.id);
      this.t = Math.max(this.t, due.at);
      due.fn();
      await this.flush();
    }
    this.t = until;
    await this.flush();
  }
}

export class FakeTree {
  readonly clock = new FakeClock();
  readonly sessions = new Map<string, FakeSession>();
  readonly agents = new Map<string, FakeAgent>();
  readonly scripts = new Map<string, (message: MessageLike, turn: number) => Script>();
  readonly listeners: Listener[] = [];
  readonly agentsCreated: unknown[] = [];
  readonly resumed: unknown[] = [];
  readonly mounts: { agent: string; preset: string }[] = [];
  readonly selections: { agent: string; selection: unknown }[] = [];
  readonly registeredTools: { name: string }[] = [];
  readonly attached: string[] = [];
  readonly persisted: { id: string; cwd?: string; parentSession?: string; agentPreset?: string; origin?: string; createdAt: number }[] = [];
  routes = new Set<string>(["stub/echo", "deepseek-official/deepseek-v4-flash"]);
  brokenPresets = new Set<string>();
  modelsCalls: string[] = [];
  private createdAt = 1;

  emit(session: FakeSession, event: EventLike): void {
    session.events.push(event);
    for (const l of [...this.listeners]) l(session, event);
  }
  script(bot: string, fn: (message: MessageLike, turn: number) => Script): void { this.scripts.set(bot, fn); }
  /** A room: Kairos's live session in a channel. */
  newRoom(id: string, cwd: string): FakeAgent {
    const session = new FakeSession(id, { cwd, agentPreset: "kairos", createdAt: this.createdAt++ });
    session.tree = this;
    const agent = new FakeAgent(this, session);
    this.sessions.set(id, session);
    this.agents.set(id, agent);
    return agent;
  }
  /** A cold member on disk (a header only), for the resume path. */
  persistMember(id: string, room: string, bot: string, cwd: string): void {
    this.persisted.push({ id, cwd, parentSession: room, agentPreset: bot, createdAt: this.createdAt++ });
  }

  readonly ctx = {
    agents: {
      get: (id: string) => this.agents.get(id),
      create: async (opts: { sessionId: string; meta: { cwd: string; parentSession?: string; agentPreset?: string }; agentOptions?: unknown; setup?: (agentCtx: unknown) => Promise<unknown> | unknown }) => {
        if (this.agents.has(opts.sessionId)) throw new Error(`session "${opts.sessionId}" already exists`);
        this.agentsCreated.push(opts);
        const session = new FakeSession(opts.sessionId, { ...opts.meta, createdAt: this.createdAt++ });
        session.tree = this;
        const bot = opts.meta.agentPreset ?? "";
        const agent = new FakeAgent(this, session, this.scripts.get(bot) ?? (() => ({ kind: "answer", text: "(pass)" })));
        await opts.setup?.({ agent });
        this.sessions.set(session.id, session);
        this.agents.set(session.id, agent);
        this.persisted.push({ id: session.id, ...opts.meta, createdAt: session.header.createdAt });
        return { agent, dispose: async () => {} };
      },
      resume: async (opts: { resumeSessionId: string; agentOptions?: unknown; setup?: (agentCtx: unknown) => Promise<unknown> | unknown }) => {
        const header = this.persisted.find((h) => h.id === opts.resumeSessionId);
        if (header === undefined) throw new Error(`session "${opts.resumeSessionId}" not found`);
        if (this.agents.has(opts.resumeSessionId)) throw new Error(`agent "${opts.resumeSessionId}" is already registered`);
        this.resumed.push(opts);
        const session = new FakeSession(header.id, header);
        session.tree = this;
        const agent = new FakeAgent(this, session, this.scripts.get(header.agentPreset ?? "") ?? (() => ({ kind: "answer", text: "(pass)" })));
        await opts.setup?.({ agent });
        this.sessions.set(session.id, session);
        this.agents.set(session.id, agent);
        return { agent, dispose: async () => {} };
      },
    },
    sessions: { get: (id: string) => this.sessions.get(id) },
    sessionPersistence: { list: async () => [...this.persisted] },
    tools: { register: (definition: { name: string }) => { this.registeredTools.push(definition); return () => { this.registeredTools.splice(this.registeredTools.indexOf(definition), 1); }; } },
    sessionProjections: { register: () => () => {} },
    permissionPresets: {
      set: (session: FakeSession, name: string) => { this.emit(session, { type: "permission/preset", seq: session.seq, data: { preset: name } }); },
      current: (events: readonly EventLike[]) => {
        const last = [...events].reverse().find((e) => e.type === "permission/preset");
        return last === undefined ? "workspace-write" : String((last.data as { preset: string }).preset);
      },
    },
    agentPresets: {
      mount: async (agentCtx: { agent: FakeAgent }, id: string) => {
        if (this.brokenPresets.has(id)) throw new Error(`agent preset "${id}" is broken: not a list`);
        this.mounts.push({ agent: agentCtx.agent.id, preset: id });
        return { id };
      },
    },
    agentDefaultModel: { currentSelection: () => ({ provider: "deepseek-official", model: "deepseek-v4-flash" }) },
    llm: { resolveCallConfig: async (config: { provider: string; model: string }) => { if (!this.routes.has(`${config.provider}/${config.model}`)) throw new Error(`no adapter serves ${config.provider}`); return config; } },
    workspaceRegistry: { resolveByPath: async (_path: string) => ({ attachSession: async (id: string) => { this.attached.push(id); } }) },
    apiProxy: { sessions: { models: async (request: { payload: { sessionId: string } }) => { this.modelsCalls.push(request.payload.sessionId); return { ok: true }; } } },
    on: (_name: "session/event", listener: Listener) => { this.listeners.push(listener); return () => { const i = this.listeners.indexOf(listener); if (i >= 0) this.listeners.splice(i, 1); return i >= 0; }; },
    logger: { warn: (_m: string) => {} },
  };
}

export const makeFakeTree = (): FakeTree => new FakeTree();
```

- [ ] **Step 2: Typecheck**

Run: `cd face && npm run typecheck`
Expected: clean (the file is under `tests/`, which tsconfig includes). If `pendingFinish` is flagged "used before declaration", move its declaration above `drive()`.

- [ ] **Step 3: Commit**

```bash
git add face/tests/room-fake.ts
git commit -m "test(face): a fake dsh tree with scriptable agents and a manual clock for the room engine"
```

---

### Task 6: The engine, part 1 — module skeleton, member lifecycle, one driven turn (`face/src/room.ts`)

**Files:**
- Create: `face/src/room.ts`
- Test: `face/tests/room-engine.test.ts`

**Interfaces:**
- Consumes: Task 3's rules, Task 4's `registerRoomProjection`, Task 5's fake, `installModelSelection` from `@deepseek-ai/dsh-agent`, `createUserMessage` from `@deepseek-ai/dsh-llm`, `SESSION_ID_RE` from `sessions.ts`, `DEFAULT_PRESET` from `overlay.ts`.
- Produces (the shapes every later task and plan 3 rely on): `RoomContextLike`, `SessionLike`, `AgentLike`, `RoomChannel { workspaceId; name; dir }`, `RoomDeps`, `RoomClock`, `RoomEngine` with — this task — `constructor(deps)`, `roomOf(agentId, channel)`, `ensureMember(room, bot)`, `runMemberTurn(room, member, roster, trigger, brief?)`, `post(room, message)` (outbox + flush), `whenQuiet(room)`, `dispose()`. The source types are `type` aliases (Task 3 must use `type`, not `interface`, for `RoomAnswerSource`, `RoomRoundEndSource`, `RoomDeltaSource`, `OperatorMentionSource` — an interface is not assignable to `Record<string, unknown>`; fix Task 3 if it used `interface`).

- [ ] **Step 1: Write the failing tests (part 1)**

```ts
// face/tests/room-engine.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { RoomEngine, type RoomDeps } from "../src/room.ts";
import { ROOM_CAPS, type EventLike, type RosterBot } from "../src/room-rules.ts";
import { makeFakeTree, type FakeTree } from "./room-fake.ts";

const CHANNEL = { workspaceId: "ws-1", name: "storage-chain", dir: "/repo/strategies/storage-chain" };
const roster: RosterBot[] = [
  { id: "buffett", name: "巴菲特型", model: "stub/echo" },
  { id: "speculator", name: "投机型" },
  { id: "macro", name: "Macro View" },
];

function engineOn(tree: FakeTree, over: Partial<RoomDeps> = {}): RoomEngine {
  return new RoomEngine({
    ctx: tree.ctx as unknown as RoomDeps["ctx"],
    home: "/nowhere",
    channelFor: async (cwd) => (cwd === CHANNEL.dir ? CHANNEL : null),
    listBots: async () => roster.map((b) => ({ ...b })),
    clock: tree.clock,
    installModelSelection: (agentCtx, ref) => { tree.selections.push({ agent: (agentCtx as { agent: { id: string } }).agent.id, selection: ref.current }); return () => {}; },
    log: () => {},
    ...over,
  });
}
const sources = (events: readonly EventLike[]) => events.filter((e) => e.type === "user/message").map((e) => (e.data as { source: Record<string, unknown> }).source);

test("ensureMember creates a member once: root-created, parented, preset-joined, read-only before publish, attached to the channel, model from preset.yml", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const [a, b] = await Promise.all([engine.ensureMember(room, roster[0]), engine.ensureMember(room, roster[0])]);
  assert.equal(a, b, "concurrent ensures share one creation");
  assert.equal(tree.agentsCreated.length, 1);
  const created = tree.agentsCreated[0] as { sessionId: string; meta: Record<string, unknown>; agentOptions: unknown };
  assert.match(created.sessionId, /^session-[0-9a-f-]{36}$/);
  assert.deepEqual(created.meta, { cwd: CHANNEL.dir, parentSession: "session-room", agentPreset: "buffett" });
  assert.deepEqual(created.agentOptions, { provider: "stub", model: "echo" }, "preset.yml's route, served, is the member's");
  assert.deepEqual(tree.mounts, [{ agent: created.sessionId, preset: "buffett" }]);
  assert.deepEqual(tree.selections[0].selection, { provider: "stub", model: "echo" });
  assert.equal(tree.ctx.permissionPresets.current(a.agent.session.events), "read-only");
  assert.equal(a.agent.session.events[0].type, "permission/preset", "the pin is the session's first fact - inside setup, before publish (a fresh session has no end-seed marker)");
  assert.deepEqual(tree.attached, [created.sessionId]);
});

test("an unserved preset.yml route falls back to the default with a note; no route at all is the default silently", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const odd = await engine.ensureMember(room, { id: "speculator", name: "投机型", model: "nope/x" });
  assert.deepEqual((tree.agentsCreated[0] as { agentOptions: unknown }).agentOptions, { provider: "deepseek-official", model: "deepseek-v4-flash" });
  assert.match(engine.noteFor(room, "speculator") ?? "", /nope\/x is not served/);
  await engine.ensureMember(room, roster[2]);
  assert.equal(engine.noteFor(room, "macro"), undefined);
  assert.ok(odd);
});

test("a member that already exists on disk is RESUMED, never recreated - by the answer in the room log, else by its header", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  tree.persistMember("session-old", "session-room", "buffett", CHANNEL.dir);
  tree.persistMember("session-fork", "session-room", "kairos", CHANNEL.dir); // a fork of the room: kairos preset, never a member
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const m = await engine.ensureMember(room, roster[0]);
  assert.equal(m.agent.id, "session-old");
  assert.equal(tree.agentsCreated.length, 0);
  assert.equal(tree.resumed.length, 1);
  assert.deepEqual(tree.mounts, [{ agent: "session-old", preset: "buffett" }], "a resume joins the preset again in its own setup");
  // a second room-runtime (say, after the engine was rebuilt) finds the same session through the log
  const engine2 = engineOn(tree);
  kairos.session.append("user/message", { id: "a1", role: "user", content: [{ type: "text", text: "view" }], source: { kind: "room", form: "answer", bot: "buffett", name: "巴菲特型", sessionId: "session-old", turn: 1, round: 1 } }, { surfaceOp: "append" });
  const again = await engine2.ensureMember(engine2.roomOf("session-room", CHANNEL), roster[0]);
  assert.equal(again.agent.id, "session-old", "already live: neither created nor resumed");
  assert.equal(tree.resumed.length, 1);
});

test("a member whose preset is gone fails visibly at ensure, with dsh's reason", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  tree.brokenPresets.add("buffett");
  const engine = engineOn(tree);
  await assert.rejects(engine.ensureMember(engine.roomOf("session-room", CHANNEL), roster[0]), /broken: not a list/);
});

test("one driven turn: the member gets the attributed delta with the rules, its final text comes back, and its own log carries the cursor", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  kairos.session.append("user/message", { id: "u1", role: "user", content: [{ type: "text", text: "SanDisk 值得买吗" }], source: { kind: "user" } }, { surfaceOp: "append" });
  tree.script("buffett", (message) => ({ kind: "answer", text: `I read: ${message.content[0].text?.includes("SanDisk 值得买吗") ? "yes" : "no"}. 买` }));
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const member = await engine.ensureMember(room, roster[0]);
  const turn = engine.runMemberTurn(room, member, roster, "dispatch", "state a view");
  await tree.clock.advance(50);
  const result = await turn;
  assert.equal(result.record.state, "answered");
  assert.equal(result.text, "I read: yes. 买");
  assert.equal(result.record.turn, 1);
  const prompt = member.agent.session.events.find((e) => e.type === "user/message")!.data as { content: { text: string }[]; source: Record<string, unknown> };
  assert.match(prompt.content[0].text, /操作员: SanDisk 值得买吗/);
  assert.match(prompt.content[0].text, /Kairos asks this batch: state a view/);
  assert.match(prompt.content[0].text, /exactly \(pass\)/);
  assert.deepEqual(prompt.source, { kind: "room", form: "delta", room: "session-room", bot: "buffett", messageIds: ["u1"], trigger: "dispatch", brief: "state a view" });
  // the cursor: a second turn with nothing new says so
  const second = engine.runMemberTurn(room, member, roster, "mention");
  await tree.clock.advance(50);
  const prompt2 = member.agent.session.events.filter((e) => e.type === "user/message")[1].data as { content: { text: string }[]; source: { messageIds: string[] } };
  assert.match(prompt2.content[0].text, /\(nothing new\)/);
  assert.deepEqual(prompt2.source.messageIds, []);
  await second;
});

test("final-text rule on a tool-using turn; an empty or (pass) text is passed; an error turn is failed and the round goes on", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "after the tool", toolFirst: true }));
  tree.script("speculator", () => ({ kind: "answer", text: "(pass)" }));
  tree.script("macro", () => ({ kind: "error", message: "NO_ADAPTER" }));
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const results = Promise.all(roster.map(async (b) => engine.runMemberTurn(room, await engine.ensureMember(room, b), roster, "dispatch", "q")));
  await tree.clock.advance(50);
  const [a, s, m] = await results;
  assert.equal(a.text, "after the tool");
  assert.equal(s.record.state, "passed");
  assert.equal(m.record.state, "failed");
  assert.match(m.record.reason ?? "", /NO_ADAPTER/);
});

test("deadlines: the base timeout extends while the member runs or has a gate pending, and the hard cap cancels with keepInbox", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "hang" }));
  tree.script("speculator", () => ({ kind: "gate" }));
  tree.script("macro", () => ({ kind: "answer", text: "slow but fine", afterMs: ROOM_CAPS.turnTimeoutMs * 2 + 5 }));
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const hang = engine.runMemberTurn(room, await engine.ensureMember(room, roster[0]), roster, "dispatch", "q");
  const gate = engine.runMemberTurn(room, await engine.ensureMember(room, roster[1]), roster, "dispatch", "q");
  const slow = engine.runMemberTurn(room, await engine.ensureMember(room, roster[2]), roster, "dispatch", "q");
  await tree.clock.advance(ROOM_CAPS.turnTimeoutMs + 10);
  assert.equal(tree.agents.get(tree.agentsCreated.map((c) => (c as { sessionId: string }).sessionId)[0])!.cancelled.length, 0, "still running at the base timeout: extended, not cancelled");
  await tree.clock.advance(ROOM_CAPS.turnTimeoutMs + 10);
  const slowResult = await slow;
  assert.equal(slowResult.record.state, "answered", "a running member that answers inside the hard cap is answered");
  await tree.clock.advance(ROOM_CAPS.turnHardCapMs);
  const [h, g] = await Promise.all([hang, gate]);
  assert.equal(h.record.state, "timed-out");
  assert.equal(g.record.state, "timed-out", "a pending gate extends the base timeout but never the hard cap (R6)");
  for (const id of tree.agentsCreated.slice(0, 2).map((c) => (c as { sessionId: string }).sessionId)) {
    const agent = tree.agents.get(id)!;
    assert.equal(agent.cancelled.length, 1);
    assert.deepEqual(agent.cancelled[0].cause, { kind: "hook", reason: "room: turn hard cap reached" });
    assert.deepEqual(agent.cancelled[0].options, { keepInbox: true });
  }
});

test("post: an answer is appended to the room log at once while no Kairos turn is open, and held until turn/end otherwise", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const msg = (id: string) => ({ id, role: "user" as const, content: [{ type: "text", text: "v" }], source: { kind: "room", form: "answer", bot: "buffett", name: "巴菲特型", sessionId: "s", turn: 1, round: 1 } });
  engine.post(room, msg("a1"));
  assert.deepEqual(sources(kairos.session.events).map((s) => s.form), ["answer"], "quiet room: appended now");
  kairos.wake(); // Kairos opens a turn
  engine.post(room, msg("a2"));
  assert.equal(sources(kairos.session.events).length, 1, "a turn is open: held");
  kairos.sleep();
  await tree.clock.flush();
  assert.equal(sources(kairos.session.events).length, 2, "flushed on turn/end");
  assert.equal(kairos.session.events.at(-1)!.type, "user/message");
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/room-engine.test.ts`
Expected: FAIL — cannot find `../src/room.ts`.

- [ ] **Step 3: Write the module, part 1**

```ts
// face/src/room.ts
/** The room engine: `dispatch`, member sessions, deltas, rounds, continuations,
 * caps, deadlines, the `room` projection and the operator's `@` — spec §4, §5.
 *
 * Installed on the booted ROOT context by main.ts (`installRoom`), the way Gate
 * 2 and the `agent_<bin>` tools are: a root-level `session/event` listener sees
 * every session, a root-created member is a runtime root (so it can ask the
 * operator a question - a runtime-owned child is refused `DELEGATED_CALLER`),
 * and the disposers ride the face's lifetime.
 *
 * HOW A ROOM FACT IS RECORDED (plan 2, deviation 1): only through KNOWN dsh
 * event types. dsh's persistence refuses to reload a log carrying a type
 * outside its generated catalog, so there are no `room/*` events. Membership
 * is the member's own header (`parentSession` + `agentPreset`); the dispatch is
 * the tool's own `tool/call`/`tool/result`; an answer is a `user/message` in
 * Kairos's session with `source.kind === 'room'`; the member's cursor is the
 * delta message in ITS log.
 *
 * HOW AN ANSWER REACHES KAIROS (deviation 2): appended straight onto the room
 * session's log with `surfaceOp: 'append'` - visible at once, seq now, in the
 * next request's history - but ONLY while the room log is quiet (no open turn),
 * because a user message dropped between an assistant tool-call message and
 * its tool result breaks the running request. Otherwise it waits in the room's
 * outbox for the next `turn/end`. Kairos is woken only by the round-end
 * `followup`, issued in the same synchronous block as the last flush.
 *
 * WHAT THIS IS NOT. Dispatch grants nothing: a member's tools are its mask,
 * its writes are its `read-only` sandbox mode (pinned inside creation setup),
 * its orders are Gate 2. The roster it checks is a menu (channels spec §5).
 * @module
 */
import { randomUUID } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";
import { installModelSelection as installDshModelSelection } from "@deepseek-ai/dsh-agent";
import { createUserMessage } from "@deepseek-ai/dsh-llm";
import type { BotRow } from "./bots.ts";
import { isJsonBody, isTrustedDataRequest } from "./data.ts";
import { FORBIDDEN, HttpError, readBody } from "./http.ts";
import { DEFAULT_PRESET } from "./overlay.ts";
import { readRosters } from "./roster.ts";
import { registerRoomProjection } from "./room-projection.ts";
import {
  ROOM_CAPS, dispatchResultText, finalTextOf, formatDelta, isPass, memberPrompt, parseModelRoute,
  resolveMentions, roomLinesOf, roundEndText, validateDispatch,
  type DispatchArgs, type EventLike, type MessageLike, type RoomCaps, type RoomTurnRecord, type RosterBot,
  type RoundOutcome, type TurnTrigger,
} from "./room-rules.ts";
import { SESSION_ID_RE } from "./sessions.ts";
import type { RouteRegistrar } from "./static.ts";

const BIN = "kairos-face";

/* ---------- what the engine reads of the tree, stated structurally ---------- */

/** dsh-session's `Session`, narrowed. `append` is used on the ROOM session only (deviation 2). */
export interface SessionLike {
  readonly id: string;
  readonly header: { readonly cwd?: string; readonly parentSession?: string; readonly agentPreset?: string; readonly origin?: string };
  readonly events: readonly EventLike[];
  readonly seq: number;
  append(type: "user/message", data: MessageLike, opts: { surfaceOp: "append" }): unknown;
}
/** dsh-agent's `Agent`, narrowed. */
export interface AgentLike {
  readonly id: string;
  readonly status: "idle" | "running";
  readonly session: SessionLike;
  followup(message: MessageLike): void;
  cancel(cause: { kind: "hook"; reason: string }, options?: { keepInbox?: boolean }): void;
}
export interface ModelSelectionLike { provider: string; model: string; reasoningEffort?: string }
/** dsh-agent's `ModelSelectionRef`. */
export interface ModelSelectionRefLike { current: ModelSelectionLike | undefined; assembled: ModelSelectionLike | undefined }
/** The unpublished agent scope `setup` receives: `agentCtx.agent` is the agent being composed. */
export interface AgentCtxLike { agent?: AgentLike }
export interface CreateMemberOptions {
  sessionId: string;
  meta: { cwd: string; parentSession: string; agentPreset: string };
  agentOptions: { provider: string; model: string };
  setup(agentCtx: AgentCtxLike): Promise<void>;
}
export interface ResumeMemberOptions { resumeSessionId: string; agentOptions: { provider: string; model: string }; setup(agentCtx: AgentCtxLike): Promise<void> }
export interface PersistedHeaderLike { id: string; cwd?: string; parentSession?: string; agentPreset?: string; origin?: string; createdAt: number }
/** dsh-tools' `ToolRunContext`, narrowed: the calling agent and Kairos's TURN signal (which the round must not run on). */
export interface RoomToolExec { agent?: AgentLike; signal: AbortSignal }
/** dsh-tools' `ToolDefinition`, stated the way agents.ts states it. */
export interface RoomToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  output: { schema: Record<string, unknown>; render(args: unknown, value: unknown): { type: "text"; text: string }[] };
  timeoutMs: number;
  execute(args: unknown, exec: RoomToolExec): Promise<unknown>;
  presentCall(args: unknown): { card: "generic"; title: string; kind: "read"; rawInput?: unknown };
}
export interface RoomContextLike {
  agents: {
    get(id: string): AgentLike | undefined;
    create(options: CreateMemberOptions): Promise<{ agent: AgentLike }>;
    resume(options: ResumeMemberOptions): Promise<{ agent: AgentLike }>;
  };
  sessions: { get(id: string): SessionLike | undefined };
  sessionPersistence?: { list(): Promise<PersistedHeaderLike[]> };
  tools: { register(definition: RoomToolDefinition): () => void };
  sessionProjections?: { register(definition: never): () => void };
  permissionPresets: { set(session: SessionLike, name: string): void; current(events: readonly EventLike[]): string };
  agentPresets: { mount(agentCtx: AgentCtxLike, id: string): Promise<unknown> };
  agentDefaultModel: { currentSelection(): ModelSelectionLike };
  llm: { resolveCallConfig(config: { provider: string; model: string }): Promise<unknown> };
  workspaceRegistry: { resolveByPath(path: string): Promise<{ attachSession(id: string): Promise<void> } | undefined> };
  /** The gateway; `sessions.models` resumes a cold session through the gateway's OWN composition (see `ensureLive`). */
  apiProxy?: { sessions: { models(request: { rpcId: string; payload: { sessionId: string } }): Promise<unknown> } };
  on(name: "session/event", listener: (session: SessionLike, event: EventLike) => void): () => boolean;
  logger?: { warn(message: string): void };
}

/* ---------- the engine's own seams ---------- */

export interface RoomChannel { workspaceId: string; name: string; dir: string }
export interface RoomClock { now(): number; setTimeout(fn: () => void, ms: number): unknown; clearTimeout(handle: unknown): void }
export interface RoomDeps {
  ctx: RoomContextLike;
  /** The harness home holding `face/channels.json`. */
  home: string;
  /** Which channel a session's directory belongs to (panels.ts `channelFor`, with `dir`). */
  channelFor(cwd: string | undefined): Promise<RoomChannel | null>;
  /** `listBots(botsRoot, presets.list)` from bots.ts, narrowed. */
  listBots(): Promise<Pick<BotRow, "id" | "name" | "model" | "broken">[]>;
  caps?: Partial<RoomCaps>;
  clock?: RoomClock;
  /** dsh-agent's `installModelSelection`; injected so the fake tree can record it. */
  installModelSelection?: (agentCtx: AgentCtxLike, ref: ModelSelectionRefLike) => () => void;
  log?: (line: string) => void;
}

export interface Member { bot: string; name: string; agent: AgentLike; queue: Promise<unknown> }
export interface MemberTurnResult { record: RoomTurnRecord; text: string }
export interface Round {
  n: number;
  mode: "parallel" | "serial" | "mention";
  superseded: boolean;
  capped: boolean;
  continuations: string[];
  continuationsRun: number;
  turns: RoomTurnRecord[];
}
export interface Room {
  id: string;
  channel: RoomChannel;
  members: Map<string, Member>;
  ensuring: Map<string, Promise<Member>>;
  selections: Map<string, { selection: ModelSelectionLike; note?: string }>;
  /** Messages for the room log, waiting for a quiet log (deviation 2). */
  outbox: MessageLike[];
  roundsThisSend: number;
  turnsThisSend: number;
  active?: Round;
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err));
const defaultClock: RoomClock = { now: () => Date.now(), setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: (h) => clearTimeout(h as NodeJS.Timeout) };

/** No open turn on this log: the last `turn/start` has its `turn/end`. */
export function isQuiet(session: SessionLike): boolean {
  const events = session.events;
  for (let i = events.length - 1; i >= 0; i--) {
    const type = events[i].type;
    if (type === "turn/end") return true;
    if (type === "turn/start") return false;
  }
  return true;
}

/** The turn's open gate, read from ITS log (deviation 8): an `ask_user_question` call with no result yet, or an approval asked and not decided. */
export function gatePending(events: readonly EventLike[], turn: number): boolean {
  const openAsks = new Set<string>();
  const openApprovals = new Set<string>();
  for (const event of events) {
    const data = event.data as Record<string, unknown> | undefined;
    if (data === undefined) continue;
    if (event.type === "tool/call" && data.turn === turn && data.name === "ask_user_question" && typeof data.callId === "string") openAsks.add(data.callId);
    else if (event.type === "tool/result" && data.turn === turn) {
      const block = (data.message as { content?: { toolCallId?: unknown }[] } | undefined)?.content?.[0];
      if (typeof block?.toolCallId === "string") openAsks.delete(block.toolCallId);
    } else if (event.type === "approval/asked" && typeof data.id === "string") openApprovals.add(data.id);
    else if (event.type === "approval/decided" && typeof data.id === "string") openApprovals.delete(data.id);
  }
  return openAsks.size > 0 || openApprovals.size > 0;
}

/** Message ids a member has already been shown, from the delta prompts in its own log (its durable cursor). */
export function seenIdsOf(events: readonly EventLike[]): Set<string> {
  const seen = new Set<string>();
  for (const event of events) {
    if (event.type !== "user/message") continue;
    const source = (event.data as MessageLike | undefined)?.source as { kind?: unknown; form?: unknown; messageIds?: unknown } | undefined;
    if (source?.kind === "room" && source.form === "delta" && Array.isArray(source.messageIds)) {
      for (const id of source.messageIds) if (typeof id === "string") seen.add(id);
    }
  }
  return seen;
}

export class RoomEngine {
  private readonly rooms = new Map<string, Room>();
  /** member session id → the listener of the turn being driven on it (one at a time per member). */
  private readonly turnWaiters = new Map<string, (event: EventLike) => void>();
  private readonly quietWaiters = new Map<string, Array<() => void>>();
  private readonly disposers: Array<() => void> = [];
  readonly caps: RoomCaps;
  private readonly clock: RoomClock;
  private readonly installSelection: NonNullable<RoomDeps["installModelSelection"]>;
  private readonly log: (line: string) => void;

  constructor(private readonly deps: RoomDeps) {
    this.caps = { ...ROOM_CAPS, ...deps.caps };
    this.clock = deps.clock ?? defaultClock;
    this.installSelection = deps.installModelSelection ?? ((agentCtx, ref) => installDshModelSelection(agentCtx as never, ref as never));
    this.log = deps.log ?? ((line) => console.log(`${BIN}: ${line}`));
    const off = deps.ctx.on("session/event", (session, event) => this.onEvent(session, event));
    this.disposers.push(() => { off(); });
  }

  dispose(): void {
    for (const d of this.disposers.splice(0)) d();
  }

  /** The runtime for a room session; created on first sight. */
  roomOf(agentId: string, channel: RoomChannel): Room {
    let room = this.rooms.get(agentId);
    if (room === undefined) {
      room = { id: agentId, channel, members: new Map(), ensuring: new Map(), selections: new Map(), outbox: [], roundsThisSend: 0, turnsThisSend: 0 };
      this.rooms.set(agentId, room);
    }
    return room;
  }

  /** The model-fallback note for a bot in this room, if its route was not served. */
  noteFor(room: Room, bot: string): string | undefined { return room.selections.get(bot)?.note; }

  /* ---------- the event bus ---------- */

  private onEvent(session: SessionLike, event: EventLike): void {
    this.turnWaiters.get(session.id)?.(event);
    const room = this.rooms.get(session.id);
    if (room === undefined) return;
    /* Everything below runs in a later tick: `Session.append` rejects reentrancy,
     * and these reactions append to the very session that just emitted. */
    if (event.type === "turn/end") {
      const waiters = this.quietWaiters.get(room.id);
      this.quietWaiters.delete(room.id);
      queueMicrotask(() => {
        this.flush(room);
        for (const w of waiters ?? []) w();
      });
    } else if (event.type === "user/message") {
      const source = (event.data as MessageLike | undefined)?.source;
      if (source?.kind === "user") queueMicrotask(() => this.onOperatorSend(room));
    }
  }

  /** Spec §4.4: every operator send resets the caps; a running round is superseded (its running turns finish). */
  private onOperatorSend(room: Room): void {
    room.roundsThisSend = 0;
    room.turnsThisSend = 0;
    if (room.active !== undefined) room.active.superseded = true;
  }

  /* ---------- the room log (deviation 2) ---------- */

  /** Queue a message for the room log and append it now if the log is quiet. */
  post(room: Room, message: MessageLike): void {
    room.outbox.push(message);
    this.flush(room);
  }

  private flush(room: Room): void {
    if (room.outbox.length === 0) return;
    const session = this.deps.ctx.sessions.get(room.id);
    if (session === undefined || !isQuiet(session)) return;
    for (const message of room.outbox.splice(0)) session.append("user/message", message, { surfaceOp: "append" });
  }

  /** Resolves once the room log has no open turn (immediately when it already has none). */
  whenQuiet(room: Room): Promise<void> {
    const session = this.deps.ctx.sessions.get(room.id);
    if (session !== undefined && isQuiet(session)) return Promise.resolve();
    return new Promise((resolve) => {
      const list = this.quietWaiters.get(room.id) ?? [];
      list.push(() => { void this.whenQuiet(room).then(resolve); });
      this.quietWaiters.set(room.id, list);
    });
  }

  private roomAgent(room: Room): AgentLike {
    const agent = this.deps.ctx.agents.get(room.id);
    if (agent === undefined) throw new Error(`room session ${room.id} is not live`);
    return agent;
  }

  /* ---------- members (spec §2.4, §4.1, §4.7) ---------- */

  async ensureMember(room: Room, bot: RosterBot): Promise<Member> {
    const have = room.members.get(bot.id);
    if (have !== undefined) return have;
    let pending = room.ensuring.get(bot.id);
    if (pending === undefined) {
      pending = this.materializeMember(room, bot).finally(() => room.ensuring.delete(bot.id));
      room.ensuring.set(bot.id, pending);
    }
    return pending;
  }

  /** preset.yml's route when the tree serves it, else the default with a visible note. Cached per room. */
  private async selectionFor(room: Room, bot: RosterBot): Promise<ModelSelectionLike> {
    const cached = room.selections.get(bot.id);
    if (cached !== undefined) return cached.selection;
    const fallback = this.deps.ctx.agentDefaultModel.currentSelection();
    let entry: { selection: ModelSelectionLike; note?: string } = { selection: { provider: fallback.provider, model: fallback.model } };
    if (bot.model !== undefined) {
      const route = parseModelRoute(bot.model);
      if (route === undefined) entry = { ...entry, note: `${bot.name}: preset.yml model "${bot.model}" is not one provider/model route; using the default route.` };
      else {
        try {
          await this.deps.ctx.llm.resolveCallConfig(route);
          entry = { selection: route };
        } catch {
          entry = { ...entry, note: `${bot.name}: model ${bot.model} is not served by this tree; using the default route.` };
        }
      }
    }
    room.selections.set(bot.id, entry);
    if (entry.note !== undefined) this.log(entry.note);
    return entry.selection;
  }

  /** The member's session on disk or in the room log, if it exists. */
  private async findMemberSession(room: Room, bot: string): Promise<string | undefined> {
    const live = this.deps.ctx.sessions.get(room.id);
    for (const event of live?.events ?? []) {
      if (event.type !== "user/message") continue;
      const source = (event.data as MessageLike | undefined)?.source as { kind?: unknown; bot?: unknown; sessionId?: unknown } | undefined;
      if (source?.kind === "room" && source.bot === bot && typeof source.sessionId === "string" && source.sessionId !== "") return source.sessionId;
    }
    const headers = await this.deps.ctx.sessionPersistence?.list() ?? [];
    const mine = headers
      .filter((h) => h.parentSession === room.id && h.agentPreset === bot && h.origin === undefined)
      .sort((a, b) => b.createdAt - a.createdAt);
    return mine[0]?.id;
  }

  private async materializeMember(room: Room, bot: RosterBot): Promise<Member> {
    const selection = await this.selectionFor(room, bot);
    const agentOptions = { provider: selection.provider, model: selection.model };
    const existing = await this.findMemberSession(room, bot.id);
    /* The gateway's own composeAgent, restated: the model selection ref, then the
     * preset join. Plus, for a NEW member, the read-only pin — INSIDE setup so it
     * is the session's first permission fact and no create→set window exists. */
    const setup = async (agentCtx: AgentCtxLike, pin: boolean): Promise<void> => {
      this.installSelection(agentCtx, { current: { ...selection }, assembled: undefined });
      await this.deps.ctx.agentPresets.mount(agentCtx, bot.id);
      if (pin) {
        const session = agentCtx.agent?.session;
        if (session === undefined) throw new Error("member setup has no scoped agent");
        this.deps.ctx.permissionPresets.set(session, "read-only");
      }
    };
    let agent: AgentLike;
    if (existing !== undefined) {
      agent = this.deps.ctx.agents.get(existing)
        ?? (await this.deps.ctx.agents.resume({ resumeSessionId: existing, agentOptions, setup: (agentCtx) => setup(agentCtx, false) })).agent;
    } else {
      const sessionId = `session-${randomUUID()}`;
      agent = (await this.deps.ctx.agents.create({
        sessionId,
        meta: { cwd: room.channel.dir, parentSession: room.id, agentPreset: bot.id },
        agentOptions,
        setup: (agentCtx) => setup(agentCtx, true),
      })).agent;
      const effective = this.deps.ctx.permissionPresets.current(agent.session.events);
      if (effective !== "read-only") throw new Error(`member session ${sessionId} for ${bot.id} is "${effective}", not read-only; refusing to prompt it`);
      const ws = await this.deps.ctx.workspaceRegistry.resolveByPath(room.channel.dir).catch(() => undefined);
      await ws?.attachSession(sessionId).catch((err: unknown) => this.log(`could not attach ${sessionId} to channel ${room.channel.name}: ${errText(err)}`));
    }
    const member: Member = { bot: bot.id, name: bot.name, agent, queue: Promise.resolve() };
    room.members.set(bot.id, member);
    return member;
  }

  /* ---------- one member turn (spec §4.2, §4.6) ---------- */

  /** Run `fn` after whatever this member is already doing (an `@` to a running member is queued, never refused). */
  enqueue<T>(member: Member, fn: () => Promise<T>): Promise<T> {
    const next = member.queue.then(fn, fn);
    member.queue = next.then(() => undefined, () => undefined);
    return next;
  }

  /** The delta this member has not seen: room lines (log + outbox) minus its cursor. */
  private deltaFor(room: Room, roster: readonly RosterBot[], member: Member): { text: string; messageIds: string[] } {
    const roomSession = this.deps.ctx.sessions.get(room.id);
    const lines = roomLinesOf(roomSession?.events ?? [], room.outbox, roster);
    const seen = seenIdsOf(member.agent.session.events);
    const fresh = lines.filter((line) => !seen.has(line.id));
    return { text: formatDelta(fresh, member.bot), messageIds: fresh.map((line) => line.id) };
  }

  async runMemberTurn(room: Room, member: Member, roster: readonly RosterBot[], trigger: TurnTrigger, brief?: string): Promise<MemberTurnResult> {
    const delta = this.deltaFor(room, roster, member);
    const text = memberPrompt({ roomName: room.channel.name, roster, self: member.bot, delta: delta.text, trigger, ...(brief === undefined ? {} : { brief }) });
    const message = createUserMessage({
      content: [{ type: "text", text }],
      source: { kind: "room", form: "delta", room: room.id, bot: member.bot, messageIds: delta.messageIds, trigger, ...(brief === undefined ? {} : { brief }) },
    });
    const outcome = await this.driveTurn(member, () => member.agent.followup(message as unknown as MessageLike));
    const base = { bot: member.bot, name: member.name, sessionId: member.agent.id };
    if (outcome.kind === "ended") {
      const reason = outcome.reason;
      if (reason.kind === "error") return { record: { ...base, turn: outcome.turn, state: "failed", reason: errorText(reason.error) }, text: "" };
      if (reason.kind === "aborted") return { record: { ...base, turn: outcome.turn, state: outcome.cancelledByUs ? "timed-out" : "failed", reason: outcome.cancelledByUs ? "turn hard cap" : "cancelled" }, text: "" };
      if (reason.kind === "interrupted") return { record: { ...base, turn: outcome.turn, state: "failed", reason: "interrupted" }, text: "" };
      const answer = finalTextOf(member.agent.session.events, outcome.turn);
      if (answer === "" || isPass(answer)) return { record: { ...base, turn: outcome.turn, state: "passed" }, text: "" };
      return { record: { ...base, turn: outcome.turn, state: "answered" }, text: answer };
    }
    return { record: { ...base, state: "failed", reason: outcome.reason }, text: "" };
  }

  /**
   * Start a turn on a member and wait for ITS `turn/end`. The turn is the first
   * `turn/start` after the send (members are single-driven through `enqueue`).
   * Deadline: the base timeout, extended while the member runs or has a gate
   * pending, up to the hard cap, which cancels (keeping the inbox).
   */
  private driveTurn(member: Member, start: () => void): Promise<
    { kind: "ended"; turn: number; reason: { kind: string; error?: unknown }; cancelledByUs: boolean } | { kind: "never-started"; reason: string }
  > {
    const session = member.agent.session;
    const sinceSeq = session.seq;
    const startedAt = this.clock.now();
    return new Promise((resolve) => {
      let turn: number | undefined;
      let timer: unknown;
      let cancelledByUs = false;
      let settled = false;
      const finish = (value: Parameters<typeof resolve>[0]): void => {
        if (settled) return;
        settled = true;
        this.clock.clearTimeout(timer);
        this.turnWaiters.delete(session.id);
        resolve(value);
      };
      const arm = (ms: number): void => {
        this.clock.clearTimeout(timer);
        timer = this.clock.setTimeout(check, ms);
      };
      const check = (): void => {
        const elapsed = this.clock.now() - startedAt;
        const running = member.agent.status === "running" || (turn !== undefined && gatePending(session.events, turn));
        if (elapsed < this.caps.turnHardCapMs && running) {
          arm(Math.min(this.caps.turnTimeoutMs, this.caps.turnHardCapMs - elapsed));
          return;
        }
        cancelledByUs = true;
        member.agent.cancel({ kind: "hook", reason: "room: turn hard cap reached" }, { keepInbox: true });
        /* The loop answers a cancel with `turn/end aborted`; if it does not, do not wait forever. */
        arm(5_000);
        if (turn === undefined) finish({ kind: "never-started", reason: "no turn opened before the deadline" });
        else if (elapsed >= this.caps.turnHardCapMs + 5_000) finish({ kind: "ended", turn, reason: { kind: "aborted" }, cancelledByUs: true });
      };
      this.turnWaiters.set(session.id, (event) => {
        if (event.seq < sinceSeq) return;
        const data = event.data as { turn?: number; reason?: { kind: string; error?: unknown } } | undefined;
        if (turn === undefined && event.type === "turn/start" && typeof data?.turn === "number") turn = data.turn;
        else if (event.type === "turn/end" && turn !== undefined && data?.turn === turn) {
          finish({ kind: "ended", turn, reason: data.reason ?? { kind: "completed" }, cancelledByUs });
        }
      });
      arm(this.caps.turnTimeoutMs);
      try {
        start();
      } catch (err) {
        finish({ kind: "never-started", reason: errText(err) });
      }
    });
  }
}

const errorText = (error: unknown): string => {
  const e = error as { code?: unknown; message?: unknown } | undefined;
  const code = typeof e?.code === "string" ? e.code : undefined;
  const message = typeof e?.message === "string" ? e.message : "";
  return code === undefined ? (message || "error") : (message === "" ? code : `${code}: ${message}`);
};
```

- [ ] **Step 4: Run the tests and typecheck**

Run: `cd face && npx tsx --test tests/room-engine.test.ts && npm run typecheck`
Expected: PASS, clean. Two things to watch: the deadline test's arithmetic assumes the fake clock fires the base-timeout check at exactly `turnTimeoutMs` — the `hang` member is `running`, so the first check extends; the `gate` member's script emits an `ask_user_question` `tool/call`, so `gatePending` is true and it also extends; only after `turnHardCapMs` does `check` cancel. If `gatePending` is never consulted because `status` is already `running` in the fake, add a fake script variant where `status` flips to `idle` but the ask stays open — or accept that the fake keeps `running` and assert `gatePending` separately in a unit test below.

- [ ] **Step 5: Add the two pure-helper tests to the same file**

```ts
test("gatePending reads an open ask or an undecided approval from the member's own log; isQuiet reads the last turn boundary", () => {
  const events: EventLike[] = [
    { type: "turn/start", seq: 0, data: { turn: 1 } },
    { type: "tool/call", seq: 1, data: { turn: 1, step: 1, callId: "q1", name: "ask_user_question", arguments: "{}" } },
  ];
  assert.equal(gatePending(events, 1), true);
  assert.equal(gatePending(events, 2), false);
  events.push({ type: "tool/result", seq: 2, data: { turn: 1, step: 1, message: { id: "r", role: "user", content: [{ type: "tool-result", toolCallId: "q1", content: [] }], source: { kind: "tool", callId: "q1" } } } });
  assert.equal(gatePending(events, 1), false);
  events.push({ type: "approval/asked", seq: 3, data: { id: "ap1", toolName: "bash" } });
  assert.equal(gatePending(events, 1), true);
  events.push({ type: "approval/decided", seq: 4, data: { id: "ap1", outcome: "rejected" } });
  assert.equal(gatePending(events, 1), false);
  const session = { id: "s", header: {}, events, seq: events.length, append: () => undefined };
  assert.equal(isQuiet(session), false, "turn 1 is still open");
  events.push({ type: "turn/end", seq: 5, data: { turn: 1, reason: { kind: "completed" } } });
  assert.equal(isQuiet(session), true);
  assert.equal(isQuiet({ ...session, events: [] }), true, "an empty log is quiet");
});
```

Import `gatePending, isQuiet` from `../src/room.ts`. Run the file again; expected PASS.

- [ ] **Step 6: Commit**

```bash
git add face/src/room.ts face/tests/room-engine.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): the room engine, part 1 - members created from the root context with parentSession, the preset join and the read-only pin inside setup, resumed never recreated; one driven turn with the attributed delta, the final-text rule and the extending deadline; answers appended to a quiet room log
```

---

### Task 7: The engine, part 2 — rounds, continuations, caps, supersession, the operator's `@`

**Files:**
- Modify: `face/src/room.ts`
- Test: `face/tests/room-engine.test.ts`

**Interfaces:**
- Consumes: part 1.
- Produces: `RoomEngine.dispatch(agentId, channel, args, roster): Promise<DispatchOutcome>` (`{ round, remainingRounds, notCalled: string[], notes: string[] }`, throws `Error` with the model-facing message on a refusal), `RoomEngine.runRound(...)` (internal), `RoomEngine.say(sessionId, text): Promise<{ addressed: string[] }>`, `RoomEngine.rosterFor(channel): Promise<RosterBot[]>`, `RoomEngine.describe(sessionId)`.

- [ ] **Step 1: Write the failing tests (part 2)**

Append to `face/tests/room-engine.test.ts`:

```ts
const answers = (events: readonly EventLike[]) => sources(events).filter((s) => s.kind === "room" && s.form === "answer").map((s) => s.bot);
const roundEnds = (events: readonly EventLike[]) => sources(events).filter((s) => s.kind === "room" && s.form === "round-end");

test("a parallel round: every member gets the same delta and sees no peer this round; answers land in the room log; Kairos is woken once with who spoke and who passed", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  kairos.session.append("user/message", { id: "u1", role: "user", content: [{ type: "text", text: "开会" }], source: { kind: "user" } }, { surfaceOp: "append" });
  const prompts: Record<string, string> = {};
  tree.script("buffett", (m) => { prompts.buffett = m.content[0].text ?? ""; return { kind: "answer", text: "买", afterMs: 20 }; });
  tree.script("speculator", (m) => { prompts.speculator = m.content[0].text ?? ""; return { kind: "answer", text: "(pass)", afterMs: 5 }; });
  const engine = engineOn(tree);
  const out = await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "parallel", brief: "各说各的", reason: "first views" }, roster);
  assert.deepEqual(out, { round: 1, remainingRounds: 2, notCalled: ["macro"], notes: [] });
  await tree.clock.advance(100);
  assert.doesNotMatch(prompts.buffett, /投机型/, "parallel: no peer answer this round");
  assert.doesNotMatch(prompts.speculator, /巴菲特型:/);
  assert.deepEqual(answers(kairos.session.events), ["buffett"], "a pass is not an answer");
  assert.equal(kairos.inbox.nextTurn.length, 1, "woken exactly once");
  const end = kairos.inbox.nextTurn[0];
  assert.deepEqual(end.source.form, "round-end");
  assert.equal((end.source as { outcome: string }).outcome, "settled");
  assert.deepEqual((end.source as { turns: { bot: string; state: string }[] }).turns.map((t) => `${t.bot}:${t.state}`), ["speculator:passed", "buffett:answered"]);
  assert.match(end.content[0].text ?? "", /Answered: 巴菲特型\. Passed: 投机型\./);
  assert.ok(kairos.session.events.findIndex((e) => (e.data as { source?: { form?: string } })?.source?.form === "answer") >= 0, "the answer is in the log BEFORE the wake is queued");
});

test("a serial round: the later member's delta carries the earlier answer", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  const prompts: Record<string, string> = {};
  tree.script("buffett", () => ({ kind: "answer", text: "买" }));
  tree.script("speculator", (m) => { prompts.speculator = m.content[0].text ?? ""; return { kind: "answer", text: "卖" }; });
  const engine = engineOn(tree);
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "serial", brief: "q", reason: "r" }, roster);
  await tree.clock.advance(100);
  assert.match(prompts.speculator, /巴菲特型: 买/);
});

test("a peer @ queues one continuation after the dispatched turns, bounded, and Kairos is woken after it", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  let macroTurns = 0;
  tree.script("buffett", () => ({ kind: "answer", text: "@macro 你怎么看 @macro 再说一次" }));
  tree.script("speculator", () => ({ kind: "answer", text: "@macro @buffett @speculator" }));
  tree.script("macro", (m, turn) => { macroTurns = turn; return { kind: "answer", text: `macro turn ${turn}: ${m.content[0].text?.includes("continuation") ? "cont" : "plain"}` }; });
  const engine = engineOn(tree);
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" }, roster);
  await tree.clock.advance(200);
  assert.equal(macroTurns, 1, "one continuation for macro however many peers named it");
  assert.deepEqual(answers(kairos.session.events).sort(), ["buffett", "macro", "speculator"]);
  const end = kairos.inbox.nextTurn[0];
  assert.equal((end.source as { turns: unknown[] }).turns.length, 3);
  assert.ok(kairos.session.events.filter((e) => (e.data as { source?: { form?: string } })?.source?.form === "answer").length === 3, "all three answers precede the wake");
});

test("caps: the round cap refuses a fourth dispatch; the bot-message cap ends a round capped; a new operator send resets both", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  for (const b of roster) tree.script(b.id, () => ({ kind: "answer", text: "v" }));
  const engine = engineOn(tree, { caps: { maxBotMessages: 4, maxRounds: 2 } });
  const args = { to: ["buffett", "speculator", "macro"], mode: "parallel" as const, brief: "q", reason: "r" };
  await engine.dispatch("session-room", CHANNEL, args, roster);
  await tree.clock.advance(100);
  await engine.dispatch("session-room", CHANNEL, args, roster);
  await tree.clock.advance(100);
  const ends = roundEnds(kairos.session.events.concat(kairos.inbox.nextTurn.map((m, i) => ({ type: "user/message", seq: 1000 + i, data: m }))));
  assert.deepEqual(ends.map((e) => e.outcome), ["settled", "capped"], "round 2 ran one turn of three before the message cap");
  await assert.rejects(engine.dispatch("session-room", CHANNEL, args, roster), /round cap/);
  // the operator speaks: the gateway logs a user message on the room
  kairos.session.append("user/message", { id: "u2", role: "user", content: [{ type: "text", text: "再来" }], source: { kind: "user" } }, { surfaceOp: "append" });
  await tree.clock.flush();
  const out = await engine.dispatch("session-room", CHANNEL, args, roster);
  assert.equal(out.round, 1);
});

test("a dispatch while a round is running is refused; an operator message mid-round supersedes it - running turns finish, nothing further starts", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "slow", afterMs: 50 }));
  tree.script("speculator", () => ({ kind: "answer", text: "@macro", afterMs: 10 }));
  tree.script("macro", () => ({ kind: "answer", text: "never" }));
  const engine = engineOn(tree);
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" }, roster);
  await assert.rejects(engine.dispatch("session-room", CHANNEL, { to: ["macro"], mode: "parallel", brief: "q", reason: "r" }, roster), /still running|not settled/);
  await tree.clock.advance(20);
  kairos.session.append("user/message", { id: "u2", role: "user", content: [{ type: "text", text: "换个话题" }], source: { kind: "user" } }, { surfaceOp: "append" });
  await tree.clock.advance(200);
  assert.deepEqual(answers(kairos.session.events).sort(), ["buffett", "speculator"], "the running turn finished and landed; the continuation never started");
  const end = kairos.inbox.nextTurn[0];
  assert.equal((end.source as { outcome: string }).outcome, "superseded");
});

test("say: an @ is the operator's message, appended to the room, not a prompt; the named members turn; an @ to a running member is queued", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  const turns: string[] = [];
  tree.script("buffett", (m, turn) => { turns.push(`buffett:${turn}`); return { kind: "answer", text: "b", afterMs: 30 }; });
  tree.script("speculator", (m, turn) => { turns.push(`speculator:${turn}`); return { kind: "answer", text: "s" }; });
  const engine = engineOn(tree);
  engine.rosterFor = async () => roster; // the roster read is the file's; stub it here
  const first = await engine.say("session-room", "@buffett @speculator 你们怎么看");
  assert.deepEqual(first.addressed, ["buffett", "speculator"]);
  assert.deepEqual(sources(kairos.session.events).at(-1), { kind: "user", mention: ["buffett", "speculator"] }, "in the room log as the operator's, with whom it addressed");
  assert.equal(kairos.inbox.nextTurn.length, 0, "Kairos is not prompted");
  const second = await engine.say("session-room", "@buffett 补一句");
  assert.deepEqual(second.addressed, ["buffett"]);
  await tree.clock.advance(100);
  assert.deepEqual(turns, ["buffett:1", "speculator:1", "buffett:2"], "the second @ ran after the first turn, never refused");
  assert.deepEqual(answers(kairos.session.events), ["speculator", "buffett", "buffett"]);
  assert.equal(kairos.inbox.nextTurn.length, 0, "no round-end for @ turns");
  const none = await engine.say("session-room", "no mention at all");
  assert.deepEqual(none, { addressed: [] });
  assert.equal(tree.modelsCalls.length, 0, "a live room needs no resume");
});

test("say on a cold room resumes it through the gateway's own composition before touching it", async () => {
  const tree = makeFakeTree();
  const engine = engineOn(tree);
  engine.rosterFor = async () => roster;
  tree.persisted.push({ id: "session-cold", cwd: CHANNEL.dir, agentPreset: "kairos", createdAt: 1 });
  tree.ctx.apiProxy.sessions.models = async (request: { payload: { sessionId: string } }) => { tree.modelsCalls.push(request.payload.sessionId); tree.newRoom(request.payload.sessionId, CHANNEL.dir); return { ok: true }; };
  tree.script("buffett", () => ({ kind: "answer", text: "b" }));
  const out = await engine.say("session-cold", "@buffett hi");
  assert.deepEqual(out.addressed, ["buffett"]);
  assert.deepEqual(tree.modelsCalls, ["session-cold"]);
});

test("describe reports the roster, the runtime members and the caps left", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "b" }));
  const engine = engineOn(tree);
  engine.rosterFor = async () => roster;
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, roster);
  await tree.clock.advance(50);
  const d = await engine.describe("session-room");
  assert.deepEqual(d.roster.map((b) => b.id), ["buffett", "speculator", "macro"]);
  assert.equal(Object.keys(d.members).length, 1);
  assert.match(d.members.buffett.sessionId, /^session-/);
  assert.deepEqual(d.caps, { roundsLeft: 2, messagesLeft: 9, maxRounds: 3, maxBotMessages: 10 });
});
```

(In the `say` tests, `engine.rosterFor = async () => roster` overrides the file-backed read; `rosterFor` is a public method for exactly this reason, and Task 8's tool tests use the real one against a temp home.)

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd face && npx tsx --test tests/room-engine.test.ts`
Expected: FAIL — `dispatch` is not a function.

- [ ] **Step 3: Add part 2 to `face/src/room.ts`**

Add inside `RoomEngine` (after `runMemberTurn`):

```ts
  /* ---------- rounds (spec §4.3, §4.4, §4.6) ---------- */

  /** The channel's bot roster, named: the file's ids with the display names dsh's roster reports. */
  async rosterFor(channel: RoomChannel): Promise<RosterBot[]> {
    const { rosters, corrupt } = await readRosters(this.deps.home);
    if (corrupt) throw new Error(`the channel roster is unreadable; repair ${this.deps.home}/face/channels.json`);
    if (!Object.hasOwn(rosters, channel.workspaceId)) throw new Error(`channel "${channel.name}" has no roster yet; it gets one the first time the channel list loads, and the operator checks bots in on the channel page`);
    const bots = await this.deps.listBots();
    return rosters[channel.workspaceId].bots.map((id) => {
      const row = bots.find((b) => b.id === id);
      return { id, name: row?.name ?? id, ...(row?.model === undefined ? {} : { model: row.model }), ...(row?.broken === undefined ? {} : { broken: row.broken }) };
    });
  }

  /**
   * Start a round for Kairos and return at once (the tool result tells the model
   * to end its turn). Refuses on the round cap and while a round is unsettled.
   */
  async dispatch(agentId: string, channel: RoomChannel, args: DispatchArgs, roster: readonly RosterBot[]): Promise<{ round: number; remainingRounds: number; notCalled: string[]; notes: string[] }> {
    const room = this.roomOf(agentId, channel);
    if (room.active !== undefined && !room.active.superseded) {
      throw new Error(`round ${room.active.n} is still running (${room.active.turns.length} of its turns have ended); end your turn and dispatch again when you are woken`);
    }
    if (room.roundsThisSend >= this.caps.maxRounds) {
      throw new Error(`the round cap (${this.caps.maxRounds} per operator message) is reached; reply to the operator now`);
    }
    room.roundsThisSend++;
    const round: Round = { n: room.roundsThisSend, mode: args.mode, superseded: false, capped: false, continuations: [], continuationsRun: 0, turns: [] };
    room.active = round;
    const notes: string[] = [];
    for (const id of args.to) {
      const bot = roster.find((b) => b.id === id);
      if (bot === undefined) continue;
      await this.selectionFor(room, bot);
      const note = this.noteFor(room, id);
      if (note !== undefined) notes.push(note);
    }
    void this.runRound(room, round, args.to, roster, "dispatch", args.brief).catch((err: unknown) => this.log(`round ${round.n} in ${room.channel.name} failed: ${errText(err)}`));
    return {
      round: round.n,
      remainingRounds: this.caps.maxRounds - room.roundsThisSend,
      notCalled: roster.filter((b) => !args.to.includes(b.id)).map((b) => b.id),
      notes,
    };
  }

  private answerMessage(record: RoomTurnRecord, text: string, round: number): MessageLike {
    return createUserMessage({
      content: [{ type: "text", text }],
      source: { kind: "room", form: "answer", bot: record.bot, name: record.name, sessionId: record.sessionId, turn: record.turn ?? 0, round },
    }) as unknown as MessageLike;
  }

  private async runRound(room: Room, round: Round, to: readonly string[], roster: readonly RosterBot[], trigger: TurnTrigger, brief?: string): Promise<void> {
    const runOne = async (id: string, trig: TurnTrigger): Promise<void> => {
      const bot = roster.find((b) => b.id === id);
      if (bot === undefined || round.superseded) return;
      if (room.turnsThisSend >= this.caps.maxBotMessages) { round.capped = true; return; }
      room.turnsThisSend++;
      let member: Member;
      try {
        member = await this.ensureMember(room, bot);
      } catch (err) {
        round.turns.push({ bot: id, name: bot.name, sessionId: "", state: "failed", reason: errText(err) });
        return;
      }
      const result = await this.enqueue(member, () => this.runMemberTurn(room, member, roster, trig, brief));
      round.turns.push(result.record);
      if (result.record.state !== "answered") return;
      this.post(room, this.answerMessage(result.record, result.text, round.n));
      for (const peer of resolveMentions(result.text, roster.filter((b) => b.id !== id))) {
        if (round.continuations.includes(peer)) continue;
        if (round.continuationsRun + round.continuations.length >= this.caps.maxContinuations) break;
        round.continuations.push(peer);
      }
    };
    if (round.mode === "serial") { for (const id of to) await runOne(id, trigger); }
    else await Promise.all(to.map((id) => runOne(id, trigger)));
    while (!round.superseded && round.continuations.length > 0) {
      const id = round.continuations.shift() as string;
      round.continuationsRun++;
      await runOne(id, "continuation");
    }
    const outcome: RoundOutcome = round.superseded ? "superseded" : round.capped ? "capped" : "settled";
    if (trigger === "dispatch") await this.finishRound(room, round, outcome);
    if (room.active === round) room.active = undefined;
  }

  /** Every buffered answer onto the log, then the ONE wake - one synchronous block once the log is quiet. */
  private async finishRound(room: Room, round: Round, outcome: RoundOutcome): Promise<void> {
    await this.whenQuiet(room);
    this.flush(room);
    const text = roundEndText(round.n, outcome, round.turns, Math.max(0, this.caps.maxRounds - room.roundsThisSend));
    const end = createUserMessage({
      content: [{ type: "text", text }],
      source: { kind: "room", form: "round-end", round: round.n, outcome, turns: round.turns },
    });
    this.roomAgent(room).followup(end as unknown as MessageLike);
  }

  /* ---------- the operator's `@` (spec §4.4 rule 1) ---------- */

  /** The channel a session belongs to, live or cold; `null` when it is in none. */
  private async channelOf(sessionId: string): Promise<RoomChannel | null> {
    const live = this.deps.ctx.sessions.get(sessionId);
    let cwd = live?.header.cwd;
    if (cwd === undefined) cwd = (await this.deps.ctx.sessionPersistence?.list() ?? []).find((h) => h.id === sessionId)?.cwd;
    return this.deps.channelFor(cwd);
  }

  /** A cold room session becomes live through the gateway's OWN composition path
   * (`session.models` resumes via its agent resolver and changes nothing else),
   * so the face never composes Kairos's session itself. */
  private async ensureLive(sessionId: string): Promise<AgentLike> {
    const live = this.deps.ctx.agents.get(sessionId);
    if (live !== undefined) return live;
    if (this.deps.ctx.apiProxy === undefined) throw new HttpError(409, "the room session is not live and the gateway is not available to resume it");
    await this.deps.ctx.apiProxy.sessions.models({ rpcId: `room-${randomUUID()}`, payload: { sessionId } });
    const resumed = this.deps.ctx.agents.get(sessionId);
    if (resumed === undefined) throw new HttpError(404, "no such session");
    return resumed;
  }

  /**
   * The operator's `@`: resolved against the roster deterministically, appended
   * to the room as the operator's own message (never a prompt - Kairos sees it
   * on its next wake), and each named member turns on the standard delta. A
   * member mid-turn takes it after that turn. Resets the caps like every send.
   */
  async say(sessionId: string, text: string): Promise<{ addressed: string[] }> {
    const channel = await this.channelOf(sessionId);
    if (channel === null) throw new HttpError(404, "this session is in no channel");
    const roster = await this.rosterFor(channel).catch((err: unknown) => { throw new HttpError(409, errText(err)); });
    const addressed = resolveMentions(text, roster);
    if (addressed.length === 0) return { addressed: [] };
    await this.ensureLive(sessionId);
    const room = this.roomOf(sessionId, channel);
    const message = createUserMessage({ content: [{ type: "text", text }], source: { kind: "user", mention: addressed } });
    this.post(room, message as unknown as MessageLike);
    this.onOperatorSend(room);
    const round: Round = { n: room.active?.n ?? 0, mode: "mention", superseded: false, capped: false, continuations: [], continuationsRun: 0, turns: [] };
    void this.runRound(room, round, addressed, roster, "mention").catch((err: unknown) => this.log(`@ turn in ${room.channel.name} failed: ${errText(err)}`));
    return { addressed };
  }

  /** What the client asks about a room: the roster, the members this engine drove, the caps left. Never resumes anything. */
  async describe(sessionId: string): Promise<{ roster: RosterBot[]; members: Record<string, { sessionId: string; name: string }>; caps: { roundsLeft: number; messagesLeft: number; maxRounds: number; maxBotMessages: number }; round?: { n: number; mode: string; superseded: boolean } }> {
    const channel = await this.channelOf(sessionId);
    if (channel === null) throw new HttpError(404, "this session is in no channel");
    const roster = await this.rosterFor(channel).catch(() => [] as RosterBot[]);
    const room = this.rooms.get(sessionId);
    const members: Record<string, { sessionId: string; name: string }> = {};
    for (const [bot, member] of room?.members ?? []) members[bot] = { sessionId: member.agent.id, name: member.name };
    return {
      roster,
      members,
      caps: {
        roundsLeft: Math.max(0, this.caps.maxRounds - (room?.roundsThisSend ?? 0)),
        messagesLeft: Math.max(0, this.caps.maxBotMessages - (room?.turnsThisSend ?? 0)),
        maxRounds: this.caps.maxRounds,
        maxBotMessages: this.caps.maxBotMessages,
      },
      ...(room?.active === undefined ? {} : { round: { n: room.active.n, mode: room.active.mode, superseded: room.active.superseded } }),
    };
  }
```

`onOperatorSend` in `say` resets before the message's own `user/message` event fires (which resets again, idempotently); the mention round is not stored in `room.active` because a mention batch never blocks a dispatch (a busy member queues).

- [ ] **Step 4: Run the tests and typecheck**

Run: `cd face && npx tsx --test tests/room-engine.test.ts && npm run typecheck`
Expected: PASS, clean. If the "caps" test's second round records `capped` with a different turn count than expected, check the order: the cap is checked BEFORE `turnsThisSend++`, so with `maxBotMessages: 4` round 1 uses three and round 2 starts one.

- [ ] **Step 5: Commit**

```bash
git add face/src/room.ts face/tests/room-engine.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): the room engine, part 2 - parallel and serial rounds, peer-@ continuations bounded per round, the three caps with settled/capped/superseded outcomes, one wake per round after every answer is in the log, and the operator's @ as a non-waking room message
```

---

### Task 8: The engine, part 3 — the `dispatch` tool, the two routes, `installRoom`

**Files:**
- Modify: `face/src/room.ts`
- Test: `face/tests/room-engine.test.ts`

**Interfaces:**
- Consumes: parts 1–2, Task 4's `registerRoomProjection`.
- Produces: `dispatchToolDefinition(engine, deps): RoomToolDefinition`; `installRoom(deps): RoomEngine` (registers the tool, the projection unit and the bus listener; `engine.dispose()` unregisters all); `registerRoomRoutes(webServer, engine)` mounting `POST /data/rooms/say { sessionId, text }` → `{ ok, addressed }` and `POST /data/rooms/state { sessionId }` → `{ ok, ...describe }`.

- [ ] **Step 1: Write the failing tests (part 3)**

Append to `face/tests/room-engine.test.ts` (imports: `dispatchToolDefinition, installRoom, registerRoomRoutes` from `../src/room.ts`; `mkdtemp`, `tmpdir`, `join`; `setBots` from `../src/roster.ts`; the route recorder helper used by `bots.test.ts` — import or copy it):

```ts
test("the dispatch tool: global, Kairos-only, channel-only, roster-checked; validates, starts the round and names who was not called", async () => {
  const tree = makeFakeTree();
  const home = await mkdtemp(join(tmpdir(), "face-room-"));
  await setBots(home, CHANNEL.workspaceId, ["buffett", "speculator"]);
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "b" }));
  const engine = installRoom({
    ctx: tree.ctx as unknown as RoomDeps["ctx"], home,
    channelFor: async (cwd) => (cwd === CHANNEL.dir ? CHANNEL : null),
    listBots: async () => roster, clock: tree.clock, installModelSelection: () => () => {}, log: () => {},
  });
  assert.deepEqual(tree.registeredTools.map((t) => t.name), ["dispatch"]);
  const tool = tree.registeredTools[0] as unknown as ReturnType<typeof dispatchToolDefinition>;
  assert.match(tool.description, /roster/);
  assert.match(tool.description, /end your turn/i);
  const exec = (agent: unknown) => ({ agent, signal: new AbortController().signal }) as never;

  await assert.rejects(tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, exec(undefined)), /needs a session/);
  const bot = { id: "session-bot", status: "idle", session: { id: "session-bot", header: { cwd: CHANNEL.dir, agentPreset: "buffett" }, events: [], seq: 0 } };
  await assert.rejects(tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, exec(bot)), /Kairos's tool/);
  const nowhere = { ...kairos, session: { ...kairos.session, header: { cwd: "/elsewhere", agentPreset: "kairos" } } };
  await assert.rejects(tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, exec(nowhere)), /in no channel/);
  await assert.rejects(tool.execute({ to: ["macro"], mode: "parallel", brief: "q", reason: "r" }, exec(kairos)), /macro is not on this channel's roster.*buffett, speculator/);

  const value = await tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "first" }, exec(kairos)) as { text: string; round: number; notCalled: string[] };
  assert.equal(value.round, 1);
  assert.deepEqual(value.notCalled, ["speculator"]);
  const rendered = tool.output.render({}, value)[0].text;
  assert.match(rendered, /Dispatched 巴菲特型 \(parallel\)/);
  assert.match(rendered, /Not called: 投机型\./);
  assert.deepEqual(tool.presentCall({ to: ["buffett"], mode: "parallel", brief: "q", reason: "first" }), { card: "generic", title: "dispatch buffett (parallel)", kind: "read", rawInput: "first" });
  await tree.clock.advance(100);
  assert.equal(kairos.inbox.nextTurn.length, 1);
  engine.dispose();
  assert.equal(tree.registeredTools.length, 0, "dispose unregisters the tool");
  assert.equal(tree.listeners.length, 0, "and the bus listener");
});

test("the two routes: say and state, fenced like every /data route", async () => {
  const tree = makeFakeTree();
  const home = await mkdtemp(join(tmpdir(), "face-room-"));
  await setBots(home, CHANNEL.workspaceId, ["buffett"]);
  tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "b" }));
  const engine = installRoom({
    ctx: tree.ctx as unknown as RoomDeps["ctx"], home,
    channelFor: async (cwd) => (cwd === CHANNEL.dir ? CHANNEL : null),
    listBots: async () => roster, clock: tree.clock, installModelSelection: () => () => {}, log: () => {},
  });
  const routes = recorder();
  registerRoomRoutes(routes, engine);
  assert.deepEqual(routes.paths(), ["/data/rooms/say", "/data/rooms/state"]);
  const forged = JSON.parse(await routes.call("/data/rooms/say", { method: "POST", json: { sessionId: "session-room", text: "@buffett" }, host: "evil.example.com" }));
  assert.equal(forged.status, 403);
  const bad = JSON.parse(await routes.call("/data/rooms/say", { method: "POST", json: { sessionId: "nope", text: "@buffett" } }));
  assert.equal(bad.status, 400);
  const said = JSON.parse(await routes.call("/data/rooms/say", { method: "POST", json: { sessionId: "session-room", text: "@buffett hi" } }));
  assert.equal(said.status, 200);
  assert.deepEqual(said.body.addressed, ["buffett"]);
  await tree.clock.advance(50);
  const state = JSON.parse(await routes.call("/data/rooms/state", { method: "POST", json: { sessionId: "session-room" } }));
  assert.equal(state.status, 200);
  assert.deepEqual(state.body.roster.map((b: { id: string }) => b.id), ["buffett"]);
  assert.ok(state.body.members.buffett.sessionId);
  const nowhere = JSON.parse(await routes.call("/data/rooms/state", { method: "POST", json: { sessionId: "session-none" } }));
  assert.equal(nowhere.status, 404);
});
```

`recorder()` must offer `paths()`, and `call(path, { method, json, host? })` returning the JSON-encoded `{status, body}` — look at how `bots.test.ts` / `channels.test.ts` drive routes and reuse that helper (extract it into `face/tests/route-recorder.ts` if it is duplicated).

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd face && npx tsx --test tests/room-engine.test.ts`
Expected: FAIL — `installRoom` is not exported.

- [ ] **Step 3: Add part 3 to `face/src/room.ts`**

After the class:

```ts
/* ---------- the tool (spec §4.3) ---------- */

const DISPATCH_DESCRIPTION =
  "Ask the bots on this channel's roster for their views, each in its own voice. You are the organizer: choose whom (bot ids " +
  "from the roster), the mode (parallel: everyone answers independently and sees no peer this round - use it first on a fresh " +
  "question; serial: each later bot sees the earlier answers), a brief (the question or task for this batch) and a reason " +
  "(why these, why this mode - it lands in the transcript). The call returns at once; END YOUR TURN after it. You will be " +
  "woken once when the round ends, with who answered and who passed; every answer will be in this conversation, attributed. " +
  "Then name the disagreements before you conclude. A bot that is not on the roster cannot be called; the refusal names the " +
  "roster. Caps per operator message: 3 rounds, 10 bot messages, 2 peer continuations per round. Dispatch grants a bot nothing.";

export function dispatchToolDefinition(engine: RoomEngine, deps: Pick<RoomDeps, "channelFor">): RoomToolDefinition {
  return {
    name: "dispatch",
    description: DISPATCH_DESCRIPTION,
    parameters: {
      type: "object",
      properties: {
        to: { type: "array", items: { type: "string" }, description: "bot ids from this channel's roster, in speaking order for serial" },
        mode: { type: "string", enum: ["parallel", "serial"] },
        brief: { type: "string", description: "the question or task for this batch" },
        reason: { type: "string", description: "why these bots, why this mode" },
      },
      required: ["to", "mode", "brief", "reason"],
      additionalProperties: false,
    },
    output: {
      schema: {
        type: "object",
        properties: { text: { type: "string" }, round: { type: "number" }, called: { type: "array", items: { type: "string" } }, notCalled: { type: "array", items: { type: "string" } } },
        required: ["text", "round", "called", "notCalled"],
        additionalProperties: false,
      },
      render: (_args, value) => [{ type: "text", text: (value as { text: string }).text }],
    },
    timeoutMs: 30_000,
    async execute(args, exec) {
      const agent = exec.agent;
      if (agent === undefined) throw new Error("dispatch needs a session to run in");
      const preset = agent.session.header.agentPreset;
      if (preset !== undefined && preset !== DEFAULT_PRESET) throw new Error("dispatch is Kairos's tool; a voice does not dispatch");
      const channel = await deps.channelFor(agent.session.header.cwd);
      if (channel === null) throw new Error("dispatch works in a channel session; this session is in no channel");
      const roster = await engine.rosterFor(channel);
      const valid = validateDispatch(args, roster);
      if (!valid.ok) throw new Error(valid.message);
      const started = await engine.dispatch(agent.id, channel, valid.value, roster);
      return {
        text: dispatchResultText(valid.value, roster, started.round, started.remainingRounds, started.notes),
        round: started.round,
        called: valid.value.to,
        notCalled: started.notCalled,
      };
    },
    presentCall(args) {
      const a = (args !== null && typeof args === "object" ? args : {}) as { to?: unknown; mode?: unknown; reason?: unknown };
      const to = Array.isArray(a.to) ? a.to.filter((x): x is string => typeof x === "string").join(", ") : "?";
      return { card: "generic", title: `dispatch ${to} (${typeof a.mode === "string" ? a.mode : "?"})`, kind: "read", rawInput: typeof a.reason === "string" ? a.reason.slice(0, 200) : undefined };
    },
  };
}

/* ---------- install ---------- */

/** Register the tool, the projection unit and the bus on the ROOT context. Returns the engine; `dispose()` unwinds all three. */
export function installRoom(deps: RoomDeps): RoomEngine {
  const engine = new RoomEngine(deps);
  const unregister = deps.ctx.tools.register(dispatchToolDefinition(engine, deps));
  const registry = deps.ctx.sessionProjections;
  const unproject = registry === undefined ? undefined : registerRoomProjection(registry as unknown as Parameters<typeof registerRoomProjection>[0]);
  if (registry === undefined) deps.ctx.logger?.warn(`${BIN}: sessionProjections is not in the tree; the room strip will have no state`);
  engine.onDispose(() => { unregister(); unproject?.(); });
  return engine;
}

/* ---------- routes ---------- */

export function registerRoomRoutes(webServer: RouteRegistrar, engine: RoomEngine): void {
  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify(body));
  };
  const post = (act: (body: Record<string, unknown>) => Promise<object>) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      if (req.method !== "POST") return send(res, 405, { ok: false, error: "POST only" });
      if (!isJsonBody(req)) return send(res, 415, { ok: false, error: "application/json only" });
      try {
        let body: Record<string, unknown>;
        try {
          const parsed: unknown = JSON.parse(await readBody(req, 16_384));
          if (parsed === null || typeof parsed !== "object") throw new Error("not an object");
          body = parsed as Record<string, unknown>;
        } catch (err) {
          if (err instanceof HttpError) throw err;
          throw new HttpError(400, "body must be a JSON object");
        }
        if (typeof body.sessionId !== "string" || !SESSION_ID_RE.test(body.sessionId)) throw new HttpError(400, "invalid session id");
        return send(res, 200, { ok: true, ...(await act(body)) });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        console.error(`${BIN}: room route failed:`, err);
        return send(res, 500, { ok: false, error: "request failed" });
      }
    };
  webServer.register({ kind: "exact", path: "/data/rooms/say", handler: post(async (body) => {
    if (typeof body.text !== "string" || body.text.trim() === "") throw new HttpError(400, "text required");
    return engine.say(body.sessionId as string, body.text);
  }) });
  webServer.register({ kind: "exact", path: "/data/rooms/state", handler: post(async (body) => engine.describe(body.sessionId as string)) });
}
```

`FORBIDDEN` is a JSON string already; `send` above `JSON.stringify`s objects — write it as the other modules do (`typeof body === "string" ? body : JSON.stringify(body)`). Add to the class:

```ts
  /** Run `fn` when the engine is disposed (the tool and projection disposers). */
  onDispose(fn: () => void): void { this.disposers.push(fn); }
```

- [ ] **Step 4: Run the whole face suite and typecheck**

Run: `cd face && npm test && npm run typecheck`
Expected: PASS (offline; the smoke files skip), clean.

- [ ] **Step 5: Commit**

```bash
git add face/src/room.ts face/tests/room-engine.test.ts face/tests/route-recorder.ts
git commit -F /tmp/msg.txt
```

(omit `route-recorder.ts` if no helper was extracted) with `/tmp/msg.txt`:

```
feat(face): the dispatch tool - global, Kairos-only, channel-only, roster-checked, returning at once and naming who was not called; installRoom on the root context; POST /data/rooms/say and /state
```

---

### Task 9: Wiring — `main.ts`, Kairos's persona, the template

**Files:**
- Modify: `face/src/main.ts`
- Modify: `dsh/profile/persona.md`
- Modify: `face/tests/persona.test.ts` (only if it pins the file's exact text)
- Test: `face/tests/boot.test.ts` (unchanged), `face/tests/persona.test.ts`

**Interfaces:**
- Consumes: Task 8's `installRoom`, `registerRoomRoutes`; Task 2's `channelFor` with `dir`.
- Produces: a booted face with `dispatch` in Kairos's roster, the `room` unit registered, and the two routes mounted; the persona paragraph the spec's §4.4 default rests on.

- [ ] **Step 1: Wire the engine in `face/src/main.ts`**

After `registerBotRoutes(...)` and before `registerPanelRoutes(...)`, add:

```ts
/* Rooms: the engine lives on the ROOT context (a root-created member is a
 * runtime root, so it can ask the operator a question; a root listener sees
 * every session). `channelFor` is the same lookup the agent tools use, now
 * carrying the channel directory a member session is created in. */
const deps = panelDeps(booted.ctx, process.cwd());
const room = installRoom({
  ctx: booted.ctx as unknown as RoomContextLike,
  home: dshHome,
  channelFor: deps.channelFor,
  listBots: () => listBots(BOTS_ROOT, () => agentPresets.list()),
});
registerRoomRoutes(booted.ctx.webServer, room);
```

and pass `deps` (not a second `panelDeps(...)` call) to `registerPanelRoutes`. Import `installRoom, registerRoomRoutes, type RoomContextLike` from `./room.ts`. Print one line after the URL line: `console.log(\`${BIN}: rooms: dispatch registered; caps ${JSON.stringify(room.caps)}\`);`.

- [ ] **Step 2: Add the room default to `dsh/profile/persona.md`**

Append one paragraph (no `{{` — the file is a strict template, `readPersona` refuses it otherwise):

```
When a channel has bots on its roster you organize the room: on a fresh question let every present voice state its view independently first (dispatch in parallel, one brief), end your turn, and when you are woken name the disagreements between them before you conclude. Address a voice again only when its view moves the question. A voice is evidence you weigh, never a verdict; the conclusion is yours, and the operator's @ reaches a voice without you.
```

If `face/tests/persona.test.ts` or `bots-smoke.test.ts` compares the file to a fixed string, update the expectation; `bots-smoke.test.ts` compares only the prefix before the first `{{`, which is unchanged.

- [ ] **Step 3: Run the offline suite, typecheck, and a real boot**

Run: `cd face && npm test && npm run typecheck`
Expected: PASS, clean.

Then a real boot against a scratch home to see the wiring hold (no browser):

```bash
cd face && DSH_HOME=$(mktemp -d) npx tsx -e "
import { setupFaceProfile } from './src/setup.ts';
import { bootFace } from './src/boot.ts';
setupFaceProfile(process.env.DSH_HOME);
const { ctx, dispose } = await bootFace({ profileName: 'face', port: 0, dshHome: process.env.DSH_HOME });
const names = ctx.get('tools').schemas().map((s) => s.name);
console.log('dispatch registered before main wiring?', names.includes('dispatch'));
await dispose();
"
```

Expected: `false` (the tool is registered by `main.ts`, not by `bootFace`) — this only proves the tree still boots. The real proof is the smoke of Task 11.

- [ ] **Step 4: Commit**

```bash
git add face/src/main.ts dsh/profile/persona.md face/tests/persona.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat(face): main wires the room engine and its routes on the root context; the persona carries the room default - independent views first, then the disagreements
```

---

### Task 10: The whole round in-process on a stub model — `face/tests/stub-llm.ts`, `face/tests/room-smoke.test.ts`

**Files:**
- Create: `face/tests/stub-llm.ts`
- Create: `face/tests/room-smoke.test.ts`

**Interfaces:**
- Consumes: everything above; `LlmAdapter`, `CallId` from `@deepseek-ai/dsh-llm`; `renderPrompt` from `@deepseek-ai/dsh-system-prompt`; `makeRepoBotsRoot` from `./bots-fixture.ts`; `createBot`, `listBots` from `../src/bots.ts`; `setBots` from `../src/roster.ts`; `panelDeps` from `../src/panels.ts`; `installRoom`, `registerRoomRoutes` from `../src/room.ts`.
- Produces: `StubAdapter` (a scripted `LlmAdapter` whose `stream` yields text, a tool call, or throws), and the one smoke that proves S5, S6, the `read-only` pin, the member's sandbox denial (D12), the home-scope denial (plan 1's deferral 4), the projection and its cache row (R13), the `@` route, the `AGENTS.md` chain, and `dispatch`'s absence from a bot's schemas.

- [ ] **Step 1: Write the stub adapter**

```ts
// face/tests/stub-llm.ts
/** A scripted model route for the smoke tests: no key, no network. Only
 * `stream()` is abstract on `LlmAdapter`; the catalog methods are answered so
 * `session.models`/`selectModel` and `resolveCallConfig` accept the route.
 * The script decides per request (it sees the session id and the messages);
 * a thrown script is dsh's "iteration failure" → `turn/end {kind:'error'}`. */
import { CallId, LlmAdapter, type GenerateOptions, type LlmModelInfo, type LlmResolvedModelInfo, type StreamChunk } from "@deepseek-ai/dsh-llm";

export type StubReply =
  | { kind: "text"; text: string }
  | { kind: "tool"; name: string; args: unknown }
  | { kind: "error"; message: string };

let calls = 0;

export class StubAdapter extends LlmAdapter {
  constructor(private readonly script: (options: GenerateOptions) => StubReply) { super(); }
  override providerInfo(provider: string) { return { id: provider, name: "Stub" }; }
  override listModels(provider: string): Promise<readonly LlmModelInfo[]> {
    return Promise.resolve([{ provider, id: "echo", name: "echo", inputModalities: ["text"] }]);
  }
  override resolveModel(provider: string, model: string): Promise<LlmResolvedModelInfo> {
    return Promise.resolve({ provider, id: model, name: model, inputModalities: ["text"], context: { contextWindow: 128_000 } });
  }
  override async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const reply = this.script(options);
    if (reply.kind === "error") throw new Error(reply.message);
    if (reply.kind === "text") {
      yield { type: "block-start", index: 0, blockType: "text" };
      yield { type: "text-delta", index: 0, text: reply.text };
      yield { type: "block-end", index: 0, block: { type: "text", text: reply.text } };
      yield { type: "usage", usage: { inputTokens: 1, outputTokens: 1 } };
      yield { type: "finish", reason: { kind: "stop" } };
      return;
    }
    const id = CallId(`stub-call-${++calls}`);
    const args = JSON.stringify(reply.args);
    yield { type: "block-start", index: 0, blockType: "tool-call" };
    yield { type: "tool-call-delta", index: 0, id, name: reply.name, argumentsDelta: args };
    yield { type: "block-end", index: 0, block: { type: "tool-call", id, name: reply.name, arguments: args } };
    yield { type: "finish", reason: { kind: "tool-calls" } };
  }
}
```

If `override` on a method the base declares non-abstract fails to typecheck (a base method typed as a property), drop the keyword; if `CallId` is not a callable brand at runtime, replace with `\`stub-call-${++calls}\` as unknown as CallId`.

- [ ] **Step 2: Write the smoke**

```ts
// face/tests/room-smoke.test.ts
/** The room, end to end, in-process, on a stub model and no key (spec §8's
 * last smoke bullets; S5 and S6, which plan 1 deferred here).
 *
 * One boot, one file (smoke.test.ts). The bots root is `mkdtemp`'d INSIDE the
 * repository so the shipped relative plugin path mounts (bots-fixture.ts).
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { mkdir, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { renderPrompt } from "@deepseek-ai/dsh-system-prompt";
import type { GenerateOptions } from "@deepseek-ai/dsh-llm";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { createBot, listBots } from "../src/bots.ts";
import { panelDeps } from "../src/panels.ts";
import { setBots } from "../src/roster.ts";
import { installRoom, registerRoomRoutes, type RoomContextLike } from "../src/room.ts";
import { makeRepoBotsRoot } from "./bots-fixture.ts";
import { StubAdapter, type StubReply } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
const MARKER = "ROOM-SMOKE-AGENTS-MARKER";

interface Ev { type: string; seq: number; data?: Record<string, unknown> }
const sourceOf = (e: Ev): Record<string, unknown> | undefined => (e.data?.source ?? (e.data?.message as { source?: unknown } | undefined)?.source) as Record<string, unknown> | undefined;
const lastUserText = (o: GenerateOptions): string => {
  const last = [...o.messages].reverse().find((m) => m.role === "user");
  return (last?.content ?? []).map((b) => (b as { text?: string }).text ?? "").join("\n");
};
async function waitFor(what: string, check: () => boolean, ms = 30_000): Promise<void> {
  const until = Date.now() + ms;
  while (!check()) {
    if (Date.now() > until) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 50));
  }
}

test("room smoke: dispatch → two members → answers in the room log → one wake → synthesis; read-only members; @; the projection and its cache", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  const bots = await makeRepoBotsRoot();
  const root = mkdtempSync(join(tmpdir(), "face-room-root-"));
  const home = mkdtempSync(join(tmpdir(), "face-roomsmoke-"));
  try {
    const soul = (name: string) => `You are ${name}, a test voice in the room smoke.`;
    await createBot(bots, { id: "alpha", name: "Alpha", soul: soul("Alpha"), model: "stub/echo" });
    await createBot(bots, { id: "beta", name: "Beta", soul: soul("Beta"), model: "stub/echo" });
    await createBot(bots, { id: "gamma", name: "Gamma", soul: soul("Gamma"), model: "stub/echo" });
    const channelDir = await realpath(await (async () => { const d = join(root, "strategies", "room-test"); await mkdir(d, { recursive: true }); return d; })());
    await writeFile(join(root, "AGENTS.md"), `# smoke\n${MARKER}\n`);
    setupFaceProfile(home);
    const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    try {
      const sessions = ctx.get("sessions") as { get(id: string): { id: string; header: Record<string, unknown>; events: Ev[] } | undefined; list(): { id: string; header: Record<string, unknown>; events: Ev[] }[] };
      const agents = ctx.get("agents") as { get(id: string): { id: string; session: { header: Record<string, unknown>; events: Ev[] } } | undefined };
      const presets = ctx.get("agentPresets") as { list(): Promise<{ id: string; broken?: string }[]> };
      const tools = ctx.get("tools") as { schemas(scope?: object): { name: string }[]; execute(exec: object): Promise<{ isError: boolean; content?: { text?: string }[] }> };
      const permission = ctx.get("permissionPresets") as { current(events: readonly Ev[]): string };
      const systemPrompt = ctx.get("systemPrompt") as { assemble(context: { scope?: object; agent?: object }): Promise<Parameters<typeof renderPrompt>[0]> };
      const registry = ctx.get("workspaceRegistry") as { create(path: string): Promise<{ id: string; path: string }> };
      const projections = ctx.get("sessionProjections") as { snapshot(session: object): { values: Record<string, unknown> } };
      const llm = ctx.get("llm") as { registerAdapter(providers: string[], adapter: object): () => void };

      /* The script: who is asking is the session's preset; what to say is where the conversation is. */
      const presetOf = (o: GenerateOptions): string => String(sessions.get(String(o.sessionId))?.header.agentPreset ?? "");
      llm.registerAdapter(["stub"], new StubAdapter((o): StubReply => {
        if (o.purpose !== undefined) return { kind: "text", text: "room smoke" }; // titles, compaction
        const who = presetOf(o);
        const last = [...o.messages].reverse()[0];
        const lastKind = String((last?.source as { kind?: unknown } | undefined)?.kind);
        const lastForm = String((last?.source as { form?: unknown } | undefined)?.form);
        if (who === "kairos") {
          if (lastKind === "tool") return { kind: "text", text: "Waiting for the room." };
          if (lastKind === "room" && lastForm === "round-end") return { kind: "text", text: `Synthesis: ${lastUserText(o).split("\n")[1]}` };
          return { kind: "tool", name: "dispatch", args: { to: ["alpha", "beta", "gamma"], mode: "parallel", brief: "state your view on X", reason: "independent views first" } };
        }
        if (who === "alpha") {
          const text = lastUserText(o);
          if (lastKind === "tool") return { kind: "text", text: "alpha: the write was refused, as it should be" };
          if (/addressed you directly/.test(text)) return { kind: "tool", name: "bash", args: { command: `printf x > ${JSON.stringify(join(channelDir, "s4-member-should-not-exist.txt"))}`, description: "member write probe" } };
          return { kind: "text", text: "alpha: buy X" };
        }
        if (who === "beta") return { kind: "text", text: "(pass)" };
        if (who === "gamma") return { kind: "error", message: "gamma's model exploded" };
        return { kind: "text", text: "home: noted" };
      }));

      const ws = await registry.create(channelDir);
      await setBots(home, ws.id, ["alpha", "beta", "gamma"]);
      const deps = panelDeps(ctx, root, home);
      const engine = installRoom({
        ctx: ctx as unknown as RoomContextLike, home,
        channelFor: deps.channelFor,
        listBots: () => listBots(bots, () => presets.list()),
      });
      registerRoomRoutes(ctx.webServer, engine);

      const base = `http://127.0.0.1:${ctx.webServer.port}`;
      let n = 0;
      const rpc = async (method: string, payload: object): Promise<Record<string, unknown>> => {
        const res = await fetch(`${base}/api/${method}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ type: "client-request", rpcId: `r${++n}`, method, payload }) });
        const body = await res.json() as { result?: { ok?: boolean; value?: Record<string, unknown>; error?: unknown } };
        assert.equal(body.result?.ok, true, `${method}: ${JSON.stringify(body.result?.error)}`);
        return body.result!.value!;
      };
      const data = async (path: string, body: object): Promise<Record<string, unknown>> => {
        const res = await fetch(`${base}${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
        return await res.json() as Record<string, unknown>;
      };

      /* Kairos's room session, on the stub route. */
      const created = await rpc("session.create", { workspaceId: ws.id });
      const roomId = String(created.sessionId);
      assert.equal(created.agentPreset, "kairos");
      await rpc("session.selectModel", { sessionId: roomId, provider: "stub", model: "echo" });
      assert.ok(tools.schemas(agents.get(roomId) as object).some((s) => s.name === "dispatch"), "dispatch is in Kairos's roster");

      await rpc("session.prompt", { sessionId: roomId, mode: "queue", content: [{ type: "text", text: "各位对 X 的看法？" }] });
      const room = () => sessions.get(roomId)!.events;
      await waitFor("the synthesis", () => {
        const events = room();
        const end = events.findIndex((e) => sourceOf(e)?.form === "round-end");
        return end >= 0 && events.slice(end).some((e) => e.type === "assistant/message" && JSON.stringify(e.data).includes("Synthesis:"));
      }, 60_000);

      /* The log sequence (S5 restated for deviation 2): every answer precedes the
       * round-end, the round-end wake opens exactly ONE new turn, and the synthesis is in it. */
      const events = room();
      const types = events.map((e) => `${e.type}${e.type === "user/message" ? `:${String(sourceOf(e)?.kind)}/${String(sourceOf(e)?.form ?? "")}` : ""}${e.type === "tool/call" ? `:${String(e.data?.name)}` : ""}`);
      const firstEnd = types.indexOf("turn/end");
      const answerAt = types.indexOf("user/message:room/answer");
      const roundEndAt = types.indexOf("user/message:room/round-end");
      const secondStart = types.indexOf("turn/start", firstEnd);
      assert.ok(types.indexOf("tool/call:dispatch") < firstEnd, "dispatch was called in the first turn");
      assert.ok(answerAt > firstEnd && answerAt < roundEndAt, "alpha's answer landed after Kairos's turn ended and before the wake");
      assert.ok(roundEndAt > secondStart && types.slice(secondStart, roundEndAt).filter((t) => t === "turn/start").length === 1, "the wake is one turn");
      const dispatchResult = events.find((e) => e.type === "tool/result" && JSON.stringify(e.data).includes("Dispatched"));
      assert.match(JSON.stringify(dispatchResult?.data), /Not called: none\./);
      const roundEnd = sourceOf(events[roundEndAt]) as { outcome: string; turns: { bot: string; state: string; sessionId: string }[] };
      assert.equal(roundEnd.outcome, "settled");
      assert.deepEqual(Object.fromEntries(roundEnd.turns.map((t) => [t.bot, t.state])), { alpha: "answered", beta: "passed", gamma: "failed" }, "a failing model is failed and the round settles");

      /* The members: parented, preset-joined, read-only before their first prompt, AGENTS.md in the chain, no dispatch. */
      const list = (await rpc("session.list", {})).items as { sessionId: string; parentSessionId?: string; agentPreset?: string; cwd?: string; origin?: string; projections?: { values: Record<string, unknown> } }[];
      const members = list.filter((s) => s.parentSessionId === roomId);
      assert.deepEqual(members.map((m) => m.agentPreset).sort(), ["alpha", "beta", "gamma"]);
      for (const m of members) {
        assert.equal(m.cwd, channelDir);
        assert.equal(m.origin, undefined);
        const agent = agents.get(m.sessionId)!;
        assert.equal(permission.current(agent.session.events), "read-only");
        assert.equal(agent.session.events[0].type, "permission/preset", "the pin is the first event - dsh appends no end-seed marker to a fresh session");
        assert.equal(tools.schemas(agent as object).some((s) => s.name === "dispatch"), false, "a voice never sees dispatch");
        const prompt = renderPrompt(await systemPrompt.assemble({ agent: agent as object, scope: agent as object }));
        assert.ok(prompt.includes(`You are ${m.agentPreset![0].toUpperCase()}${m.agentPreset!.slice(1)}, a test voice`), "the bot's persona is in its prompt (S6)");
        const chain = agent.session.events.find((e) => e.type === "user/message" && sourceOf(e)?.kind === "plugin" && JSON.stringify(e.data).includes(MARKER));
        assert.ok(chain !== undefined, `${m.agentPreset}: the channel's AGENTS.md chain reached the member`);
      }
      const alpha = members.find((m) => m.agentPreset === "alpha")!;
      const alphaDelta = agents.get(alpha.sessionId)!.session.events.find((e) => sourceOf(e)?.form === "delta");
      assert.match(JSON.stringify(alphaDelta?.data), /各位对 X 的看法/);
      assert.match(JSON.stringify(alphaDelta?.data), /exactly \(pass\)/);

      /* The projection: on the live snapshot and on the session.list row. */
      const snap = projections.snapshot(sessions.get(roomId) as object).values.room as { kind: string; members: Record<string, { state: string }>; round: { open: boolean; outcome?: string } };
      assert.equal(snap.kind, "room");
      assert.deepEqual(Object.fromEntries(Object.entries(snap.members).map(([k, v]) => [k, v.state])), { alpha: "answered", beta: "passed", gamma: "failed" });
      assert.deepEqual(snap.round.open, false);
      assert.equal(snap.round.outcome, "settled");
      const row = list.find((s) => s.sessionId === roomId)!;
      assert.equal((row.projections?.values.room as { kind?: string } | undefined)?.kind, "room", "the room value rides session.list");
      assert.equal((members[0].projections?.values.room as { kind?: string } | undefined)?.kind, "member");

      /* The cache row (R13): Kairos's turn/end is a mandatory write. */
      const cacheFile = join(home, "storages", "session_projcache.json");
      await waitFor("the projection cache file", () => existsSync(cacheFile) && readFileSync(cacheFile, "utf8").includes(roomId), 10_000);

      /* The operator's @: not a prompt; alpha turns, tries to write into the channel, is refused INSIDE the tool content (D12, R10). */
      const before = room().length;
      const said = await data("/data/rooms/say", { sessionId: roomId, text: "@alpha 写个文件试试" });
      assert.deepEqual(said.addressed, ["alpha"]);
      await waitFor("alpha's second answer", () => room().slice(before).some((e) => sourceOf(e)?.form === "answer" && String(sourceOf(e)?.bot) === "alpha"), 60_000);
      const mention = room().slice(before).find((e) => e.type === "user/message" && sourceOf(e)?.kind === "user");
      assert.deepEqual(sourceOf(mention!)?.mention, ["alpha"], "the operator's message is in the room, addressed");
      const alphaEvents = agents.get(alpha.sessionId)!.session.events;
      const probe = alphaEvents.find((e) => e.type === "tool/result" && JSON.stringify(e.data).includes("s4-member-should-not-exist"));
      assert.ok(probe !== undefined, "the member ran its write");
      assert.match(JSON.stringify(probe!.data), /sandbox: file access denied/);
      assert.equal(existsSync(join(channelDir, "s4-member-should-not-exist.txt")), false);
      assert.equal(room().filter((e) => e.type === "turn/start").length, 2, "an @ never woke Kairos");

      /* Plan 1's deferral 4: a HOME session writes its journal and is refused on ../SOUL.md. */
      const homeSession = await rpc("session.create", { cwd: join(bots, "alpha", "journal"), agentPreset: "alpha" });
      const homeAgent = agents.get(String(homeSession.sessionId))!;
      const write = async (target: string) => tools.execute({ callId: `home-${Math.random()}`, name: "bash", arguments: { command: `printf probe > ${JSON.stringify(target)}`, description: "home write probe" }, agent: homeAgent, signal: new AbortController().signal });
      const inside = await write(join(bots, "alpha", "journal", "probe.md"));
      assert.equal(existsSync(join(bots, "alpha", "journal", "probe.md")), true, `a home writes its journal; saw ${JSON.stringify(inside.content?.map((c) => c.text).join(" ").slice(0, 200))}`);
      const soulBefore = await readFile(join(bots, "alpha", "SOUL.md"), "utf8");
      const outside = await write(join(bots, "alpha", "SOUL.md"));
      const text = (outside.content ?? []).map((c) => c.text ?? "").join("\n");
      console.log(`home-scope observed: ${text.replace(/\s+/g, " ").slice(0, 200)}`);
      assert.match(text, /sandbox: file access denied/, "a home cannot rewrite its own SOUL.md");
      assert.equal(await readFile(join(bots, "alpha", "SOUL.md"), "utf8"), soulBefore);
    } finally {
      await dispose();
    }
  } finally {
    await rm(bots, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
  }
});
```

- [ ] **Step 3: Run the smoke**

Run: `cd face && FACE_SMOKE=1 npx tsx --test tests/room-smoke.test.ts`
Expected: PASS within a minute. Things that legitimately need adjusting on a first run, and what to do:
- **`selectModel` refuses `stub`** → the adapter's `resolveModel` shape is off; compare with `dsh-llm-deepseek`'s `modelInfoFor` and add what `normalizeModelInfo` demands.
- **Kairos's first request does not reach the stub** → `session.prompt` refused with `model-unavailable`: `routeServed` checks `listProviders()`; make sure `registerAdapter` ran before the prompt.
- **`assistant/message` for the tool call finishes the turn without executing** → the `finish` reason must be `{ kind: "tool-calls" }` and the block a `tool-call` block with a string `arguments`.
- **The AGENTS.md chain assertion fails** → find where `dsh-agent-instructions` injects (a `user/message` with `source.kind === 'plugin'`) and match on that; if it injects only into the FIRST request's history rather than the log, read `agent.session.deriveMessages()` instead. Do not weaken the assertion to "some plugin message exists".
- **The home-scope write to `../SOUL.md` is NOT refused** → this is a measurement (plan 1 deferred it). Print the observed content, keep the assertion failing, and record the fact in the spec's §16 (Task 11) as an open D12 gap rather than passing the test by loosening it.
- **The round-end never arrives** → print `types` from the room log; the usual cause is the round waiting on a member whose stub reply did not end its turn (a `tool` reply with no follow-up `text` reply loops), or `whenQuiet` waiting on a room whose `turn/end` was missed because the engine was installed after the session was created (install BEFORE `session.create`, as the test does).

- [ ] **Step 4: Run the whole suite both ways**

Run: `cd face && npm test && FACE_SMOKE=1 npm test && npm run typecheck`
Expected: PASS, PASS, clean. Note the counts for the commit message and for `DEVELOPMENT.md` (plan 4).

- [ ] **Step 5: Commit**

```bash
git add face/tests/stub-llm.ts face/tests/room-smoke.test.ts
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
test(face): the room in-process on a stub model - dispatch to three members, answers on the log before one wake, synthesis in one turn, read-only members with the AGENTS.md chain and no dispatch, the projection on the row and in the cache, the operator's @ with a member write refused in content, and a home refused on its own SOUL.md
```

---

### Task 11: Record what the build changed — the spec's §16, plan 2 block

**Files:**
- Modify: `docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md` (append to §16)

- [ ] **Step 1: Append the plan-2 block to §16**

After the last paragraph of §16, append (fill the two `<…>` from Task 10's run):

```markdown
### Plan 2 — the room engine (server)

Built 2026-09-08 on `main` (`face/src/room.ts`, `room-rules.ts`, `room-projection.ts`; <N> face tests, <M> under `FACE_SMOKE=1`; typecheck clean). Plans 3–4 are unbuilt and this block does not touch them.

**Deviations from the design, each forced by a substrate fact measured while planning.**

1. **No `room/*` session events.** `Session.append` accepts any type, but every persistence read runs the log through the generated closed set `KNOWN_SESSION_EVENT_TYPES` and refuses a type outside it unless the event carries `ignorable: true` — which `append` cannot set (`dsh-session-persistence/lib/index.js`, `assertEventsSupported`; `dsh-session/lib/index.js`, `append`). One `room/member` would make the room session unresumable and its cold listing throw. So §2.4's "room membership is a room fact" became a header fact plus the log: a member is a session whose header carries `parentSession = <room>`, no `origin`, and a bot `agentPreset` (forks carry the source's preset, subagent children carry `origin`); the dispatch is the tool's own `tool/call` + `tool/result` (the result text names who was NOT called); a member's answer is a `user/message` on the room session with `source: { kind: 'room', form: 'answer', bot, name, sessionId, turn, round }`; the round end is the waking `user/message` with `form: 'round-end'` carrying every turn's state; the member's cursor is the delta message in ITS log (`form: 'delta'`, `messageIds`). §4.6's event list is retired; the `room` projection unit folds these known events instead (`face/src/room-projection.ts`).
2. **Answers are appended, never injected.** §4.3's "every member answer enters the room log via `inject` as it lands, so the operator sees bubbles appear while Kairos sleeps" does not hold: `inject` splices the inbox, and the `user/message` the client renders lands only when Kairos's next step claims it; an inject on a running driver forces an extra step or opens a stray turn. The engine appends the answer straight onto the room session's log (`surfaceOp: 'append'`) while the log is quiet — no open turn — and otherwise holds it in a per-room outbox flushed at the next `turn/end`. Kairos is woken only by the round-end `followup`, sent in the same synchronous block as the last flush, so the claim is one turn with every answer already above it. S5 was restated for this: proven in `room-smoke.test.ts` (answer before round-end, one `turn/start` for the wake, synthesis inside it).
3. **The `read-only` pin runs inside creation `setup`.** §2.4's create-then-`set` window and its "do not deliver the first prompt until `set` has logged" rule are unnecessary: `permissionPresets.set` on `agentCtx.agent.session` inside `setup` logs `permission/preset` + `sandbox/mode` + `approval/policy` before publication, and `pinInitialPermission` fills only missing facts. The pin is every member session's first event (asserted; a fresh session carries no `session/end-seed` marker — dsh appends it only over a seed).
4. **Fine states are the client's.** The projection registry has no out-of-fold write, so §6's "thinking / writing / tool … folded by the plugin into the unit" cannot be done. The unit carries coarse state (`called`, `answered`, `passed`, `failed`, `timed-out`, the round, `organizing`); plan 3 derives the fine states from the member sessions' own `assistant/chunk` block starts, which the mux already forwards for every live session.
5. **`preset.yml` `model:` is honored through `installModelSelection`, not `session.selectModel`** — the RPC saves the selection as the host-wide default. The route is validated with `llm.resolveCallConfig`; an unserved route falls back to `agentDefaultModel.currentSelection()` with a line in the dispatch result.
6. **A round cut short by a new operator message ends `superseded`**, a third outcome beside `settled` and `capped` (Rule 5).
7. **The hard-cap cancel keeps the inbox** (`cancel(cause, { keepInbox: true })`); dsh clears it by default.
8. **A pending gate is read from the member's log** — an `ask_user_question` call with no result, or an `approval/asked` with no `approval/decided` — because questions leave no session event.
9. **The engine is installed on the root context by `main.ts`, not as a cordis row** (the spec's "room plugin row"): a root-created member is a runtime root, which is what lets it ask the operator a question (`userQuestions.ask` refuses a runtime-owned child with `DELEGATED_CALLER`) and keeps the gateway from fencing its gates as subagent-owned. `dispatch` is registered globally through `ctx.tools.register`; the bots' allow masks exclude it without naming it (plan 1, deviation 2).
10. **The operator's `@` is a face route**, `POST /data/rooms/say`: the client sends a message containing `@` there first; the route resolves mentions deterministically against the roster (by id; by display name only when one token), appends the message to the room as the operator's own (`kind: 'user'`, `mention: [...]`) without waking Kairos, and turns the named members; a message that names nobody comes back `addressed: []` and the client then sends it as an ordinary prompt. A cold room is made live through the gateway's own composition (`apiProxy.sessions.models`), never composed by the face.

**Spike outcomes** (`FACE_SMOKE=1 npm test`, 2026-09-08, `room-smoke.test.ts`).

- **S5** — restated per deviation 2 and proven: two answers appended to a quiet room log, one `followup`, one turn, the synthesis inside it; a `followup` issued while Kairos ran (the dispatch turn) landed after its `turn/end`.
- **S6** — a member created in-process with `meta: { cwd, parentSession, agentPreset }` and a `setup` of `installModelSelection` + `agentPresets.mount` + `permissionPresets.set` carries `agentPreset` and `parentSessionId` on its `session.list` row, shows the bot's persona in its first assembled prompt, lacks `dispatch` in its schemas, and logs `read-only` as its first event; no "published without joining" warning.
- **S4 for a member** — a bash write from a member into its channel directory came back `isError: false` with `[sandbox: file access denied under read-only mode]` in the content and no file (R10 holds in a room).
- **Plan 1's deferral 4 (home scope)** — <observed: a home session wrote `journal/probe.md` and was refused on `../SOUL.md` with the same marker | or what was seen>.
- **R13** — with the `session-projection-cache` overlay row, `$DSH_HOME/storages/session_projcache.json` carries the room session after Kairos's first `turn/end`; the `room` value rides the `session.list` row for the room and the members.
- **S8 (new)** — the persistence catalog is closed (deviation 1). Recorded here because the spec's §13 table did not know to ask.

**Where the as-built truth now lives.** `face/src/room.ts` (module header), `room-rules.ts`, `room-projection.ts`; the smoke; plan 3 adds the client and `face/README.md`; plan 4 the reference documents and the charter.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md
git commit -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
docs(spec): section 16 records plan 2 - no room/* events (the persistence catalog is closed), answers appended to a quiet room log instead of injected, the read-only pin inside setup, fine states left to the client, and the spike outcomes
```

---

## Self-review (run by the plan's author before handing off)

**Spec coverage, §4 by section.** §4.1 what a room is → Task 6 (`roomOf`, lazy `ensureMember`, membership by header + log) and Task 2 (`bots[]`, the menu). §4.2 what a member sees → Task 3 (`roomLinesOf`, `formatDelta`, `memberPrompt`, the four rules) and Task 6 (`seenIdsOf`, the cursor in the member's log); "not another member's tool calls" holds because only final text enters the room log. §4.3 `dispatch` → Task 8 (validation naming the roster, returns at once, the "not called" clause) and Task 7 (parallel / serial / round end / one wake). §4.4 rules → Task 3 (`resolveMentions`) and Task 7 (`say`, peer continuations, caps reset on every send, an `@` to a running member queued through `enqueue`). §4.5 synthesis → the persona (Task 9) and the round-end text (Task 3). §4.6 caps, timeouts, endings → Task 3 (`ROOM_CAPS`, `finalTextOf`, `isPass`) and Tasks 6–7 (deadline extension, hard cap cancel, failed-counts-as-pass, `capped` vs `settled` vs `superseded`, mid-round operator message). §4.7 roster changes → the roster is re-read on every dispatch (`rosterFor`), so an un-checked bot is no longer resolvable while its session stays in the channel listing; "a preset that is gone refuses visibly" → `failed` with dsh's reason (Task 6 test). §2.4 the per-session configuration → Task 6 (`cwd`, `parentSession`, `agentPreset`, `read-only`, model). §2.5 model → Task 1 + Task 6. §5 "Gate 2 for a bot" is plan 1's (already proven); "a member asks the operator" is a plan 3 rendering concern — the pending gate extends the deadline here (Task 6). §6 projection → Task 4 (coarse states) — fine states deferred to plan 3 by deviation 4. §8 unit list → Tasks 3, 4, 6, 7, 8 tests; the smoke list → Task 10 (S5, S6, read-only, home scope, resume-not-recreate is covered offline in Task 6, `dispatch` absent from a bot, the whole round with a failing stub, `AGENTS.md` chain, the cache). Not in this plan, by design: the client (bubbles, strip, inline gates, `@` in the composer, roster check-in UI, needs-you marks), the live drill, `face/README.md` — plan 3; every reference document and the charter — plan 4.

**Placeholder scan.** Every step carries its code; the two `<…>` in Task 11 are measurements the executor fills from Task 10's run, and the plan says so.

**Type consistency.** `RosterBot` is the one roster shape everywhere (`id`, `name`, `model?`, `broken?`); `RoomChannel` is `{ workspaceId, name, dir }` in `panels.ts`, `room.ts` and the tests; `MessageLike.source` is `{ kind: string } & Record<string, unknown>` and the four source shapes are `type` aliases so they satisfy it; `RoomTurnRecord.state` is `MemberTurnState` and the projection's `MemberCoarseState` adds `called`; `engine.rosterFor` is public (the tool and the `say` tests use it); `installRoom` takes `RoomDeps` and `main.ts` builds it from `panelDeps(...).channelFor` (now with `dir`) and `listBots`.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-08-rooms-2-engine.md`. Execute with **superpowers:subagent-driven-development**: one fresh subagent per task, in order (Tasks 1–11), each reading this plan's header, Global Constraints and its own task; run the offline suite after every task and the smoke after Task 10; review between tasks. Plan 3 (`2026-09-08-rooms-3-client-and-drills.md`) starts only after Task 10's smoke passes.
