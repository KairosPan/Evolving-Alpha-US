/** The room, end to end, in-process, on a stub model and no key (spec §8's
 * last smoke bullets; S5 and S6, which plan 1 deferred here).
 *
 * One boot, one file (this one): every FACE_SMOKE test owns its own bootFace,
 * which is why the room's live drill is room-smoke.test.ts rather than another
 * case inside smoke.test.ts. The bots root is `mkdtemp`'d INSIDE the
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
const textOf = (m: GenerateOptions["messages"][number] | undefined): string =>
  (m?.content ?? []).map((b) => (b as { text?: string }).text ?? "").join("\n");
const lastUserText = (o: GenerateOptions): string => textOf([...o.messages].reverse().find((m) => m.role === "user"));
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
    /* `.git`, then the file: `findProjectRoot` walks up for a marker and falls
     * back to the cwd itself, so without one the chain would be the channel
     * directory alone and `root/AGENTS.md` would never be read. The marker is
     * what makes this a CHAIN assertion (root → strategies → the channel). */
    await mkdir(join(root, ".git"), { recursive: true });
    await writeFile(join(root, "AGENTS.md"), `# smoke\n${MARKER}\n`);
    setupFaceProfile(home);
    const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    try {
      /* `as unknown as`: dsh's own `SessionHeader` is a closed interface, not a `Record`. */
      const sessions = ctx.get("sessions") as unknown as { get(id: string): { id: string; header: Record<string, unknown>; events: Ev[] } | undefined };
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
      /* Deviation 2's whole claim, measured inside the request that tests it:
       * an answer appended with `surfaceOp: 'append'` is in the HISTORY of the
       * synthesis call, and the round-end wake is the last user message. */
      let synthesisRequest: { answerInHistory: boolean; roundEndIsLast: boolean } | undefined;
      llm.registerAdapter(["stub"], new StubAdapter((o): StubReply => {
        if (o.purpose !== undefined) return { kind: "text", text: "room smoke" }; // titles, compaction
        const who = presetOf(o);
        const last = [...o.messages].reverse()[0];
        const lastKind = String((last?.source as { kind?: unknown } | undefined)?.kind);
        const lastForm = String((last?.source as { form?: unknown } | undefined)?.form);
        if (who === "kairos") {
          if (lastKind === "tool") return { kind: "text", text: "Waiting for the room." };
          if (lastKind === "room" && lastForm === "round-end") {
            const users = o.messages.filter((m) => m.role === "user");
            synthesisRequest = {
              answerInHistory: users.some((m) => textOf(m).includes("alpha: buy X")),
              roundEndIsLast: String((users.at(-1)?.source as { form?: unknown } | undefined)?.form) === "round-end",
            };
            return { kind: "text", text: `Synthesis: ${lastUserText(o).split("\n")[1]}` };
          }
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

      /* Deviation 2, asserted where it is actually decided - dsh's own history
       * derivation for the wake request, not the log the client reads. */
      assert.deepEqual(synthesisRequest, { answerInHistory: true, roundEndIsLast: true },
        "the appended answer is IN the synthesis request's messages, with the round-end wake last");

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
        /* `agent-instructions`, not `plugin`: `workspaceContextMessage`'s `kind:"plugin"`
         * message is only a content carrier - what dsh-agent-instructions publishes
         * onto the log is the `agent-instructions`/`instructions` source. */
        const chain = agent.session.events.find((e) => e.type === "user/message" && sourceOf(e)?.kind === "agent-instructions" && JSON.stringify(e.data).includes(MARKER));
        assert.ok(chain !== undefined, `${m.agentPreset}: the channel's AGENTS.md chain reached the member; user/message sources seen: ${JSON.stringify(agent.session.events.filter((e) => e.type === "user/message").map((e) => sourceOf(e)?.kind))}`);
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
