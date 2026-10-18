# Gravit Redesign · Plan 1: The Map and the Seam — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gravit's first request carries `GRAVIT.md` (and an optional `GRAVIT.local.md`) as its workspace instructions and nothing of `AGENTS.md` or `CLAUDE.md`; the persona loses its dead `report` reference; the date enters every Gravit prompt; the documents say so.

**Architecture:** dsh-base's `agent-instructions` row is patched by `composeFace` (like the persona patch: after the operator's layers, guarded on the row's presence, the whole config restated) to read `GRAVIT.md` / `GRAVIT.local.md` only. `GRAVIT.md` replaces the old `AGENTS.md` as the map every dsh agent in the tree reads; `AGENTS.md` is rewritten for coding agents. Gravit's default preset gains its first row, the face-owned `face/plugins/gravit.js`, which registers one scoped prompt section, `deployment:today`. Nothing else in the composition, the host plane or the bots changes.

**Tech Stack:** Node 22, TypeScript via tsx, `node --test`; dsh 0.2.0-rc.2 (`@deepseek-ai/dsh-agent-instructions`, `@deepseek-ai/dsh-system-prompt`, `@deepseek-ai/dsh-agent-preset`); plain ESM JavaScript for `face/plugins/*` (loaded by `file:` URL, imports nothing).

**Spec:** `docs/superpowers/specs/2026-10-15-gravit-agent-redesign-design.md` — §4 (the mind layer), §8 (changes by file, the plan-1 rows), §9 (tests), §12 (plan 1). The seams this plan adds are entered in `docs/dsh-upgrade-guide.md` §3.2 group H (spec B10).

## Global Constraints

- **Prerequisite:** `chore/gravit-rename` has merged into `main` and this branch has merged `main`. Every path and identifier below is post-rename: `bots/gravit/`, `Gravit-Design.md`, `gravit-face` (`BIN`), `DEFAULT_PRESET = "gravit"`, `LEGACY_PRESET = "kairos"` (the alias preset the rename keeps, same composition as `gravit`), `isHostPreset`, the bot plugin `gravit-bot`. Task 0 verifies this before anything is written.
- dsh pin unchanged: every `@deepseek-ai/dsh-*` dependency exact at `0.2.0-rc.2` (`face/src/version.ts` `DSH_PIN`; `face/tests/version.test.ts` sweeps). One package is newly declared, at that exact version: `@deepseek-ai/dsh-agent-instructions`.
- The system prompt is a strict `{{…}}` template with no escape: `GRAVIT.md`, `AGENTS.md`, `dsh/profile/persona.md` and every section text `gravit.js` registers contain no `{{`; `gravit.js` sections set `interpolate: false`.
- `GRAVIT.md` is **≤ 4,500 bytes**, English, facts only (no identity, no orders). The `agent-instructions` budget stays `maxBytes: 65536`.
- `face/plugins/gravit.js` imports nothing (it is loaded by a `file:` URL the face rebases), exactly like `face/plugins/bot.js`.
- Tests and gates, run from `face/`: `npm test`, `npm run typecheck` (`skipLibCheck: false`), `FACE_SMOKE=1 npm test` for the real boots (one boot per test file); from the repo root: `python -m pytest`. A task is done only with all four green.
- Commit messages are written to a file and committed with `git commit -F <file>`; never backticks or `$()` inside a `-m` argument (they execute in this harness's shell).
- Docs are a first-class deliverable: `DEVELOPMENT.md` follows the code in the same change (Task 7); the charter changes one word here (D13) and the rest in plan 3.

## Review Focus

1. `GRAVIT.md` growing past its 4,500-byte budget, or past dsh's 65,536-byte baseline cap — the most specific file is truncated last, silently; expected: the suite refuses the growth. Pinned by `face/tests/gravit-md.test.ts` (Task 1).
2. A `GRAVIT.local.md` on the operator's machine that never reaches the prompt — nothing would say so; expected: the local overlay is in the baseline when present. Pinned by `instructions-smoke.test.ts` (Task 4).
3. An operator row for `agent-instructions` in `cordis.patch.yml` silently overridden by the face's patch (it composes after the operator layers); expected: the operator is told where the row is owned. Pinned by `setup.test.ts` on `PATCH_HEADER` (Task 4).
4. The date section at a time-zone boundary — a session started at 23:30 local must read the local date, not UTC's; expected: `Today is <local date>`. Pinned by `todayText`'s zone test (Task 6).
5. The room caps sentence drifting from `ROOM_CAPS` after it moves from `AGENTS.md` to `GRAVIT.md`; expected: the model-facing figures never drift from the engine's. Pinned by `room-rules.test.ts`, re-pointed at `GRAVIT.md` (Task 1).

---

### Task 0: Precondition and baseline

**Files:**
- none created; the branch merges `main`

- [ ] **Step 1: Verify the rename has landed on `main`**

Run (from the worktree `.claude/worktrees/feat+agent-redesign`):
```bash
git ls-tree --name-only main bots/ | grep -x bots/gravit
```
and
```bash
git show main:face/src/overlay.ts | grep -n 'DEFAULT_PRESET = "gravit"'
```
Expected: the first prints `bots/gravit`, the second prints the `DEFAULT_PRESET = "gravit"` line. If either prints nothing, STOP: plan 0 (the rename) has not merged; nothing below may start.

- [ ] **Step 2: Merge `main` into this branch**

Run: `git merge --no-edit main`
Expected: a merge commit or "Already up to date"; no conflicts (this branch holds only `docs/` additions).

- [ ] **Step 3: Install and baseline**

Run: `cd face && npm ci && npm test && npm run typecheck && cd .. && python -m pytest`
Expected: every suite green; note the test counts in the plan's execution log (the offline face suite was 642 pass / 12 skipped at 0.2.0-rc.2 before the rename; the rename added tests).

- [ ] **Step 4: Baseline the real boots once**

Run: `cd face && FACE_SMOKE=1 npm test`
Expected: green. (Each smoke boots its own tree; ~2 minutes.)

---

### Task 1: `GRAVIT.md`, the map every agent reads; `AGENTS.md` for coding agents

**Files:**
- Create: `GRAVIT.md` (repo root)
- Create: `face/tests/gravit-md.test.ts`
- Modify: `AGENTS.md` (rewritten whole)
- Modify: `.gitignore` (append `GRAVIT.local.md`)
- Modify: `face/tests/room-rules.test.ts:24-41` (reads `GRAVIT.md`)
- Modify: `face/tests/channelName.test.ts:12,17` (comment: `AGENTS.md` → `GRAVIT.md`)
- Modify: `CLAUDE.md` (the `AGENTS.md` row, a new `GRAVIT.md` row, the `bots/` row's "inert default", the reading-order line)

**Interfaces:**
- Produces: `GRAVIT.md` whose "Rooms" paragraph carries the sentence `Caps per operator message: 3 rounds, 10 bot messages, 2 peer continuations per round.` (the regex in `room-rules.test.ts` recognizes it), and whose bed table rows are byte-identical to the two data rows of the table in `docs/backtest-rules.md`.

- [ ] **Step 1: Write the failing content test**

`face/tests/gravit-md.test.ts`:
```ts
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const GRAVIT_MD = fileURLToPath(new URL("../../GRAVIT.md", import.meta.url));
const RULES_MD = fileURLToPath(new URL("../../docs/backtest-rules.md", import.meta.url));
/** Spec §4.2: the budget of the one file every dsh agent in the tree reads on its first request. */
const BUDGET_BYTES = 4500;

test("GRAVIT.md fits its budget and contains no template group", () => {
  const text = readFileSync(GRAVIT_MD, "utf8");
  assert.ok(Buffer.byteLength(text, "utf8") <= BUDGET_BYTES, `GRAVIT.md is ${Buffer.byteLength(text, "utf8")} bytes; the budget is ${BUDGET_BYTES}`);
  assert.equal(text.includes("{{"), false, "the system prompt is a strict template with no escape");
});

test("GRAVIT.md's bed table is docs/backtest-rules.md's, row for row", () => {
  const rows = (file: string) => readFileSync(file, "utf8").split("\n").filter((line) => /^\| `data\/pit\//.test(line));
  const expected = rows(RULES_MD);
  assert.equal(expected.length, 2, "backtest-rules.md has the two bed rows");
  assert.deepEqual(rows(GRAVIT_MD), expected, "a bed window changed in one file and not the other");
});

test("GRAVIT.md states facts, not identity: it never tells the reader who it is", () => {
  const text = readFileSync(GRAVIT_MD, "utf8");
  assert.equal(/^You are /m.test(text), false);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd face && npx tsx --test tests/gravit-md.test.ts`
Expected: FAIL — `ENOENT … GRAVIT.md`.

- [ ] **Step 3: Write `GRAVIT.md`**

The exact file (keep the bed rows byte-identical to `docs/backtest-rules.md`'s; the caps sentence verbatim):

````markdown
# GRAVIT.md — the workspace, for every agent dsh runs here

Read by Gravit, its role children and the bots alike, as workspace instructions: facts about
this tree, never anyone's identity or orders. When this file and the tree disagree, the tree is
right and this file is wrong.

Three layers. MARKET and ACCOUNT are the `alpaca_kit` package: import it for backtests
(`alpaca_kit.replay.replay_days`), call its MCP tools for interactive reads. STRATEGY is
`strategies/`: one directory per strategy, Gravit's arena.

## Where things are

- `alpaca_kit/` — the data and account library, and the MCP server the `mcp__alpaca-kit__*`
  tools come from. Prices are RAW/unadjusted everywhere. Corporate actions key on
  announce_date := Alpaca's process_date.
- `strategies/<name>/` — `THESIS.md`, `screen.py`, `backtest.py`, `backtests/`, `journal.md`,
  `status.yaml`; `strategies/_template` is the copy source.
- `data/pit/` — the offline point-in-time beds (the table below). `data/` is gitignored.
- `docs/backtest-rules.md` — the five honest-eval rules every backtest follows.
- `roles/` — Gravit's role library; `bots/` — the operator's voices. Both are the operator's.

## Point-in-time reads

Every dated market read goes through `replay_days` (backtests) or the alpaca-kit MCP tools
(interactive). A bare `make_source()` returns a RAW source with no lookahead guard: wrap it in
`GuardedSource` with an `AsOfGuard` for the day, or do not read it. The AKShare tools
(`mcp__akshare__*`) are public A-share queries with NO guard — never backtest evidence; check
their errors, timestamps and `truncated` (the default limit is 500 rows). Retrieval time is not
exchange time.

## The beds — the only usable windows

| bed | usable window | trading days | 200DMA valid from | 52-week metrics from |
|---|---|---|---|---|
| `data/pit/2yr` | 2024-06-03 .. 2026-07-09 | 526 | 2025-03-20 | 2025-06-04 |
| `data/pit/broad` | 2025-11-17 .. 2026-03-27 | 90 | never | never |

Outside a window a snapshot read raises `SnapshotMissingError`, while bar and corp-action reads
return EMPTY frames and say nothing: bound every replay with `start=` and `end=`. The beds carry
no warmup — `screen(kind="trend_template")` returns nothing before 2025-06-05 on `2yr` and ever
on `broad`. Offline work sets `ALPHA_PIT_ROOT=data/pit/2yr` and `ALPHA_DATA_SOURCE=snapshot`,
both resolved against the CWD; a channel session's shell runs in `strategies/<name>/`, so use
the absolute bed path there (`backtest.py` anchors on its own file and is immune).

## A strategy directory

Lifecycle, in `status.yaml`: `idea | researching | validated | paper | retired` (`paper` is
reserved until the order gate opens). Three optional headline keys the channel page renders:
`one_line`, `next`, `numbers`. Name a strategy as the face names channels: a letter or digit
first, then letters, digits, `-` and `_`, at most 41 code points, no spaces or dots — the name
becomes a path typed into shell by hand, and `cd x y` is zsh's two-argument form, exit 0 in the
wrong directory whenever the substituted path exists. Commit your own iterations; git log is the
audit trail. A new strategy starts with one batched `ask_user_question`, not with code: the
thesis and the falsification terms that would retire it, which bed and which window (warmup
moves the honest start), and what the operator wants measured; a brief that already answers
those is the answer.

## Rooms

A channel whose roster has bots is a room; Gravit organizes it with `dispatch`. Caps per
operator message: 3 rounds, 10 bot messages, 2 peer continuations per round. The operator's
`@<bot>` reaches a voice directly.

## Tests

`python -m pytest` at the repo root: offline, no keys. Keep it green.

## Never edit

`data/pit/` contents; the installed dsh profile copies under the harness home; anything under
`bots/` or `roles/` (propose in conversation — the operator authors them); `docs/research/`.
````

- [ ] **Step 4: Run the content test to verify it passes**

Run: `cd face && npx tsx --test tests/gravit-md.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Re-point the caps pin at `GRAVIT.md`**

In `face/tests/room-rules.test.ts`: the comment at lines 24–28 and the test title at line 29 say `GRAVIT.md`'s "Rooms" paragraph; line 30 reads `new URL("../../GRAVIT.md", import.meta.url)`; the three assertion messages at lines 38–40 say `GRAVIT.md`. The regex at line 33 is unchanged.

- [ ] **Step 6: Run the room-rules test**

Run: `cd face && npx tsx --test tests/room-rules.test.ts`
Expected: PASS, including "GRAVIT.md's caps sentence matches ROOM_CAPS".

- [ ] **Step 7: Rewrite `AGENTS.md` for its remaining readers**

The exact file:

```markdown
# AGENTS.md — for coding agents

This file is read by coding agents working on this repository (Claude Code and Codex read it).
The research agent, Gravit, does not: dsh hands it `GRAVIT.md` and nothing else.

- Read `CLAUDE.md` first — the map, the commands, the gotchas. Depth: `DEVELOPMENT.md`
  (mechanism), `Gravit-Design.md` (intent), `face/README.md` (the face's contracts and drills).
- `GRAVIT.md` is a product file: every dsh agent in the tree reads it on its first request.
  Change it as you would change a prompt — deliberately, inside its byte budget, with
  `face/tests/gravit-md.test.ts` green.
- `strategies/` is Gravit's arena. `bots/`, `roles/`, `data/pit/` and `docs/research/` are the
  operator's: do not edit them unless asked.
- Keep both suites green: `python -m pytest` at the root; `npm test && npm run typecheck` in
  `face/`, plus `FACE_SMOKE=1 npm test` after any change under `face/src`, `face/plugins` or to
  the dsh pins.
- Commit messages go in a file and through `git commit -F`; never backticks or `$()` in `-m`.
```

- [ ] **Step 8: `.gitignore`, the two comments, the `CLAUDE.md` rows**

Append to `.gitignore`:
```
# the operator's machine-local instruction overlay for dsh agents (GRAVIT.md's twin)
GRAVIT.local.md
```
In `face/tests/channelName.test.ts` lines 12 and 17: `AGENTS.md` → `GRAVIT.md`.
In `CLAUDE.md`'s map table: the `AGENTS.md` row reads `for coding agents (Claude Code and Codex read it); Gravit does not — see GRAVIT.md`; a new row directly below it: `` `GRAVIT.md` `` | `the workspace instructions every dsh agent in the tree reads on its first request — facts only, ≤ 4,500 bytes (face/tests/gravit-md.test.ts); the face patches dsh's agent-instructions row to read it and GRAVIT.local.md, nothing else`; the `bots/` row's "`gravit` the inert default" becomes "`gravit` the default, carrying the face's `gravit.js` row (the date section)"; the closing reading-order line ends `→ GRAVIT.md for what Gravit itself sees`.

- [ ] **Step 9: Run the offline suite**

Run: `cd face && npm test && npm run typecheck`
Expected: green.

- [ ] **Step 10: Commit**

```bash
git add GRAVIT.md AGENTS.md .gitignore CLAUDE.md face/tests/gravit-md.test.ts face/tests/room-rules.test.ts face/tests/channelName.test.ts
printf '%s\n' 'feat: GRAVIT.md is the map every dsh agent reads; AGENTS.md is for coding agents' '' 'The caps-sentence pin and the bed-table pin follow it (spec section 4.2).' > /tmp/msg-plan1-t1.txt
git commit -F /tmp/msg-plan1-t1.txt
```

---

### Task 2: The `agent-instructions` patch in `composeFace`

**Files:**
- Create: `face/src/instructions.ts`
- Modify: `face/src/boot.ts:343-378` (after the persona patch)
- Modify: `face/src/setup.ts:39-60` (`PATCH_HEADER` names the row)
- Modify: `face/package.json` (declare `@deepseek-ai/dsh-agent-instructions` at `0.2.0-rc.2`; then `npm install` once to sync the lockfile)
- Modify: `face/tests/boot.test.ts:63-87` (the layer count) and a new test beside line 373
- Modify: `face/tests/setup.test.ts` (one assertion on the header)
- Modify: `face/tests/room-smoke.test.ts:61-65,216` and `face/tests/subagents-smoke.test.ts:68` (the fixture file is `GRAVIT.md`)

**Interfaces:**
- Produces, in `face/src/instructions.ts`:
  - `export const AGENT_INSTRUCTIONS_ROW_ID = "agent-instructions"` (dsh-base's row id, installed `dsh-base/cordis.patch.yml` row `agent-instructions`)
  - `export const INSTRUCTION_FILE = "GRAVIT.md"`, `export const LOCAL_INSTRUCTION_FILE = "GRAVIT.local.md"`
  - `export const INSTRUCTIONS_CONFIG = { maxBytes: 65536, instructionFileCandidates: [INSTRUCTION_FILE], localInstructionFileCandidates: [LOCAL_INSTRUCTION_FILE] } satisfies AgentInstructionsConfig` where `AgentInstructionsConfig` is `import type { Config } from "@deepseek-ai/dsh-agent-instructions"`
  - `export function instructionsPatch(): { id: string; name: "@deepseek-ai/dsh-agent-instructions"; config: typeof INSTRUCTIONS_CONFIG }` — a fresh object per call (the include's patch algorithm assigns into rows by reference).
- Consumes: `composeFace`'s `rows` set and `patches` array (`face/src/boot.ts`).

- [ ] **Step 1: Write the failing composition tests**

Append to `face/tests/boot.test.ts` (the import goes beside the file's other imports at the top):
```ts
import { AGENT_INSTRUCTIONS_ROW_ID, INSTRUCTIONS_CONFIG } from "../src/instructions.ts";

/* Spec §4.1 L3: dsh-base's default candidates are AGENTS.md and CLAUDE.md; the
 * face restates the row's whole config (a named config replaces the row's) so
 * Gravit reads GRAVIT.md and its local twin and nothing else. Composed AFTER
 * the operator layers, like the persona patch, and guarded like it. */
test("composeFace patches agent-instructions to GRAVIT.md and GRAVIT.local.md, after the operator layers", () => {
  const home = freshHome();
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const row = composeEntries([patches]).find((entry) => entry.id === AGENT_INSTRUCTIONS_ROW_ID);
  assert.equal(row?.name, "@deepseek-ai/dsh-agent-instructions");
  assert.deepEqual(row?.config, { maxBytes: 65536, instructionFileCandidates: ["GRAVIT.md"], localInstructionFileCandidates: ["GRAVIT.local.md"] });
  assert.deepEqual(row?.config, INSTRUCTIONS_CONFIG);
  const index = patches.findIndex((patch) => (patch as { id?: string }).id === AGENT_INSTRUCTIONS_ROW_ID);
  const persona = patches.findIndex((patch) => (patch as { id?: string }).id === "system-prompt");
  assert.ok(index > persona, "the instructions patch follows the persona patch");
  assert.equal(index, patches.length - 2, "and precedes only the face overlay");
});
```
In the existing test "composeFace stacks exactly the layers it means to" (line 69), change `5 + policy.length` to `6 + policy.length` and the comment to list "+ agent-instructions".

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd face && npx tsx --test tests/boot.test.ts`
Expected: FAIL — the new test cannot import `../src/instructions.ts`; the layer-count test fails on `5 + policy.length` once the import exists.

- [ ] **Step 3: Declare the package and write `face/src/instructions.ts`**

Add `"@deepseek-ai/dsh-agent-instructions": "0.2.0-rc.2"` to `dependencies` in `face/package.json` (alphabetical position), run `cd face && npm install` once so `package-lock.json` records the direct dependency (it is already installed transitively through dsh-base; the install is a no-op on `node_modules`). Then write the module with the exports in the Interfaces block; a header comment cites the installed `dsh-base/cordis.patch.yml` row `agent-instructions` (`maxBytes: 65536`, no candidates = the package defaults `['AGENTS.md', 'CLAUDE.md']`).

- [ ] **Step 4: Patch the row in `composeFace`**

In `face/src/boot.ts`, directly after the persona patch block (after line 378) and before the overlay push:
```ts
  /* The instructions patch (spec §4.1 L3): the row's whole config restated —
   * a named config REPLACES the row's — so the candidates are exactly ours.
   * Guarded like the persona patch: an unmatched patch is silent. */
  if (rows.has(AGENT_INSTRUCTIONS_ROW_ID)) patches.push(instructionsPatch());
```
Update the `composeFace` doc comment (lines 261–268) to list "the instructions patch" after "Gravit's persona".

- [ ] **Step 5: Run the composition tests**

Run: `cd face && npx tsx --test tests/boot.test.ts && npm run typecheck`
Expected: PASS; tsc clean (the `satisfies` against the package's `Config` is the contract check).

- [ ] **Step 6: Name the row in `PATCH_HEADER` and pin it**

In `face/src/setup.ts` `PATCH_HEADER`, extend the face-owned list sentence: after "the system-prompt persona (personaPrefix only - other system-prompt keys set here are kept)" add ", the agent-instructions row (restated whole: GRAVIT.md and GRAVIT.local.md are the only candidates)". In `face/tests/setup.test.ts` add:
```ts
test("the written patch header names the agent-instructions row the face owns", () => {
  const home = mkdtempSync(join(tmpdir(), "face-setup-"));
  setupFaceProfile(home);
  const header = readFileSync(join(home, "profiles", "face", "cordis.patch.yml"), "utf8");
  assert.match(header, /agent-instructions row/);
  assert.match(header, /GRAVIT\.md and GRAVIT\.local\.md/);
});
```
(Reuse the file's existing imports and temp-dir helper if it has one.)

- [ ] **Step 7: Move the two smoke fixtures to `GRAVIT.md`**

`face/tests/room-smoke.test.ts` line 65: `writeFile(join(root, "GRAVIT.md"), …)`; the comment at lines 61–64 and the assertion message at line 216 say `GRAVIT.md`. `face/tests/subagents-smoke.test.ts` line 68: `writeFile(join(root, "GRAVIT.md"), …)`. (With the patch in force, an `AGENTS.md` fixture would never be read and both smokes would fail on their chain assertions.)

- [ ] **Step 8: Run the offline suite, then the two smokes**

Run: `cd face && npm test && npm run typecheck && FACE_SMOKE=1 npx tsx --test tests/room-smoke.test.ts tests/subagents-smoke.test.ts`
Expected: green.

- [ ] **Step 9: Commit**

```bash
git add face/src/instructions.ts face/src/boot.ts face/src/setup.ts face/package.json face/package-lock.json face/tests/boot.test.ts face/tests/setup.test.ts face/tests/room-smoke.test.ts face/tests/subagents-smoke.test.ts
printf '%s\n' 'feat(face): the agent-instructions row reads GRAVIT.md and GRAVIT.local.md only' '' 'composeFace restates the row after the operator layers, guarded like the persona patch; PATCH_HEADER names it; the two smokes that wrote an AGENTS.md fixture write GRAVIT.md.' > /tmp/msg-plan1-t2.txt
git commit -F /tmp/msg-plan1-t2.txt
```

---

### Task 3: The instructions smoke — what reaches the first request

**Files:**
- Create: `face/tests/instructions-smoke.test.ts`

**Interfaces:**
- Consumes: `bootFace`, `setupFaceProfile`, `makeBotsRoot`, `createBot`, `PLUGIN_ABS`, `renderComposition`, `mountClient`, `remote`, `signIn`, `StubAdapter` — exactly as `face/tests/subagents-smoke.test.ts` and `bots-smoke.test.ts` use them.

- [ ] **Step 1: Write the smoke (it fails until Task 2 is in; it is written after Task 2 so it passes first time — run it to see it PASS, then break it once)**

```ts
/** What dsh-agent-instructions publishes onto a session's log at its first
 * request, on a real tree, after the face's agent-instructions patch (Task 2):
 * GRAVIT.md and GRAVIT.local.md from the .git root down to the cwd, never
 * AGENTS.md or CLAUDE.md, for Gravit, for a channel session and for a bot.
 * Own file, gated: one boot per process. */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { GenerateOptions } from "@deepseek-ai/dsh-llm";
import { SessionId } from "@deepseek-ai/dsh-session";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { createBot, renderComposition } from "../src/bots.ts";
import { makeBotsRoot, PLUGIN_ABS } from "./bots-fixture.ts";
import { mountClient, remote, signIn } from "./remote.ts";
import { StubAdapter } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
const MARK = { root: "GRAVIT_ROOT_7f3a", local: "GRAVIT_LOCAL_7f3a", channel: "GRAVIT_CHANNEL_7f3a", agents: "AGENTS_7f3a", claude: "CLAUDE_7f3a" };

test("instructions smoke: GRAVIT.md and its local twin reach every first request; AGENTS.md and CLAUDE.md never do", {
  skip: gated && "set FACE_SMOKE=1", timeout: 120_000,
}, async () => {
  const bots = await makeBotsRoot();
  const root = await realpath(await mkdtemp(join(tmpdir(), "face-instructions-root-")));
  const home = await mkdtemp(join(tmpdir(), "face-instructions-home-"));
  let dispose: (() => Promise<void>) | undefined;
  try {
    await mkdir(join(root, ".git"));
    await writeFile(join(root, "GRAVIT.md"), `# fixture\n${MARK.root}\n`);
    await writeFile(join(root, "GRAVIT.local.md"), `${MARK.local}\n`);
    await writeFile(join(root, "AGENTS.md"), `${MARK.agents}\n`);
    await writeFile(join(root, "CLAUDE.md"), `${MARK.claude}\n`);
    await mkdir(join(root, "strategies", "x"), { recursive: true });
    await writeFile(join(root, "strategies", "x", "GRAVIT.md"), `${MARK.channel}\n`);
    await createBot(bots, { id: "probe", name: "Probe", soul: "You are Probe, a test voice." });
    await writeFile(join(bots, "probe", "agent.cordis.yml"), renderComposition({ soul: "You are Probe, a test voice.", allow: ["read"], plugin: PLUGIN_ABS }));
    setupFaceProfile(home);
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n- id: agent-default-model\n  config:\n    provider: stub\n    model: echo\n`);
    const booted = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    dispose = booted.dispose;
    const { ctx } = booted;
    ctx.llm.registerAdapter(["stub"], new StubAdapter((_request: GenerateOptions) => ({ kind: "text", text: "ok" })));
    const base = `http://127.0.0.1:${ctx.webServer.port}`;
    mountClient(ctx);
    const cookie = await signIn(ctx, base);
    const baselineOf = async (request: { cwd: string; agentPreset?: string }): Promise<string> => {
      const { sessionId } = await remote<{ sessionId: string }>(base, cookie, "session/create", { request });
      await remote(base, cookie, "session/prompt", { request: { requestId: `instr-${crypto.randomUUID()}`, sessionId, mode: "queue", content: [{ type: "text", text: "hello" }] } });
      const agent = ctx.agents.get(SessionId(sessionId))!;
      await agent.whenIdle();
      const baseline = agent.session.snapshotEvents().filter((event) => event.type === "user/message"
        && ((event.data as { source?: { kind?: string } }).source?.kind === "agent-instructions"));
      assert.ok(baseline.length > 0, `${request.cwd}: an agent-instructions baseline was published`);
      return JSON.stringify(baseline);
    };
    const gravit = await baselineOf({ cwd: root });
    assert.ok(gravit.includes(MARK.root), "GRAVIT.md reaches Gravit");
    assert.ok(gravit.includes(MARK.local), "GRAVIT.local.md reaches Gravit");
    assert.equal(gravit.includes(MARK.agents), false, "AGENTS.md never does");
    assert.equal(gravit.includes(MARK.claude), false, "CLAUDE.md never does");
    const channel = await baselineOf({ cwd: join(root, "strategies", "x") });
    assert.ok(channel.includes(MARK.root) && channel.includes(MARK.channel), "a channel session gets the chain, root down to its own GRAVIT.md");
    assert.equal(channel.includes(MARK.agents) || channel.includes(MARK.claude), false);
    const bot = await baselineOf({ cwd: root, agentPreset: "probe" });
    assert.ok(bot.includes(MARK.root), "the row is host-plane: a bot reads GRAVIT.md too");
    assert.equal(bot.includes(MARK.agents), false);
  } finally {
    await dispose?.();
    await Promise.all([rm(bots, { recursive: true, force: true }), rm(root, { recursive: true, force: true }), rm(home, { recursive: true, force: true })]);
  }
});
```

- [ ] **Step 2: Run it**

Run: `cd face && FACE_SMOKE=1 npx tsx --test tests/instructions-smoke.test.ts`
Expected: PASS.

- [ ] **Step 3: Prove it discriminates**

Temporarily change `INSTRUCTIONS_CONFIG.instructionFileCandidates` in `face/src/instructions.ts` to `["AGENTS.md"]`, run the smoke, expect FAIL on "GRAVIT.md reaches Gravit"; revert. (`boot.test.ts` also fails on the deep-equal; both are the pin.)

- [ ] **Step 4: Run the whole gated suite and commit**

Run: `cd face && FACE_SMOKE=1 npm test`
Expected: green (thirteen real boots now).
```bash
git add face/tests/instructions-smoke.test.ts
printf '%s\n' 'test(face): the instructions smoke pins what reaches a first request' > /tmp/msg-plan1-t3.txt
git commit -F /tmp/msg-plan1-t3.txt
```

---

### Task 4: The persona's dead `report` reference

**Files:**
- Modify: `dsh/profile/persona.md` (the last paragraph, one sentence)
- Modify: `face/tests/persona.test.ts:41-45`

- [ ] **Step 1: Write the failing assertion**

In `face/tests/persona.test.ts`, the test "the shipped persona.md is valid and names Gravit" (post-rename title) gains:
```ts
  assert.equal(text.includes("through report"), false, "the 0.1.1 report tool left dsh at 0.2.0 (tool-subagent-report, b91e7ce366); the persona must not name it");
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/persona.test.ts`
Expected: FAIL on the new assertion.

- [ ] **Step 3: Edit the sentence**

In `dsh/profile/persona.md`, the last paragraph's second sentence currently reads: `Work within that scope, keep the inherited permissions, and return a self-contained result to your parent through report when available.` It becomes: `Work within that scope, keep the inherited permissions, and return a self-contained result to your parent.` Nothing else in the file changes (B6: persona content is the next round's).

- [ ] **Step 4: Run the persona tests and commit**

Run: `cd face && npx tsx --test tests/persona.test.ts tests/bots-smoke.test.ts` (the latter offline-skips; with `FACE_SMOKE=1` it still finds the persona's first `{{`-prefix in the prompt)
Expected: PASS.
```bash
git add dsh/profile/persona.md face/tests/persona.test.ts
printf '%s\n' 'fix(persona): drop the report tool, gone at dsh 0.2.0' > /tmp/msg-plan1-t4.txt
git commit -F /tmp/msg-plan1-t4.txt
```

---

### Task 5: `face/plugins/gravit.js` — the date section, and Gravit's first composition row

**Files:**
- Create: `face/plugins/gravit.js`
- Create: `face/tests/gravit-plugin.test.ts`
- Modify: `bots/gravit/agent.cordis.yml` (from `[]` to one row)
- Modify: `face/src/overlay.ts` (export `GRAVIT_PLUGIN_RELATIVE`)
- Modify: `face/tests/bots-fixture.ts` (the fixture default preset carries the row; export `GRAVIT_PLUGIN_ABS`)
- Modify: `face/tests/bot-presets.test.ts:97-105`, `face/tests/boot.test.ts:359-373`, `face/tests/bots-smoke.test.ts:120-130`

**Interfaces:**
- Produces, in `face/plugins/gravit.js` (plain ESM, no imports):
  - `export const name = "gravit"`; `export const inject = ["systemPrompt"]`
  - `export const TODAY_SECTION = "deployment:today"`
  - `export function validateGravitConfig(config: unknown): string | undefined` — `undefined` when valid. Valid: a plain object; `cycle`, when present, a non-empty string; `roles`, when present, an array of `{ tool: string, summary: string }` with `tool` matching `/^role_[a-z0-9_]+$/` and `summary` non-empty. (Plans 2 and 3 fill those keys; this plan ships `config: {}`.)
  - `export function todayText(now: Date, timeZone: string): string` — exactly `Today is YYYY-MM-DD, Weekday (Zone).` in that zone, e.g. `Today is 2026-10-18, Sunday (America/New_York).`
  - `export function apply(ctx, config)` — validates (throws `gravit: <reason>` otherwise); registers through `ctx.effect` one section `{ name: TODAY_SECTION, order: ctx.systemPrompt.getSectionOrder("DEPLOYMENT_PERSONA_PREFIX") + 1, interpolate: false, text: () => todayText(new Date(), Intl.DateTimeFormat().resolvedOptions().timeZone) }` (a context-resolved text, re-evaluated at each assembly — dsh-system-prompt README "Sections carry static or context-resolved text"; the installed `Section` type is the contract tsc does not see here, so the test below pins the shape against the installed `SystemPrompt`).
- Produces, in `face/src/overlay.ts`: `export const GRAVIT_PLUGIN_RELATIVE = "../../face/plugins/gravit.js"` (relative from `bots/gravit/`, as `BOT_PLUGIN_RELATIVE` is from `bots/<id>/`).
- Produces, in `face/tests/bots-fixture.ts`: `export const GRAVIT_PLUGIN_ABS = join(REPO, "face", "plugins", "gravit.js")`; `populateBotsRoot(root, gravitPlugin = GRAVIT_PLUGIN_RELATIVE)` writes `bots/gravit/agent.cordis.yml` as one row `{ id: "gravit", name: gravitPlugin, config: {} }` (`js-yaml` `dump`, as `renderComposition` does); `makeBotsRoot()` passes `GRAVIT_PLUGIN_ABS` (a temp root rebases the relative path to nowhere), `makeRepoBotsRoot()` keeps the relative default (the shipped path, exercised).

- [ ] **Step 1: Write the failing plugin test**

`face/tests/gravit-plugin.test.ts` (the `fakeTree` of `bot-plugin.test.ts` reduced to `effect`, `systemPrompt.section`, `systemPrompt.getSectionOrder`):
```ts
import test from "node:test";
import assert from "node:assert/strict";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import { TODAY_SECTION, apply, inject, name, todayText, validateGravitConfig } from "../plugins/gravit.js";

const dshSectionOrder = (slot: "DEPLOYMENT_PERSONA_PREFIX"): number => SystemPrompt.prototype.getSectionOrder(slot);

function fakeScope() {
  const sections: Array<{ name: string; order: number; interpolate?: boolean; text: unknown }> = [];
  const disposers: Array<() => unknown> = [];
  const ctx = {
    effect(fn: () => unknown) { const d = fn(); assert.equal(typeof d, "function"); disposers.push(d as () => unknown); return d; },
    systemPrompt: {
      section(section: { name: string; order: number; interpolate?: boolean; text: unknown }) {
        sections.push(section);
        return () => { sections.splice(sections.indexOf(section), 1); };
      },
      getSectionOrder: (slot: "DEPLOYMENT_PERSONA_PREFIX") => dshSectionOrder(slot),
    },
  };
  return { ctx, sections, unload: () => { for (const d of disposers.splice(0).reverse()) d(); } };
}

test("gravit: name and inject are what the composition relies on", () => {
  assert.equal(name, "gravit");
  assert.deepEqual(inject, ["systemPrompt"]);
  assert.equal(TODAY_SECTION, "deployment:today");
});

test("validateGravitConfig: {} is valid; cycle and roles are checked when present", () => {
  assert.equal(validateGravitConfig({}), undefined);
  assert.match(validateGravitConfig(null) ?? "", /object/);
  assert.match(validateGravitConfig({ cycle: "" }) ?? "", /cycle/);
  assert.equal(validateGravitConfig({ cycle: "Open one goal per cycle." }), undefined);
  assert.match(validateGravitConfig({ roles: [{ tool: "screener", summary: "x" }] }) ?? "", /role_/);
  assert.match(validateGravitConfig({ roles: [{ tool: "role_screener", summary: "" }] }) ?? "", /summary/);
  assert.equal(validateGravitConfig({ roles: [{ tool: "role_screener", summary: "runs the screen" }] }), undefined);
});

test("todayText renders the LOCAL date of the zone, ISO date then weekday", () => {
  assert.equal(todayText(new Date("2026-10-18T12:00:00Z"), "America/New_York"), "Today is 2026-10-18, Sunday (America/New_York).");
  assert.equal(todayText(new Date("2026-10-18T03:00:00Z"), "America/New_York"), "Today is 2026-10-17, Saturday (America/New_York).");
  assert.equal(todayText(new Date("2026-10-18T03:00:00Z"), "Asia/Shanghai"), "Today is 2026-10-18, Sunday (Asia/Shanghai).");
});

test("apply registers exactly one scoped, uninterpolated section right after the persona slot, and unload removes it", () => {
  const tree = fakeScope();
  apply(tree.ctx, {});
  assert.equal(tree.sections.length, 1);
  const [section] = tree.sections;
  assert.equal(section.name, TODAY_SECTION);
  assert.equal(section.order, dshSectionOrder("DEPLOYMENT_PERSONA_PREFIX") + 1);
  assert.equal(section.interpolate, false);
  assert.equal(typeof section.text, "function");
  assert.match((section.text as () => string)(), /^Today is \d{4}-\d{2}-\d{2}, [A-Z][a-z]+ \(.+\)\.$/);
  tree.unload();
  assert.equal(tree.sections.length, 0);
});

test("apply refuses a bad config with its reason", () => {
  assert.throws(() => apply(fakeScope().ctx, { cycle: 7 }), /gravit: .*cycle/);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd face && npx tsx --test tests/gravit-plugin.test.ts`
Expected: FAIL — cannot find `../plugins/gravit.js`.

- [ ] **Step 3: Write `face/plugins/gravit.js`**

Per the Interfaces block. `todayText`: `new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now)` gives `YYYY-MM-DD`; `new Intl.DateTimeFormat("en-US", { timeZone, weekday: "long" }).format(now)` gives the weekday. The header comment states: imports nothing (loaded by `file:` URL, rebased by `definitionFor`); the section is SCOPED to the preset revision's standing layer, so only sessions joined to Gravit's preset see it (bots never do); `interpolate: false` because the text is not a template; order = the persona slot + 1 so the date follows identity.

- [ ] **Step 4: Run the plugin test**

Run: `cd face && npx tsx --test tests/gravit-plugin.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Gravit's composition carries the row; the fixtures follow**

`bots/gravit/agent.cordis.yml` becomes:
```yaml
# bots/gravit/agent.cordis.yml
# Gravit's composition. Every row here reaches every Gravit session (and the
# legacy alias preset, which declares the same rows) and nothing else's. Plan 1
# of the 2026-10-15 redesign: the face's gravit plugin, the date section. Plan 2
# makes this file a GENERATED mirror of roles/ and adds the role rows.
- id: gravit
  name: ../../face/plugins/gravit.js
  config: {}
```
`face/src/overlay.ts`: add `GRAVIT_PLUGIN_RELATIVE` beside `DEFAULT_PRESET`, with the comment that `definitionFor` rebases it to an absolute `file:` URL (dsh resolves a preset's rows against the declaring context's base). `face/tests/bots-fixture.ts`: per the Interfaces block.

Update the three tests:
- `face/tests/bot-presets.test.ts` (the two tests at ~97–105): the default's `plugins` deep-equals `[{ id: "gravit", name: pathToFileURL(GRAVIT_PLUGIN_ABS).href, config: {} }]` (import `pathToFileURL` from `node:url`); the assertion message reads "the shipped default composes the gravit plugin and nothing else; the host roster is untouched because the plugin masks no tool".
- `face/tests/boot.test.ts` (~364–373): the expected `plugins` is the same one-row list.
- `face/tests/bots-smoke.test.ts` S3 (~120–130): keep `names(tools.schemas(gravit))` equal to `names(tools.schemas())` ("the gravit plugin masks nothing"); add `assert.match(await promptOf(gravit), /\nToday is \d{4}-\d{2}-\d{2}, [A-Z][a-z]+ \(.+\)\.\n/, "the date section is in Gravit's prompt (plan 1)")` and, in the bot block (~138–141), `assert.equal(probePrompt.includes("Today is "), false, "the section is scoped to Gravit's preset: a bot never sees it")`.

- [ ] **Step 6: Run the offline suite and the bots smoke**

Run: `cd face && npm test && npm run typecheck && FACE_SMOKE=1 npx tsx --test tests/bots-smoke.test.ts tests/room-smoke.test.ts`
Expected: green. (room-smoke mounts the fixture default too; a broken `gravit` row would refuse the boot there — that refusal is the fail-loud contract of spec §5.1.)

- [ ] **Step 7: Commit**

```bash
git add face/plugins/gravit.js face/tests/gravit-plugin.test.ts bots/gravit/agent.cordis.yml face/src/overlay.ts face/tests/bots-fixture.ts face/tests/bot-presets.test.ts face/tests/boot.test.ts face/tests/bots-smoke.test.ts
printf '%s\n' 'feat(face): gravit.js, the date section, as the first row of the default preset' '' 'Scoped to Gravit sessions; the host roster is untouched. The fixtures carry the row by absolute path, the repo composition by the shipped relative path.' > /tmp/msg-plan1-t5.txt
git commit -F /tmp/msg-plan1-t5.txt
```

---

### Task 6: The documents follow the tree

**Files:**
- Modify: `DEVELOPMENT.md` §3.3 (rewritten: `GRAVIT.md`), §3.7 (the "State" paragraph: the default is no longer an empty composition), §4.3 (a paragraph "The instructions patch" after "The persona patch"), §7.3 (two new test files: `gravit-md.test.ts`, `gravit-plugin.test.ts`; one new real boot: `instructions-smoke.test.ts`, the count becomes thirteen), §4.2 module table (a row for `src/instructions.ts`; the `plugins/` row mentions `gravit.js`)
- Modify: `dsh/README.md` (every line that says dsh reads `AGENTS.md` now says `GRAVIT.md`; the "Notes → Editing" sentence names `GRAVIT.md`'s never-edit list)
- Modify: `face/README.md` ("Tests": the boot count and the table row for `instructions-smoke.test.ts`; "The profile": one sentence on the instructions patch beside the persona patch; the room drill step that names the channel's `AGENTS.md` chain says `GRAVIT.md`)
- Modify: `Gravit-Design.md` D13 (one word: the prohibition is carried by `GRAVIT.md` and review)
- Modify: `docs/dsh-upgrade-guide.md` (§3.1: the H6 row's "where" cell names `face/src/instructions.ts` and the row leaves the hand-check table for §3.2 group H as `H10 the face's instructions patch (boot.test.ts, instructions-smoke)`; §7.3: the first bullet is marked landed in plan 1)

- [ ] **Step 1: Find every statement that is now false**

Run: `grep -n "AGENTS.md" DEVELOPMENT.md dsh/README.md face/README.md Gravit-Design.md CLAUDE.md docs/dsh-upgrade-guide.md`
Expected: a list; each hit is either about coding agents (keep) or about what dsh loads / what Gravit reads (change to `GRAVIT.md`).

- [ ] **Step 2: Write `DEVELOPMENT.md` §3.3**

Replace the section with:
```markdown
### 3.3 `GRAVIT.md`

The workspace map every dsh agent in the tree reads on its first request — Gravit, its role
children and the bots alike — so it states facts only: the three layers and where each lives,
the PIT rule, the strategy directory contract and lifecycle, the bed windows (its table is
pinned row for row to `docs/backtest-rules.md`), the room caps sentence (pinned to
`ROOM_CAPS`), the never-edit list. Budget 4,500 bytes, no `{{` (`face/tests/gravit-md.test.ts`).

Discovery is dsh's (`dsh-agent-instructions`, the `agent-instructions` row dsh-base mounts,
64 KiB budget), but the candidates are the face's: `composeFace` restates the row's config
(`src/instructions.ts`: `instructionFileCandidates: ["GRAVIT.md"]`,
`localInstructionFileCandidates: ["GRAVIT.local.md"]`) after the operator's layers, so
`AGENTS.md` and `CLAUDE.md` are never read by any agent in the tree — `AGENTS.md` is the coding
agents' file now, `CLAUDE.md` Claude Code's. The loader walks from the `.git` root down to the
session's cwd, so a channel session also reads any `strategies/<name>/GRAVIT.md`; a gitignored
`GRAVIT.local.md` beside the root file is the operator's machine-local overlay
(`tests/instructions-smoke.test.ts` pins all three readers and both exclusions). Two dsh facts
the patch does not change (installed `dsh-agent-instructions/lib/index.js`, `USER_GLOBAL_FILE`
and the baseline identity): the user-global file is hard-coded `$DSH_HOME/AGENTS.md` and still
loads when the operator has one, and the candidate list is part of the baseline's identity, so
a session resumed across this change receives one replacement baseline. The facts
`GRAVIT.md` shares with `CLAUDE.md` (beds, RAW, warmup) are repeated in `docs/backtest-rules.md`,
both mechanics skills, `scripts/face_data.py`, `strategies/_template/backtest.py` and §2.4; when a
bed changes, all of them move.
```

- [ ] **Step 3: The other sections, the README rows, the charter word, the guide rows**

Per the Files list. `DEVELOPMENT.md` §4.3's new paragraph states the mechanism in one sentence each: the row, the restated config, the guard, the position after the persona patch, the `PATCH_HEADER` line, and that an operator row for it is overridden silently like a persona row. §3.7's state paragraph: "`bots/gravit` is the default composition every session that names no preset joins; since plan 1 of the 2026-10-15 redesign it carries one row, the face's `gravit.js` (the `deployment:today` section, scoped to Gravit's sessions), and masks no tool, so Gravit's tools stay exactly the host's."

- [ ] **Step 4: Verify nothing stale remains, then the suites**

Run: `grep -n "hands Kairos\|hands Gravit this file\|AGENTS.md \*and\* \`CLAUDE.md\`" CLAUDE.md DEVELOPMENT.md dsh/README.md face/README.md ; cd face && npm test && npm run typecheck`
Expected: the grep prints nothing; the suites are green.

- [ ] **Step 5: Commit**

```bash
git add DEVELOPMENT.md dsh/README.md face/README.md Gravit-Design.md docs/dsh-upgrade-guide.md
printf '%s\n' 'docs: GRAVIT.md and the instructions patch in DEVELOPMENT.md, the READMEs, the charter word and the upgrade guide' > /tmp/msg-plan1-t6.txt
git commit -F /tmp/msg-plan1-t6.txt
```

---

### Task 7: Measure the first request

**Files:**
- Modify: `DEVELOPMENT.md` §4.3 (the measured numbers, beside the 2026-10-10 figures)

- [ ] **Step 1: Boot the real face on the operator's home with keys, once**

This is the operator's drill (the face needs `.env.deepseek` and `.env.alpaca`, which the preview sandbox cannot read): in the operator's Terminal panel, from the primary checkout after this branch has merged, `cd face && npm start`; open the printed `?token=` URL; `+ new` in the repo root; send one word.

- [ ] **Step 2: Read the projection cache**

Run: `ls -t ~/.dsh/storages/session_projcache/sessions | head -1` then `python3 -c "import json,sys,glob,os; p=max(glob.glob(os.path.expanduser('~/.dsh/storages/session_projcache/sessions/*.json')), key=os.path.getmtime); d=json.load(open(p)); print(json.dumps(d.get('contextBreakdown', d), indent=1)[:2000])"`
Expected: `messages` well under the 4,040 heuristic tokens of 2026-10-10 (the instructions baseline was 3,443 of it; `GRAVIT.md` is ≤ 4,500 bytes ≈ 1,200 tokens); `system` up by the date line only; `tools` unchanged.

- [ ] **Step 3: Record and commit**

Add the three measured numbers to `DEVELOPMENT.md` §4.3 next to the 2026-10-10 figures, with the date and the session id.
```bash
git add DEVELOPMENT.md
printf '%s\n' 'docs: the first-request measurement after plan 1' > /tmp/msg-plan1-t7.txt
git commit -F /tmp/msg-plan1-t7.txt
```

---

## Self-review (done while writing)

- **Spec coverage.** §4.1 L3 (Task 2), §4.2 (Task 1), §4.3 (Task 1), §4.4 (Task 5), B6's two persona edits (the rename does the name; Task 4 the sentence), §8 plan-1 rows (Tasks 1–6), §9's `boot.test.ts`, `policy.test.ts` unchanged (verified: the patch is not a policy default), `instructions-smoke`, `gravit-plugin.test.ts`, the `room-smoke`/`subagents-smoke` fixture moves, §12 plan 1 (the measurement, Task 7). §10's charter edits are plan 3's except D13's word.
- **Step scan.** Every code step names its file and signature; the two long verbatim texts (`GRAVIT.md`, `AGENTS.md`) are exact copy the spec outlined and the implementer cannot invent; `gravit.js`'s body is left to the implementer except the two `Intl` calls, which the zone test pins.
- **Type consistency.** `INSTRUCTIONS_CONFIG` / `instructionsPatch()` / `AGENT_INSTRUCTIONS_ROW_ID` (Task 2) are the names Task 6's docs cite; `GRAVIT_PLUGIN_RELATIVE` (overlay.ts) and `GRAVIT_PLUGIN_ABS` (bots-fixture.ts) are the two path constants Task 5's three test edits use; `TODAY_SECTION`, `todayText`, `validateGravitConfig`, `apply` are the plugin's exports its test imports.
- **Review Focus.** All five pinned (Tasks 1, 4, 2, 5, 1).
- **Proportion.** The plan is about 1.3× the spec's length; the two verbatim files are the bulk and are deliverables.
