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
import { SessionId, type Session } from "@deepseek-ai/dsh-session";
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
    const childrenBefore = [...requested.keys()].filter(isChild).length;
    await prompt("RUN_SCREENER");
    await gravit.whenIdle();
    const failed = gravit.session.snapshotEvents().filter((e) => e.type === "tool/result").at(-1)!;
    assert.match(JSON.stringify(failed.data), /unknown global tool.*mcp__alpaca-kit__earnings/);
    assert.equal([...requested.keys()].filter(isChild).length, childrenBefore, "no child was created");
  } finally {
    await dispose?.();
    await Promise.all([rm(bots, { recursive: true, force: true }), rm(root, { recursive: true, force: true }), rm(home, { recursive: true, force: true })]);
  }
});
