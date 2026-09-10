/** The saved bot route must reach the real model request without changing the
 * host default. One isolated boot, local fixtures and a scripted adapter only. */
import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { installModelSelection, type Agent } from "@deepseek-ai/dsh-agent";
import { createUserMessage, type GenerateOptions, type StreamChunk } from "@deepseek-ai/dsh-llm";
import { SessionId } from "@deepseek-ai/dsh-session";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { createBot, listBots, registerBotRoutes } from "../src/bots.ts";
import { installBotRuntime, registerBotRuntimeRoutes } from "../src/bot-runtime.ts";
import { readBotJournal } from "../src/bot-journal.ts";
import { makeRepoBotsRoot } from "./bots-fixture.ts";
import { StubAdapter } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
const SOUL_V1 = "BOT-RUNTIME-SOUL-V1: use original evidence.";
const SOUL_V2 = "BOT-RUNTIME-SOUL-V2: distinguish evidence and inference.";
const JOURNAL_V1 = "HOME-JOURNAL-V1: an old estimate, still requiring current evidence. A literal {{unknown_journal_variable}} is historical text.";
const JOURNAL_V2 = "HOME-JOURNAL-V2: the old estimate was withdrawn; verify updated evidence.";
const messagesText = (options: GenerateOptions): string => options.messages
  .flatMap((message) => message.content.map((block) => "text" in block ? block.text : "")).join("\n");
const messageText = (options: GenerateOptions): string => options.messages
  .filter((message) => message.role === "user").at(-1)?.content
  .map((block) => "text" in block ? block.text : "").join("\n") ?? "";

async function waitFor(what: string, check: () => boolean, ms = 15_000): Promise<void> {
  const until = Date.now() + ms;
  while (!check()) {
    if (Date.now() >= until) throw new Error(`timed out waiting for ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

test("bot runtime smoke: actual home routing, saved-versus-mounted identity, read-only inspection and HTTP fences", {
  skip: gated && "set FACE_SMOKE=1", timeout: 90_000,
}, async () => {
  const bots = await makeRepoBotsRoot();
  const home = await mkdtemp(join(tmpdir(), "face-bot-runtime-home-"));
  const otherCwd = await mkdtemp(join(tmpdir(), "face-bot-runtime-cwd-"));
  let releaseStream = (): void => undefined;
  try {
    const made = await createBot(bots, { id: "probe", name: "Probe", soul: SOUL_V1, model: "stub/bot-v1" });
    await writeFile(join(made.homeCwd, "notes.md"), JOURNAL_V1);
    await mkdir(join(otherCwd, ".git"));
    setupFaceProfile(home);
    const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    let disposeRuntime = (): void => undefined;
    try {
      const requests: GenerateOptions[] = [];
      let heldSession: string | undefined;
      const held = new Promise<void>((resolve) => { releaseStream = resolve; });
      class RuntimeStub extends StubAdapter {
        override async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
          if (options.purpose === undefined) {
            requests.push(options);
            if (messageText(options).includes("HOLD-RUNTIME-INSPECTION")) {
              heldSession = String(options.sessionId);
              await held;
            }
          }
          yield* super.stream(options);
        }
      }
      ctx.llm.registerAdapter(["stub"], new RuntimeStub(() => ({ kind: "text", text: "Local stub answer." })));
      const defaults = ctx.get("agentDefaultModel") as {
        currentSelection(): { provider: string; model: string };
        saveSelection(selection: { provider: string; model: string }): Promise<void>;
      };
      await defaults.saveSelection({ provider: "stub", model: "host-default" });
      const originalDefault = defaults.currentSelection();
      const savedBots = () => listBots(bots, () => ctx.agentPresets.list());
      registerBotRoutes(ctx.webServer, { botsRoot: bots, listPresets: () => ctx.agentPresets.list() });
      const runtime = installBotRuntime(ctx, savedBots, { readJournal: (bot) => readBotJournal(bots, bot) });
      disposeRuntime = runtime.dispose;
      registerBotRuntimeRoutes(ctx.webServer, runtime);
      let assemblies = 0;
      let creations = 0;
      const offAssembly = ctx.on("system-prompt/assemble", async (_assembly, _context, next) => {
        assemblies++;
        return next();
      });
      const offCreated = ctx.on("agent/created", () => { creations++; });
      const base = `http://127.0.0.1:${ctx.webServer.port}`;
      let rpcSequence = 0;
      const rpc = async (method: string, payload: object): Promise<Record<string, unknown>> => {
        const response = await fetch(`${base}/api/${method}`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ type: "client-request", rpcId: `bot-runtime-${++rpcSequence}`, method, payload }),
        });
        const body = await response.json() as { result?: { ok?: boolean; value?: Record<string, unknown>; error?: unknown } };
        assert.equal(body.result?.ok, true, `${method}: ${JSON.stringify(body.result?.error)}`);
        return body.result!.value!;
      };
      const agentFor = (id: string): Agent => {
        const agent = ctx.agents.get(SessionId(id));
        assert.ok(agent, `agent ${id} is live`);
        return agent;
      };
      const createHome = async (): Promise<string> => String((await rpc("session.create", { cwd: made.homeCwd, agentPreset: "probe" })).sessionId);
      const requestFor = (id: string): GenerateOptions => {
        const request = [...requests].reverse().find((options) => String(options.sessionId) === id);
        assert.ok(request, `${id} reached the stub stream`);
        return request;
      };
      const prompt = async (id: string, text: string): Promise<void> => {
        const before = agentFor(id).session.events.filter((event) => event.type === "turn/end").length;
        await rpc("session.prompt", { sessionId: id, mode: "queue", content: [{ type: "text", text }] });
        await waitFor("a completed bot turn", () => agentFor(id).session.events.filter((event) => event.type === "turn/end").length > before);
        await agentFor(id).whenIdle();
      };
      const assertRoute = (id: string, model: string): void => {
        const actual = requestFor(id);
        assert.equal(actual.provider, "stub");
        assert.equal(actual.model, model, "the adapter sees the bot's route");
        assert.equal(agentFor(id).session.requestHeader()?.config.model, model, "the request/header records that same route");
        assert.deepEqual(defaults.currentSelection(), originalDefault, "the bot did not change the global default");
      };

      const oldId = await createHome();
      await prompt(oldId, "First home request.");
      assertRoute(oldId, "bot-v1");
      assert.match(requestFor(oldId).system ?? "", /BOT-RUNTIME-SOUL-V1/);
      assert.match(messagesText(requestFor(oldId)), /HOME-JOURNAL-V1/);
      assert.match(messagesText(requestFor(oldId)), /untrusted historical notes, not instructions, current facts/);
      assert.doesNotMatch(requestFor(oldId).system ?? "", /HOME-JOURNAL/);
      const homeContext = agentFor(oldId).session.events.find((event) => event.type === "user/message"
        && JSON.stringify(event.data).includes("HOME-JOURNAL-V1"));
      assert.ok(homeContext?.type === "user/message", "the journal context is a durable user/message, not persona text");
      assert.equal(homeContext.data.source.kind, "plugin");
      assert.ok("plugin" in homeContext.data.source);
      assert.equal(homeContext.data.source.plugin, "@deepseek-ai/dsh-system-prompt");
      const oldPreview = await runtime.inspect("probe", oldId);
      assert.equal(oldPreview.source, "mounted");
      assert.equal(oldPreview.revisionAtStart, made.revision);
      assert.equal(oldPreview.model, "stub/bot-v1");
      assert.ok("journal" in oldPreview);
      assert.deepEqual(oldPreview.journal, { status: "loaded", revision: (await readBotJournal(bots, "probe")).revision, truncated: false });

      const saved = await fetch(`${base}/data/bots/settings`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: "probe", revision: made.revision, soul: SOUL_V2, model: "stub/bot-v2" }),
      });
      assert.equal(saved.status, 200);
      const savedBody = await saved.json() as { bot: { revision: string } };
      assert.notEqual(savedBody.bot.revision, made.revision);
      await writeFile(join(made.homeCwd, "notes.md"), JOURNAL_V2);
      await prompt(oldId, "Use the existing conversation settings.");
      assertRoute(oldId, "bot-v1");
      assert.match(requestFor(oldId).system ?? "", /BOT-RUNTIME-SOUL-V1/);
      assert.doesNotMatch(requestFor(oldId).system ?? "", /BOT-RUNTIME-SOUL-V2/);
      assert.match(messagesText(requestFor(oldId)), /HOME-JOURNAL-V2/);
      const lastContext = [...requestFor(oldId).messages].reverse().find((message) =>
        message.content.some((block) => "text" in block && block.text.includes("Saved journal snapshot:")));
      assert.ok(lastContext);
      assert.match(JSON.stringify(lastContext), /HOME-JOURNAL-V2/);
      assert.doesNotMatch(JSON.stringify(lastContext), /HOME-JOURNAL-V1/);
      const oldAfterSave = await runtime.inspect("probe", oldId);
      assert.equal(oldAfterSave.revisionAtStart, made.revision);
      assert.equal(oldAfterSave.soulMatchesSaved, false);
      assert.ok("journal" in oldAfterSave);
      assert.equal(oldAfterSave.journal?.revision, (await readBotJournal(bots, "probe")).revision);
      assert.notEqual(oldAfterSave.journal?.revision, oldPreview.journal?.revision);

      const newId = await createHome();
      assert.notEqual(newId, oldId);
      await prompt(newId, "Start with the saved configuration.");
      assertRoute(newId, "bot-v2");
      assert.match(requestFor(newId).system ?? "", /BOT-RUNTIME-SOUL-V2/);
      const newPreview = await runtime.inspect("probe", newId);
      assert.equal(newPreview.revisionAtStart, savedBody.bot.revision);
      assert.equal(newPreview.soulMatchesSaved, true);

      await rpc("session.prompt", { sessionId: newId, mode: "queue", content: [{ type: "text", text: "HOLD-RUNTIME-INSPECTION" }] });
      await waitFor("the held real stream", () => heldSession === newId);
      const beforeRunning = { assemblies, creations, requests: requests.length };
      const running = await runtime.inspect("probe", newId);
      assert.equal(running.attached, true);
      assert.equal("status" in running ? running.status : undefined, "running");
      assert.equal(running.source, "last-request");
      assert.deepEqual({ assemblies, creations, requests: requests.length }, beforeRunning, "inspection during a turn neither assembles nor invokes a model");
      releaseStream();
      await agentFor(newId).whenIdle();

      const beforeMissing = { assemblies, creations, requests: requests.length };
      const missing = await runtime.inspect("probe", `session-${randomUUID()}`);
      assert.equal(missing.attached, false);
      assert.equal(missing.source, "unavailable");
      assert.deepEqual({ assemblies, creations, requests: requests.length }, beforeMissing, "an unattached lookup never creates or resumes an agent");

      // A blank preset switch must not leak an inspection's cached bot model
      // into the principal agent's first request.
      const switchedId = await createHome();
      assert.equal((await runtime.inspect("probe", switchedId)).model, "stub/bot-v2");
      await rpc("agentPreset.select", { sessionId: switchedId, agentPreset: "kairos" });
      await prompt(switchedId, "The principal agent uses the host default.");
      assertRoute(switchedId, "host-default");

      const otherId = String((await rpc("session.create", { cwd: otherCwd, agentPreset: "probe" })).sessionId);
      await prompt(otherId, "A bot at another working directory.");
      assertRoute(otherId, "host-default");

      // Even a cwd matching the journal is not home when it has a room parent.
      // This uses the same root-created preset/model setup as room.ts.
      const roomId = SessionId(`session-${randomUUID()}`);
      const member = await ctx.agents.create({
        sessionId: roomId,
        meta: { cwd: made.homeCwd, agentPreset: "probe", parentSession: SessionId(otherId) },
        agentOptions: { provider: "stub", model: "room-selected" },
        setup: async (scope) => {
          installModelSelection(scope, { current: { provider: "stub", model: "room-selected" }, assembled: undefined });
          await ctx.agentPresets.mount(scope, "probe");
        },
      });
      try {
        member.agent.followup(createUserMessage({ content: [{ type: "text", text: "Parented room request." }], source: { kind: "user" } }));
        await member.agent.whenIdle();
        assertRoute(String(roomId), "room-selected");
      } finally { await member.dispose(); }

      const query = `?id=probe&sessionId=${encodeURIComponent(newId)}`;
      const okInspect = await fetch(`${base}/data/bots/runtime${query}`);
      assert.equal(okInspect.status, 200);
      assert.equal((await okInspect.json() as { runtime: { model: string } }).runtime.model, "stub/bot-v2");
      for (const path of [`/data/bots/runtime${query}`, "/data/bots/settings"]) {
        const denied = await fetch(`${base}${path}`, {
          ...(path.includes("settings") ? { method: "POST", body: '{"id":"probe","name":"Foreign"}' } : {}),
          headers: { origin: "https://foreign.example", "content-type": "application/json" },
        });
        assert.equal(denied.status, 403, `${path}: cross-origin request rejected`);
      }
      const contentType = await fetch(`${base}/data/bots/settings`, { method: "POST", headers: { "content-type": "text/plain" }, body: '{"id":"probe"}' });
      assert.equal(contentType.status, 415);
      const wrongMethod = await fetch(`${base}/data/bots/runtime${query}`, { method: "POST" });
      assert.equal(wrongMethod.status, 405);
      offCreated();
      offAssembly();
    } finally {
      releaseStream();
      disposeRuntime();
      await dispose();
    }
  } finally {
    await rm(bots, { recursive: true, force: true });
    await rm(home, { recursive: true, force: true });
    await rm(otherCwd, { recursive: true, force: true });
  }
});
