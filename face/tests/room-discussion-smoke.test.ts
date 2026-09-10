/** The optional discussion contract and each bot's journal, through the real
 * dsh request/log path. Fixture directories and scripted model responses only. */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { GenerateOptions } from "@deepseek-ai/dsh-llm";
import { SessionId } from "@deepseek-ai/dsh-session";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { createBot, listBots } from "../src/bots.ts";
import { readBotJournal } from "../src/bot-journal.ts";
import { installBotRuntime } from "../src/bot-runtime.ts";
import type { DiscussionSummary, MemberView, StructuredBrief } from "../src/room-contract.ts";
import { panelDeps } from "../src/panels.ts";
import { setBots } from "../src/roster.ts";
import { installRoom, type RoomContextLike } from "../src/room.ts";
import { makeRepoBotsRoot } from "./bots-fixture.ts";
import { StubAdapter, type StubReply } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
const BRIEF: StructuredBrief = {
  question: "BRIEF-QUESTION: Does recurring demand support the thesis?",
  context: "BRIEF-CONTEXT: Compare the declared positions and report evidence gaps.",
  evidence: ["BRIEF-EVIDENCE: examine dated renewal cohorts"],
  falsification: "BRIEF-FALSIFICATION: two consecutive deteriorating renewal cohorts",
  output: "BRIEF-OUTPUT: conclusion, uncertainty, and conditions for changing view",
};
const ALPHA_VIEW: MemberView = {
  position: "ALPHA-POSITION: recurring demand supports a provisional thesis.",
  evidence: ["ALPHA-EVIDENCE: fixture cohort disclosure, as of 2026-08-31."],
  uncertainties: ["ALPHA-UNCERTAINTY: customer concentration is not yet measured."],
  changeConditions: ["ALPHA-CHANGE: revise if the next cohort loses more customers."],
  disagreements: [],
};
const BETA_VIEW: MemberView = {
  position: "BETA-POSITION: remain unconvinced until renewal evidence improves.",
  evidence: ["BETA-EVIDENCE: fixture cohort comparability remains unverified."],
  uncertainties: ["BETA-UNCERTAINTY: whether reported retention excludes discounts."],
  changeConditions: ["BETA-CHANGE: revise after an independently verified renewal cohort."],
  disagreements: [{ with: "alpha", point: "BETA-DISAGREEMENT: the available cohort does not establish recurring demand." }],
};
const ALPHA_PROSE = "Alpha's answer: the thesis is provisional and needs a fresh cohort check.";
const BETA_PROSE = "Beta's answer: I disagree with Alpha about what the disclosed cohort establishes.";
const GAMMA_TEXT = "Gamma's original answer: pricing risk remains unresolved.\n\n```room-view\n{\"position\":42}\n```";
const answer = (prose: string, view: MemberView) => `${prose}\n\n\`\`\`room-view\n${JSON.stringify(view)}\n\`\`\``;
type Event = { type: string; seq: number; data?: unknown };
const sourceOf = (event: Event): Record<string, unknown> | undefined => {
  const data = event.data as { source?: Record<string, unknown>; message?: { source?: Record<string, unknown> } } | undefined;
  return data?.source ?? data?.message?.source;
};
const textOf = (message: GenerateOptions["messages"][number]): string =>
  message.content.map((block) => "text" in block ? block.text : "").join("\n");
const allText = (request: GenerateOptions): string => request.messages.map(textOf).join("\n");
const kindOf = (message: GenerateOptions["messages"][number]): Record<string, unknown> =>
  ("source" in message ? message.source : {}) as Record<string, unknown>;
async function waitFor(what: string, check: () => boolean, ms = 30_000): Promise<void> {
  const until = Date.now() + ms;
  while (!check()) {
    if (Date.now() >= until) throw new Error(`timed out waiting for ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

test("room discussion smoke: structured brief, private journals, serial disagreement, fallback prose and durable synthesis", {
  skip: gated && "set FACE_SMOKE=1", timeout: 90_000,
}, async () => {
  const bots = await makeRepoBotsRoot();
  const root = await mkdtemp(join(tmpdir(), "face-discussion-root-"));
  const home = await mkdtemp(join(tmpdir(), "face-discussion-home-"));
  try {
    for (const id of ["alpha", "beta", "gamma"]) {
      const bot = await createBot(bots, { id, name: id.toUpperCase(), soul: `You are ${id}, a fixture research voice.`, model: "stub/discussion" });
      await writeFile(join(bot.homeCwd, "notes.md"), `PRIVATE-${id.toUpperCase()}-JOURNAL: historical claims require fresh verification.`);
    }
    const channelPath = join(root, "strategies", "discussion");
    await mkdir(channelPath, { recursive: true });
    const channelDir = await realpath(channelPath);
    await mkdir(join(root, ".git"));
    setupFaceProfile(home);
    const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    let disposeRuntime = (): void => undefined;
    let disposeRoom = (): void => undefined;
    try {
      const requests: { who: string; request: GenerateOptions }[] = [];
      let synthesis: GenerateOptions | undefined;
      ctx.llm.registerAdapter(["stub"], new StubAdapter((request): StubReply => {
        if (request.purpose !== undefined) return { kind: "text", text: "fixture title" };
        const who = String(ctx.sessions.get(request.sessionId!)?.header.agentPreset ?? "");
        requests.push({ who, request });
        // A first request may append a runtime-context snapshot after its
        // trigger. Route on the actual source, never on the last text block.
        const trigger = [...request.messages].reverse().find((message) =>
          kindOf(message).kind === "room" || kindOf(message).kind === "user" || kindOf(message).kind === "tool");
        const source = trigger ? kindOf(trigger) : {};
        if (who === "kairos") {
          if (source.kind === "tool") return { kind: "text", text: "Waiting for the discussion round." };
          if (source.kind === "room" && source.form === "round-end") {
            synthesis = request;
            return { kind: "text", text: "DISCUSSION-SYNTHESIS: compare the disagreement and verify the next renewal cohort." };
          }
          return { kind: "tool", name: "dispatch", args: {
            to: ["alpha", "beta", "gamma"], mode: "serial", brief: BRIEF,
            reason: "Use serial responses to examine the preceding member's actual position.",
          } };
        }
        if (who === "alpha") return { kind: "text", text: answer(ALPHA_PROSE, ALPHA_VIEW) };
        if (who === "beta") return { kind: "text", text: answer(BETA_PROSE, BETA_VIEW) };
        if (who === "gamma") return { kind: "text", text: GAMMA_TEXT };
        return { kind: "error", message: `Unexpected fixture preset: ${who}` };
      }));
      const defaults = ctx.get("agentDefaultModel") as {
        currentSelection(): { provider: string; model: string };
        saveSelection(selection: { provider: string; model: string }): Promise<void>;
      };
      await defaults.saveSelection({ provider: "stub", model: "host-default" });
      const originalDefault = defaults.currentSelection();
      const savedBots = () => listBots(bots, () => ctx.agentPresets.list());
      const runtime = installBotRuntime(ctx, savedBots, { readJournal: (bot) => readBotJournal(bots, bot) });
      disposeRuntime = runtime.dispose;
      const registry = ctx.get("workspaceRegistry") as { create(path: string): Promise<{ id: string }> };
      const persistence = ctx.get("sessionPersistence") as {
        readRaw(id: SessionId): Promise<{ content: string } | undefined>;
        load(id: SessionId): Promise<{ events: Event[] }>;
      };
      const ws = await registry.create(channelDir);
      await setBots(home, ws.id, ["alpha", "beta", "gamma"]);
      const deps = panelDeps(ctx, root, home);
      const engine = installRoom({ ctx: ctx as unknown as RoomContextLike, home, channelFor: deps.channelFor, listBots: savedBots });
      disposeRoom = () => engine.dispose();
      const base = `http://127.0.0.1:${ctx.webServer.port}`;
      let sequence = 0;
      const rpc = async (method: string, payload: object): Promise<Record<string, unknown>> => {
        const response = await fetch(`${base}/api/${method}`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ type: "client-request", rpcId: `discussion-${++sequence}`, method, payload }),
        });
        const body = await response.json() as { result?: { ok?: boolean; value?: Record<string, unknown>; error?: unknown } };
        assert.equal(body.result?.ok, true, `${method}: ${JSON.stringify(body.result?.error)}`);
        return body.result!.value!;
      };
      const created = await rpc("session.create", { workspaceId: ws.id });
      const roomId = SessionId(String(created.sessionId));
      assert.equal(created.agentPreset, "kairos");
      const room = ctx.agents.get(roomId)!;
      assert.ok(room);
      await rpc("session.prompt", { sessionId: roomId, mode: "queue", content: [{ type: "text", text: "Examine recurring demand and compare the cohort evidence." }] });
      await waitFor("the completed synthesis", () => Boolean(synthesis)
        && room.session.events.some((event) => event.type === "assistant/message" && JSON.stringify(event.data).includes("DISCUSSION-SYNTHESIS")));
      await room.whenIdle();
      assert.ok(synthesis);
      assert.deepEqual(defaults.currentSelection(), originalDefault, "member routes never change the global default");

      const events = room.session.events;
      const sources = events.filter((event) => event.type === "user/message").map(sourceOf);
      const answers = sources.filter((source) => source?.kind === "room" && source.form === "answer");
      assert.equal(answers.length, 3, "all valid and malformed answers remain in the discussion");
      const alpha = answers.find((source) => source?.bot === "alpha")!;
      const beta = answers.find((source) => source?.bot === "beta")!;
      const gamma = answers.find((source) => source?.bot === "gamma")!;
      assert.deepEqual(alpha.view, ALPHA_VIEW);
      assert.equal(alpha.displayText, ALPHA_PROSE);
      assert.deepEqual(beta.view, BETA_VIEW);
      assert.equal(beta.displayText, BETA_PROSE);
      assert.equal(gamma.view, undefined);
      assert.equal(gamma.displayText, undefined);
      assert.match(String(gamma.viewIssue), /position.*non-empty.*string/);
      const gammaEvent = events.find((event) => sourceOf(event)?.form === "answer" && sourceOf(event)?.bot === "gamma")!;
      assert.equal((gammaEvent.data as { content: { text: string }[] }).content[0].text, GAMMA_TEXT);

      const roundEnd = sources.find((source) => source?.form === "round-end")!;
      assert.equal(roundEnd.outcome, "settled");
      const discussion = roundEnd.discussion as DiscussionSummary;
      assert.deepEqual(discussion.brief, BRIEF);
      assert.deepEqual(discussion.views.map(({ bot, view }) => ({ bot, view })), [
        { bot: "alpha", view: ALPHA_VIEW }, { bot: "beta", view: BETA_VIEW },
      ]);
      assert.deepEqual(discussion.unstructuredBots, ["gamma"]);

      for (const id of ["alpha", "beta", "gamma"]) {
        const request = requests.find((entry) => entry.who === id)?.request;
        assert.ok(request, `${id} reached the actual adapter`);
        assert.equal(request.model, "discussion");
        const prompt = allText(request);
        for (const marker of ["BRIEF-QUESTION", "BRIEF-CONTEXT", "BRIEF-EVIDENCE", "BRIEF-FALSIFICATION", "BRIEF-OUTPUT"]) assert.ok(prompt.includes(marker), `${id}: ${marker}`);
        assert.match(prompt, /room-view/);
        assert.ok(prompt.includes(`PRIVATE-${id.toUpperCase()}-JOURNAL`));
        assert.doesNotMatch(request.system ?? "", /PRIVATE-.*-JOURNAL/);
        for (const other of ["alpha", "beta", "gamma"].filter((other) => other !== id)) {
          assert.ok(!prompt.includes(`PRIVATE-${other.toUpperCase()}-JOURNAL`), `${id} never loads ${other}'s journal`);
        }
        const member = ctx.agents.get(request.sessionId!)!;
        await member.whenIdle();
        const delta = member.session.events.find((event) => sourceOf(event)?.form === "delta");
        assert.deepEqual(sourceOf(delta!)?.brief, BRIEF, "structured brief source survives delivery");
        const journalEvent = member.session.events.find((event) => event.type === "user/message"
          && sourceOf(event)?.plugin === "@deepseek-ai/dsh-system-prompt"
          && JSON.stringify(event.data).includes(`PRIVATE-${id.toUpperCase()}-JOURNAL`));
        assert.ok(journalEvent, `${id}: runtime context is in the canonical event log`);
        assert.equal(sourceOf(journalEvent)?.kind, "plugin");
        assert.equal(sourceOf(journalEvent)?.form, "snapshot");
        assert.ok((sourceOf(journalEvent)?.sections as { name: string }[]).some((section) => section.name === "bot-journal"));
        const inspection = await runtime.inspect(id, String(request.sessionId));
        assert.ok("journal" in inspection);
        assert.equal(inspection.journal?.status, "loaded");
      }
      const betaRequest = requests.find((entry) => entry.who === "beta")!.request;
      assert.ok(allText(betaRequest).includes(ALPHA_PROSE), "serial beta sees alpha's real answer before declaring disagreement");
      const wake = synthesis.messages.find((message) => kindOf(message).form === "round-end");
      assert.ok(wake);
      for (const marker of ["BETA-DISAGREEMENT", "ALPHA-CHANGE", "BETA-CHANGE", "Answers without a valid structured view: @gamma"]) {
        assert.ok(textOf(wake).includes(marker), `Kairos receives ${marker} in the actual wake`);
      }
      assert.match(textOf(wake), /not a vote/);
      assert.ok(allText(synthesis).includes(GAMMA_TEXT), "the malformed contract's original answer still reaches synthesis");
      assert.doesNotMatch(allText(synthesis), /PRIVATE-.*-JOURNAL/, "private journal snapshots are not directly copied to Kairos");

      // Flush through the public lifecycle barrier, then read both the durable
      // artifact and the persistence loader, independent of the UI projection.
      await ctx.sessions.flush(room.session);
      const artifact = await persistence.readRaw(roomId);
      assert.ok(artifact);
      assert.ok(artifact.content.includes("BETA-DISAGREEMENT"));
      assert.ok(artifact.content.includes("displayText"));
      const persisted = await persistence.load(roomId);
      const persistedAnswers = persisted.events.filter((event) => sourceOf(event)?.form === "answer").map(sourceOf);
      assert.deepEqual(persistedAnswers, answers, "source view/displayText/viewIssue fields survive durable reload");
      const persistedRound = persisted.events.find((event) => sourceOf(event)?.form === "round-end")!;
      assert.deepEqual(sourceOf(persistedRound)?.discussion, discussion, "round discussion source survives durable reload");
    } finally {
      disposeRoom();
      disposeRuntime();
      await dispose();
    }
  } finally {
    await rm(bots, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
    await rm(home, { recursive: true, force: true });
  }
});
