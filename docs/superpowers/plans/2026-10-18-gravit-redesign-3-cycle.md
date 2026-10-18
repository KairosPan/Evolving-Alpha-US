# Gravit Redesign · Plan 3: The Cycle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One operator message with an idea produces one batched question and then a research cycle that runs to its verdict under a dsh goal, inside the strategy directory, with the role library doing the screen, the backtests and the audit; the charter and `DEVELOPMENT.md` say so; the first cycle and the first request are measured.

**Architecture:** The cycle is a contract text, `dsh/profile/cycle.md`, injected by `face/plugins/gravit.js` as the `gravit:cycle` section for Gravit's sessions only (blank for delegated children), carried into the composition the same way the role summaries are (the `gravit` row's `cycle` key, rendered by `face/src/roles.ts` and mirrored in `bots/gravit/agent.cordis.yml`). The loop itself is dsh's: `create_goal` with `max_goal_rounds: 24`, the round driver, `update_goal` for completion, blocking and the operator-authorized resume. No face code drives a round.

**Tech Stack:** as plans 1 and 2; dsh-base's `goal`, `goal-round-driver`, `tool-goal` rows, already mounted on Gravit's tree.

**Spec:** `docs/superpowers/specs/2026-10-15-gravit-agent-redesign-design.md` — §6 (the research cycle), §7 (prompt budget), §10 (the charter and `DEVELOPMENT.md` amendments), §11.1 (e) (the goal facts), §12 (plan 3).

## Global Constraints

- Plans 1 and 2 have merged into this branch (Task 0 checks). Plan 1's and plan 2's constraints bind.
- `dsh/profile/cycle.md` is ≤ 3,000 bytes, English, and is the ONLY file that tells Gravit how to run a cycle; `persona.md` stays as plan 1 left it (B6), `GRAVIT.md` carries no behaviour.
- The goal facts (installed dsh 0.2.0-rc.2): `create_goal(objective, max_goal_rounds)`; `update_goal(goal_id, revision, action ∈ edit|pause|resume|complete|blocked, objective?, max_goal_rounds?, blocked_reason?)`; the model's `resume` is accepted only in a direct human turn on a root agent; a paused goal is never the model's to resume; the model-path blocked code is always `model-reported`; an automatic round may not block before round 3 (`blockedAfterConsecutiveRounds`); the driver blocks at the cap with `round-limit`. The contract text states what the model can do, never what it cannot reach.
- Caps per cycle (B8): 24 goal rounds (enforced by the goal), 12 role calls (a journal count, D16). No wall clock. Usage recorded, not capped.
- Docs are a first-class deliverable: the charter edits of §10 land here, exactly as listed in Task 4.

## Review Focus

1. The cycle text leaking into a role child, which has no goal tools and would try to "open a goal": the section must be blank for a delegated child. Pinned by `gravit-plugin.test.ts` and `roles-smoke.test.ts` (Tasks 1–2).
2. A restart mid-cycle: the goal is disarmed, nothing continues, and the operator's next message must be enough; expected: the contract tells Gravit to `update_goal resume` on that message. Pinned by the cycle drill's restart step (Task 3); the mechanism is dsh's (§11.1 e).
3. Gravit blocking an automatic round before round 3 and getting `GOAL_TOOL_BLOCK_THRESHOLD`: the contract tells it to continue until it may. Pinned by the drill's blocked-path step (Task 3).
4. `cycle.md` edited with a `{{` group: the section is `interpolate: false`, so braces are literal, not an error — expected: allowed; pinned by `cycle.test.ts` (Task 1), so the rule is stated, not assumed.
5. The mirror drifting once `cycle` joins the composition: pinned by the drift test now rendering with the cycle (Task 1).

---

### Task 0: Precondition

- [ ] **Step 1: Plans 1 and 2 are in**

Run: `test -d roles/reviewer && grep -n 'gravitRows' face/src/roles.ts | head -1 && cd face && npm test && npm run typecheck`
Expected: the directory exists, the grep prints, both suites green.

---

### Task 1: `cycle.md`, `face/src/cycle.ts`, the `gravit:cycle` section, the composition

**Files:**
- Create: `dsh/profile/cycle.md`
- Create: `face/src/cycle.ts`; Create: `face/tests/cycle.test.ts`
- Modify: `face/plugins/gravit.js` (`CYCLE_SECTION`; the `cycle` key → the section)
- Modify: `face/src/boot.ts` (`FaceBootOptions.cyclePath?`; `composeFace` passes `cycle` into `gravitRows`), `face/scripts/render-roles.ts` (renders with the cycle)
- Modify: `GRAVIT.md` (the "A new strategy starts with one batched `ask_user_question`…" sentence plan 1 added is removed: it lives in `cycle.md` now)
- Modify: `bots/gravit/agent.cordis.yml` (regenerated), `face/tests/gravit-plugin.test.ts`, `face/tests/boot.test.ts`, `face/tests/roles.test.ts`

**Interfaces:**
- Produces, in `face/src/cycle.ts`: `export const CYCLE_PATH: string` (`<repo>/dsh/profile/cycle.md`, module-relative like `PERSONA_PATH`); `export const CYCLE_MAX_BYTES = 3000`; `export function readCycle(path: string): string` — the trimmed text; throws with the path when empty or over `CYCLE_MAX_BYTES`; braces are allowed (the section does not interpolate).
- Produces, in `face/plugins/gravit.js`: `export const CYCLE_SECTION = "gravit:cycle"`; `apply` registers, when `config.cycle` is present, `{ name: CYCLE_SECTION, order: ctx.systemPrompt.getSectionOrder("DEPLOYMENT_PERSONA_SUFFIX") - 50, interpolate: false, text: (context) => isDelegated(context) ? "" : config.cycle }`.
- `FaceBootOptions.cyclePath?: string` — defaults to `CYCLE_PATH`; `composeFace` passes `readCycle(...)` as `cycle` to `gravitRows`; a throw refuses the compose with the path.
- `renderGravitComposition(roles, { cycle })` and the mirror now carry the cycle text as the `gravit` row's `cycle` (a YAML block scalar).

- [ ] **Step 1: Write the failing tests**

`face/tests/cycle.test.ts`:
```ts
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CYCLE_MAX_BYTES, CYCLE_PATH, readCycle } from "../src/cycle.ts";

test("the shipped cycle.md reads, fits its budget, and carries the six steps and the caps", () => {
  const text = readCycle(CYCLE_PATH);
  assert.ok(Buffer.byteLength(text, "utf8") <= CYCLE_MAX_BYTES);
  for (const step of ["Step 0", "Step 1", "Steps 2 to 5", "Step 6"]) assert.ok(text.includes(step), step);
  assert.ok(text.includes("max_goal_rounds 24") && text.includes("12 role calls"));
  assert.ok(text.includes("update_goal with action resume"), "the restart path is stated");
  assert.ok(text.includes("child-limit, bed-window, data-missing or needs-operator"), "the blocked vocabulary is stated");
});

test("readCycle: trimmed; empty and oversized refused with the path; braces allowed", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-cycle-"));
  const good = join(dir, "cycle.md");
  await writeFile(good, "\n# Cycle\n\nOpen {{nothing}}.\n\n");
  assert.equal(readCycle(good), "# Cycle\n\nOpen {{nothing}}.");
  const empty = join(dir, "empty.md");
  await writeFile(empty, "  \n");
  assert.throws(() => readCycle(empty), (e: Error) => e.message.includes(empty) && /empty/.test(e.message));
  const big = join(dir, "big.md");
  await writeFile(big, "x".repeat(CYCLE_MAX_BYTES + 1));
  assert.throws(() => readCycle(big), /bytes/);
});
```
Append to `face/tests/gravit-plugin.test.ts` (extend `fakeScope`'s `getSectionOrder` to accept `"DEPLOYMENT_PERSONA_SUFFIX"`):
```ts
test("gravit: the cycle section sits just before the persona suffix, is literal, and is blank for a delegated child", () => {
  const tree = fakeScope();
  apply(tree.ctx, { cycle: "# The research cycle\n\nStep 0 — ask once." });
  const section = tree.sections.find((s) => s.name === CYCLE_SECTION)!;
  assert.ok(section);
  assert.equal(section.order, dshSectionOrder("DEPLOYMENT_PERSONA_SUFFIX") - 50);
  assert.equal(section.interpolate, false);
  assert.equal((section.text as (c: unknown) => string)({ agent: { session: { header: {} } } }), "# The research cycle\n\nStep 0 — ask once.");
  assert.equal((section.text as (c: unknown) => string)({ agent: { session: { header: { origin: "subagent" } } } }), "");
  assert.equal(fakeScope().sections.length, 0);
});
```
In `face/tests/boot.test.ts`: the plan-2 test "composeFace builds preset-gravit from roles/ in memory" also asserts `(plugins[0].config as { cycle: string }).cycle === readCycle(CYCLE_PATH)`; a new test: `composeFace({ …, cyclePath: join(dir, "empty.md") })` throws naming that path. In `face/tests/roles.test.ts`: the drift test renders `renderGravitComposition(readRoles(ROLES_ROOT), { cycle: readCycle(CYCLE_PATH) })`.

- [ ] **Step 2: Run them to verify they fail**

Run: `cd face && npx tsx --test tests/cycle.test.ts tests/gravit-plugin.test.ts tests/boot.test.ts tests/roles.test.ts`
Expected: FAIL — `../src/cycle.ts` missing; `CYCLE_SECTION` missing; the mirror lacks `cycle`.

- [ ] **Step 3: Write `dsh/profile/cycle.md`**

The exact file:

```markdown
# The research cycle

You run research in cycles: one idea, one strategy directory, one cycle, run to its verdict.

Step 0 — ask once. A new strategy starts with ONE batched ask_user_question and no code: the
thesis in a paragraph; the falsification terms as metric, threshold and window; the bed and the
window, with warmup moving the honest start; what the operator wants measured. A brief that
already answers these is the answer: skip the ask.

Step 1 — open the goal. create_goal with the brief and the verdict criteria as the objective
and max_goal_rounds 24. The goal is the cycle's record: while it is active and armed, the round
driver prompts you again at idle until you complete or block it. After a restart an active goal
is disarmed; when the operator asks you to continue, in any wording, update_goal with action
resume re-arms it. A paused goal is the operator's to resume, not yours.

Steps 2 to 5 — work in rounds. Write THESIS.md and set status researching. Delegate the screen
to role_screener, each backtest to role_backtester, and the audit to role_reviewer before you
conclude; a role's report is a claim to check against its artifacts, never a result to copy.
Journal every result as a dated entry with the artifact paths and the numbers as measured.
Iterate while the falsification terms are undecided and the caps have room: 24 rounds, which
the goal enforces, and 12 role calls per cycle, which you count in the journal and stop at.

Step 6 — the verdict. status.yaml: validated or retired, each citing the pre-registered terms it
met or failed, or researching with the goal blocked. Fill one_line, next and numbers. The
journal's last entry is the verdict with the usage the face shows for this session. Complete the
goal. Tell the operator the verdict, what to read, and the usage.

Blocking and asking. update_goal with action blocked and a reason whose first word is one of
child-limit, bed-window, data-missing or needs-operator, then the explanation; an automatic
round may not block before its third round, so continue until it may. After Step 0, ask the
operator again only to stop — the bed cannot cover the window asked — never to continue.
```

- [ ] **Step 4: Implement `cycle.ts`, the plugin section, the compose option, the script; regenerate; trim `GRAVIT.md`**

Per the Interfaces. Remove from `GRAVIT.md` the sentence beginning "A new strategy starts with one batched" through "is the answer." (the paragraph's earlier sentences stay). Run `cd face && npm run render:roles`.

- [ ] **Step 5: Run the offline suite**

Run: `cd face && npm test && npm run typecheck`
Expected: green, including `gravit-md.test.ts` (the budget still holds) and the drift test.

- [ ] **Step 6: Commit**

```bash
git add dsh/profile/cycle.md face/src/cycle.ts face/tests/cycle.test.ts face/plugins/gravit.js face/src/boot.ts face/scripts/render-roles.ts GRAVIT.md bots/gravit/agent.cordis.yml face/tests/gravit-plugin.test.ts face/tests/boot.test.ts face/tests/roles.test.ts
printf '%s\n' 'feat: the research-cycle contract as the gravit:cycle section, for Gravit sessions only' > /tmp/msg-plan3-t1.txt
git commit -F /tmp/msg-plan3-t1.txt
```

---

### Task 2: The smokes see the contract where it belongs

**Files:**
- Modify: `face/tests/bots-smoke.test.ts` (S3: Gravit's prompt contains `Step 0 — ask once`; the bot's does not)
- Modify: `face/tests/roles-smoke.test.ts` (the reviewer child's system message does not contain `Step 0 — ask once`)

- [ ] **Step 1: Add the three assertions, run the two smokes**

Run: `cd face && FACE_SMOKE=1 npx tsx --test tests/bots-smoke.test.ts tests/roles-smoke.test.ts`
Expected: PASS.

- [ ] **Step 2: Commit**

```bash
git add face/tests/bots-smoke.test.ts face/tests/roles-smoke.test.ts
printf '%s\n' 'test(face): the cycle section reaches Gravit and no one else' > /tmp/msg-plan3-t2.txt
git commit -F /tmp/msg-plan3-t2.txt
```

---

### Task 3: The cycle drill, run once, and the two measurements

**Files:**
- Modify: `face/README.md` ("The cycle drill (run after any change to cycle.md, roles/ or the dsh pins)" after the role drill)
- Modify: `DEVELOPMENT.md` §4.3 (the measured first request for Gravit and for one child, beside the 2026-10-10 and plan-1 figures), §7.4 (the drill's row)

- [ ] **Step 1: Write the drill**

```markdown
## The cycle drill (run after any change to cycle.md, roles/ or the dsh pins)

On the operator's face (`cd face && npm start` with the keys; the 2yr bed mounted), not a
scratch home: the drill writes a strategy directory and the operator judges the result.

1. `+ new` on a channel created from `_template` for the drill (`cycle-drill-<date>`). Send one
   message: an idea in two sentences, no brief. Expected: ONE ask_user_question batch — thesis,
   falsification terms, bed and window, what to measure — and no file written before it.
2. Answer the batch. Expected: Gravit calls `create_goal` (the chat shows the goal), writes
   THESIS.md and `status: researching`, then rounds follow by themselves: the chat shows a round
   header per round, `role_screener` and `role_backtester` calls with their reports relayed,
   journal entries with artifact paths, `role_reviewer` before the verdict. No card for the
   operator; no question after step 1 unless the bed cannot cover the window asked.
3. The verdict: `status.yaml` reads `validated` or `retired` with the terms cited, or
   `researching` with a blocked goal whose reason starts with `child-limit`, `bed-window`,
   `data-missing` or `needs-operator`; `one_line`, `next`, `numbers` filled; the journal's last
   entry is the verdict with the usage line; the goal is complete (the log's last `goal/change`).
4. Restart: stop the face mid-cycle on a second drill channel, start it again, send "continue".
   Expected: Gravit calls `update_goal` with `resume` and the rounds continue; the goal did not
   continue on its own after the restart.
5. Record: rounds used, role calls (count the child history), wall time, the session's usage,
   and the first-request numbers for Gravit's session and for one child, read from
   `~/.dsh/storages/session_projcache/sessions/<id>.json` (`contextBreakdown`), into
   `DEVELOPMENT.md` §4.3 and §7.4 with the date.
```

- [ ] **Step 2: Run it once; record it**

The operator runs the drill (keys, the live home); the implementer records the numbers and the date. A failure at any step is fixed before Task 4 — the contract text is the usual suspect, the goal mechanics the next.

- [ ] **Step 3: Commit**

```bash
git add face/README.md DEVELOPMENT.md
printf '%s\n' 'docs: the cycle drill, run <date>, and the measured first requests' > /tmp/msg-plan3-t3.txt
git commit -F /tmp/msg-plan3-t3.txt
```

---

### Task 4: The charter, `DEVELOPMENT.md`, the roadmap, the guide

**Files:**
- Modify: `Gravit-Design.md` (exact edits below)
- Modify: `DEVELOPMENT.md` (§3.3 one sentence: the Step 0 rule lives in `dsh/profile/cycle.md`; §3.6 the goal-tools row gains "the cycle's loop: `create_goal` 24 rounds, `update_goal` resume on the operator's message"; §4.3 the `gravit:cycle` section; §4.5 unchanged; §9 three residuals appended after the last R-item; §10 the forward list)
- Modify: `ROADMAP.md` (Part II built log: the 2026-10 redesign entry; Part I item (2) "daily-run cadence" unchanged)
- Modify: `dsh/README.md` (the `profile/` table row: `persona.md` + `cycle.md`), `CLAUDE.md` (the `dsh/` row names `profile/{persona,cycle}.md` and `roles/`)
- Modify: `docs/dsh-upgrade-guide.md` (§3.2 group C: `C21 the goal loop: create_goal/update_goal parameters, the direct-human authority on resume, blockedAfterConsecutiveRounds, the driver's round-limit (cycle.test.ts, the cycle drill)`; §4 a row "the cycle caps are cycle.md's, not a dsh config"; §7.3 the remaining bullets marked landed; §6.3 a line that plans 1–3 landed)

- [ ] **Step 1: The charter edits (spec §10)**

In `Gravit-Design.md`:
- §1 "What it is not": the sentence `Nothing runs unattended.` becomes `Nothing *starts* unattended. A research cycle the operator starts runs to its verdict inside its strategy directory without further attention; the operator judges it afterwards from the journal and the diff.`
- §1 second paragraph, after "Temporary subagents perform bounded delegated work (§7.2).": add `The role library — three one-shot roles with their own persona and tools — is the prebuilt form of that delegation (§7.2).`
- §3 the agent row: `works strategies/ · runs research cycles under a goal · queries via MCP tools · consults room bots · delegates to the role library and to bounded child tasks · may call rostered local CLIs as tools`.
- §4 the write map: the `strategies/` row's writer becomes `**Gravit**, including the role children and bounded tasks it delegates to under inherited permissions`; a new row `dsh/profile/cycle.md` — writer `operator only` — audit `the research-cycle contract Gravit runs; Gravit proposes changes in conversation and never edits it; git` (the `roles/<id>/` row was added by plan 2).
- §5 D5's "Due when" adds `, or the first cycle whose usage surprises the operator`; D14's debt reads `Structured room evidence, child-task results and role reports have no independent verification…`; a new row `D16 | The per-cycle role-call cap (12) is a count Gravit keeps in the journal, not a threshold the harness enforces (Rule 1) | the round cap is enforced by the goal, every call is in the child history, and the operator reads the journal | the first overrun`.
- §7.2, a new last paragraph: `The role library is the prebuilt form of a delegated task: a role is an operator-authored persona plus an exact tool allow-list the dsh backend enforces at the child's creation (`roles/<id>/`), surfaced to Gravit as a one-shot tool. It is never a bot (no roster, no journal, no room) and never a bot's substitute: a role has hands and no voice, a bot a voice and no hands. A role's report is a claim Gravit checks (D14).`
- §8 a new trigger row: `A role is given a bot's tools, the account tools, or ask_user_question | §7.2 · D12 · run the order drill with that role's child`.
- §9: replace the second bullet's first sentence with `**Evaluate real research and make acceptance explicit** (D14, D16) …` and add at the end a fourth bullet: `**The next round: persona, memory, the teaching channel.** The persona's mechanics paragraphs move to the tool descriptions, scoped sections and skills dsh provides; the style pack moves into a memory substrate the operator designs; the teaching channel is designed with it. Deferred by the operator on 2026-10-15.`

- [ ] **Step 2: `DEVELOPMENT.md` §9 residuals (appended, numbered after the last)**

- `R<n>` — the 12-call cap is a journal count (D16): no harness threshold; the first overrun adds a face-side counter on `agent/created` for one session's children.
- `R<n+1>` — a goal survives a restart disarmed; the operator's next message is the resume path (the model's `update_goal resume` is accepted only in a direct human turn); a paused goal needs `/goal resume`, which the face's client does not send — the operator uses the tool through Gravit or edits the goal.
- `R<n+2>` — the tool-schema block (32,003 heuristic tokens on 2026-10-10) is attributed per tool by Task 5; Gravit's own mask (`tools.restrict` in `gravit.js`) is the next round's lever, decided on those numbers.

- [ ] **Step 3: Verify and commit**

Run: `grep -n "Nothing \*starts\* unattended\|D16\|role library" Gravit-Design.md | head; cd face && npm test`
Expected: the three greps print; the suite is green (no code changed).
```bash
git add Gravit-Design.md DEVELOPMENT.md ROADMAP.md dsh/README.md CLAUDE.md docs/dsh-upgrade-guide.md
printf '%s\n' 'docs: the charter and DEVELOPMENT.md carry the cycle, the roles and D16; the guide closes its 7.3 watchlist' > /tmp/msg-plan3-t4.txt
git commit -F /tmp/msg-plan3-t4.txt
```

---

### Task 5: Attribute the tool-schema block per tool (spec §7)

**Files:**
- Create: `face/scripts/schema-sizes.ts`
- Modify: `DEVELOPMENT.md` §4.3 (the per-server totals)

**Interfaces:**
- `face/scripts/schema-sizes.ts`: boots a face tree exactly as `scripts/check-home.ts` boots a COPY of the home — but with the MCP rows ENABLED (it needs the operator's keys in the environment, so it runs in the operator's terminal) — reads `ctx.tools.schemas()`, prints one line per tool `<name>\t<bytes of JSON.stringify(schema)>\t<bytes/4 as a token estimate>` sorted by size, then one line per prefix group (`mcp__alpaca-kit__`, `mcp__akshare__`, `agent_`, the rest) with the group total, and disposes. Usage: `DSH_HOME=$SCRATCH/dsh-sizes npx tsx scripts/schema-sizes.ts` against a copy of the home.

- [ ] **Step 1: Write the script**

Reuse `bootFace({ profileName: "face", port: 0, dshHome })` and `dispose()`; no new dependency. The live-home guard of `check-home.ts` (`liveHomeCandidates`) is reused: the script refuses the operator's real home by device and inode.

- [ ] **Step 2: Run it once on a copy of the home, record**

Run (operator's terminal, keys in the environment): `cp -a ~/.dsh $SCRATCH/dsh-sizes && cd face && DSH_HOME=$SCRATCH/dsh-sizes npx tsx scripts/schema-sizes.ts | tail -8 ; rm -rf $SCRATCH/dsh-sizes`
Expected: the group totals; the 2026-10-10 hypothesis (the 14 AKShare tools dominate) confirmed or refuted in numbers. Record the four group totals and the top five tools in `DEVELOPMENT.md` §4.3.

- [ ] **Step 3: Commit**

```bash
git add face/scripts/schema-sizes.ts DEVELOPMENT.md
printf '%s\n' 'chore(face): schema-sizes.ts attributes the tool-schema block per tool; the numbers recorded' > /tmp/msg-plan3-t5.txt
git commit -F /tmp/msg-plan3-t5.txt
```

---

## Self-review (done while writing)

- **Spec coverage.** §6 steps 0–6 and the caps (Task 1's text), the gates and blocking vocabulary as corrected by §11.1 (e) (Task 1), §7 measurement and attribution (Tasks 3, 5), §9's cycle drill and measurement (Task 3), §10's charter and `DEVELOPMENT.md` amendments (Task 4), §12 plan 3, B10 (Task 4's guide rows).
- **Step scan.** The cycle text is the deliverable; `cycle.ts` and the plugin change are fully determined by the tests; the drills are procedures with expected observations; the script's output format is fixed.
- **Type consistency.** `CYCLE_PATH`, `CYCLE_MAX_BYTES`, `readCycle` (cycle.ts); `CYCLE_SECTION` (gravit.js); `FaceBootOptions.cyclePath`; `gravitRows(…, { plugin, cycle })` and `renderGravitComposition(…, { cycle })` as plan 2 defined them.
- **Review Focus.** 1 (Tasks 1–2), 2–3 (Task 3, mechanism dsh's), 4 (Task 1), 5 (Task 1).
- **Proportion.** Shorter than plans 1 and 2: the loop is dsh's; this plan is a text, a section, two drills and the documents.
