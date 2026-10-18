# Gravit Redesign · Plan 2: The Role Library — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gravit's sessions carry three one-shot role tools — `role_screener`, `role_backtester`, `role_reviewer` — each spawning a child with its own persona and an exact tool allow-list the dsh backend enforces; the roles are three small operator-owned directories under `roles/`, rendered by the face into Gravit's preset composition.

**Architecture:** `roles/<id>/ROLE.md` + `role.yml` are read at boot by `face/src/roles.ts`, which renders one `@deepseek-ai/dsh-tool-subagent` row per role (`provider: spawn`, `backgroundMode: one-shot`, `persona`, `toolFilter.allow`) plus the `gravit` plugin row now carrying the role summaries; `composeFace` hands those rows to `definitionFor` in memory, so the committed `bots/gravit/agent.cordis.yml` becomes a generated mirror a test keeps from drifting. `face/plugins/gravit.js` registers the `gravit:roles` section (the summaries; `dsh-tool-subagent` has no description key) and blanks it for delegated children, which join Gravit's preset. Allow-lists are exact tool names because `tools.restrict()` accepts nothing else and checks them at delegation time.

**Tech Stack:** as plan 1; newly declared at the pin: `@deepseek-ai/dsh-tool-subagent` (types only, for the `satisfies` contract check).

**Spec:** `docs/superpowers/specs/2026-10-15-gravit-agent-redesign-design.md` — §5 (the organization), §5.3 (the three roles), §5.4 as corrected by §11.1 (a), §8 (the plan-2 rows), §9 (tests and the role drill). Seams added here enter `docs/dsh-upgrade-guide.md` §3.2 group C and H.

## Global Constraints

- Plan 1 has merged into this branch (the `gravit` row, `GRAVIT_PLUGIN_RELATIVE`, `gravit.js` with `validateGravitConfig` and `deployment:today`, the instructions patch) — Task 0 checks.
- Everything in plan 1's Global Constraints still binds: the rename precondition, the pin, no `{{` in any persona or section text, `gravit.js` imports nothing, the four gates, `git commit -F`.
- **Allow-lists are exact global tool names**, matching `/^[A-Za-z0-9_-]+$/`, no `*`: `tools.restrict({ allow })` checks membership in the tree at the child's creation (`dsh-tools` `restrictableNames`), and an unknown name fails that delegation with `tools.restrict() names unknown global tool …`. The MCP names carry the operator's server name as the installed profile mounts it: `mcp__alpaca-kit__<raw>`.
- No role names `ask_user_question` (a delegated child has no human answerer: `DELEGATED_CALLER`), `web_search`, any delegation tool (`subagent`, `subagent_fork`, `send_message`, `interrupt_agent`, `list_agents`, `workflow`, `ralph`, any `role_*`), the goal or todo tools, the job tools, `dispatch`, `exit_plan_mode`, any `agent_*`, any account or order tool, any `mcp__akshare__*`.
- A role's `description` (the summary Gravit reads) is ≤ 300 characters; `ROLE.md` is ≤ 2,000 bytes.
- `roles/_template/` is never rendered; a role id obeys `/^[a-z0-9][a-z0-9-]{0,63}$/`; its tool name is `role_` + the id with `-` → `_`.

## Review Focus

1. A role naming a tool the tree lacks at delegation time (the alpaca-kit server down, or a typo in `role.yml`): the delegation must fail with the tool's name in Gravit's tool result, never spawn a child with a silently narrower list. Pinned by `roles-smoke.test.ts` (Task 4, the unregistered stand-in).
2. A child inheriting Gravit's `role_*` tools or the `gravit:roles` text through the preset it joins: the allow-list must remove the tools and the section must be empty for a child. Pinned by `roles-smoke.test.ts` (Task 4) and `gravit-plugin.test.ts` (Task 2).
3. A `role.yml` written with the bots' `mcp__*__<raw>` wildcard: it would pass as a literal name and fail every delegation; expected: refused at boot with the file named and the exact form shown. Pinned by `roles.test.ts` (Task 1).
4. `ROLE.md` with a `{{` group: the child's persona is interpolated strictly and every step would throw; expected: refused at boot. Pinned by `roles.test.ts` (Task 1).
5. The committed mirror `bots/gravit/agent.cordis.yml` drifting from `roles/`: a reader of the file would trust a composition that is not the one booted. Pinned by the drift test in `roles.test.ts` (Task 2).

---

### Task 0: Precondition

- [ ] **Step 1: Plan 1 is in**

Run: `git log --oneline main..HEAD | grep -c 'gravit.js\|GRAVIT.md' ; test -f face/plugins/gravit.js && grep -n 'validateGravitConfig' face/plugins/gravit.js | head -1`
Expected: a non-zero count and the `validateGravitConfig` line. Then `cd face && npm test && npm run typecheck` green.

---

### Task 1: `roles/` on disk and `face/src/roles.ts` reads them

**Files:**
- Create: `roles/_template/ROLE.md`, `roles/_template/role.yml`, `roles/_template/README.md`
- Create: `roles/screener/ROLE.md`, `roles/screener/role.yml`; `roles/backtester/…`; `roles/reviewer/…`
- Create: `face/src/roles.ts`
- Create: `face/tests/roles.test.ts`
- Modify: `face/package.json` (declare `@deepseek-ai/dsh-tool-subagent` at `0.2.0-rc.2`; `npm install` once)

**Interfaces:**
- Produces, in `face/src/roles.ts`:
  - `export const ROLES_ROOT: string` — `<repo>/roles`, module-relative like `BOTS_ROOT`
  - `export const ROLE_TEMPLATE = "_template"`, `export const ROLE_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/`, `export const TOOL_NAME_RE = /^[A-Za-z0-9_-]+$/`, `export const SUMMARY_MAX = 300`, `export const ROLE_MD_MAX_BYTES = 2000`
  - `export interface RoleFile { id: string; tool: string; name: string; description: string; persona: string; allow: string[]; model?: string }`
  - `export function toolNameFor(id: string): string` — `"role_" + id.replace(/-/g, "_")`
  - `export function readRoles(root: string): RoleFile[]` — synchronous; directories of `root` whose name passes `ROLE_ID_RE` and is not `ROLE_TEMPLATE`, sorted by id; throws an `Error` whose message starts with the offending file's absolute path for: a missing root; a missing or empty `ROLE.md`, one over `ROLE_MD_MAX_BYTES`, or one containing `{{`; a missing or non-mapping `role.yml`; `name` or `description` missing or blank; `description` over `SUMMARY_MAX`; `allow` not a non-empty list of strings; an entry failing `TOOL_NAME_RE` (the message for an entry containing `*` says: `wildcards are not accepted; name the exact tool, e.g. mcp__alpaca-kit__screen`); `model` present but not matching `MODEL_ROUTE_RE` (imported from `./bots.ts`).
- Consumes: `MODEL_ROUTE_RE` from `face/src/bots.ts`; `js-yaml`'s `load`.

- [ ] **Step 1: Write the failing tests**

`face/tests/roles.test.ts`:
```ts
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ROLES_ROOT, ROLE_TEMPLATE, readRoles, toolNameFor } from "../src/roles.ts";

/** A throwaway roles root with one valid role; the caller breaks it. */
async function makeRolesRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "face-roles-"));
  await mkdir(join(root, ROLE_TEMPLATE));
  await writeFile(join(root, ROLE_TEMPLATE, "ROLE.md"), "You are <role name>.\n");
  await mkdir(join(root, "probe"));
  await writeFile(join(root, "probe", "ROLE.md"), "You are the probe, a test role.\n");
  await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: a test role\nallow:\n  - read\n  - mcp__alpaca-kit__earnings\n");
  return root;
}

const FORBIDDEN = new Set(["ask_user_question", "web_search", "web_fetch", "subagent", "subagent_fork", "send_message", "interrupt_agent",
  "list_agents", "workflow", "ralph", "create_goal", "get_goal", "update_goal", "todo_write", "job_output", "job_list", "job_kill",
  "dispatch", "exit_plan_mode", "mcp__alpaca-kit__account", "mcp__alpaca-kit__positions", "mcp__alpaca-kit__orders",
  "mcp__alpaca-kit__place_order", "mcp__alpaca-kit__cancel_order"]);

test("toolNameFor: role_ plus the id with dashes as underscores", () => {
  assert.equal(toolNameFor("screener"), "role_screener");
  assert.equal(toolNameFor("data-check"), "role_data_check");
});

test("the shipped roles: three, exact names only, skill on every list, nothing forbidden, the reviewer reads only", () => {
  const roles = readRoles(ROLES_ROOT);
  assert.deepEqual(roles.map((r) => r.tool), ["role_backtester", "role_reviewer", "role_screener"]);
  for (const role of roles) {
    assert.ok(role.allow.includes("skill"), `${role.id} can load the mechanics skills`);
    assert.ok(role.description.length <= 300 && role.description.length > 0, role.id);
    for (const name of role.allow) {
      assert.equal(name.includes("*"), false, `${role.id}: ${name} is exact`);
      assert.equal(FORBIDDEN.has(name) || name.startsWith("role_") || name.startsWith("mcp__akshare__") || name.startsWith("agent_"), false, `${role.id}: ${name} is never a role's`);
    }
  }
  const reviewer = roles.find((r) => r.id === "reviewer")!;
  for (const hand of ["bash", "write", "edit", "str_replace_editor"]) assert.equal(reviewer.allow.includes(hand), false, `the reviewer has no ${hand}`);
  assert.ok(roles.find((r) => r.id === "screener")!.allow.includes("mcp__alpaca-kit__screen"));
});

test("readRoles skips _template and reads a valid role", async () => {
  const root = await makeRolesRoot();
  try {
    const roles = readRoles(root);
    assert.deepEqual(roles.map((r) => r.id), ["probe"]);
    assert.deepEqual(roles[0], { id: "probe", tool: "role_probe", name: "Probe", description: "a test role", persona: "You are the probe, a test role.", allow: ["read", "mcp__alpaca-kit__earnings"] });
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("readRoles refuses, naming the file: braces, an empty persona, a wildcard, an empty allow list, a bad model, a missing root", async () => {
  const root = await makeRolesRoot();
  try {
    await writeFile(join(root, "probe", "ROLE.md"), "You are {{nobody}}.\n");
    assert.throws(() => readRoles(root), (e: Error) => e.message.startsWith(join(root, "probe", "ROLE.md")) && /\{\{/.test(e.message));
    await writeFile(join(root, "probe", "ROLE.md"), "\n");
    assert.throws(() => readRoles(root), /ROLE\.md.*empty/);
    await writeFile(join(root, "probe", "ROLE.md"), "You are the probe.\n");
    await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: x\nallow: [mcp__*__screen]\n");
    assert.throws(() => readRoles(root), /role\.yml.*wildcards are not accepted; name the exact tool, e\.g\. mcp__alpaca-kit__screen/);
    await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: x\nallow: []\n");
    assert.throws(() => readRoles(root), /allow/);
    await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: x\nallow: [read]\nmodel: nope\n");
    assert.throws(() => readRoles(root), /model/);
  } finally { await rm(root, { recursive: true, force: true }); }
  assert.throws(() => readRoles(join(tmpdir(), "no-such-roles-root")), /missing/);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd face && npx tsx --test tests/roles.test.ts`
Expected: FAIL — `../src/roles.ts` not found.

- [ ] **Step 3: Write the three roles and the template**

`roles/_template/ROLE.md`:
```markdown
You are <role name>, a one-shot role on Gravit's research team. Gravit hands you a strategy directory and a brief; you do one bounded piece of work inside it and return a report. You never edit THESIS.md, journal.md or status.yaml, and you draw no conclusion about the thesis.

Report, under exactly these four headings: **status** (`done` or `blocked`, one line of why); **what was measured**; **paths** (every file you wrote or read, relative to the strategy directory); **limits** (what you could not check). Keep it under 6,000 characters.
```
`roles/_template/role.yml`:
```yaml
# roles/_template/role.yml - copy the directory, then edit. The directory name is the id
# ([a-z0-9][a-z0-9-]*); the tool Gravit sees is role_<id> with - as _.
name: <role name>
description: <one line Gravit reads when it chooses a role, at most 300 characters>
# Exact tool names only (no wildcards): host tools by name, MCP tools as
# mcp__<server>__<raw> with the server named as the installed profile mounts it.
allow:
  - read
  - glob
  - grep
  - skill
# model: deepseek-official/deepseek-v4-flash   # optional: the route this role's children run on
```
`roles/_template/README.md`:
```markdown
# A role

One directory = one role = one `role_<id>` tool on Gravit's sessions, a one-shot child with its
own persona and an exact tool allow-list the dsh spawn backend enforces at the child's creation.

| File | Owner | What |
|---|---|---|
| `ROLE.md` | the operator | the child's persona; no `{{` (the prompt is a strict template); ≤ 2,000 bytes |
| `role.yml` | the operator | `name`, `description` (the summary Gravit reads, ≤ 300 chars), `allow` (exact tool names), optional `model` |

The face reads this directory at boot (`face/src/roles.ts`) and renders Gravit's composition from
it; `bots/gravit/agent.cordis.yml` is the generated mirror (`npm run render:roles` in `face/`),
and a test fails when it drifts. Gravit proposes a role in conversation and never writes here.
A tool a role names must exist in the tree when the role is called, or that call fails naming
the tool. A role never carries `ask_user_question` (a child has no human to ask), delegation,
goals, orders or the AKShare tools.
```
`roles/screener/ROLE.md`:
```markdown
You are the screener, a one-shot role on Gravit's research team. Gravit hands you a strategy directory and a brief; you run that strategy's screen over the point-in-time bed for the days asked and return the candidates with the fields that were actually measured.

Rules you keep: every market read goes through the PIT channels — the alpaca-kit MCP tools, or `screen.py` run from the strategy directory with the absolute bed path; you never read the market any other way. You write only the candidates file under the strategy directory; you never edit THESIS.md, journal.md or status.yaml, and you draw no conclusion about the thesis.

Report, under exactly these four headings: **status** (`done` or `blocked`, one line of why); **what was measured** (the days, the count of candidates per day, the fields, the days discarded and why); **paths** (every file you wrote, relative to the strategy directory); **limits** (what you could not check, warmup gaps, truncated results). Keep the whole report under 6,000 characters; the full candidate list goes in the file, not the report.
```
`roles/screener/role.yml`:
```yaml
name: Screener
description: Runs the strategy's screen over the PIT bed for the days you name and returns the candidates with the measured fields and the days discarded; writes only the candidates file, draws no conclusion.
allow:
  - bash
  - read
  - write
  - glob
  - grep
  - skill
  - mcp__alpaca-kit__screen
  - mcp__alpaca-kit__market_snapshot
  - mcp__alpaca-kit__breadth
  - mcp__alpaca-kit__daily_bars
  - mcp__alpaca-kit__calendar
  - mcp__alpaca-kit__corp_actions
  - mcp__alpaca-kit__earnings
```
`roles/backtester/ROLE.md`:
```markdown
You are the backtester, a one-shot role on Gravit's research team. Gravit hands you a strategy directory, the backtest to run (`backtest.py`, or the variant it names) and the window; you run it under the five rules of `docs/backtest-rules.md`, write the artifact under `backtests/`, and return the headline numbers.

Before you run anything, load the `backtest-rules` skill and keep every rule: the PIT channel through `replay_days`, the replay bounded to the bed window, a delisting as a terminal loss, gross returns unless THESIS.md declares a cost model, no same-day round trip, missing data discarded and counted. You may edit `backtest.py` to run the variant asked; you never edit THESIS.md, journal.md or status.yaml, and you never widen the window past the bed.

Report, under exactly these four headings: **status** (`done` or `blocked`, one line of why); **what was measured** (the window actually used, the sample size, hit rate, mean and median return, worst case, the count of discarded days, and each of the five rules marked kept or broken); **paths** (the artifact and any file you changed, relative to the strategy directory); **limits** (warmup, data gaps, anything approximate). Keep it under 6,000 characters.
```
`roles/backtester/role.yml`:
```yaml
name: Backtester
description: Runs backtest.py (or the variant you name) under the five honest-eval rules, bounded to the bed window, writes the artifact under backtests/ and returns the headline numbers with each rule marked kept or broken; never edits THESIS.md.
allow:
  - bash
  - read
  - write
  - edit
  - glob
  - grep
  - skill
  - mcp__alpaca-kit__daily_bars
  - mcp__alpaca-kit__calendar
  - mcp__alpaca-kit__corp_actions
  - mcp__alpaca-kit__earnings
```
`roles/reviewer/ROLE.md`:
```markdown
You are the reviewer, a one-shot role on Gravit's research team, and you only read. Gravit hands you a strategy directory; you audit THESIS.md, the artifacts under `backtests/` and journal.md against the five rules of `docs/backtest-rules.md` (load the `backtest-rules` skill first) and against the falsification terms THESIS.md pre-registered, and you report.

You check that every number in the journal is in an artifact and was measured as stated; that the replay stayed inside the bed window and past the warmup; that the five rules held; that the falsification terms are specific (metric, threshold, window) and that the artifacts decide them. You edit nothing and run no backtest: when something must be re-run, say so.

Report, under exactly these four headings: **status** (`done` or `blocked`); **what was measured** (each falsification term with the artifact that decides it and the verdict it implies — met, failed or undecided; every violation with file and line); **paths** (the files you read); **limits** (what you could not verify). End with one line — `recommend: validated`, `recommend: retired` or `recommend: continue` — and the reason. Keep it under 6,000 characters.
```
`roles/reviewer/role.yml`:
```yaml
name: Reviewer
description: Read-only audit of THESIS.md, the backtest artifacts and the journal against the five rules and the pre-registered falsification terms; reports violations with file and line and ends with recommend validated, retired or continue.
allow:
  - read
  - glob
  - grep
  - skill
  - mcp__alpaca-kit__daily_bars
  - mcp__alpaca-kit__calendar
  - mcp__alpaca-kit__corp_actions
  - mcp__alpaca-kit__market_snapshot
```

- [ ] **Step 4: Declare the package and write `face/src/roles.ts`**

Add `"@deepseek-ai/dsh-tool-subagent": "0.2.0-rc.2"` to `face/package.json` dependencies; `cd face && npm install`. Write `readRoles`, `toolNameFor` and the constants per the Interfaces block (the row rendering comes in Task 2). The header comment states why names are exact (`dsh-tools` `restrict()` checks `restrictableNames` membership in the child's creation window — installed `dsh-tools/lib/index.js`, `restrict`) and that a missing tool fails the delegation, not the boot.

- [ ] **Step 5: Run the tests**

Run: `cd face && npx tsx --test tests/roles.test.ts && npm run typecheck`
Expected: PASS (4 tests); tsc clean.

- [ ] **Step 6: Commit**

```bash
git add roles face/src/roles.ts face/tests/roles.test.ts face/package.json face/package-lock.json
printf '%s\n' 'feat: the role library on disk and face/src/roles.ts reads it' '' 'Three roles (screener, backtester, reviewer) and the template; exact tool names only.' > /tmp/msg-plan2-t1.txt
git commit -F /tmp/msg-plan2-t1.txt
```

---

### Task 2: Rendering: the rows, the `gravit:roles` section, the mirror and its drift test

**Files:**
- Modify: `face/src/roles.ts` (add `gravitRows`, `renderGravitComposition`, `GRAVIT_PLUGIN_URL`, `GRAVIT_ROW_ID`, `roleRowId`)
- Modify: `face/plugins/gravit.js` (the `roles` key → the `gravit:roles` section; `rolesText`, `isDelegated`)
- Create: `face/scripts/render-roles.ts`; Modify: `face/package.json` (script `"render:roles": "tsx scripts/render-roles.ts"`)
- Modify: `bots/gravit/agent.cordis.yml` (regenerated), `bots/gravit/preset.yml` (`description: the principal agent - the host composition plus the role library`)
- Modify: `face/tests/roles.test.ts`, `face/tests/gravit-plugin.test.ts`

**Interfaces:**
- Produces, in `face/src/roles.ts`:
  - `export const GRAVIT_ROW_ID = "gravit"`; `export const roleRowId = (id: string) => "role-" + id`
  - `export const GRAVIT_PLUGIN_URL: string` — `pathToFileURL(<face>/plugins/gravit.js).href`, module-relative (the in-memory form; a `file:` URL passes `rebaseName` untouched)
  - `export interface GravitRowsOptions { plugin: string; cycle?: string }`
  - `export function gravitRows(roles: readonly RoleFile[], options: GravitRowsOptions): PresetRow[]` — first `{ id: GRAVIT_ROW_ID, name: options.plugin, config: { roles: roles.map((r) => ({ tool: r.tool, summary: r.description })), ...(options.cycle === undefined ? {} : { cycle: options.cycle }) } }`, then per role `{ id: roleRowId(r.id), name: "@deepseek-ai/dsh-tool-subagent", config: { provider: "spawn", toolName: r.tool, backgroundMode: "one-shot", persona: r.persona, toolFilter: { allow: [...r.allow] }, ...(r.model === undefined ? {} : { agentOptions: { provider: r.model.split("/")[0], model: r.model.split("/")[1] } }) } satisfies ToolSubagentConfig }` with `ToolSubagentConfig` = `import type { Config } from "@deepseek-ai/dsh-tool-subagent"`. `PresetRow` is `PresetDefinition["plugins"][number]` (as `bot-presets.ts` names it; export it from there).
  - `export function renderGravitComposition(roles: readonly RoleFile[], options: { cycle?: string }): string` — a `GENERATED` header (three comment lines: generated by `face/src/roles.ts renderGravitComposition` from `roles/` and `dsh/profile/cycle.md`, do not hand-edit, `npm run render:roles`) + `dump(gravitRows(roles, { plugin: GRAVIT_PLUGIN_RELATIVE, cycle: options.cycle }), { schema: entryListSchema, lineWidth: -1, noRefs: true })`.
- Produces, in `face/plugins/gravit.js`:
  - `export const ROLES_SECTION = "gravit:roles"`
  - `export function isDelegated(context): boolean` — `context?.agent?.session?.header?.origin === "subagent"`
  - `export function rolesText(roles: {tool: string; summary: string}[]): string` — `""` for an empty list; otherwise `Roles. One-shot delegates on your team, each with its own persona and tools; call one by its tool name with a self-contained brief, and treat its report as a claim to check, never a result to copy. Every report carries four headings: status, what was measured, paths, limits.` then one line per role `- <tool> — <summary>`.
  - `apply` registers, when `config.roles` is present: `{ name: ROLES_SECTION, order: ctx.systemPrompt.getSectionOrder("TOOL_SUBAGENT") + 1, interpolate: false, text: (context) => isDelegated(context) ? "" : rolesText(config.roles) }` through `ctx.effect`.

- [ ] **Step 1: Write the failing tests**

Append to `face/tests/gravit-plugin.test.ts` (extend `fakeScope` so `getSectionOrder` accepts `"TOOL_SUBAGENT"` too):
```ts
test("gravit: the roles section follows dsh's subagent section, lists every role, and is empty for a delegated child", () => {
  const tree = fakeScope();
  const roles = [{ tool: "role_screener", summary: "runs the screen" }, { tool: "role_reviewer", summary: "audits" }];
  apply(tree.ctx, { roles });
  const section = tree.sections.find((s) => s.name === ROLES_SECTION)!;
  assert.ok(section, "registered");
  assert.equal(section.order, dshSectionOrder("TOOL_SUBAGENT") + 1);
  assert.equal(section.interpolate, false);
  const root = (section.text as (c: unknown) => string)({ agent: { session: { header: { origin: undefined } } } });
  assert.match(root, /^Roles\. /);
  assert.ok(root.includes("- role_screener — runs the screen") && root.includes("- role_reviewer — audits"));
  assert.equal((section.text as (c: unknown) => string)({ agent: { session: { header: { origin: "subagent" } } } }), "", "a child joins the preset and must not read Gravit's role list");
  assert.equal(isDelegated({ agent: { session: { header: { origin: "subagent" } } } }), true);
  assert.equal(isDelegated({}), false);
});

test("gravit: without a roles key there is no roles section; an empty list renders nothing", () => {
  const tree = fakeScope();
  apply(tree.ctx, {});
  assert.equal(tree.sections.some((s) => s.name === ROLES_SECTION), false);
  assert.equal(rolesText([]), "");
});
```
Append to `face/tests/roles.test.ts`:
```ts
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { GRAVIT_PLUGIN_URL, GRAVIT_ROW_ID, gravitRows, renderGravitComposition, roleRowId } from "../src/roles.ts";
import { GRAVIT_PLUGIN_RELATIVE } from "../src/overlay.ts";

test("gravitRows: the gravit row carries the summaries; one one-shot spawn row per role with persona and an exact allow list", () => {
  const roles = readRoles(ROLES_ROOT);
  const rows = gravitRows(roles, { plugin: GRAVIT_PLUGIN_URL }) as Array<{ id: string; name: string; config: Record<string, unknown> }>;
  assert.equal(rows[0].id, GRAVIT_ROW_ID);
  assert.equal(rows[0].name, GRAVIT_PLUGIN_URL);
  assert.ok(GRAVIT_PLUGIN_URL.startsWith("file:") && GRAVIT_PLUGIN_URL.endsWith("/face/plugins/gravit.js"));
  assert.deepEqual(rows[0].config, { roles: roles.map((r) => ({ tool: r.tool, summary: r.description })) });
  assert.equal(rows.length, 1 + roles.length);
  for (const role of roles) {
    const row = rows.find((r) => r.id === roleRowId(role.id))!;
    assert.equal(row.name, "@deepseek-ai/dsh-tool-subagent");
    assert.deepEqual(Object.keys(row.config).sort(), ["backgroundMode", "persona", "provider", "toolFilter", "toolName"]);
    assert.deepEqual(row.config, { provider: "spawn", toolName: role.tool, backgroundMode: "one-shot", persona: role.persona, toolFilter: { allow: role.allow } });
  }
});

test("the committed mirror bots/gravit/agent.cordis.yml is exactly the render of roles/ (drift fails here)", () => {
  const mirror = readFileSync(new URL("../../bots/gravit/agent.cordis.yml", import.meta.url), "utf8");
  assert.equal(mirror, renderGravitComposition(readRoles(ROLES_ROOT), {}), "run: cd face && npm run render:roles");
  assert.ok(mirror.includes(`name: ${GRAVIT_PLUGIN_RELATIVE}`), "the mirror names the plugin by the shipped relative path");
  assert.equal(mirror.includes("file:"), false, "and never by a machine-specific URL");
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd face && npx tsx --test tests/roles.test.ts tests/gravit-plugin.test.ts`
Expected: FAIL — `gravitRows` not exported; `ROLES_SECTION` not exported.

- [ ] **Step 3: Implement `gravitRows`, `renderGravitComposition`, the plugin section, the script**

Per the Interfaces. `face/scripts/render-roles.ts` writes `renderGravitComposition(readRoles(ROLES_ROOT), {})` to `<BOTS_ROOT>/gravit/agent.cordis.yml` and prints the path (plan 3 adds the cycle). Then run it once: `cd face && npm run render:roles`; set `bots/gravit/preset.yml`'s description.

- [ ] **Step 4: Run the tests**

Run: `cd face && npx tsx --test tests/roles.test.ts tests/gravit-plugin.test.ts && npm run typecheck`
Expected: PASS; tsc clean.

- [ ] **Step 5: Commit**

```bash
git add face/src/roles.ts face/plugins/gravit.js face/scripts/render-roles.ts face/package.json bots/gravit/agent.cordis.yml bots/gravit/preset.yml face/tests/roles.test.ts face/tests/gravit-plugin.test.ts
printf '%s\n' 'feat(face): render Gravit composition from roles/; the gravit:roles section; the generated mirror' > /tmp/msg-plan2-t2.txt
git commit -F /tmp/msg-plan2-t2.txt
```

---

### Task 3: `composeFace` builds the default preset from `roles/`

**Files:**
- Modify: `face/src/bot-presets.ts` (`definitionFor(botsRoot, id, rows?)`; export `PresetRow`)
- Modify: `face/src/boot.ts` (`FaceBootOptions.rolesRoot?`; `composeFace` reads the roles and hands the rows to `definitionFor` for the default — and to the legacy alias the rename declares beside it)
- Modify: `face/tests/boot.test.ts`, `face/tests/bot-presets.test.ts`

**Interfaces:**
- `definitionFor(botsRoot: string, id: string, rows?: readonly unknown[]): PresetDefinition` — with `rows`, the composition file is not read (its absence is not an error) and `rows` are rebased exactly as file rows are; without, unchanged.
- `FaceBootOptions.rolesRoot?: string` — the `roles/` directory; tests point it at a fixture; defaults to `ROLES_ROOT`.
- `composeFace` produces the default preset as `definitionFor(botsRoot, DEFAULT_PRESET, gravitRows(readRoles(rolesRoot), { plugin: GRAVIT_PLUGIN_URL }))`; a `readRoles` throw refuses the compose with the file path (the fail-loud contract, spec §5.1). Wherever the rename builds the legacy alias from the default definition, it receives this definition.

- [ ] **Step 1: Write the failing tests**

In `face/tests/boot.test.ts` replace the plan-1 test "composeFace takes the static preset row from bots/gravit" with:
```ts
import { GRAVIT_PLUGIN_URL, gravitRows, readRoles } from "../src/roles.ts";

test("composeFace builds preset-gravit from roles/ in memory: the gravit row by absolute URL, one spawn row per role", async () => {
  const home = freshHome();
  const bots = await makeBotsRoot();
  const rolesRoot = await makeRolesRoot();   // the helper from roles.test.ts, moved to bots-fixture.ts as `makeRolesRoot`
  try {
    const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home, botsRoot: bots, rolesRoot });
    const row = composeEntries([patches]).find((entry) => entry.id === "preset-gravit");
    const expected = definitionFor(bots, "gravit", gravitRows(readRoles(rolesRoot), { plugin: GRAVIT_PLUGIN_URL }));
    assert.deepEqual(row?.config, expected);
    const plugins = (row?.config as { plugins: Array<{ id: string; name: string }> }).plugins;
    assert.deepEqual(plugins.map((p) => p.id), ["gravit", "role-probe"]);
    assert.equal(plugins[0].name, GRAVIT_PLUGIN_URL);
  } finally { await rm(rolesRoot, { recursive: true, force: true }); }
});

test("composeFace refuses a roles root with a bad role, naming the file", async () => {
  const home = freshHome();
  const rolesRoot = await makeRolesRoot();
  try {
    await writeFile(join(rolesRoot, "probe", "ROLE.md"), "You are {{nobody}}.\n");
    assert.throws(() => composeFace({ profileName: "face", port: 3090, dshHome: home, rolesRoot }), (e: Error) => e.message.includes(join(rolesRoot, "probe", "ROLE.md")));
  } finally { await rm(rolesRoot, { recursive: true, force: true }); }
});
```
In `face/tests/bot-presets.test.ts`, the two default-definition tests from plan 1 become: `definitionFor(root, "gravit", [{ id: "gravit", name: GRAVIT_PLUGIN_URL, config: {} }])` deep-equals `{ id: "gravit", name: "Gravit", description: …, plugins: [{ id: "gravit", name: GRAVIT_PLUGIN_URL, config: {} }] }` (a `file:` URL passes through), and `definitionFor(root, "gravit", rows)` succeeds after `rm(join(root, "gravit", "agent.cordis.yml"))` (the file is not read when rows are given).

- [ ] **Step 2: Run them to verify they fail**

Run: `cd face && npx tsx --test tests/boot.test.ts tests/bot-presets.test.ts`
Expected: FAIL on the `rows` argument / `rolesRoot` option.

- [ ] **Step 3: Implement**

`definitionFor` gains the optional `rows`; `composeFace` reads `readRoles(opts.rolesRoot ?? ROLES_ROOT)` before `faceOverlay(...)` and passes the rows; the comment at the static row (boot.ts ~379–388) now says the default is rendered from `roles/`, the mirror file is for readers, and a bad role refuses the compose. Move `makeRolesRoot` into `face/tests/bots-fixture.ts` (export) and import it from both test files. Update `boot.test.ts`'s "refuses a default preset whose composition is missing" test: with rows given the file is not read, so the test now removes `bots/gravit/preset.yml`? No — an absent `preset.yml` is empty metadata by design; delete that test and replace it with the bad-role refusal above.

- [ ] **Step 4: Run the offline suite and the smokes that boot the default**

Run: `cd face && npm test && npm run typecheck && FACE_SMOKE=1 npx tsx --test tests/bots-smoke.test.ts tests/room-smoke.test.ts tests/instructions-smoke.test.ts`
Expected: green. The smokes boot with the repo's `roles/` (the default `rolesRoot`), so each real tree now mounts three `dsh-tool-subagent` rows inside the preset; a mount failure here would be the registry's `broken` → `bootFace`'s roster audit refusal.

- [ ] **Step 5: Commit**

```bash
git add face/src/bot-presets.ts face/src/boot.ts face/tests/boot.test.ts face/tests/bot-presets.test.ts face/tests/bots-fixture.ts face/tests/roles.test.ts
printf '%s\n' 'feat(face): the default preset is rendered from roles/ at compose time' > /tmp/msg-plan2-t3.txt
git commit -F /tmp/msg-plan2-t3.txt
```

---

### Task 4: The roles smoke — a child with the role's persona and exactly its tools

**Files:**
- Create: `face/tests/roles-smoke.test.ts`
- Modify: `face/tests/bots-smoke.test.ts` (S3: Gravit's view = the host's plus the three role tools; a bot's view has none)

**Interfaces:**
- Consumes: the stub-LLM boot pattern of `subagents-smoke.test.ts` (scratch profile with `agent-default-model: stub/echo`, `mcp-akshare` disabled, `registerAdapter(["stub"], …)`, `session/create` + `session/prompt` over the cookie, `requested` map keyed by session id, `header.origin === "subagent"`), `tools.register` stand-ins as `bots-smoke.test.ts` registers `mcp__drill__submit_order`.

- [ ] **Step 1: Update S3 in `bots-smoke.test.ts`**

Replace the "adds and removes nothing" assertion with:
```ts
assert.deepEqual(names(tools.schemas(gravit)), [...names(tools.schemas()), "role_backtester", "role_reviewer", "role_screener"].sort(),
  "Gravit's tools are the host's plus the role library (spec §5.1)");
```
and in the bot block: `assert.equal(names(tools.schemas(probe)).some((n) => n.startsWith("role_")), false, "a bot never sees a role tool")`.

- [ ] **Step 2: Write the roles smoke**

```ts
/** Role delegation on a real tree: `role_reviewer` and `role_screener` spawn a
 * one-shot child whose persona is the role's (shadowing Gravit's), whose tools
 * are exactly the role's allow list (ancestor-layer `role_*` tools removed,
 * `gravit:roles` blank), and whose result returns through the tool; a role
 * naming a tool the tree lacks fails loudly at delegation. The MCP tools the
 * roles name are stand-ins registered under the exact production names.
 * Own file, gated. */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { GenerateOptions } from "@deepseek-ai/dsh-llm";
import { SessionId } from "@deepseek-ai/dsh-session";
import { assembleContextFor } from "@deepseek-ai/dsh-agent";
import { renderPrompt } from "@deepseek-ai/dsh-system-prompt";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { ROLES_ROOT, readRoles } from "../src/roles.ts";
import { makeBotsRoot } from "./bots-fixture.ts";
import { mountClient, remote, signIn } from "./remote.ts";
import { StubAdapter, type StubReply } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
const sourceKind = (m: { source?: unknown }) => ((m.source ?? {}) as { kind?: string }).kind;
const textOf = (m: GenerateOptions["messages"][number]) => m.content.map((b) => "text" in b ? b.text : "").join("\n");
const lastHuman = (r: GenerateOptions) => [...r.messages].reverse().find((m) => ["user", "tool"].includes(String(sourceKind(m))));
async function waitFor(label: string, check: () => boolean, ms = 30_000) {
  const until = Date.now() + ms;
  while (!check()) { if (Date.now() >= until) throw new Error(`timed out: ${label}`); await new Promise((r) => setTimeout(r, 20)); }
}

test("roles smoke: persona, exact tools, the result, and a loud failure for a missing tool", { skip: gated && "set FACE_SMOKE=1", timeout: 180_000 }, async () => {
  const bots = await makeBotsRoot();
  const root = await realpath(await mkdtemp(join(tmpdir(), "face-roles-root-")));
  const home = await mkdtemp(join(tmpdir(), "face-roles-home-"));
  let dispose: (() => Promise<void>) | undefined;
  try {
    await mkdir(join(root, ".git"));
    await writeFile(join(root, "GRAVIT.md"), "# fixture\n");
    setupFaceProfile(home);
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n- id: agent-default-model\n  config:\n    provider: stub\n    model: echo\n`);
    const booted = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    dispose = booted.dispose;
    const { ctx } = booted;
    const tools = ctx.get("tools") as { register(d: unknown): () => void; schemas(scope?: object): { name: string }[] };
    /* Stand-ins under the exact production names the shipped roles allow, plus one they do not. */
    const mcpNames = new Set(readRoles(ROLES_ROOT).flatMap((r) => r.allow).filter((n) => n.startsWith("mcp__")));
    mcpNames.add("mcp__alpaca-kit__account");
    const unregister = new Map<string, () => void>();
    for (const name of mcpNames) unregister.set(name, tools.register({ name, description: `stand-in ${name}`, parameters: {}, output: { schema: { type: "object" }, render: () => [{ type: "text", text: "ok" }] }, execute: async () => ({}) }));
    const requested = new Map<string, GenerateOptions[]>();
    const script = (request: GenerateOptions): StubReply => {
      if (request.purpose !== undefined) return { kind: "text", text: "fixture" };
      const id = String(request.sessionId);
      requested.set(id, [...requested.get(id) ?? [], request]);
      const header = ctx.sessions.get(request.sessionId!)?.header;
      const trigger = lastHuman(request);
      const text = trigger ? textOf(trigger) : "";
      if (header?.origin === "subagent") return { kind: "text", text: text.includes("REVIEW_FIXTURE") ? "REVIEW_DONE" : "SCREEN_DONE" };
      if (sourceKind(trigger!) === "user" && text === "RUN_REVIEWER") return { kind: "tool", name: "role_reviewer", args: { description: "Audit the fixture", prompt: "REVIEW_FIXTURE: audit the fixture strategy." } };
      if (sourceKind(trigger!) === "user" && text === "RUN_SCREENER") return { kind: "tool", name: "role_screener", args: { description: "Screen one day", prompt: "SCREEN_FIXTURE: screen 2025-06-05." } };
      return { kind: "text", text: "PARENT_DONE" };
    };
    ctx.llm.registerAdapter(["stub"], new StubAdapter(script));
    const base = `http://127.0.0.1:${ctx.webServer.port}`;
    mountClient(ctx);
    const cookie = await signIn(ctx, base);
    const { sessionId } = await remote<{ sessionId: string }>(base, cookie, "session/create", { request: { cwd: root } });
    const gravit = ctx.agents.get(SessionId(sessionId))!;
    const prompt = (value: string) => remote(base, cookie, "session/prompt", { request: { requestId: `roles-${crypto.randomUUID()}`, sessionId, mode: "queue", content: [{ type: "text", text: value }] } });
    const gravitPrompt = renderPrompt(await ctx.systemPrompt.assemble(assembleContextFor(gravit)));
    assert.ok(gravitPrompt.includes("- role_reviewer — "), "Gravit reads the roles section");
    const childRequestAfter = async (marker: string) => {
      await waitFor(`child ${marker}`, () => [...requested.entries()].some(([id, rs]) => ctx.sessions.get(SessionId(id))?.header.origin === "subagent" && rs.some((r) => r.messages.some((m) => textOf(m).includes(marker)))));
      const [id, rs] = [...requested.entries()].find(([id, rs]) => ctx.sessions.get(SessionId(id))?.header.origin === "subagent" && rs.some((r) => r.messages.some((m) => textOf(m).includes(marker))))!;
      return { id: SessionId(id), request: rs[0], header: ctx.sessions.get(SessionId(id))!.header };
    };
    /* reviewer */
    await prompt("RUN_REVIEWER");
    const reviewer = await childRequestAfter("REVIEW_FIXTURE");
    await gravit.whenIdle();
    const reviewerTools = reviewer.request.tools!.map((t) => t.name).sort();
    for (const kept of ["read", "glob", "grep", "skill", "mcp__alpaca-kit__daily_bars", "mcp__alpaca-kit__calendar", "mcp__alpaca-kit__corp_actions", "mcp__alpaca-kit__market_snapshot"]) assert.ok(reviewerTools.includes(kept), `reviewer keeps ${kept}`);
    for (const gone of ["bash", "write", "edit", "ask_user_question", "web_search", "subagent", "subagent_fork", "send_message", "role_reviewer", "role_screener", "role_backtester", "mcp__alpaca-kit__account", "mcp__alpaca-kit__screen"]) assert.equal(reviewerTools.includes(gone), false, `reviewer never sees ${gone}`);
    const system = reviewer.request.messages[0];
    assert.equal(system.role, "system");
    assert.ok(textOf(system).includes("You are the reviewer"), "the role persona is the child's");
    assert.equal(textOf(system).includes("You are Gravit"), false, "and it shadows Gravit's");
    assert.equal(textOf(system).includes("Roles. One-shot delegates"), false, "the roles section is blank for a child");
    assert.match(textOf(system), /Today is \d{4}-\d{2}-\d{2}/, "the date reaches the child");
    assert.equal(reviewer.header.origin, "subagent");
    assert.equal(reviewer.header.agentPreset, "gravit");
    assert.equal(reviewer.header.cwd, root);
    assert.ok(gravit.session.snapshotEvents().some((e) => e.type === "tool/result" && JSON.stringify(e.data).includes("REVIEW_DONE")), "the child's text returns through the tool");
    /* screener */
    await prompt("RUN_SCREENER");
    const screener = await childRequestAfter("SCREEN_FIXTURE");
    await gravit.whenIdle();
    const screenerTools = screener.request.tools!.map((t) => t.name);
    assert.ok(["bash", "write", "mcp__alpaca-kit__screen"].every((n) => screenerTools.includes(n)));
    assert.equal(screenerTools.includes("edit"), false);
    /* a tool the tree lacks: the delegation fails naming it, no child runs */
    unregister.get("mcp__alpaca-kit__earnings")!();
    const childrenBefore = [...requested.keys()].filter((id) => ctx.sessions.get(SessionId(id))?.header.origin === "subagent").length;
    await prompt("RUN_SCREENER");
    await gravit.whenIdle();
    const failed = gravit.session.snapshotEvents().filter((e) => e.type === "tool/result").at(-1)!;
    assert.match(JSON.stringify(failed.data), /unknown global tool.*mcp__alpaca-kit__earnings/);
    assert.equal([...requested.keys()].filter((id) => ctx.sessions.get(SessionId(id))?.header.origin === "subagent").length, childrenBefore, "no child was created");
  } finally {
    await dispose?.();
    await Promise.all([rm(bots, { recursive: true, force: true }), rm(root, { recursive: true, force: true }), rm(home, { recursive: true, force: true })]);
  }
});
```

- [ ] **Step 3: Run both smokes**

Run: `cd face && FACE_SMOKE=1 npx tsx --test tests/roles-smoke.test.ts tests/bots-smoke.test.ts`
Expected: PASS. If the missing-tool assertion's wording differs (the error text is dsh's: `tools.restrict() names unknown global tool "mcp__alpaca-kit__earnings"`), pin the exact text seen.

- [ ] **Step 4: Run the whole gated suite and commit**

Run: `cd face && FACE_SMOKE=1 npm test`
Expected: green (fourteen real boots).
```bash
git add face/tests/roles-smoke.test.ts face/tests/bots-smoke.test.ts
printf '%s\n' 'test(face): the roles smoke - persona, exact tools, the result, the loud missing-tool failure' > /tmp/msg-plan2-t4.txt
git commit -F /tmp/msg-plan2-t4.txt
```

---

### Task 5: The role drill and the documents

**Files:**
- Modify: `face/README.md` (a section "Roles (roles/ + src/roles.ts + plugins/gravit.js)" after "Bots", and "The role drill (run after any face or dsh change)" after "The room drill"; "Tests": the fourteenth boot)
- Modify: `DEVELOPMENT.md` (§3.6 a `role_<id>` row: "Gravit's preset, `src/roles.ts`; scoped — a bot never sees it; a child removes it through its own allow list"; a new §3.8 "The role directory contract" modeled on §3.7; §3.7's state paragraph; §4.3 the default preset's rows; §4.2 module rows for `src/roles.ts` and `plugins/gravit.js`; §7.3 the new tests; §7.4 the role drill)
- Modify: `CLAUDE.md` (a `roles/` row; the `bots/` row's `gravit` text names the role rows)
- Modify: `Gravit-Design.md` §4 (the write-map row for `roles/<id>/`: operator by file edit; Gravit proposes, never authors; git and the drift test)
- Modify: `docs/dsh-upgrade-guide.md` (§3.2 group C: `C20 per-role dsh-tool-subagent rows inside the default preset: config keys provider/toolName/backgroundMode/persona/toolFilter (+agentOptions), the row's persona as the child's deployment:persona-prefix, toolFilter as tools.restrict({allow}) of exact names in the child's creation window (roles.test.ts, roles-smoke)`; §3.1 a hand-check row: the operator's MCP server name as written in `roles/*/role.yml`; §7.3 bullets two and three marked landed)

- [ ] **Step 1: Write the role drill (manual, scratch home with the operator's MCP rows)**

Into `face/README.md`, after the room drill:
```markdown
## The role drill (run after any face or dsh change)

On a face booted against a COPY of the harness home with the operator's MCP rows mounted (the
runbook's §7 A recipe: `DSH_HOME=$SCRATCH/dsh-drill FACE_PORT=3091 npm start`, real keys).

1. Open the `room-drill` channel and send: "Use role_screener for one day, 2025-06-05, on the
   2yr bed, and report." Expected: Gravit calls `role_screener` (one tool card), waits, and
   relays a report with the four headings; no card for the operator.
2. The agent panel's child history lists one `one-shot` child labelled by the description
   Gravit gave it. Read its first request's `header.tools` from its log (the durable proof of
   what was offered; the ask-user drill's step 7 recipe reads the zstd log): exactly the
   screener's allow list — no `mcp__alpaca-kit__account`, no `subagent`, no `role_*` — and its
   system prompt opens with the screener's persona, not Gravit's.
3. Stop the alpaca-kit server (kill its process) and send: "Run role_reviewer on this strategy."
   Expected: the tool result is an error naming `mcp__alpaca-kit__…` as an unknown global tool;
   no child is created. Restart the face.
4. `/data/plugins.json` lists the three `role-*` rows under the `preset-gravit` entry, ACTIVE.
Record the date and the pin in DEVELOPMENT.md §7.4.
```

- [ ] **Step 2: Run the drill once; record it**

The operator (or the implementer in the operator's terminal) runs steps 1–4; the date goes into `DEVELOPMENT.md` §7.4's table as `passed <date>` or the failure is fixed first.

- [ ] **Step 3: The documents**

Per the Files list; §3.8's text follows §3.7's shape: the files, who writes them, how the face reads them, the grammar, the exact-name rule and its reason, the mirror and the drift test, the child's view (joins the preset; allow removes the role tools; sections blank), the never-`ask_user_question` rule.

- [ ] **Step 4: Verify and commit**

Run: `grep -n "role_" DEVELOPMENT.md face/README.md CLAUDE.md | wc -l ; cd face && npm test && npm run typecheck`
Expected: a non-zero count; green.
```bash
git add face/README.md DEVELOPMENT.md CLAUDE.md Gravit-Design.md docs/dsh-upgrade-guide.md
printf '%s\n' 'docs: the role library, its drill, and the seams it adds' > /tmp/msg-plan2-t5.txt
git commit -F /tmp/msg-plan2-t5.txt
```

---

## Self-review (done while writing)

- **Spec coverage.** §5.1 (Tasks 2–3), §5.2 (Task 1), §5.3 (Task 1's three roles and lists), §5.4 as corrected (Task 4's child assertions, Task 2's blank section), §5.5 (Task 4's bot assertion), §8 plan-2 rows (`roles/`, `roles.ts`, `render-roles.ts`, the mirror, `bot-presets.ts`, `bots.ts`'s `isDefault` text — the latter is unchanged because the bots page already describes the default as the host composition; `preset.yml` carries the new description), §9 (`roles.test.ts`, `gravit-plugin.test.ts`, `boot.test.ts`, `roles-smoke`, the moved tests, the role drill). §11.1 (a) and (b) are the plan's premises.
- **Step scan.** Every code step names its file and signature; the role texts are deliverables; `roles.ts`'s bodies are determined by the tests and the Interfaces.
- **Type consistency.** `RoleFile`, `readRoles`, `toolNameFor`, `gravitRows`, `GravitRowsOptions`, `renderGravitComposition`, `GRAVIT_PLUGIN_URL`, `GRAVIT_ROW_ID`, `roleRowId`, `ROLES_ROOT` (roles.ts); `GRAVIT_PLUGIN_RELATIVE` (overlay.ts, plan 1); `ROLES_SECTION`, `rolesText`, `isDelegated` (gravit.js); `definitionFor(botsRoot, id, rows?)` and `PresetRow` (bot-presets.ts); `FaceBootOptions.rolesRoot`; `makeRolesRoot` (bots-fixture.ts) — each used by exactly the names defined.
- **Review Focus.** All five pinned (Tasks 4, 4+2, 1, 1, 2).
- **Proportion.** About plan 1's length; the role texts and the smoke are the bulk.
