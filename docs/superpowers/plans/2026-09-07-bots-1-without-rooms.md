# Bots Without Rooms — Implementation Plan (plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After this plan the operator can create a bot from a form, talk to it at its home, and see it listed beside Kairos — Kairos is told who it is for the first time, every session joins a dsh agent preset, and a bot's tools are a mask over Kairos's roster.

**Architecture:** The face mounts `@deepseek-ai/dsh-agent-presets` with the repository's `bots/` directory as its only root and an inert `kairos` preset as the default. A bot is a directory `bots/<id>/` whose `agent.cordis.yml` names one face-owned, dependency-free plugin (`face/plugins/bot.js`) that registers the bot's persona section and an allow-list tool mask into the preset's scope, plus a `dsh-skill-filesystem` row for its stance pack. Bot home sessions are created by the existing client through the gateway's own `session.create({ cwd, agentPreset })`, which mounts the preset itself — no in-process agent creation in this plan. Kairos's identity is the `system-prompt` row's `persona` config, set from `dsh/profile/persona.md` by a face-owned patch.

**Tech Stack:** Node 22 · TypeScript (`tsc --noEmit`, no build step — `tsx` runs sources directly) · `node:test` via `tsx --test tests/*.test.ts` (one process per file) · dsh `0.1.1-rc.2` exact (`face/src/version.ts` `DSH_PIN`) · cordis `4.0.2` · js-yaml `4.3.2` · plain-ESM browser client with no bundler and no cache headers.

**Spec:** `docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md` — read §1, §2, §3, §7, §8, §13, §14 before Task 1. This plan is its §14 item 1. Rooms (`dispatch`, member sessions, the participants strip, the roster's `bots[]`) are plans 2–3; the charter amendment is plan 4.

**Deviations from the spec, to be recorded in its post-build amendments block:**
1. **One face-owned plugin instead of `@deepseek-ai/dsh-persona` + `kairos-face/bot-mask`.** `dsh-persona` is not in the face's bundle and its registry availability is unverified; the mask needs a face plugin anyway; and dsh's own `dsh-subagent` composes a child exactly this way — a scoped `deployment:persona` section plus `tools.restrict` (`dsh-subagent/lib/index.js:570-582`). So `face/plugins/bot.js` does both. Spec S1 (`!!js` reading `SOUL.md`) is moot: the face writes the persona text into the composition, as the spec's fallback already said.
2. **The mask is an `allow` list, not a `deny` list.** `dsh-tools/README.md:22`: "Deny masks admit later unnamed globals, while allow masks exclude later names." The tools a bot must never have are exactly the ones registered *after* the mount — `agent_<bin>` on connect, `mcp__…__place_order` when the MCP server comes up, `dispatch` in plan 2. An allow list excludes them without naming them.
3. **Spec S6 (in-process composed session) is not needed here.** The gateway's `session.create` accepts `agentPreset` and performs the mount in its own `setup` (`dsh-host-apiproxy/lib/index.js:454-460, 1754-1768, 2104-2118`). Home sessions ride that path from the client. S6 moves to plan 2 (member sessions need `parentSession` and the `read-only` pin).

## Global Constraints

- Every `@deepseek-ai/dsh-*` dependency is pinned **exactly** `0.1.1-rc.2`; `face/tests/version.test.ts` sweeps `dependencies` and `devDependencies` programmatically and fails on any other range or installed version. Run `npm install` in `face/` after editing `package.json`.
- **One `bootFace` per test process** (`face/tests/smoke.test.ts:12-22`): every FACE_SMOKE test is its own `face/tests/<name>.test.ts`, gated `skip: gated && "set FACE_SMOKE=1"`, booting into a `mkdtempSync` home via `setupFaceProfile(home)`; never `~/.dsh`.
- Bot id grammar is dsh's preset-id grammar `[a-z0-9][a-z0-9-]*` (`dsh-agent-presets/README.md:11`); `_template` and `kairos` are refused as ids by the face.
- The dsh system prompt is a **strict `{{…}}` template with no escape** (`dsh-system-prompt/README.md:13, 88`). `dsh/profile/persona.md` may reference only `{{model}}` and `{{cwd}}`; a bot's persona text may contain no `{{` at all. Both are validated where they are read and refused where they are written.
- Authoring is the face's own filesystem write, never `ctx.agentPresets.copy()` (it re-tightens the tree to owner-only permissions, `dsh-agent-presets/README.md:61`).
- Rule 5: a broken preset is listed with its reason, never skipped; a bot directory the preset roster does not report is shown as such.
- Rule 2: the mask is *visibility*, not authority — every doc sentence says so; write asymmetry is the sandbox (plan 2).
- Docs cite files and symbols, never line numbers (`DEVELOPMENT.md` "Citation rule").
- `face/client/*` is served with no cache headers: **hard-reload** the browser after any client edit before believing what you see.
- Every log line is `${BIN}: …` with `const BIN = "kairos-face"` declared per module.
- Commit after every task (`git commit -F <file>` when the message carries backticks or parentheses).
- Nothing in this plan edits `Kairos-Design.md` or `CLAUDE.md` (plan 4).

## File Structure

| File | Responsibility |
|---|---|
| `face/plugins/bot.js` (new) | the bot composition plugin `kairos-bot`: validates config, registers the `deployment:persona` section and the allow-list `tools.restrict` into the calling (preset) scope; dependency-free ESM |
| `face/src/persona.ts` (new) | `validatePersonaTemplate`, `readPersona` — Kairos's deployment persona, read at compose time, refused if malformed |
| `face/src/overlay.ts` | + the `agent-presets` row (`bots/` root, default `kairos`, no user root); `faceOverlay` gains a `botsRoot` parameter |
| `face/src/boot.ts` | + the `system-prompt` persona patch beside the `hmr` patch; + boot assertion that the roster and its default mount; `FaceBootOptions.botsRoot?` |
| `face/src/setup.ts` | the patch header names the two new face-owned row ids |
| `face/src/bots.ts` (new) | `isBotId`, `renderComposition`, `renderPresetMeta`, `createBot`, `updateSoul`, `listBots`, `registerBotRoutes` (`GET /data/bots.json`, `POST /data/bots`, `POST /data/bots/soul`) |
| `face/src/main.ts` | wires `registerBotRoutes` |
| `face/client/botId.js` (new) | `proposeBotId(displayName)` — pure, browser-shipped |
| `face/client/grouping.js` | `bucketFor(channel, archived, bot)` + `BOT_KEY_PREFIX`, `isBotKey` |
| `face/client/chat.js` | Bots section on the agent face; bot page (home, soul editor); New bot form; `pendingAgentPreset`; bot buckets in the sidebar; collapsed-key filter; `knownFolders` exclusion |
| `bots/_template/` (new) | `agent.cordis.yml`, `preset.yml`, `SOUL.md`, `README.md`, `skills/README.md`, `journal/notes.md` |
| `bots/kairos/` (new) | `agent.cordis.yml` (`[]`), `preset.yml` |
| `dsh/profile/persona.md` (new) | Kairos's deployment persona |
| `face/tests/bot-plugin.test.ts`, `persona.test.ts`, `bots.test.ts`, `botId.test.ts` (new); `grouping.test.ts`, `overlay.test.ts`, `boot.test.ts` (modified) | offline |
| `face/tests/bots-smoke.test.ts`, `bot-sandbox-smoke.test.ts`, `askuser-noclient-smoke.test.ts` (new) | FACE_SMOKE, one boot each |
| `face/README.md`, `DEVELOPMENT.md`, `AGENTS.md` | the Bots section and drill; mechanism rows; `bots/` on the never-edit line |

**Test fixtures shared by several tasks** — put this helper in `face/tests/bots-fixture.ts` in Task 4 and import it from every later test:

```ts
// face/tests/bots-fixture.ts
import { mkdtemp, mkdir, writeFile, cp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
/** Absolute path of the real plugin file: a temp bots root cannot reach it by `../../face/…`. */
export const PLUGIN_ABS = join(REPO, "face", "plugins", "bot.js");

/** A throwaway `bots/` root: the repo's real `_template`, an inert `kairos`, and nothing else. */
export async function makeBotsRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "face-bots-"));
  await cp(join(REPO, "bots", "_template"), join(root, "_template"), { recursive: true });
  await mkdir(join(root, "kairos"));
  await writeFile(join(root, "kairos", "agent.cordis.yml"), "[]\n");
  await writeFile(join(root, "kairos", "preset.yml"), "name: Kairos\ndescription: the principal agent\n");
  return root;
}
```

---

### Task 1: The bot composition plugin `face/plugins/bot.js`

**Files:**
- Create: `face/plugins/bot.js`
- Test: `face/tests/bot-plugin.test.ts`

**Interfaces:**
- Consumes: nothing (dependency-free; the loader resolves it by a relative path from a preset directory, `dsh-agent-presets/README.md:65-69`).
- Produces: `name = "kairos-bot"`, `inject = ["systemPrompt", "tools"]`, `validateBotConfig(config): string | undefined`, `expandAllow(allow: string[], known: Set<string>): { allow: string[]; missing: string[] }`, `apply(ctx, config)`. Config shape `{ persona: string; allow: string[] }`. Task 4 renders this row into every composition; Task 7 proves it on a real tree.

- [ ] **Step 1: Write the failing test**

```ts
// face/tests/bot-plugin.test.ts
import test from "node:test";
import assert from "node:assert/strict";
// Plain ESM JS (the dsh loader imports it by path); tsconfig `allowJs` lets tsx import it here.
import { apply, expandAllow, inject, name, validateBotConfig } from "../plugins/bot.js";

test("kairos-bot: name and inject are what the composition relies on", () => {
  assert.equal(name, "kairos-bot");
  assert.deepEqual(inject, ["systemPrompt", "tools"]);
});

test("validateBotConfig refuses what would fail at render or mount, and accepts the template shape", () => {
  assert.equal(validateBotConfig({ persona: "You are Probe.", allow: ["bash"] }), undefined);
  assert.match(validateBotConfig(null) ?? "", /object/);
  assert.match(validateBotConfig({ persona: "", allow: ["bash"] }) ?? "", /persona/);
  assert.match(validateBotConfig({ persona: "Hi {{model}}", allow: ["bash"] }) ?? "", /\{\{/);
  assert.match(validateBotConfig({ persona: "x", allow: [] }) ?? "", /allow/);
  assert.match(validateBotConfig({ persona: "x", allow: ["bash", 3] }) ?? "", /allow/);
});

test("expandAllow keeps exact names that exist, expands mcp__*__<raw> against the tree, and reports the rest", () => {
  const known = new Set(["bash", "read", "mcp__alpaca-kit__earnings", "mcp__alpaca-kit__place_order", "agent_claude"]);
  const out = expandAllow(["bash", "mcp__*__earnings", "web_search", "mcp__*__orders"], known);
  assert.deepEqual(out.allow, ["bash", "mcp__alpaca-kit__earnings"]);
  assert.deepEqual(out.missing, ["web_search", "mcp__*__orders"]);
});

test("apply registers the persona section at order 0 and one allow-list restriction, both through effects", () => {
  const sections: unknown[] = [];
  const restrictions: unknown[] = [];
  const warnings: string[] = [];
  const ctx = {
    effect(fn: () => unknown) { return fn(); },
    logger: { warn: (m: string) => { warnings.push(m); } },
    systemPrompt: { section(s: unknown) { sections.push(s); return () => {}; } },
    tools: {
      schemas: () => [{ name: "bash" }, { name: "read" }, { name: "subagent" }],
      restrict(r: unknown) { restrictions.push(r); return () => {}; },
    },
  };
  apply(ctx, { persona: "You are Probe, a test voice.", allow: ["bash", "read", "web_search"] });
  assert.deepEqual(sections, [{ name: "deployment:persona", order: 0, text: "You are Probe, a test voice." }]);
  assert.deepEqual(restrictions, [{ allow: ["bash", "read"] }]);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /web_search/);
});

test("apply throws before touching the tree when no allowed tool exists", () => {
  const ctx = {
    effect(fn: () => unknown) { return fn(); },
    systemPrompt: { section() { throw new Error("must not be reached"); } },
    tools: { schemas: () => [{ name: "bash" }], restrict() { throw new Error("must not be reached"); } },
  };
  assert.throws(() => apply(ctx, { persona: "x", allow: ["nothing_here"] }), /none of the allowed tools/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd face && npx tsx --test tests/bot-plugin.test.ts`
Expected: FAIL — `Cannot find module '../plugins/bot.js'`.

- [ ] **Step 3: Write the plugin**

```js
// face/plugins/bot.js
/**
 * `kairos-bot` — the one plugin every bot composition mounts.
 *
 * A bot is a dsh agent preset (`bots/<id>/agent.cordis.yml`, spec §2). Its
 * composition names this file by a RELATIVE path (`../../face/plugins/bot.js`),
 * which the preset mount resolves from the preset's own directory
 * (dsh-agent-presets README, "A relative path still resolves from the preset's
 * own directory"). From `bots/` no `node_modules` is reachable, so this file
 * imports nothing: the persona goes in through `ctx.systemPrompt.section`, the
 * mask through `ctx.tools.restrict`, both registered into the CALLING context's
 * scope — the preset's standing layer — so they cover every agent joined to the
 * preset and nothing else. dsh-subagent composes a child the same way.
 *
 * WHAT THIS IS NOT. The mask is visibility, not authority (dsh-tools README:
 * "live visibility composition, not an authority boundary"). What a bot may
 * WRITE is its session's sandbox mode; what it may ORDER is Gate 2. Spec D12.
 *
 * `allow`, not `deny`: dsh admits later-registered globals through a deny
 * mask and excludes them through an allow mask. The tools a voice must never
 * see — `agent_<bin>` on connect, `mcp__…__place_order` when the MCP server
 * comes up, `dispatch` in plan 2 — are all registered AFTER the mount.
 */
export const name = "kairos-bot";
export const inject = ["systemPrompt", "tools"];

/** The dsh system prompt is a strict `{{…}}` template with no escape; a bot's
 *  persona interpolates nothing, so any `{{` would fail every render. */
export function validateBotConfig(config) {
  if (config === null || typeof config !== "object") return "config must be an object";
  const { persona, allow } = config;
  if (typeof persona !== "string" || persona.trim() === "") return "persona must be a non-empty string";
  if (persona.includes("{{")) return "persona must not contain '{{' (the system prompt is a strict template with no escape)";
  if (!Array.isArray(allow) || allow.length === 0 || allow.some((n) => typeof n !== "string" || n === "")) {
    return "allow must be a non-empty array of tool names";
  }
  return undefined;
}

/** Resolve the allow list against the tools the tree actually has: exact names
 *  pass when present; `mcp__*__<raw>` expands to every MCP tool with that raw
 *  name whatever the operator named the server; everything else is reported,
 *  because `tools.restrict` rejects a name it does not know. */
export function expandAllow(allow, known) {
  const out = [];
  const missing = [];
  for (const entry of allow) {
    const star = /^mcp__\*__(.+)$/.exec(entry);
    if (star !== null) {
      const raw = star[1];
      const hits = [...known].filter((n) => /^mcp__[^_].*__/.test(n) && n.endsWith(`__${raw}`)).sort();
      if (hits.length === 0) missing.push(entry);
      else out.push(...hits);
      continue;
    }
    if (known.has(entry)) out.push(entry);
    else missing.push(entry);
  }
  return { allow: out, missing };
}

export function apply(ctx, config) {
  const problem = validateBotConfig(config);
  if (problem !== undefined) throw new Error(`kairos-bot: ${problem}`);
  const known = new Set(ctx.tools.schemas().map((schema) => schema.name));
  const { allow, missing } = expandAllow(config.allow, known);
  if (missing.length > 0) ctx.logger?.warn?.(`kairos-bot: allow names not in this tree, ignored: ${missing.join(", ")}`);
  if (allow.length === 0) throw new Error("kairos-bot: none of the allowed tools exist in this tree; the bot would have no hands at all");
  ctx.effect(() => ctx.systemPrompt.section({ name: "deployment:persona", order: 0, text: config.persona }));
  ctx.effect(() => ctx.tools.restrict({ allow }));
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd face && npx tsx --test tests/bot-plugin.test.ts`
Expected: PASS (5 tests). Then `npm run typecheck` — expected clean (the JS file is imported, not type-checked; `allowJs` without `checkJs`).

- [ ] **Step 5: Commit**

```bash
git add face/plugins/bot.js face/tests/bot-plugin.test.ts
git commit -m "feat(face): the bot composition plugin - a scoped persona and an allow-list mask, dependency-free"
```

---

### Task 2: Kairos's deployment persona (`dsh/profile/persona.md`, `face/src/persona.ts`)

**Files:**
- Create: `dsh/profile/persona.md`, `face/src/persona.ts`
- Test: `face/tests/persona.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `PERSONA_VARIABLES = ["model", "cwd"]`, `validatePersonaTemplate(text: string): string | undefined`, `readPersona(path: string): string` (trimmed text; throws `kairos-face: <path>: <problem>`), `PERSONA_PATH` (absolute path of `dsh/profile/persona.md`, module-relative). Task 3 pushes the patch.

- [ ] **Step 1: Write the failing test**

```ts
// face/tests/persona.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PERSONA_PATH, readPersona, validatePersonaTemplate } from "../src/persona.ts";

test("validatePersonaTemplate accepts model and cwd, refuses everything else the strict renderer would throw on", () => {
  assert.equal(validatePersonaTemplate("You are Kairos. Your working directory is {{cwd}} on {{model}}."), undefined);
  assert.match(validatePersonaTemplate("") ?? "", /empty/);
  assert.match(validatePersonaTemplate("   \n") ?? "", /empty/);
  assert.match(validatePersonaTemplate("Hello {{date}}") ?? "", /unknown persona variable \{\{date\}\}/);
  assert.match(validatePersonaTemplate("Hello {{ model }") ?? "", /unbalanced/);
  assert.match(validatePersonaTemplate("Hello {{{model}}}") ?? "", /unbalanced|unknown/);
});

test("readPersona returns the trimmed file and throws with the path on a bad template", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-persona-"));
  const good = join(dir, "good.md");
  await writeFile(good, "\nYou are Probe in {{cwd}}.\n\n");
  assert.equal(readPersona(good), "You are Probe in {{cwd}}.");
  const bad = join(dir, "bad.md");
  await writeFile(bad, "You are {{nobody}}.");
  assert.throws(() => readPersona(bad), (err: Error) => err.message.includes(bad) && /nobody/.test(err.message));
});

test("the shipped persona.md is valid and names Kairos", () => {
  const text = readPersona(PERSONA_PATH);
  assert.match(text, /You are Kairos/);
  assert.equal(validatePersonaTemplate(text), undefined);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd face && npx tsx --test tests/persona.test.ts`
Expected: FAIL — `Cannot find module '../src/persona.ts'`.

- [ ] **Step 3: Write the module and the persona**

```ts
// face/src/persona.ts
/** Kairos's deployment persona — the order-0 `deployment:persona` section of
 * every prompt the face assembles, set on dsh-base's `system-prompt` row by
 * the patch `composeFace` pushes (boot.ts). Before this file existed the row's
 * `persona` was `''` and the model was never told it was Kairos (charter D11).
 *
 * The renderer is STRICT (dsh-system-prompt README: "complete `{{…}}` groups
 * are interpreted strictly against the registered variables … with no escape
 * syntax"): an unknown variable fails EVERY step of EVERY session. So the text
 * is validated where it is read, and a bad file refuses the boot with the path
 * in the message rather than shipping a prompt that throws later.
 * @module
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** The variables the shipped loop registers (dsh-system-prompt README, `persona` row). */
export const PERSONA_VARIABLES: readonly string[] = ["model", "cwd"];

/** Resolved from this module, never from the working directory (data.ts does the same). */
export const PERSONA_PATH = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "dsh", "profile", "persona.md");

/** `undefined` when the text will render; otherwise one reason. Stricter than
 * dsh: every `{{` here must open a known variable, so a lone brace is refused too. */
export function validatePersonaTemplate(text: string): string | undefined {
  if (text.trim() === "") return "persona is empty";
  const GROUP = /\{\{([^{}]*)\}\}/g;
  for (const match of text.matchAll(GROUP)) {
    const variable = match[1].trim();
    if (!PERSONA_VARIABLES.includes(variable)) {
      return `unknown persona variable {{${variable}}} (known: ${PERSONA_VARIABLES.join(", ")})`;
    }
  }
  /* Stricter than dsh on purpose: once every complete `{{model}}`/`{{cwd}}`
   * group is removed, no brace may remain. dsh tolerates a lone `{`, but
   * `{{{model}}}` and `{{ model }` both throw there, and persona prose has no
   * use for a stray brace - refusing them all is the cheaper rule to explain. */
  if (/[{}]/.test(text.replace(GROUP, ""))) return "unbalanced {{ }} in persona (a brace outside a {{model}}/{{cwd}} group)";
  return undefined;
}

/** Read and validate; throws with the path so a boot failure names the file. */
export function readPersona(path: string): string {
  const text = readFileSync(path, "utf8");
  const problem = validatePersonaTemplate(text);
  if (problem !== undefined) throw new Error(`kairos-face: ${path}: ${problem}`);
  return text.trim();
}
```

```markdown
<!-- dsh/profile/persona.md -->
You are Kairos, the one principal agent of a market–strategy–account research workbench run by one operator on one machine. Your working directory is {{cwd}}.

The strategy directories under strategies/ are your arena: theses with falsification terms, executable screens, backtests, a journal, a lifecycle state. You write them freely and git is the ledger. You read the market only through point-in-time channels, you state what was actually measured, and a backtest that cannot be honest fails loudly rather than succeeding approximately.

The operator is your only teacher. Their style pack is the default you follow; when your findings conflict with it you report the conflict — never silently defer, never silently override. Mechanics rules are law, not style.

You do not trade. Order tools sit behind a gate the operator answers, and the roster of other agents on a channel is a menu of voices you may consult, never hands that act for you.
```

The `<!-- -->` line is a comment for this plan only — the file starts at "You are Kairos".

- [ ] **Step 4: Run test to verify it passes**

Run: `cd face && npx tsx --test tests/persona.test.ts && npm run typecheck`
Expected: PASS (3 tests); typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add dsh/profile/persona.md face/src/persona.ts face/tests/persona.test.ts
git commit -m "feat(face): Kairos's deployment persona, validated against the strict prompt template"
```

---

### Task 3: Mount the preset roster and set the persona (overlay, boot, setup, `bots/kairos`)

**Files:**
- Modify: `face/package.json` (two dependencies), `face/src/overlay.ts`, `face/src/boot.ts`, `face/src/setup.ts`
- Create: `bots/kairos/agent.cordis.yml`, `bots/kairos/preset.yml`
- Test: `face/tests/overlay.test.ts`, `face/tests/boot.test.ts` (modify)

**Interfaces:**
- Consumes: `readPersona`, `PERSONA_PATH` (Task 2).
- Produces: `faceOverlay(port: number, dshHome: string, botsRoot: string): FacePatchEntry[]`; `BOTS_ROOT` (absolute `<repo>/bots`), `DEFAULT_PRESET = "kairos"`, `AGENT_PRESETS_ROW_ID = "agent-presets"`, `SYSTEM_PROMPT_ROW_ID = "system-prompt"` exported from `overlay.ts`; `FaceBootOptions.botsRoot?: string` (defaults to `BOTS_ROOT`); `composeFace` pushes `{ id: "system-prompt", name: "@deepseek-ai/dsh-system-prompt", config: { persona } }`; `bootFace` refuses to start when `ctx.get("agentPresets")` is absent or the default preset is missing/broken.

- [ ] **Step 1: Add the dependencies and install**

Edit `face/package.json` `dependencies` (alphabetical, exact pin):

```json
    "@deepseek-ai/dsh-agent-presets": "0.1.1-rc.2",
    "@deepseek-ai/dsh-system-prompt": "0.1.1-rc.2",
```

Run: `cd face && npm install && npx tsx --test tests/version.test.ts`
Expected: PASS — both packages already sit in `node_modules` at the pin (transitively); declaring them makes the type imports below legal under the README's "declared deps only" contract.

- [ ] **Step 2: Write the failing tests**

In `face/tests/overlay.test.ts`, change the row-set test to eleven rows and pass a bots root:

```ts
const BOTS = "/tmp/face-test-bots";
test("overlay inserts exactly the eleven rows with loopback config", () => {
  const patches = faceOverlay(3090, HOME, BOTS);
  assert.equal(patches.length, 1);
  const rows = patches[0].insert!;
  const byId = new Map(rows.map(r => [r.id, r]));
  assert.deepEqual(
    [...byId.keys()].sort(),
    ["agent-presets", "api-gateway", "connection", "cordis-host-runner", "directory-picker", "storage",
      "storage-domain", "storage-json", "tool-ask-user", "webserver", "workspace"],
  );
  assert.deepEqual(byId.get("agent-presets")!.config, {
    default: "kairos",
    roots: [{ path: BOTS, trust: "user" }],
    includeUserRoot: false,
  });
});
```

Update every other `faceOverlay(3090, HOME)` call in that file to `faceOverlay(3090, HOME, BOTS)`. The "carries no config it does not own" loop is unchanged (`agent-presets` carries config the face owns).

In `face/tests/boot.test.ts`: add `"agent-presets"` to `OVERLAY_ROW_IDS`; change the layer-count assertion from `3` to `4` with the comment `dsh-base insert + hmr disable + system-prompt persona + face overlay`; add:

```ts
test("composeFace sets Kairos's persona on dsh-base's system-prompt row", () => {
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const row = composeEntries([patches]).find((r) => r.id === "system-prompt");
  assert.ok(row, "system-prompt row present");
  const persona = (row!.config as { persona?: string }).persona ?? "";
  assert.match(persona, /^You are Kairos/);
  assert.equal(persona, readPersona(PERSONA_PATH));
});
```

with `import { PERSONA_PATH, readPersona } from "../src/persona.ts";`.

Run: `cd face && npx tsx --test tests/overlay.test.ts tests/boot.test.ts`
Expected: FAIL — eleven vs ten rows; layer count 3 ≠ 4; `system-prompt` config has `persona: ''`.

- [ ] **Step 3: Write the overlay row**

In `face/src/overlay.ts`: add the type import and constants, widen the signature, insert the row after `tool-ask-user`:

```ts
import type { Config as AgentPresetsConfig } from "@deepseek-ai/dsh-agent-presets";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

/** The repository's bot directory — the ONLY preset root the face scans. Module-relative. */
export const BOTS_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "bots");
/** The inert preset every session that names none joins (spec S3). */
export const DEFAULT_PRESET = "kairos";
export const AGENT_PRESETS_ROW_ID = "agent-presets";
/** dsh-base's system-prompt row, whose `persona` composeFace sets (boot.ts). */
export const SYSTEM_PROMPT_ROW_ID = "system-prompt";

export function faceOverlay(port: number, dshHome: string, botsRoot: string): FacePatchEntry[] {
```

and the row:

```ts
      /* A bot is a dsh agent preset: a directory under `bots/` holding one
       * `agent.cordis.yml` (spec §2). The roster's only root is the repository's
       * own `bots/` — `includeUserRoot: false` keeps `$DSH_HOME/.agent-presets`
       * out, so a bot the repository does not carry cannot exist. `default` is
       * REQUIRED by the plugin and is what the gateway mounts for a session that
       * names no preset: `kairos`, an empty composition, so Kairos's own sessions
       * keep the flat host roster unchanged (spec S3). The plugin warns on every
       * agent created outside a preset once a roster is mounted; the default
       * makes that warning unreachable. */
      { id: AGENT_PRESETS_ROW_ID, name: "@deepseek-ai/dsh-agent-presets",
        config: { default: DEFAULT_PRESET, roots: [{ path: botsRoot, trust: "user" }], includeUserRoot: false }
          satisfies AgentPresetsConfig },
```

- [ ] **Step 4: Write the persona patch and the boot assertion**

In `face/src/boot.ts`:

```ts
import type { Config as SystemPromptConfig } from "@deepseek-ai/dsh-system-prompt";
import { BOTS_ROOT, DEFAULT_PRESET, SYSTEM_PROMPT_ROW_ID, faceOverlay } from "./overlay.ts";
import { PERSONA_PATH, readPersona } from "./persona.ts";
```

Add to `FaceBootOptions`:

```ts
  /** The preset root (`bots/`); tests point it at a fixture. Defaults to the repository's. */
  botsRoot?: string;
```

In `composeFace`, after the `hmr` push and before the overlay push:

```ts
  /* Kairos's persona: the one config value dsh-base leaves empty on purpose
   * ("the deployment persona is a deployment choice"). A non-insert patch
   * REPLACES the row's whole config (cordis-plugin-include applyEntryPatches),
   * and dsh-base sets nothing else on this row, so nothing is lost. Guarded
   * like hmr: an unmatched patch is silent, and a silently empty persona is
   * D11 all over again. `readPersona` throws on a malformed template, which
   * refuses the boot with the file named - better than a prompt that throws
   * at every step. */
  if (rows.has(SYSTEM_PROMPT_ROW_ID)) {
    patches.push({
      id: SYSTEM_PROMPT_ROW_ID,
      name: "@deepseek-ai/dsh-system-prompt",
      config: { persona: readPersona(PERSONA_PATH) } satisfies SystemPromptConfig,
    });
  }
  patches.push(...faceOverlay(opts.port, home, opts.botsRoot ?? BOTS_ROOT));
```

In `bootFace`, after the existing order-gate wiring and before `return { ctx, dispose }`:

```ts
  /* The preset roster: every session.create the gateway serves resolves a
   * preset - the named one or `default` - and fails at resolution if the
   * roster cannot supply it. Assert it here, against the LIVE service, so a
   * missing `bots/kairos` refuses the boot instead of failing every session. */
  const presets = ctx.get("agentPresets") as
    | { defaultId: string; list(): Promise<{ id: string; broken?: string }[]> }
    | undefined;
  if (presets === undefined) {
    await dispose();
    throw new Error(`${BIN}: agentPresets missing from the composed tree - the agent-presets overlay row did not mount`);
  }
  const roster = await presets.list();
  const fallback = roster.find((preset) => preset.id === presets.defaultId);
  if (fallback === undefined || fallback.broken !== undefined) {
    await dispose();
    throw new Error(
      `${BIN}: default agent preset "${presets.defaultId}" is ` +
      (fallback === undefined ? `not in the roster (${roster.map((p) => p.id).join(", ") || "empty"})` : `broken: ${fallback.broken}`) +
      ` under ${opts.botsRoot ?? BOTS_ROOT} - every session.create would fail at resolution`,
    );
  }
  console.log(`${BIN}: agent presets: ${roster.map((p) => p.id + (p.broken === undefined ? "" : " (broken)")).join(", ")} (default ${presets.defaultId})`);
```

(`DEFAULT_PRESET` is imported for the overlay call; `presets.defaultId` is what the live service reports, which the settings layer may override — assert against the live value.)

- [ ] **Step 5: Create the inert default preset**

```yaml
# bots/kairos/agent.cordis.yml
# The default agent preset: EMPTY on purpose. Kairos is the host plane - dsh-base's
# flat tool roster, the operator's MCP row, the face's gate and ask-user rows - and
# a session that names no preset joins this one so that the roster plugin's
# "published without joining" warning never fires and Kairos's tools stay exactly
# the host's (spec S3, verified by bots-smoke.test.ts). Add nothing here: a row
# here would reach every Kairos session.
[]
```

```yaml
# bots/kairos/preset.yml
name: Kairos
description: the principal agent - the host composition itself, no mask, no shadowed persona
```

- [ ] **Step 6: Update the profile patch header**

In `face/src/setup.ts` `PATCH_HEADER`, extend the face-owned row list: after `tool-ask-user,` insert `agent-presets, the system-prompt persona,`.

- [ ] **Step 7: Run the offline tests and typecheck**

Run: `cd face && npm test && npm run typecheck`
Expected: PASS everything (overlay eleven rows; boot four layers; persona present; version sweep covers the two new deps). If `tests/setup.test.ts` pins the header text verbatim, update its expected string to include the two new names.

- [ ] **Step 8: Boot the real thing once**

Run: `cd face && FACE_SMOKE=1 npx tsx --test tests/smoke.test.ts`
Expected: PASS, and the boot log carries `kairos-face: agent presets: kairos (default kairos)`. (The fixture home has no `bots/` of its own — the roster root is the repository's, so `kairos` is found.)

- [ ] **Step 9: Commit**

```bash
git add face/package.json face/package-lock.json face/src/overlay.ts face/src/boot.ts face/src/setup.ts bots/kairos face/tests/overlay.test.ts face/tests/boot.test.ts
git commit -F /tmp/msg.txt
```
with `/tmp/msg.txt`: `feat(face): mount the agent-preset roster on bots/ with an inert kairos default, and name Kairos in the deployment persona`.

---

### Task 4: The bot template and the server core (`bots/_template`, `face/src/bots.ts`)

**Files:**
- Create: `bots/_template/agent.cordis.yml`, `bots/_template/preset.yml`, `bots/_template/SOUL.md`, `bots/_template/README.md`, `bots/_template/skills/README.md`, `bots/_template/journal/notes.md`, `face/src/bots.ts`, `face/tests/bots-fixture.ts`
- Test: `face/tests/bots.test.ts`

**Interfaces:**
- Consumes: `HttpError` (`face/src/http.ts`), js-yaml `load`/`dump`.
- Produces (all exported from `face/src/bots.ts`):
  - `BOT_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/`, `RESERVED_IDS: ReadonlySet<string>` (`kairos`), `TEMPLATE = "_template"`, `isBotId(v: unknown): v is string`
  - `DEFAULT_ALLOW: readonly string[]`, `TEMPLATE_SOUL: string`, `BOT_PLUGIN_RELATIVE = "../../face/plugins/bot.js"`
  - `renderComposition(opts: { soul: string; allow: readonly string[]; plugin?: string }): string`
  - `renderPresetMeta(name: string, description: string): string`
  - `interface BotRow { id: string; name: string; description: string; dir: string; homeCwd: string; soul: string; isDefault: boolean; broken?: string; listed: boolean }`
  - `createBot(root: string, body: Record<string, unknown>): Promise<BotRow>`
  - `updateSoul(root: string, id: unknown, soul: unknown): Promise<BotRow>`
  - `listBots(root: string, presets: PresetLister): Promise<BotRow[]>` with `type PresetLister = () => Promise<{ id: string; broken?: string }[]>`
  - `rejectSoul(soul: unknown): string` (validated text or throws `HttpError(400)`)

- [ ] **Step 1: Write the fixture helper** — the `face/tests/bots-fixture.ts` shown under **File Structure** above, verbatim.

- [ ] **Step 2: Write the failing tests**

```ts
// face/tests/bots.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { load } from "js-yaml";
import { makeBotsRoot } from "./bots-fixture.ts";
import {
  BOT_PLUGIN_RELATIVE, DEFAULT_ALLOW, TEMPLATE_SOUL, createBot, isBotId, listBots, rejectSoul,
  renderComposition, renderPresetMeta, updateSoul,
} from "../src/bots.ts";
import { HttpError } from "../src/http.ts";

const noPresets = async () => [] as { id: string; broken?: string }[];

test("isBotId is dsh's preset grammar minus the two names the face reserves", () => {
  for (const ok of ["buffett", "a", "spec-2", "x".repeat(64)]) assert.equal(isBotId(ok), true, ok);
  for (const bad of ["", "Buffett", "_template", "kairos", "-lead", "a_b", "a.b", "a b", "巴菲特", "x".repeat(65), 42, null]) {
    assert.equal(isBotId(bad), false, JSON.stringify(bad));
  }
});

test("rejectSoul refuses an empty or templated persona and returns the trimmed text", () => {
  assert.equal(rejectSoul("  You are Probe.\n"), "You are Probe.");
  for (const bad of ["", "   ", "Hi {{model}}", 3, undefined]) {
    assert.throws(() => rejectSoul(bad), (err: HttpError) => err.status === 400, JSON.stringify(bad));
  }
});

test("renderComposition is parseable YAML naming the plugin by a relative path, the persona verbatim, and the allow list", () => {
  const text = renderComposition({ soul: "You are Probe: a test voice.\nSecond line.", allow: ["bash", "read"] });
  const rows = load(text) as { id: string; name: string; config: Record<string, unknown> }[];
  assert.deepEqual(rows.map((r) => r.id), ["bot", "skills"]);
  assert.equal(rows[0].name, BOT_PLUGIN_RELATIVE);
  assert.deepEqual(rows[0].config, { persona: "You are Probe: a test voice.\nSecond line.", allow: ["bash", "read"] });
  assert.equal(rows[1].name, "@deepseek-ai/dsh-skill-filesystem");
  assert.deepEqual(rows[1].config, { customSkillDirs: ["./skills"], includeDefaultRoots: false });
  assert.match(text, /^# GENERATED by the face/m);
});

test("the shipped template composition IS renderComposition(TEMPLATE_SOUL, DEFAULT_ALLOW) - they cannot drift", async () => {
  const root = await makeBotsRoot();
  const shipped = await readFile(join(root, "_template", "agent.cordis.yml"), "utf8");
  assert.equal(shipped, renderComposition({ soul: TEMPLATE_SOUL, allow: DEFAULT_ALLOW }));
});

test("DEFAULT_ALLOW names read and speak tools only - never orders, delegation, or another agent", () => {
  for (const forbidden of ["subagent", "subagent_fork", "workflow", "ralph", "create_goal", "todo_write", "mcp__*__place_order", "mcp__*__cancel_order", "mcp__*__orders"]) {
    assert.equal(DEFAULT_ALLOW.includes(forbidden), false, forbidden);
  }
  for (const kept of ["bash", "read", "grep", "glob", "edit", "write", "web_search", "skill", "ask_user_question", "mcp__*__daily_bars"]) {
    assert.equal(DEFAULT_ALLOW.includes(kept), true, kept);
  }
  assert.equal(DEFAULT_ALLOW.some((n) => n.startsWith("agent_")), false);
});

test("createBot copies the template, writes the three files, renders the composition, and refuses a second time", async () => {
  const root = await makeBotsRoot();
  const made = await createBot(root, { id: "probe", name: "Probe", description: "a test voice", soul: "You are Probe." });
  assert.equal(made.id, "probe");
  assert.equal(made.homeCwd, join(root, "probe", "journal"));
  await stat(join(root, "probe", "journal", "notes.md"));
  await stat(join(root, "probe", "skills", "README.md"));
  assert.equal(await readFile(join(root, "probe", "SOUL.md"), "utf8"), "You are Probe.\n");
  assert.equal(await readFile(join(root, "probe", "preset.yml"), "utf8"), renderPresetMeta("Probe", "a test voice"));
  const rows = load(await readFile(join(root, "probe", "agent.cordis.yml"), "utf8")) as { config: { persona: string } }[];
  assert.equal(rows[0].config.persona, "You are Probe.");
  await assert.rejects(createBot(root, { id: "probe", name: "Probe" }), (err: HttpError) => err.status === 409);
});

test("createBot without a soul uses the template's, and proposes an id from the name when none is given", async () => {
  const root = await makeBotsRoot();
  const made = await createBot(root, { name: "Value Investor" });
  assert.equal(made.id, "value-investor");
  assert.equal(made.soul, TEMPLATE_SOUL);
  await assert.rejects(createBot(root, { name: "巴菲特型" }), (err: HttpError) => err.status === 400 && /id/.test(err.message));
});

test("createBot refuses bad ids, reserved ids, a templated soul, and a missing template", async () => {
  const root = await makeBotsRoot();
  for (const id of ["_template", "kairos", "Bad", "a b", "../x", "", 7]) {
    await assert.rejects(createBot(root, { id, name: "x" }), (err: HttpError) => err.status === 400, JSON.stringify(id));
  }
  await assert.rejects(createBot(root, { id: "ok", name: "x", soul: "{{cwd}}" }), (err: HttpError) => err.status === 400);
  const empty = join(root, "nowhere");
  await mkdir(empty);
  await assert.rejects(createBot(empty, { id: "ok", name: "x" }), (err: HttpError) => err.status === 500 && /_template/.test(err.message));
});

test("updateSoul rewrites SOUL.md and the composition's persona together, and 404s an unknown bot", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "v1" });
  const after = await updateSoul(root, "probe", "v2 of Probe");
  assert.equal(after.soul, "v2 of Probe");
  assert.equal(await readFile(join(root, "probe", "SOUL.md"), "utf8"), "v2 of Probe\n");
  const rows = load(await readFile(join(root, "probe", "agent.cordis.yml"), "utf8")) as { config: { persona: string } }[];
  assert.equal(rows[0].config.persona, "v2 of Probe");
  await assert.rejects(updateSoul(root, "ghost", "x"), (err: HttpError) => err.status === 404);
  await assert.rejects(updateSoul(root, "probe", "{{"), (err: HttpError) => err.status === 400);
});

test("listBots reads every directory in the grammar, marks the default, carries dsh's broken reason, and flags a bot the roster does not report", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", description: "a test voice", soul: "You are Probe." });
  await mkdir(join(root, "cracked"));
  await writeFile(join(root, "cracked", "agent.cordis.yml"), "not: a list\n");
  await mkdir(join(root, "Skipped"));            // outside the grammar: not a preset, not listed
  const presets = async () => [{ id: "kairos" }, { id: "probe" }, { id: "cracked", broken: "composition is not a list" }];
  const bots = await listBots(root, presets);
  assert.deepEqual(bots.map((b) => b.id), ["cracked", "kairos", "probe"]);
  const byId = new Map(bots.map((b) => [b.id, b]));
  assert.equal(byId.get("kairos")!.isDefault, true);
  assert.equal(byId.get("probe")!.name, "Probe");
  assert.equal(byId.get("probe")!.soul, "You are Probe.");
  assert.equal(byId.get("cracked")!.broken, "composition is not a list");
  assert.equal(byId.get("cracked")!.name, "cracked");        // no preset.yml → id
  const unlisted = await listBots(root, noPresets);
  assert.equal(unlisted.find((b) => b.id === "probe")!.listed, false);
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd face && npx tsx --test tests/bots.test.ts`
Expected: FAIL — `Cannot find module '../src/bots.ts'`.

- [ ] **Step 4: Write `face/src/bots.ts` (the core; routes come in Task 5)**

```ts
// face/src/bots.ts
/** Bots: operator-authored dsh agent presets under `bots/<id>/` (spec §2).
 *
 * A bot is a directory holding `agent.cordis.yml` (the composition dsh mounts),
 * `preset.yml` (display metadata dsh reads), `SOUL.md` (the persona SOURCE),
 * `skills/` (a dsh skill root) and `journal/` (the only directory the bot may
 * write, from its home). The face is the only writer: it copies `_template`,
 * writes the metadata and the soul, and RENDERS the composition so the persona
 * row's `text` is the soul's text - dsh's `!!js` cannot read a sibling file
 * (cordis-plugin-loader evaluates it in an ESM `new Function` with neither
 * `require` nor `__dirname`), so the YAML carries a derived copy and this
 * module keeps the two in step. Editing `SOUL.md` by hand reaches nothing
 * until `updateSoul` runs again (spec R4).
 *
 * `_template` is invisible to dsh (a leading underscore is outside the preset
 * grammar) and refused as an id here; `kairos` is the inert default preset
 * (`bots/kairos`), never a bot. Ids are dsh's grammar `[a-z0-9][a-z0-9-]*`.
 * @module
 */
import { cp, readdir, readFile, stat, writeFile } from "node:fs/promises";
import type { IncomingMessage, ServerResponse } from "node:http";
import { join } from "node:path";
import { dump, load } from "js-yaml";
import { isJsonBody, isTrustedDataRequest } from "./data.ts";
import { FORBIDDEN, HttpError, readBody } from "./http.ts";
import type { RouteRegistrar } from "./static.ts";

const BIN = "kairos-face";

export const TEMPLATE = "_template";
/** dsh-agent-presets' preset-id grammar, bounded to 64 code points. */
export const BOT_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
/** Ids the grammar admits but the face refuses: the default preset is not a bot. */
export const RESERVED_IDS: ReadonlySet<string> = new Set(["kairos"]);
export const isBotId = (value: unknown): value is string =>
  typeof value === "string" && BOT_ID_RE.test(value) && !RESERVED_IDS.has(value);

/** Relative from `bots/<id>/` - the preset mount resolves a relative plugin
 *  path from the preset's own directory (dsh-agent-presets README). */
export const BOT_PLUGIN_RELATIVE = "../../face/plugins/bot.js";

/** What a voice keeps of Kairos's roster (spec §2.2.1): the shell, file read
 *  and edit, search, web, skills, the question tool, and the market-data reads
 *  of the alpaca-kit MCP server under whatever the operator named it. Absent
 *  by design: delegation (`subagent*`, `workflow`, `ralph`), goals and todos,
 *  background jobs, every `agent_<bin>`, and every order or account tool -
 *  `orders`, `place_order`, `cancel_order`. Names come from the tree the face
 *  boots (`tools.schemas()`, dumped 2026-09-07); `mcp__*__<raw>` expands
 *  against the live tree in the plugin. */
export const DEFAULT_ALLOW: readonly string[] = [
  "ask_user_question", "bash", "edit", "glob", "grep", "read", "read_image", "skill",
  "str_replace_editor", "web_search", "write",
  "mcp__*__earnings", "mcp__*__daily_bars", "mcp__*__calendar", "mcp__*__corp_actions",
  "mcp__*__market_snapshot", "mcp__*__screen", "mcp__*__breadth",
];

/** The persona a fresh copy carries until the form or `updateSoul` replaces it. */
export const TEMPLATE_SOUL =
  "You are <bot name>, a discussant on the operator's research workbench. You hold one stance and argue it " +
  "from evidence; you say plainly when the evidence is thin. You are a voice, not a hand: you write no " +
  "strategy conclusions and you never trade.";

const GENERATED_HEADER =
  "# GENERATED by the face (face/src/bots.ts renderComposition) - do not hand-edit.\n" +
  "# The persona row's text is SOUL.md's text; edit SOUL.md through the face so both move.\n";

export function renderComposition(opts: { soul: string; allow: readonly string[]; plugin?: string }): string {
  const rows = [
    { id: "bot", name: opts.plugin ?? BOT_PLUGIN_RELATIVE, config: { persona: opts.soul, allow: [...opts.allow] } },
    { id: "skills", name: "@deepseek-ai/dsh-skill-filesystem", config: { customSkillDirs: ["./skills"], includeDefaultRoots: false } },
  ];
  return GENERATED_HEADER + dump(rows, { lineWidth: -1, noRefs: true });
}

export function renderPresetMeta(name: string, description: string): string {
  return dump({ name, description }, { lineWidth: -1 });
}

/** The soul text a request may carry: non-empty, no `{{` (the prompt is a strict template). */
export function rejectSoul(soul: unknown): string {
  if (typeof soul !== "string" || soul.trim() === "") throw new HttpError(400, "soul must be a non-empty string");
  if (soul.includes("{{")) throw new HttpError(400, "soul must not contain '{{' - the system prompt is a strict template with no escape");
  return soul.trim();
}

export interface BotRow {
  id: string;
  name: string;
  description: string;
  dir: string;
  /** The bot's home session cwd - its journal, the one directory it may write. */
  homeCwd: string;
  soul: string;
  /** `kairos`: the host composition, not a bot. */
  isDefault: boolean;
  /** dsh's own reason when the composition cannot mount (Rule 5: shown, never skipped). */
  broken?: string;
  /** false when the directory is here but the preset roster did not report it. */
  listed: boolean;
}

export type PresetLister = () => Promise<{ id: string; broken?: string }[]>;

/** Lowercase ASCII, whitespace and `_` to `-`, everything outside the grammar dropped; `""` when nothing survives. */
export function proposeBotId(displayName: string): string {
  return displayName
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/[^a-z0-9-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

async function exists(path: string): Promise<boolean> {
  try { await stat(path); return true; } catch { return false; }
}

async function readMeta(dir: string): Promise<{ name?: string; description?: string }> {
  try {
    const parsed: unknown = load(await readFile(join(dir, "preset.yml"), "utf8"));
    if (parsed === null || typeof parsed !== "object") return {};
    const { name, description } = parsed as { name?: unknown; description?: unknown };
    return { ...(typeof name === "string" ? { name } : {}), ...(typeof description === "string" ? { description } : {}) };
  } catch { return {}; }
}

async function rowFor(root: string, id: string, presets: Map<string, { broken?: string }>): Promise<BotRow> {
  const dir = join(root, id);
  const meta = await readMeta(dir);
  const soul = await readFile(join(dir, "SOUL.md"), "utf8").then((s) => s.trim()).catch(() => "");
  const preset = presets.get(id);
  return {
    id, name: meta.name ?? id, description: meta.description ?? "", dir, homeCwd: join(dir, "journal"), soul,
    isDefault: id === "kairos",
    ...(preset?.broken === undefined ? {} : { broken: preset.broken }),
    listed: preset !== undefined,
  };
}

/** Every directory under `bots/` in the grammar, with dsh's view of it merged in. */
export async function listBots(root: string, presets: PresetLister): Promise<BotRow[]> {
  let entries: import("node:fs").Dirent[] = [];
  try {
    entries = await readdir(root, { withFileTypes: true });
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
    return [];
  }
  const reported = new Map((await presets()).map((p) => [p.id, p] as const));
  const ids = entries
    .filter((e) => e.isDirectory() && BOT_ID_RE.test(e.name))
    .map((e) => e.name)
    .sort((a, b) => a.localeCompare(b));
  return Promise.all(ids.map((id) => rowFor(root, id, reported)));
}

/** Birth `bots/<id>` from the template. Refuses a malformed or reserved id, a
 *  taken id, a templated soul and a missing template - never overwrites. */
export async function createBot(root: string, body: Record<string, unknown>): Promise<BotRow> {
  const name = typeof body.name === "string" && body.name.trim() !== "" ? body.name.trim() : undefined;
  const id = body.id !== undefined ? body.id : (name === undefined ? undefined : proposeBotId(name));
  if (!isBotId(id)) {
    throw new HttpError(400, "invalid bot id (lowercase letters, digits and -; starts with a letter or digit; up to 64; not kairos or _template)");
  }
  const description = typeof body.description === "string" ? body.description.trim() : "";
  const soul = body.soul === undefined ? TEMPLATE_SOUL : rejectSoul(body.soul);
  const template = join(root, TEMPLATE);
  if (!(await exists(join(template, "agent.cordis.yml")))) throw new HttpError(500, `bots/${TEMPLATE} missing`);
  const dir = join(root, id);
  if (await exists(dir)) throw new HttpError(409, "bot already exists");
  await cp(template, dir, { recursive: true, filter: (src) => !src.includes("__pycache__") });
  await writeFile(join(dir, "preset.yml"), renderPresetMeta(name ?? id, description), "utf8");
  await writeFile(join(dir, "SOUL.md"), `${soul}\n`, "utf8");
  await writeFile(join(dir, "agent.cordis.yml"), renderComposition({ soul, allow: DEFAULT_ALLOW }), "utf8");
  return rowFor(root, id, new Map());
}

/** Rewrite `SOUL.md` AND the composition's persona row - the two must never drift (spec R4). */
export async function updateSoul(root: string, id: unknown, soul: unknown): Promise<BotRow> {
  if (!isBotId(id)) throw new HttpError(400, "invalid bot id");
  const text = rejectSoul(soul);
  const dir = join(root, id);
  if (!(await exists(join(dir, "agent.cordis.yml")))) throw new HttpError(404, "no such bot");
  const current = load(await readFile(join(dir, "agent.cordis.yml"), "utf8")) as { id?: string; config?: { allow?: unknown } }[] | null;
  const allowRow = Array.isArray(current) ? current.find((r) => r?.id === "bot") : undefined;
  const allow = Array.isArray(allowRow?.config?.allow) ? (allowRow!.config!.allow as string[]) : [...DEFAULT_ALLOW];
  await writeFile(join(dir, "SOUL.md"), `${text}\n`, "utf8");
  await writeFile(join(dir, "agent.cordis.yml"), renderComposition({ soul: text, allow }), "utf8");
  return rowFor(root, id, new Map());
}
```

(`registerBotRoutes` is appended in Task 5; the imports for it — `IncomingMessage`, `ServerResponse`, `isJsonBody`, `isTrustedDataRequest`, `FORBIDDEN`, `readBody`, `RouteRegistrar` — are already at the top so Task 5 adds only the function. If `tsc` reports them unused after Task 4, leave them; Task 5 uses them the same day.)

- [ ] **Step 5: Write the template**

`bots/_template/agent.cordis.yml` — generate it, do not hand-write it:

```bash
cd face && node --input-type=module -e '
import { renderComposition, TEMPLATE_SOUL, DEFAULT_ALLOW } from "./src/bots.ts";
process.stdout.write(renderComposition({ soul: TEMPLATE_SOUL, allow: DEFAULT_ALLOW }));
' > ../bots/_template/agent.cordis.yml
```
(If `node` refuses the `.ts` import, run it through `npx tsx --eval` with the same body.)

```yaml
# bots/_template/preset.yml
name: <bot name>
description: <one line - the stance this voice argues>
```

```markdown
<!-- bots/_template/SOUL.md : exactly TEMPLATE_SOUL followed by a newline -->
You are <bot name>, a discussant on the operator's research workbench. You hold one stance and argue it from evidence; you say plainly when the evidence is thin. You are a voice, not a hand: you write no strategy conclusions and you never trade.
```

(Write the file without the comment line; `bots.test.ts` pins `createBot` without a soul to `TEMPLATE_SOUL`, and the composition test pins the YAML — keep `SOUL.md` byte-equal to `TEMPLATE_SOUL` + `\n` so the three agree.)

```markdown
# bots/_template/README.md

# A bot

One directory = one bot = one dsh agent preset. Copied by the face's **New bot** form
(`face/src/bots.ts` `createBot`); never hand-copy it — the id has to satisfy dsh's grammar
`[a-z0-9][a-z0-9-]*` and the composition has to carry the soul.

| File | Owner | What |
|---|---|---|
| `agent.cordis.yml` | the face (GENERATED) | the composition dsh mounts: the `kairos-bot` plugin (persona + tool mask) and this bot's skill root |
| `preset.yml` | the operator, via the form | `name`, `description` — what the roster shows |
| `SOUL.md` | the operator, via the form or the bot page | the persona SOURCE. The face copies it into the composition; a hand edit reaches nothing until the face saves it again |
| `skills/` | the operator | this bot's stance pack, a dsh skill root: `skills/<skill>/SKILL.md` with `name` + `description` frontmatter |
| `journal/` | the bot, from its home | the only directory the bot may write |

Rules: no `{{` anywhere in `SOUL.md` (the system prompt is a strict template with no escape);
the mask in `agent.cordis.yml` is visibility, not authority — the sandbox and Gate 2 are the fences.
Kairos never edits anything under `bots/` (AGENTS.md).
```

```markdown
# bots/_template/skills/README.md

Skills this bot carries. One directory per skill, `skills/<skill>/SKILL.md`, opening with

    ---
    name: <skill>
    description: <one line>
    ---

Both keys are required — dsh drops a SKILL.md lacking either, silently. The stance pack is the
operator's (charter P2): Kairos proposes, the operator writes.
```

```markdown
# bots/_template/journal/notes.md

# Journal

- YYYY-MM-DD: created from _template.
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd face && npx tsx --test tests/bots.test.ts && npm run typecheck`
Expected: PASS (10 tests); typecheck clean.

- [ ] **Step 7: Commit**

```bash
git add bots/_template face/src/bots.ts face/tests/bots.test.ts face/tests/bots-fixture.ts
git commit -F /tmp/msg.txt
```
with `/tmp/msg.txt`: `feat(face): bots/_template and the bot core - ids, the rendered composition, create, soul update, listing`.

---

### Task 5: The bot routes (`GET /data/bots.json`, `POST /data/bots`, `POST /data/bots/soul`) and `main.ts`

**Files:**
- Modify: `face/src/bots.ts` (append `registerBotRoutes`), `face/src/main.ts`
- Test: `face/tests/bots.test.ts` (append route tests)

**Interfaces:**
- Consumes: `listBots`, `createBot`, `updateSoul` (Task 4); `isTrustedDataRequest`, `isJsonBody` (`data.ts`); `FORBIDDEN`, `HttpError`, `readBody` (`http.ts`).
- Produces: `interface BotRouteDeps { root: string; listPresets: PresetLister }`, `registerBotRoutes(webServer: RouteRegistrar, deps: BotRouteDeps): void`. Route bodies: `GET /data/bots.json` → `{ ok: true, bots: BotRow[] }`; `POST /data/bots` `{ name?, id?, description?, soul? }` → `{ ok: true, bot: BotRow }`; `POST /data/bots/soul` `{ id, soul }` → `{ ok: true, bot: BotRow }`. Body limit 65 536 bytes (a soul is prose).

- [ ] **Step 1: Write the failing tests** (append to `face/tests/bots.test.ts`)

```ts
import type { IncomingMessage, ServerResponse } from "node:http";
import { Readable } from "node:stream";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { registerBotRoutes } from "../src/bots.ts";

function fakeRes(): { out: { status: number; body: string }; res: ServerResponse } {
  const out = { status: 0, body: "" };
  const res = {
    writeHead(status: number) { out.status = status; return res; },
    end(body?: string | Buffer) { out.body = String(body ?? ""); return res; },
  };
  return { out, res: res as unknown as ServerResponse };
}
function getReq(host = "127.0.0.1:3090", headers: Record<string, string> = {}): IncomingMessage {
  return { headers: { host, ...headers }, method: "GET" } as unknown as IncomingMessage;
}
function postReq(body: string, host = "127.0.0.1:3090", headers: Record<string, string> = {}): IncomingMessage {
  const req = Readable.from([Buffer.from(body)]) as unknown as IncomingMessage;
  (req as { headers: unknown }).headers = { host, "content-type": "application/json", ...headers };
  (req as { method: string }).method = "POST";
  return req;
}
function routesFor(root: string): Map<string, WebRoute> {
  const routes: WebRoute[] = [];
  registerBotRoutes({ register: (route) => routes.push(route) }, { root, listPresets: async () => [{ id: "kairos" }] });
  return new Map(routes.map((r) => [r.path, r]));
}

test("routes: exactly three, and the fence refuses a forged host, a cross-site fetch, and a foreign origin", async () => {
  const routes = routesFor(await makeBotsRoot());
  assert.deepEqual([...routes.keys()].sort(), ["/data/bots", "/data/bots.json", "/data/bots/soul"]);
  for (const req of [getReq("evil.example:3090"), getReq("127.0.0.1:3090", { "sec-fetch-site": "cross-site" }), getReq("127.0.0.1:3090", { origin: "http://evil.example" })]) {
    const r = fakeRes();
    await routes.get("/data/bots.json")!.handler(req, r.res);
    assert.equal(r.out.status, 403);
    assert.equal(r.out.body, '{"ok":false,"error":"forbidden"}');
  }
});

test("routes: the listing answers ok with every bot row", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe" });
  const r = fakeRes();
  await routesFor(root).get("/data/bots.json")!.handler(getReq(), r.res);
  assert.equal(r.out.status, 200);
  const body = JSON.parse(r.out.body) as { ok: boolean; bots: { id: string; listed: boolean }[] };
  assert.equal(body.ok, true);
  assert.deepEqual(body.bots.map((b) => b.id), ["kairos", "probe"]);
  assert.equal(body.bots[1].listed, false); // the fake roster reports only kairos
});

test("routes: create is POST+JSON only, 400 on junk, 200 then 409", async () => {
  const root = await makeBotsRoot();
  const create = routesFor(root).get("/data/bots")!;
  const get = fakeRes(); await create.handler(getReq(), get.res); assert.equal(get.out.status, 405);
  const text = fakeRes(); await create.handler(postReq("{}", "127.0.0.1:3090", { "content-type": "text/plain" }), text.res); assert.equal(text.out.status, 415);
  const junk = fakeRes(); await create.handler(postReq("not json"), junk.res); assert.equal(junk.out.status, 400);
  const first = fakeRes(); await create.handler(postReq('{"name":"Probe","soul":"You are Probe."}'), first.res);
  assert.equal(first.out.status, 200);
  assert.equal((JSON.parse(first.out.body) as { bot: { id: string } }).bot.id, "probe");
  await stat(join(root, "probe", "agent.cordis.yml"));
  const again = fakeRes(); await create.handler(postReq('{"name":"Probe"}'), again.res); assert.equal(again.out.status, 409);
});

test("routes: soul update carries prose past the 4 KiB default limit and 404s an unknown bot", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe" });
  const soul = routesFor(root).get("/data/bots/soul")!;
  const long = "You are Probe. " + "Argue from evidence. ".repeat(400); // ~8.6 KiB
  const ok = fakeRes(); await soul.handler(postReq(JSON.stringify({ id: "probe", soul: long })), ok.res);
  assert.equal(ok.out.status, 200);
  assert.equal(await readFile(join(root, "probe", "SOUL.md"), "utf8"), `${long.trim()}\n`);
  const missing = fakeRes(); await soul.handler(postReq('{"id":"ghost","soul":"x"}'), missing.res); assert.equal(missing.out.status, 404);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd face && npx tsx --test tests/bots.test.ts`
Expected: FAIL — `registerBotRoutes` is not exported.

- [ ] **Step 3: Append the routes to `face/src/bots.ts`**

```ts
export interface BotRouteDeps {
  /** The repository root; `bots/` is under it. */
  root: string;
  /** `ctx.agentPresets.list()`, narrowed - dsh's view of the roster, `broken` reasons included. */
  listPresets: PresetLister;
}

/** A soul is prose; the default 4 KiB body limit is for names and ids. */
const SOUL_BODY_LIMIT = 65_536;

export function registerBotRoutes(webServer: RouteRegistrar, deps: BotRouteDeps): void {
  const botsRoot = join(deps.root, "bots");
  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(typeof body === "string" ? body : JSON.stringify(body));
  };
  const get = (read: () => Promise<object>) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      try {
        return send(res, 200, { ok: true, ...(await read()) });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        console.error(`${BIN}: bots listing failed:`, err);
        return send(res, 500, { ok: false, error: "request failed" });
      }
    };
  const post = (limit: number, act: (body: Record<string, unknown>) => Promise<object>) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      if (req.method !== "POST") return send(res, 405, { ok: false, error: "POST only" });
      if (!isJsonBody(req)) return send(res, 415, { ok: false, error: "application/json only" });
      try {
        let body: Record<string, unknown>;
        try {
          const parsed: unknown = JSON.parse(await readBody(req, limit));
          if (parsed === null || typeof parsed !== "object") throw new Error("not an object");
          body = parsed as Record<string, unknown>;
        } catch (err) {
          if (err instanceof HttpError) throw err;
          throw new HttpError(400, "body must be a JSON object");
        }
        return send(res, 200, { ok: true, ...(await act(body)) });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        console.error(`${BIN}: bots route failed:`, err);
        return send(res, 500, { ok: false, error: "request failed" });
      }
    };

  webServer.register({ kind: "exact", path: "/data/bots.json", handler: get(async () => ({ bots: await listBots(botsRoot, deps.listPresets) })) });
  webServer.register({ kind: "exact", path: "/data/bots", handler: post(SOUL_BODY_LIMIT, async (body) => ({ bot: await createBot(botsRoot, body) })) });
  webServer.register({ kind: "exact", path: "/data/bots/soul", handler: post(SOUL_BODY_LIMIT, async (body) => ({ bot: await updateSoul(botsRoot, body.id, body.soul) })) });
}
```

- [ ] **Step 4: Wire it in `face/src/main.ts`**, after `registerSessionRoutes(...)` and before `await registerPanelRoutes(...)`:

```ts
import { registerBotRoutes } from "./bots.ts";
...
/* Bots: the preset roster's view comes from the live service the overlay
 * mounted (boot.ts asserts it is there); the directories are read from disk. */
const agentPresets = booted.ctx.get("agentPresets") as { list(): Promise<{ id: string; broken?: string }[]> };
registerBotRoutes(booted.ctx.webServer, { root: process.cwd(), listPresets: () => agentPresets.list() });
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd face && npm test && npm run typecheck`
Expected: PASS all; typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add face/src/bots.ts face/src/main.ts face/tests/bots.test.ts
git commit -m "feat(face): bot routes - listing, create from template, soul update - behind the loopback fence"
```

---

### Task 6: The client — Bots on the agent face, a bot's home, and bot buckets in the sidebar

**Files:**
- Create: `face/client/botId.js`
- Modify: `face/client/grouping.js`, `face/client/chat.js`
- Test: `face/tests/botId.test.ts` (new), `face/tests/grouping.test.ts` (extend)

**Interfaces:**
- Consumes: `GET /data/bots.json`, `POST /data/bots`, `POST /data/bots/soul` (Task 5); the gateway's `session.create({ cwd, agentPreset })`; `SessionSummary.agentPreset` (already on every `session.list` row, `dsh-host-apiproxy/lib/index.js:426-437`).
- Produces: `proposeBotId(displayName)` (`botId.js`, the browser twin of the server's); `bucketFor(channel, archived, bot)` with `bot: { id: string; label: string } | null`, `BOT_KEY_PREFIX = "bot:"`, `isBotKey(key)` (`grouping.js`); in `chat.js`: `pendingAgentPreset`, `botIndex`, `loadBotIndex()`, `botOf(summary)`, `openBot(bot)`, `openNewBot()`, `openBotHome(bot)`.

- [ ] **Step 1: Write the failing tests**

```ts
// face/tests/botId.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import { proposeBotId } from "../client/botId.js";
import { isBotId } from "../src/bots.ts";

test("proposeBotId folds a display name into dsh's grammar, or to nothing", () => {
  assert.equal(proposeBotId("Buffett Type"), "buffett-type");
  assert.equal(proposeBotId("  Speculator_2  "), "speculator-2");
  assert.equal(proposeBotId("Macro -- Bear!"), "macro-bear");
  assert.equal(proposeBotId("巴菲特型"), "");
  assert.equal(proposeBotId("Éric"), "eric");
  assert.equal(proposeBotId("x".repeat(80)).length, 64);
});

test("a non-empty proposal is always an id the server accepts", () => {
  for (const name of ["Buffett Type", "Speculator_2", "Macro -- Bear!", "Éric", "a", "9lives", "x".repeat(80)]) {
    const id = proposeBotId(name);
    assert.equal(isBotId(id), true, `${name} -> ${id}`);
  }
});
```

Append to `face/tests/grouping.test.ts` (and extend its import to `{ ARCHIVED_KEY, BOT_KEY_PREFIX, bucketFor, isBotKey, UNGROUPED_KEY }`):

```ts
test("a bot session buckets under its bot, after archived and before channel membership", () => {
  const bot = { id: "buffett", label: "巴菲特型" };
  assert.deepEqual(bucketFor(null, false, bot), { key: "bot:buffett", label: "巴菲特型", channel: null });
  assert.deepEqual(bucketFor({ workspaceId: "ws-1", title: "alpha" }, false, bot), { key: "bot:buffett", label: "巴菲特型", channel: null });
  assert.deepEqual(bucketFor(null, true, bot), { key: ARCHIVED_KEY, label: "archived", channel: null });
  assert.equal(bucketFor(null, false, null).key, UNGROUPED_KEY);
  assert.equal(isBotKey(`${BOT_KEY_PREFIX}buffett`), true);
  assert.equal(isBotKey("bot:Bad Id"), false);
  assert.equal(isBotKey(UNGROUPED_KEY), false);
});
```

Every existing `bucketFor(x, y)` call in the test file gains a third argument `null`.

Run: `cd face && npx tsx --test tests/botId.test.ts tests/grouping.test.ts`
Expected: FAIL — `botId.js` missing; `BOT_KEY_PREFIX`/`isBotKey` not exported.

- [ ] **Step 2: Write `face/client/botId.js` and extend `grouping.js`**

```js
// face/client/botId.js
/**
 * Propose a bot id from a display name - the browser twin of `proposeBotId`
 * in face/src/bots.ts (kept byte-identical in logic; botId.test.ts pins that
 * a non-empty proposal is always an id the server accepts).
 *
 * WHAT IT IS NOT. It is not a fence. `createBot` (src/bots.ts) keeps the only
 * gate: dsh's preset grammar `[a-z0-9][a-z0-9-]*`, minus `kairos` and
 * `_template`. This runs before the POST so the operator sees the id a name
 * becomes and can type another; a name with no ASCII letters proposes
 * nothing, and the form then requires the id field. Fail-closed.
 */
export function proposeBotId(displayName) {
  return displayName
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/[^a-z0-9-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}
```

In `face/client/grouping.js`:

```js
/** Sentinel PREFIX for a bot's home sessions: `bot:<id>` — never a real `workspaceId`. */
export const BOT_KEY_PREFIX = "bot:";
/** Whether a bucket key names a bot (the id is dsh's preset grammar). */
export function isBotKey(key) {
  return typeof key === "string" && /^bot:[a-z0-9][a-z0-9-]*$/.test(key);
}
/**
 * @param {{workspaceId: string, title: string}|null} channel
 * @param {boolean} archived
 * @param {{id: string, label: string}|null} bot - the session's bot when its
 *   `agentPreset` names one (never the default `kairos`), else `null`.
 */
export function bucketFor(channel, archived, bot) {
  if (archived) return { key: ARCHIVED_KEY, label: "archived", channel: null };
  if (bot !== null && bot !== undefined) return { key: BOT_KEY_PREFIX + bot.id, label: bot.label, channel: null };
  if (channel !== null) return { key: channel.workspaceId, label: channel.title, channel };
  return { key: UNGROUPED_KEY, label: "ungrouped", channel: null };
}
```

- [ ] **Step 3: Run the two tests**

Run: `cd face && npx tsx --test tests/botId.test.ts tests/grouping.test.ts`
Expected: PASS.

- [ ] **Step 4: `chat.js` — state, session creation, and buckets**

All edits in `face/client/chat.js`; the anchors are the current lines named.

(a) Beside `pendingWorkspaceId` (after line ~1089):

```js
/** The agent preset the NEXT `session.create` names: a bot's id for its home
 * session, `undefined` for Kairos (the gateway then mounts the default).
 * Set with `pendingCwd = <bot>.homeCwd` by openBotHome; reset wherever the
 * other two pendings are. @type {string|undefined} */
let pendingAgentPreset;
```

(b) The `send()` payload (line ~1417):

```js
      const payload = pendingWorkspaceId !== undefined
        ? { workspaceId: pendingWorkspaceId }
        : (pendingCwd === undefined ? {} : { cwd: pendingCwd });
      if (pendingAgentPreset !== undefined) payload.agentPreset = pendingAgentPreset;
      const created = await rpc("session.create", payload);
```
and after `pendingWorkspaceId = undefined;` add `pendingAgentPreset = undefined;`. Same reset in `newSession()` (line ~1065) and `onNewRound` (line ~1596).

(c) The bot index, beside `channelIndex`:

```js
/** `/data/bots.json`'s last good `bots` array - id, name, homeCwd, soul, broken?, isDefault, listed. @type {Record<string, any>[]} */
let botIndex = [];
async function loadBotIndex() {
  try {
    const body = await panelData("/data/bots.json");
    botIndex = Array.isArray(body.bots) ? body.bots : [];
  } catch { /* the sidebar labels a bot by id instead of name */ }
  return botIndex;
}
/** The bot a session belongs to, from its own header: `agentPreset` names one
 * and it is not the default. `null` for Kairos and for a preset-less session. */
function botOf(summary) {
  const id = summary?.agentPreset;
  if (typeof id !== "string" || id === "kairos") return null;
  const bot = botIndex.find((b) => b.id === id);
  return { id, label: bot?.name ?? id };
}
```

(d) `refreshSessions` (line ~945): load the three together and pass the bot —

```js
    [value] = await Promise.all([rpc("session.list"), loadChannelIndex(), loadBotIndex()]);
    ...
    const { key, label, channel } = bucketFor(channelOf(id), archived, botOf(summary));
```

(e) Bucket order (line ~987): bots after channels, before ungrouped —

```js
  const order = [...buckets.keys()].filter((key) => key !== UNGROUPED_KEY && key !== ARCHIVED_KEY && !isBotKey(key));
  order.push(...[...buckets.keys()].filter((key) => isBotKey(key)).sort());
  if (buckets.has(UNGROUPED_KEY)) order.push(UNGROUPED_KEY);
  if (buckets.has(ARCHIVED_KEY)) order.push(ARCHIVED_KEY);
```
Import `isBotKey` and `BOT_KEY_PREFIX` from `./grouping.js`.

(f) The collapsed-groups loader (line ~1205): accept bot keys —

```js
    .filter((k) => typeof k === "string" && (k === ARCHIVED_KEY || k === UNGROUPED_KEY || UUID_RE.test(k) || isBotKey(k)));
```

(g) `knownFolders()` (line ~1108): never offer a bot's journal as a "local folder" —

```js
    if (typeof cwd !== "string" || cwd === "" || dirs.has(cwd)) continue;
    if (channelIndex.root && cwd.startsWith(`${channelIndex.root}/bots/`)) continue; // a bot's home, not a folder
```

- [ ] **Step 5: `chat.js` — the Bots section, the bot page, the New bot form**

In `refreshAgentPanel()` (line ~1754), between the `local agents` block and `a2a network`:

```js
  panel.append(spGroup("bots"));
  const bots = await loadBotIndex();
  if (activePanel !== "agent") return;
  const voices = bots.filter((b) => b.isDefault !== true);
  for (const bot of voices) {
    const line = el("div", "sp-plug");
    line.append(phaseDot(bot.broken ? "failed" : bot.listed === false ? "warn" : "active"), el("span", "sp-plug-name", String(bot.name)));
    line.title = bot.broken ? `broken: ${bot.broken}` : bot.listed === false ? "on disk, not reported by the preset roster" : String(bot.description ?? "");
    panel.append(indexRow(line, () => openBot(bot)));
  }
  if (voices.length === 0) panel.append(el("div", "sp-note", "no bots yet"));
  const addBot = el("div", "sp-plug sp-add");
  addBot.append(el("span", "sp-plug-name", "+ new bot"));
  panel.append(indexRow(addBot, () => openNewBot()));
```

The bot page and its home:

```js
/** Arm the next prompt to create this bot's HOME session: cwd = its journal
 * (the only directory the bot may write), agentPreset = its id (the gateway
 * mounts the preset). Mirrors onNewRound; no session exists until the prompt. */
function openBotHome(bot) {
  openSeq += 1;
  loadingSession = null;
  activeSession = null;
  pendingWorkspaceId = undefined;
  pendingCwd = String(bot.homeCwd);
  pendingAgentPreset = String(bot.id);
  closeDetail();
  resetFlow();
  markActive();
  status(`new session · ${bot.name} at home · type below`);
}

function openBot(bot) {
  openDetail(`bot · ${bot.name}`, (inner) => {
    inner.append(el("div", "detail-title", String(bot.name)));
    inner.append(el("div", "detail-sub", `${bot.id} · ${bot.description || "no description"}`));
    if (bot.broken) inner.append(el("div", "sp-note err", `dsh cannot mount this bot: ${bot.broken}`));
    else if (bot.listed === false) inner.append(el("div", "sp-note err", "the preset roster does not report this directory - is its agent.cordis.yml present?"));
    inner.append(el("div", "detail-path", String(bot.dir)));

    const actions = el("div", "detail-actions");
    const home = el("button", "picker-btn", "open home");
    home.type = "button";
    home.disabled = Boolean(bot.broken);
    home.addEventListener("click", () => openBotHome(bot));
    actions.append(home);
    inner.append(actions);

    const homes = lastSessions.filter((s) => s.agentPreset === bot.id);
    const card = panelCard(`home sessions · ${homes.length}`);
    for (const s of homes) {
      const row = el("div", "ch-session");
      row.setAttribute("role", "button");
      row.tabIndex = 0;
      row.append(el("span", "ch-session-title", titleOf(s)));
      row.addEventListener("click", () => { closeDetail(); void openSession(String(s.sessionId)); });
      card.append(row);
    }
    if (homes.length === 0) card.append(el("div", "sp-note", "none yet - open home and say something"));
    inner.append(card);

    const soulCard = panelCard("soul");
    const soul = /** @type {HTMLTextAreaElement} */ (el("textarea", "picker-input"));
    soul.rows = 8;
    soul.value = String(bot.soul ?? "");
    const save = el("button", "picker-btn", "save soul");
    save.type = "button";
    save.addEventListener("click", async () => {
      save.disabled = true;
      try {
        const body = await panelData("/data/bots/soul", { id: bot.id, soul: soul.value });
        bot = body.bot;
        status(`saved soul of ${bot.name} - a fresh session will carry it (a running one keeps its prompt)`);
      } catch (err) {
        failed(err, "save soul");
      } finally {
        save.disabled = false;
      }
    });
    soulCard.append(soul, save);
    inner.append(soulCard);
  });
}

function openNewBot() {
  openDetail("new bot", (inner) => {
    inner.append(el("div", "detail-title", "New bot"));
    inner.append(el("div", "detail-sub", "copies bots/_template · a voice, not a hand"));
    const form = el("div", "picker-new");
    const name = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    name.type = "text";
    name.placeholder = "display name (any script)";
    const id = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    id.type = "text";
    id.placeholder = "id - lowercase letters, digits, - (proposed from the name)";
    name.addEventListener("input", () => { id.value = proposeBotId(name.value); });
    const description = /** @type {HTMLInputElement} */ (el("input", "picker-input"));
    description.type = "text";
    description.placeholder = "one line - the stance this voice argues";
    const soul = /** @type {HTMLTextAreaElement} */ (el("textarea", "picker-input"));
    soul.rows = 6;
    soul.placeholder = "persona (optional; the template's if empty; no {{ }})";
    const create = el("button", "picker-btn", "create");
    create.type = "button";
    create.addEventListener("click", async () => {
      create.disabled = true;
      try {
        const payload = { name: name.value.trim(), id: id.value.trim(), description: description.value.trim() };
        if (soul.value.trim() !== "") payload.soul = soul.value;
        const body = await panelData("/data/bots", payload);
        await refreshAgentPanel();
        openBot(body.bot);
      } catch (err) {
        failed(err, "create bot");
      } finally {
        create.disabled = false;
      }
    });
    form.append(name, id, description, soul, create);
    inner.append(form);
    inner.append(el("div", "sp-note",
      "The mask in the composition is visibility, not authority: what a bot may write is its session's sandbox, what it may order is Gate 2."));
  });
}
```

Add `import { proposeBotId } from "./botId.js";` at the top of `chat.js`.

- [ ] **Step 6: Run the offline suite, then look at it**

Run: `cd face && npm test && npm run typecheck`
Expected: PASS.

Then start the face (`preview_start` with the launch config, never Bash), **hard-reload**, open the agent face: the `bots` group shows `no bots yet` and `+ new bot`; create `Probe` with the id proposed as `probe`; the bot page opens; `open home` then a first prompt creates a session that the sidebar shows under a `Probe` group, not `ungrouped`; the strategy picker does not offer `journal` as a local folder. Read `read_console_messages` for errors before believing the screen.

- [ ] **Step 7: Commit**

```bash
git add face/client/botId.js face/client/grouping.js face/client/chat.js face/tests/botId.test.ts face/tests/grouping.test.ts
git commit -F /tmp/msg.txt
```
with `/tmp/msg.txt`: `feat(face): bots on the agent face - create form, a bot's home, and bot buckets in the sidebar`.

---

### Task 7: The three smoke tests (one boot each): presets, the sandbox probe (S4), the ask-user probe (S7)

**Files:**
- Create: `face/tests/bots-smoke.test.ts`, `face/tests/bot-sandbox-smoke.test.ts`, `face/tests/askuser-noclient-smoke.test.ts`

**Interfaces:**
- Consumes: `bootFace({ botsRoot })` (Task 3), `makeBotsRoot`, `PLUGIN_ABS` (Task 4), `renderComposition`, `createBot`; dsh services by name: `agentPresets`, `agents`, `tools`, `systemPrompt`, `permissionPresets`, `userQuestions`; the gateway over HTTP at `ctx.webServer.port` with the client-request envelope (`face/client/api.js` `rpc`, `dsh-host-apiproxy/lib/index.js:993-999`).
- Produces: the permanent form of spikes S1, S2, S3 (`bots-smoke`), and the recorded answers to S4 and S7 (their test files assert only what must hold and print what was observed).

- [ ] **Step 1: Write `face/tests/bots-smoke.test.ts`**

```ts
/** Bots on a REAL composed tree - spikes S1, S2, S3 of the spec made permanent.
 *
 * S1: a composition whose plugin row is a PATH (not a package) mounts, and the
 *     persona text the face wrote into it reaches the assembled prompt.
 * S2: `tools.restrict({allow})` from a preset row masks every agent joined to
 *     the preset - a bot session sees exactly allow ∩ tree, Kairos sees all.
 * S3: `kairos` is an empty composition and Kairos's sessions join it: their
 *     tool set is byte-identical to the host's global view.
 * Also: the roster lists a broken fixture with its reason and never `_template`;
 * a session created through the gateway with `agentPreset` carries it on its
 * header (the gateway mounts - S6 is not needed for home sessions).
 *
 * Own file, gated: one boot per process (smoke.test.ts).
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { renderPrompt } from "@deepseek-ai/dsh-system-prompt";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { createBot, renderComposition } from "../src/bots.ts";
import { PERSONA_PATH, readPersona } from "../src/persona.ts";
import { makeBotsRoot, PLUGIN_ABS } from "./bots-fixture.ts";

const gated = process.env.FACE_SMOKE !== "1";

test("bots smoke: roster, mask, persona, and an inert default on a real tree", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  const bots = await makeBotsRoot();
  /* A temp root cannot reach `../../face/plugins/bot.js`; an absolute path
   * keeps its location (dsh-agent-presets README), which is what the fixture
   * uses - the repository's real presets use the relative path. */
  await createBot(bots, { id: "probe", name: "Probe", soul: "You are Probe, a test voice." });
  await writeFile(join(bots, "probe", "agent.cordis.yml"),
    renderComposition({ soul: "You are Probe, a test voice.", allow: ["bash", "read", "ask_user_question", "no_such_tool"], plugin: PLUGIN_ABS }));
  await mkdir(join(bots, "cracked"));
  await writeFile(join(bots, "cracked", "agent.cordis.yml"), "not: a list\n");

  const home = mkdtempSync(join(tmpdir(), "face-botsmoke-"));
  setupFaceProfile(home);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
  try {
    const presets = ctx.get("agentPresets") as { defaultId: string; list(): Promise<{ id: string; broken?: string }[]> };
    const roster = await presets.list();
    assert.deepEqual(roster.map((p) => p.id).sort(), ["cracked", "kairos", "probe"], "listed - and never _template");
    assert.equal(presets.defaultId, "kairos");
    assert.match(roster.find((p) => p.id === "cracked")!.broken ?? "", /list/, "a broken preset carries dsh's reason (Rule 5)");

    const base = `http://127.0.0.1:${ctx.webServer.port}`;
    let n = 0;
    const call = async (method: string, payload: object): Promise<Record<string, unknown>> => {
      const res = await fetch(`${base}/api/${method}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ type: "client-request", rpcId: `t${++n}`, method, payload }),
      });
      const body = await res.json() as { result?: { ok?: boolean; value?: Record<string, unknown>; error?: unknown } };
      assert.equal(body.result?.ok, true, `${method}: ${JSON.stringify(body.result?.error)}`);
      return body.result!.value!;
    };
    const agents = ctx.get("agents") as { get(id: string): { ctx: unknown; session: { header: { agentPreset?: string } } } | undefined };
    const tools = ctx.get("tools") as { schemas(scope?: object): { name: string }[] };
    const systemPrompt = ctx.get("systemPrompt") as { assemble(context?: { scope?: object }): Promise<Parameters<typeof renderPrompt>[0]> };
    const names = (schemas: { name: string }[]) => schemas.map((s) => s.name).sort();

    /* S3 - Kairos: a session naming no preset joins `kairos` and keeps the host's tools. */
    const k = await call("session.create", { cwd: home });
    assert.equal(k.agentPreset, "kairos");
    const kairos = agents.get(String(k.sessionId))!;
    assert.equal(kairos.session.header.agentPreset, "kairos");
    assert.deepEqual(names(tools.schemas(kairos as object)), names(tools.schemas()), "the inert default adds and removes nothing");
    const kairosPrompt = renderPrompt(await systemPrompt.assemble({ scope: kairos as object }));
    assert.ok(kairosPrompt.includes(readPersona(PERSONA_PATH).split("\n")[0]), "D11 closed: Kairos is told who it is");

    /* S1 + S2 - a bot: the gateway mounts the preset; the mask and the persona hold. */
    const p = await call("session.create", { cwd: join(bots, "probe", "journal"), agentPreset: "probe" });
    assert.equal(p.agentPreset, "probe");
    const probe = agents.get(String(p.sessionId))!;
    assert.equal(probe.session.header.agentPreset, "probe");
    assert.deepEqual(names(tools.schemas(probe as object)), ["ask_user_question", "bash", "read"], "allow ∩ tree, unknown names dropped (S2)");
    const probePrompt = renderPrompt(await systemPrompt.assemble({ scope: probe as object }));
    assert.ok(probePrompt.includes("You are Probe, a test voice."), "the bot's persona shadows Kairos's (S1)");
    assert.equal(probePrompt.includes("You are Kairos"), false, "and Kairos's text is gone from the bot's prompt");

    /* A broken preset fails the session, visibly, and nothing else. */
    const res = await fetch(`${base}/api/session.create`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "client-request", rpcId: "t-broken", method: "session.create", payload: { cwd: home, agentPreset: "cracked" } }),
    });
    const broken = await res.json() as { result?: { ok?: boolean; error?: { code?: string } } };
    assert.equal(broken.result?.ok, false);
    assert.match(String(broken.result?.error?.code), /agent-preset/);
  } finally {
    await dispose();
  }
});
```

Run: `cd face && FACE_SMOKE=1 npx tsx --test tests/bots-smoke.test.ts`
Expected: PASS. **If S1 fails** (the path row does not load): switch `renderComposition` to a package specifier by adding `"exports": { "./bot": "./plugins/bot.js" }` to `face/package.json` and `BOT_PLUGIN_RELATIVE = "kairos-face/bot"`, re-run; record which form worked in the spec's amendments block. **If S2 fails** (the bot sees all tools): stop — the mask cannot be a preset row; redesign §2.2 of the spec before continuing (the plan's remaining tasks do not depend on it, but the product claim does).

- [ ] **Step 2: Write `face/tests/bot-sandbox-smoke.test.ts` (S4 — the recorded probe)**

```ts
/** S4: what does a file write from a `read-only` bot session produce?
 *
 * The spec accepts two answers - the sandbox's denial, or an approval card the
 * operator can grant - and refuses one: a silently changed file. This test
 * asserts the refusal and PRINTS which of the two happened, so the plan for
 * rooms (plan 2) can word D12 from an observation rather than a reading.
 * The approval service has no client here, so a raised card cannot be answered:
 * the execute is raced against a timeout, and a pending `approval/asked` in
 * the session log counts as "a card was raised".
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { makeBotsRoot } from "./bots-fixture.ts";

const gated = process.env.FACE_SMOKE !== "1";

test("S4: a read-only session's write never lands silently", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const bots = await makeBotsRoot();
  const home = mkdtempSync(join(tmpdir(), "face-sandbox-"));
  setupFaceProfile(home);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
  try {
    const base = `http://127.0.0.1:${ctx.webServer.port}`;
    const res = await fetch(`${base}/api/session.create`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "client-request", rpcId: "s4", method: "session.create", payload: { cwd: home } }),
    });
    const created = (await res.json() as { result: { value: { sessionId: string } } }).result.value;
    const agents = ctx.get("agents") as { get(id: string): { session: { events: { type: string }[] } } | undefined };
    const agent = agents.get(created.sessionId)!;
    const permission = ctx.get("permissionPresets") as { set(session: unknown, name: string): void };
    permission.set(agent.session, "read-only");
    assert.ok(agent.session.events.some((e) => e.type === "permission/preset"), "the switch is a logged event");

    const target = join(home, "s4-should-not-exist.txt");
    const tools = ctx.get("tools") as { execute(exec: object): Promise<{ isError: boolean; content?: { text?: string }[] }> };
    const outcome = await Promise.race([
      tools.execute({ callId: "s4-write", name: "bash", arguments: { command: `printf x > ${JSON.stringify(target)}` }, agent, signal: new AbortController().signal }),
      new Promise<"timeout">((resolve) => setTimeout(() => resolve("timeout"), 8_000)),
    ]);
    const asked = agent.session.events.some((e) => e.type === "approval/asked");
    const text = outcome === "timeout" ? "(timed out - a card is pending, nobody to answer)" : (outcome.content?.[0]?.text ?? "");
    console.log(`S4 observed: ${outcome === "timeout" ? "PENDING CARD" : outcome.isError ? "DENIED" : "ALLOWED?!"}; approval/asked in log: ${asked}; result: ${text.slice(0, 160)}`);

    assert.equal(existsSync(target), false, "the file must not exist");
    assert.ok(outcome === "timeout" || outcome.isError === true || asked, "either a denial or a raised card");
  } finally {
    await dispose();
  }
});
```

Run: `cd face && FACE_SMOKE=1 npx tsx --test tests/bot-sandbox-smoke.test.ts`
Expected: PASS, with one `S4 observed:` line. Copy that line verbatim into the spec's amendments block (S4 outcome).

- [ ] **Step 3: Write `face/tests/askuser-noclient-smoke.test.ts` (S7 — the recorded probe)**

```ts
/** S7: with no client connected, does `ask_user_question` block or deny?
 *
 * The README records the APPROVAL card blocking with no browser; the question
 * service was never observed. This calls the service directly and races it
 * against a timeout; whichever happens is printed, and R6 in the spec is
 * worded from it. Nothing here needs a model.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { makeBotsRoot } from "./bots-fixture.ts";

const gated = process.env.FACE_SMOKE !== "1";

test("S7: ask() with no client either blocks or fails loud - never answers silently", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-askuser-"));
  setupFaceProfile(home);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: await makeBotsRoot() });
  try {
    const questions = ctx.get("userQuestions") as {
      ask(request: { questions: { id: string; question: string; options?: { label: string }[] }[]; signal?: AbortSignal }): Promise<{ answers: { id: string; selected: string[] }[] }>;
    };
    const controller = new AbortController();
    const outcome = await Promise.race([
      questions.ask({ questions: [{ id: "q1", question: "S7 probe: is anyone there?", options: [{ label: "yes" }, { label: "no" }] }], signal: controller.signal })
        .then((answer) => ({ kind: "answered" as const, answer }), (err: unknown) => ({ kind: "rejected" as const, err })),
      new Promise<{ kind: "timeout" }>((resolve) => setTimeout(() => resolve({ kind: "timeout" }), 5_000)),
    ]);
    controller.abort();
    console.log(`S7 observed: ${outcome.kind}${outcome.kind === "rejected" ? ` - ${String((outcome as { err: unknown }).err)}` : ""}`);
    assert.notEqual(outcome.kind, "answered", "no client can have answered");
  } finally {
    await dispose();
  }
});
```

Run: `cd face && FACE_SMOKE=1 npx tsx --test tests/askuser-noclient-smoke.test.ts`
Expected: PASS, with one `S7 observed:` line (`timeout` = blocks like the approval card; `rejected - …` = fails loud with that code). Copy it into the spec's amendments block and word R6 from it in Task 8.

- [ ] **Step 4: Run everything**

Run: `cd face && npm test && FACE_SMOKE=1 npm test && npm run typecheck`
Expected: all PASS (the FACE_SMOKE run adds five boots: smoke, order-gate, and the three new files, each in its own process).

- [ ] **Step 5: Commit**

```bash
git add face/tests/bots-smoke.test.ts face/tests/bot-sandbox-smoke.test.ts face/tests/askuser-noclient-smoke.test.ts
git commit -F /tmp/msg.txt
```
with `/tmp/msg.txt`: `test(face): bots on a real tree - roster, mask, persona shadow, inert default; the S4 and S7 probes recorded`.

---

### Task 8: Documentation — the Bots section and drill, the mechanism rows, the never-edit line

**Files:**
- Modify: `face/README.md`, `DEVELOPMENT.md`, `AGENTS.md`

**Interfaces:**
- Consumes: everything above; the two `observed:` lines from Task 7.
- Produces: prose. Cite files and symbols, never line numbers.

- [ ] **Step 1: `AGENTS.md`** — the never-edit line becomes:

```
Never edit: data/pit/ contents, dsh/ profile installed copies, anything under bots/ (the operator's
voices; propose a bot in conversation, never create or change one), or anything under docs/research/.
```

- [ ] **Step 2: `face/README.md`** — a new H2 after "The master rail" and before "Chat rendering":

```markdown
## Bots (src/bots.ts + plugins/bot.js + bots/)

A bot is a dsh **agent preset**: one directory under `bots/` holding `agent.cordis.yml`
(the composition dsh mounts), `preset.yml` (name, description), `SOUL.md` (the persona
SOURCE), `skills/` (its stance pack, a dsh skill root) and `journal/` (the one directory it
may write, from its home). The face mounts `@deepseek-ai/dsh-agent-presets` with `bots/`
as its only root (`faceOverlay`, `AGENT_PRESETS_ROW_ID`) and `kairos` — an EMPTY composition —
as the default every session joins when it names none, so Kairos's own sessions keep the
host's flat roster unchanged (`bots-smoke.test.ts` pins the two tool sets equal).

**Kairos is the host plane; a bot is a mask.** Kairos is told who it is by the
`system-prompt` row's `persona`, set from `dsh/profile/persona.md` by `composeFace`
(D11 closed; a malformed template refuses the boot with the file named — `readPersona`).
A bot's composition names one face-owned plugin, `plugins/bot.js` (`kairos-bot`), which
registers the bot's persona section — shadowing Kairos's for that preset's agents — and an
**allow-list** `tools.restrict`. Allow, not deny: dsh admits later-registered globals through
a deny mask and excludes them through an allow mask, and the tools a voice must never see
(`agent_<bin>` on connect, `mcp__…__place_order` when the MCP server comes up, `dispatch` in
the rooms arc) are all registered after the mount. `mcp__*__<raw>` in the list expands
against the live tree, so the operator's server name does not matter.

**The mask is visibility, not authority.** dsh says so of every scope ("live visibility
composition, not an authority boundary"). What a bot may write is its session's sandbox mode;
what it may order is Gate 2, which is tree-wide. Neither changes when a bot is masked.

**Authoring is the face's own copy.** The **New bot** form (agent face → bots → `+ new bot`;
`POST /data/bots`) copies `bots/_template`, writes `preset.yml` and `SOUL.md`, and RENDERS
`agent.cordis.yml` so the persona row's text is the soul's (`renderComposition`) — dsh's
`!!js` cannot read a sibling file. A soul saved on the bot page (`POST /data/bots/soul`,
`updateSoul`) rewrites both. A hand edit to `SOUL.md` reaches nothing until the face saves it
again, and a running session keeps the prompt it started with: the preset's generation is
keyed on `agent.cordis.yml` alone and never reclaimed until restart (dsh-agent-presets
README, "A superseded generation is never reclaimed"). No `{{` anywhere in a soul: the prompt
is a strict template with no escape, and both the form and the plugin refuse it.

**A bot's home** is a session created with `cwd = bots/<id>/journal` and `agentPreset = <id>`
— the client's `openBotHome` arms the next prompt exactly as a channel's "new round" does,
and the gateway's own `session.create` mounts the preset (no in-process agent creation).
The sidebar buckets a bot's sessions under its name from the session summary's `agentPreset`
(`grouping.js` `bucketFor`, `BOT_KEY_PREFIX`); the strategy picker never offers a journal as a
"local folder". Ids are dsh's preset grammar `[a-z0-9][a-z0-9-]*`; the form proposes one from
the display name (`botId.js`) and the server refuses anything else, plus `kairos` and
`_template` (`isBotId`).

| Route | What |
|---|---|
| `GET /data/bots.json` | every directory in the grammar under `bots/`, with dsh's roster merged in: `broken` reasons shown, a directory the roster does not report flagged `listed: false` (Rule 5) |
| `POST /data/bots` | create — `{name, id?, description?, soul?}`; 400 grammar/`{{`, 409 exists, 500 template missing |
| `POST /data/bots/soul` | `{id, soul}` — rewrites `SOUL.md` and the composition together; 404 unknown bot |

**Deleting a bot** is `git rm -r bots/<id>`; there is no button. Its sessions remain history.

**Not built here (the rooms arc, plans 2–4 of the spec):** `dispatch`, member sessions, the
participants strip, the roster's `bots[]`, a `read-only` pin for bots in rooms, and the charter
amendment. Until then a bot has a home and a mask, and nothing else.
```

And a drill H2 after "The ask-user drill":

```markdown
## The bots drill (run after any face or dsh change)

A mask never pulled is presumed decorative.

**Step 0, no model, no key.** `FACE_SMOKE=1 npm test` boots the real tree three extra times:
`bots-smoke.test.ts` proves the roster lists a broken fixture with its reason and never
`_template`, that a session created with `agentPreset` carries it on its header, that the bot
sees exactly its allow-list ∩ the tree while Kairos sees the host's whole roster unchanged, and
that the bot's prompt opens with its own persona while Kairos's opens with `persona.md`.
`bot-sandbox-smoke.test.ts` and `askuser-noclient-smoke.test.ts` print one `observed:` line each
(S4, S7); their findings are recorded in the spec's amendments block.

**Step 0b, if you changed anything under `client/`.** Hard-reload; `registerStatic` sets no
cache headers.

**The drill**, with the face live:

1. Agent face → **bots** → `+ new bot`. Type a display name with spaces and capitals; PASS,
   part one: the id field shows the folded proposal, lowercase with dashes.
2. Create. PASS, part two: the bot page opens; `bots/<id>/` exists with `agent.cordis.yml`,
   `preset.yml`, `SOUL.md`, `skills/README.md`, `journal/notes.md`; the boot log of a restart
   lists the id under `agent presets:`.
3. `open home`, say something. PASS, part three: the sidebar shows the session under the bot's
   name, not under `ungrouped`; the reply speaks in the bot's persona, not Kairos's.
4. Ask the bot to list its tools. PASS, part four: it names the shell, file and web tools and
   `ask_user_question`, and does not name `subagent`, `place_order`, or any `agent_<bin>` — and
   if the alpaca-kit MCP server is connected, it names the market-data reads and not `orders`.
5. On the bot page, edit the soul to include `{{` and save. PASS, part five: refused with the
   strict-template message; the file is unchanged.
6. Clean up: `git rm -r bots/<id>` (or keep it — it is yours).
```

- [ ] **Step 3: `DEVELOPMENT.md`** — one row each (symbols, not lines):

- §4.2 module table: `| \`bots.ts\` | bots = \`bots/<id>/\` agent presets: \`isBotId\`, \`renderComposition\` (persona text written into the composition), \`createBot\`, \`updateSoul\`, \`listBots\` (dsh's roster merged in, \`broken\`/\`listed\`); three routes |`, `| \`persona.ts\` | Kairos's deployment persona: \`readPersona\` validates the strict \`{{}}\` template and refuses the boot on a bad file |`, and a row for `plugins/bot.js`: `| \`plugins/bot.js\` | the \`kairos-bot\` composition plugin: scoped \`deployment:persona\` section + allow-list \`tools.restrict\`, dependency-free (resolved by path from a preset) |`.
- §4.4 route table: the three bot routes with their status ladders (400 grammar/`{{`, 404, 409, 500 template missing).
- §4.5 persistent state: `| \`bots/<id>/\` | \`createBot\`, \`updateSoul\` | copied from \`_template\`; \`preset.yml\`, \`SOUL.md\` and the composition's persona row rewritten together; never overwritten by create |`, `| \`dsh/profile/persona.md\` | the operator | read by \`composeFace\` into the \`system-prompt\` row |`.
- §3: a new `### 3.5 The bot directory contract` in the shape of §3.4: the file list with one parenthetical each; `preset.yml` keys; Naming (`[a-z0-9][a-z0-9-]*`, proposal by `proposeBotId`, `kairos`/`_template` refused); State on the date this lands (`bots/kairos` inert default; `_template` only).
- §7.4 drills table: `| **Bots** — automated (\`bots-smoke\`, \`bot-sandbox-smoke\`, \`askuser-noclient-smoke\`) | roster listing incl. broken; header \`agentPreset\`; mask = allow ∩ tree; persona shadow; inert default; S4/S7 observations | a bot in a room (plan 2) | passes as of <date> |` and `| **Bots** — manual (\`face/README.md\`) | create → home → persona → tools named/not named → \`{{\` refused | | <run/not run> |`.
- §8 conventions: extend the never-edit bullet with `anything under \`bots/\``; add `- **A bot's mask is visibility, not authority.** Write sentences that say so; the sandbox mode and Gate 2 are the fences.`
- §10 forward: add `**Rooms** (spec §14 plans 2–4): \`dispatch\`, member sessions with the \`read-only\` pin, the participants strip, the roster's \`bots[]\`, the charter amendment. Done when the live room drill passes.`
- Update R6's wording in the **spec** (`docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md` §12) from the S7 line, and add the S4 line, the S1 form that worked, and the four deviations listed at the top of this plan to a new `## 16. Post-build amendments (plan 1)` block.

- [ ] **Step 4: Verify the docs' claims against the tree**

Run: `cd face && npm test && npm run typecheck` (unchanged), then read each README sentence that names a symbol and grep it: `grep -n "renderComposition\|updateSoul\|isBotId\|AGENT_PRESETS_ROW_ID\|BOT_KEY_PREFIX\|openBotHome" face/src/*.ts face/client/*.js` — every name must hit.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md face/README.md DEVELOPMENT.md docs/superpowers/specs/2026-09-07-bots-and-rooms-design.md
git commit -F /tmp/msg.txt
```
with `/tmp/msg.txt`: `docs: bots without rooms - the Bots section and drill, mechanism rows, bots/ on the never-edit line, spec amendments for plan 1`.

---

## Self-review (run by the plan's author before handing off)

**Spec coverage (plan 1 scope, spec §14 item 1):**
- S1 → Task 7 (path-row mount + persona text) with the package-specifier fallback named. ✓
- S2 → Task 1 (unit) + Task 7 (real tree). ✓
- S3 → Task 3 (`bots/kairos` = `[]`, boot assertion) + Task 7 (schema equality). ✓
- S4, S7 → Task 7 probes, recorded in Task 8. ✓
- S6 → deviation 3: not needed for home sessions; recorded for plan 2. ✓
- Mount presets → Task 3. Kairos persona (D11) → Tasks 2–3. `bot-mask` → Task 1 (folded into `kairos-bot`, deviation 1). `bots/_template`, `bots/kairos` → Tasks 3–4. Bots roster page + New bot form → Task 6. Home sessions → Task 6 (client) + Task 7 (gateway path proven). §8 tests that need no room → Tasks 1–7. ✓
- Spec §2.1 "New bot form folds a display name to an id" → `proposeBotId` (Task 4 server, Task 6 client, pinned equal by `botId.test.ts`). ✓
- Spec §2.2.1 kept/denied families → `DEFAULT_ALLOW` (Task 4), asserted by `bots.test.ts`. ✓
- Spec §7 home = `journal/` cwd, workspace-write → Task 6 `openBotHome`; the sandbox scope test ("writes to `../SOUL.md` refused") is **not** in this plan: a home session is `workspace-write` with `cwd = journal/`, which the sandbox grants by construction, but proving the refusal needs a bash write through the real sandbox from a session whose cwd is the journal — Task 7's S4 file exercises the read-only case; add the home-scope case to plan 2 alongside the member-session pin. Recorded here so it is not lost.

**Placeholder scan:** no TBD/TODO; every code step carries its code; the one data-derived step (Task 4 Step 5, generating the template YAML) names the exact command. `<date>` and `<run/not run>` in Task 8's DEVELOPMENT rows are filled at execution time by the implementer with the actual values — they are not design placeholders.

**Type consistency:** `BotRow`, `PresetLister`, `BotRouteDeps` defined in Task 4/5 and used identically in Tasks 6–7; `bucketFor(channel, archived, bot)` third argument typed `{id,label}|null` in Task 6 and passed `botOf(summary)` which returns exactly that; `faceOverlay(port, dshHome, botsRoot)` in Task 3 matches every call in Tasks 3 and 7 (`bootFace({ botsRoot })` threads it); `renderComposition({ soul, allow, plugin? })` in Task 4 matches Task 7's fixture call; the plugin's `apply(ctx, config)` consumes the same `{ persona, allow }` `renderComposition` writes.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-07-bots-1-without-rooms.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with executing-plans, batch execution with checkpoints.
