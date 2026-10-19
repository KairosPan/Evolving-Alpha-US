/** Role delegation on a real tree: `role_reviewer` and `role_screener` spawn a
 * one-shot child whose persona is the role's (shadowing Gravit's), whose tools
 * are exactly the role's allow list (ancestor-layer `role_*` tools removed,
 * `gravit:roles` and `gravit:cycle` blank), and whose result returns through
 * the tool; the reviewer's child reads the root `GRAVIT.md` in its
 * `agent-instructions` baseline; a `subagent_fork` child - seeded and
 * unrestricted - is assembled Gravit's system text byte for byte (the roles
 * list and the cycle contract included) and Gravit's tools, the premise of its
 * inherited prefix's cache reuse; a plain `subagent` child - unseeded and as
 * unrestricted - reads neither section although it can call `create_goal` and
 * every role tool; a role naming a tool the tree lacks fails loudly at
 * delegation. The MCP tools the roles name are stand-ins registered under the
 * exact production names. Own file, gated. */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { GenerateOptions } from "@deepseek-ai/dsh-llm";
import { SessionId, type Session } from "@deepseek-ai/dsh-session";
import { assembleContextFor } from "@deepseek-ai/dsh-agent";
import { renderPrompt } from "@deepseek-ai/dsh-system-prompt";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { PERSONA_PATH, readPersona } from "../src/persona.ts";
import { ROLES_ROOT, readRoles } from "../src/roles.ts";
import { makeBotsRoot } from "./bots-fixture.ts";
import { mountClient, remote, signIn } from "./remote.ts";
import { StubAdapter, type StubReply } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
/** Planted in the fixture root's GRAVIT.md: what an `agent-instructions` baseline carries when it read the file. */
const GRAVIT_MARK = "GRAVIT-ROOT-MARK-7f3a";
/** The opening words of the research-cycle contract (`dsh/profile/cycle.md`, the `gravit:cycle` section): enough
 *  to tell whether the section reached a prompt, without copying the contract into a test. The em dash is U+2014. */
const CYCLE_HEADING = "Step 0 — ask once";
const sourceKind = (m: { source?: unknown }) => ((m.source ?? {}) as { kind?: string }).kind;
const textOf = (m: GenerateOptions["messages"][number]) => m.content.map((b) => "text" in b ? b.text : "").join("\n");
const lastHuman = (r: GenerateOptions) => [...r.messages].reverse().find((m) => ["user", "tool"].includes(String(sourceKind(m))));
/** The first UTF-16 index where two strings differ, -1 when they are equal: a failure names where. */
function firstDifference(a: string, b: string): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) return i;
  return a.length === b.length ? -1 : n;
}
async function waitFor(label: string, check: () => boolean, ms = 30_000) {
  const until = Date.now() + ms;
  while (!check()) { if (Date.now() >= until) throw new Error(`timed out: ${label}`); await new Promise((r) => setTimeout(r, 20)); }
}

test("roles smoke: persona, exact tools, the result, the baseline, a fork's identical prefix, a spawn's blank sections, and a loud failure for a missing tool", { skip: gated && "set FACE_SMOKE=1", timeout: 180_000 }, async () => {
  const bots = await makeBotsRoot();
  const root = await realpath(await mkdtemp(join(tmpdir(), "face-roles-root-")));
  const home = await mkdtemp(join(tmpdir(), "face-roles-home-"));
  let dispose: (() => Promise<void>) | undefined;
  try {
    await mkdir(join(root, ".git"));
    await writeFile(join(root, "GRAVIT.md"), `# fixture\n${GRAVIT_MARK}\n`);
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
    /* A one-shot child leaves `ctx.sessions` the moment its result returns, which can be before a 20 ms
     * poll looks (measured: the lookup came back empty in most runs), so each session's header is copied
     * while its request is being served, when it is certainly there. */
    const headers = new Map<string, Session["header"]>();
    const isChild = (id: string) => headers.get(id)?.origin === "subagent";
    const script = (request: GenerateOptions): StubReply => {
      if (request.purpose !== undefined) return { kind: "text", text: "fixture" };
      const id = String(request.sessionId);
      requested.set(id, [...requested.get(id) ?? [], request]);
      const header = ctx.sessions.get(request.sessionId!)?.header;
      if (header !== undefined && !headers.has(id)) headers.set(id, { ...header });
      const trigger = lastHuman(request);
      const text = trigger ? textOf(trigger) : "";
      if (header?.isSeeded === true) return { kind: "text", text: "FORK_DONE" };
      if (header?.origin === "subagent") return { kind: "text", text: text.includes("REVIEW_FIXTURE") ? "REVIEW_DONE" : text.includes("SPAWN_FIXTURE") ? "SPAWN_DONE" : "SCREEN_DONE" };
      if (sourceKind(trigger!) === "user" && text === "RUN_REVIEWER") return { kind: "tool", name: "role_reviewer", args: { description: "Audit the fixture", prompt: "REVIEW_FIXTURE: audit the fixture strategy." } };
      if (sourceKind(trigger!) === "user" && text === "RUN_FORK") return { kind: "tool", name: "subagent_fork", args: { description: "Fork the fixture", prompt: "FORK_FIXTURE: continue." } };
      if (sourceKind(trigger!) === "user" && text === "RUN_SUBAGENT") return { kind: "tool", name: "subagent", args: { description: "Spawn the fixture", prompt: "SPAWN_FIXTURE: check one source.", run_in_background: false } };
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
    /* The positives the child's two negatives below pair with. The persona is compared up to its first
     * `{{`, as bots-smoke does (the text after it is a substituted variable); it is read from the file. */
    const rolesIntro = "Roles. One-shot delegates";
    const gravitPersona = readPersona(PERSONA_PATH).split("{{")[0];
    assert.ok(gravitPrompt.includes("- role_reviewer — "), "Gravit reads the roles section");
    assert.ok(gravitPrompt.includes(rolesIntro), "Gravit reads the roles intro");
    assert.ok(gravitPrompt.includes(CYCLE_HEADING), "Gravit reads the cycle contract");
    assert.ok(gravitPrompt.includes(gravitPersona), "Gravit is told who it is");
    const childRequestAfter = async (marker: string) => {
      await waitFor(`child ${marker}`, () => [...requested.entries()].some(([id, rs]) => isChild(id) && rs.some((r) => r.messages.some((m) => textOf(m).includes(marker)))));
      const [id, rs] = [...requested.entries()].find(([id, rs]) => isChild(id) && rs.some((r) => r.messages.some((m) => textOf(m).includes(marker))))!;
      return { id: SessionId(id), request: rs[0], header: headers.get(id)! };
    };
    /* reviewer */
    await prompt("RUN_REVIEWER");
    const reviewer = await childRequestAfter("REVIEW_FIXTURE");
    await gravit.whenIdle();
    const reviewerTools = reviewer.request.tools!.map((t) => t.name).sort();
    for (const kept of ["read", "glob", "grep", "skill", "mcp__alpaca-kit__daily_bars", "mcp__alpaca-kit__calendar", "mcp__alpaca-kit__corp_actions", "mcp__alpaca-kit__market_snapshot"]) assert.ok(reviewerTools.includes(kept), `reviewer keeps ${kept}`);
    for (const gone of ["bash", "write", "edit", "ask_user_question", "web_search", "subagent", "subagent_fork", "send_message", ...readRoles(ROLES_ROOT).map((r) => r.tool), "mcp__alpaca-kit__account", "mcp__alpaca-kit__screen"]) assert.equal(reviewerTools.includes(gone), false, `reviewer never sees ${gone}`);
    /* Equality, not subsets: dsh exempts a scope's own-layer registrations from `restrict()`, so only an exact
     * comparison with the role's allow list catches a tool the child's layer adds. */
    const role = (id: string) => readRoles(ROLES_ROOT).find((r) => r.id === id)!;
    assert.deepEqual(reviewerTools, [...role("reviewer").allow].sort(), "the reviewer's tools are exactly its allow list");
    const system = reviewer.request.messages[0];
    assert.equal(system.role, "system");
    assert.ok(textOf(system).includes("You are the reviewer"), "the role persona is the child's");
    assert.equal(textOf(system).includes(gravitPersona), false, "and it shadows Gravit's");
    assert.equal(textOf(system).includes(rolesIntro), false, "the roles section is blank for a role child: its allow list removed every role tool");
    assert.equal(textOf(system).includes(CYCLE_HEADING), false, "and so is the cycle section: its allow list removed create_goal, the visibility `gravit:cycle` is gated on");
    assert.match(textOf(system), /Today is \d{4}-\d{2}-\d{2}/, "the date reaches the child");
    assert.equal(reviewer.header.origin, "subagent");
    assert.equal(reviewer.header.agentPreset, "gravit");
    assert.equal(reviewer.header.cwd, root);
    assert.ok(gravit.session.snapshotEvents().some((e) => e.type === "tool/result" && JSON.stringify(e.data).includes("REVIEW_DONE")), "the child's text returns through the tool");
    /* The workspace map reaches a role child: dsh's agent-instructions row publishes a baseline on every
     * agent's first request, a spawn child's included. Gravit's own first request is the positive pair. */
    const baselineHasMark = (r: GenerateOptions) => r.messages.some((m) => sourceKind(m) === "agent-instructions" && textOf(m).includes(GRAVIT_MARK));
    assert.ok(baselineHasMark(requested.get(sessionId)![0]), "Gravit's baseline carries the root GRAVIT.md");
    assert.ok(baselineHasMark(reviewer.request), "so does the reviewer child's first request");
    /* fork: `subagent_fork` seeds its child with Gravit's completed turns and restricts nothing, so the
     * child's first request must open with Gravit's system text byte for byte and offer Gravit's tools,
     * or the inherited prefix loses its cache reuse. `gravit:roles` and `gravit:cycle` are gated on what the
     * assembling scope can call (plugins/gravit.js `canCall`: a role tool, `create_goal`) and on the header
     * (`isRootOrFork`: a root, or a seeded child), which is why both reach the fork unchanged. */
    await prompt("RUN_FORK");
    const fork = await childRequestAfter("FORK_FIXTURE");
    await gravit.whenIdle();
    assert.equal(fork.header.isSeeded, true, "a subagent_fork child is seeded");
    const atFork = requested.get(sessionId)!.find((r) => { const t = lastHuman(r); return t !== undefined && sourceKind(t) === "user" && textOf(t) === "RUN_FORK"; })!;
    assert.equal(fork.request.messages[0].role, "system");
    const gravitSystem = textOf(atFork.messages[0]);
    const forkSystem = textOf(fork.request.messages[0]);
    assert.ok(gravitSystem.includes(rolesIntro), "Gravit's request at the fork carries the roles section");
    assert.ok(gravitSystem.includes(CYCLE_HEADING), "Gravit's request at the fork carries the cycle contract");
    assert.ok(forkSystem.includes(CYCLE_HEADING), "and the fork child's does too: `gravit:cycle` reads create_goal's visibility and the header, and a seeded, unrestricted child passes both");
    assert.equal(forkSystem, gravitSystem, `the fork child's system text is Gravit's, whole (${forkSystem.length} vs ${gravitSystem.length} characters, first difference at ${firstDifference(forkSystem, gravitSystem)})`);
    assert.deepEqual(fork.request.tools!.map((t) => t.name), atFork.tools!.map((t) => t.name), "and its tools are Gravit's, in order");
    assert.ok(gravit.session.snapshotEvents().some((e) => e.type === "tool/result" && JSON.stringify(e.data).includes("FORK_DONE")), "the fork's text returns through the tool");
    /* spawn: a plain `subagent` child is delegated, unseeded and restricted by nothing, so its scope
     * resolves `create_goal` and every role tool as Gravit's does - the visibility half of the gate
     * admits it. It reads neither section all the same: both are gated on the header too
     * (plugins/gravit.js `isRootOrFork`), and only a fork inherits a prefix worth keeping identical;
     * the fork above is this step's positive pair. */
    await prompt("RUN_SUBAGENT");
    const spawn = await childRequestAfter("SPAWN_FIXTURE");
    await gravit.whenIdle();
    assert.equal(spawn.header.origin, "subagent");
    assert.equal(spawn.header.isSeeded, false, "a subagent child is not seeded");
    const spawnTools = spawn.request.tools!.map((t) => t.name);
    for (const visible of ["create_goal", ...readRoles(ROLES_ROOT).map((r) => r.tool)]) assert.ok(spawnTools.includes(visible), `the spawn child can call ${visible}, so only the header blanks the sections`);
    const spawnSystem = textOf(spawn.request.messages[0]);
    assert.equal(spawn.request.messages[0].role, "system");
    assert.equal(spawnSystem.includes(CYCLE_HEADING), false, "no cycle contract for a delegated child that is not a fork");
    assert.equal(spawnSystem.includes(rolesIntro), false, "and no roles section");
    assert.match(spawnSystem, /Today is \d{4}-\d{2}-\d{2}/, "the date still reaches it");
    assert.ok(gravit.session.snapshotEvents().some((e) => e.type === "tool/result" && JSON.stringify(e.data).includes("SPAWN_DONE")), "the spawn's text returns through the tool");
    /* screener */
    await prompt("RUN_SCREENER");
    const screener = await childRequestAfter("SCREEN_FIXTURE");
    await gravit.whenIdle();
    const screenerTools = screener.request.tools!.map((t) => t.name);
    assert.ok(["bash", "write", "mcp__alpaca-kit__screen"].every((n) => screenerTools.includes(n)));
    assert.equal(screenerTools.includes("edit"), false);
    assert.deepEqual([...screenerTools].sort(), [...role("screener").allow].sort(), "the screener's tools are exactly its allow list");
    /* a tool the tree lacks: the delegation fails naming it, no child runs */
    unregister.get("mcp__alpaca-kit__earnings")!();
    const childrenBefore = [...requested.keys()].filter(isChild).length;
    await prompt("RUN_SCREENER");
    await gravit.whenIdle();
    const failed = gravit.session.snapshotEvents().filter((e) => e.type === "tool/result").at(-1)!;
    /* Anchored on the quoted name right after the verb: the payload is stringified, so the quotes carry a
     * backslash, and a looser pattern would also match the name inside the error's known-tools list. */
    assert.match(JSON.stringify(failed.data), /names unknown global tools? \\"mcp__alpaca-kit__earnings\\"/);
    assert.equal([...requested.keys()].filter(isChild).length, childrenBefore, "no child was created");
  } finally {
    await dispose?.();
    await Promise.all([rm(bots, { recursive: true, force: true }), rm(root, { recursive: true, force: true }), rm(home, { recursive: true, force: true })]);
  }
});
