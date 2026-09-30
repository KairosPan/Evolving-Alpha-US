/** The optional discussion contract and each bot's journal, through the real
 * dsh request/log path. Fixture directories and scripted model responses only.
 *
 * dsh 0.2.0 deltas this file follows: `/api` calls go through `remote()` with
 * the signed browser cookie (tests/remote.ts, PLAN Appendix A); `Session.events`
 * is `snapshotEvents()` (NEW packages/core/session/src/index.ts:649); a
 * loop-built request carries the system prompt as its leading `role:'system'`
 * message, not `request.system` (NEW packages/llm/llm/src/types.ts:511-527);
 * the journal context is logged as `{kind:'runtime-context', form:'snapshot',
 * sections}` (NEW packages/core/agent-loop/src/runtime-context.ts:14-19, 161);
 * and durable reads use a persistence READ handle (NEW
 * packages/session/session-persistence/src/handle.ts:14-23, 59-83). */
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
import { createBot, listBots } from "../src/bots.ts";
import { readBotJournal } from "../src/bot-journal.ts";
import { installBotRuntime } from "../src/bot-runtime.ts";
import type { DiscussionSummary, MemberView, StructuredBrief } from "../src/room-contract.ts";
import { panelDeps } from "../src/panels.ts";
import { setBots } from "../src/roster.ts";
import { installRoom, type RoomContextLike } from "../src/room.ts";
import { makeRepoBotsRoot } from "./bots-fixture.ts";
import { mountClient, remote, signIn } from "./remote.ts";
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
/** The system prompt a loop-built request actually carried: its first
 * `role:'system'` message (`request.system` is undefined for loop requests). */
const systemOf = (request: GenerateOptions): string =>
  textOf(request.messages.find((message) => "role" in message && message.role === "system") ?? { content: [] } as unknown as GenerateOptions["messages"][number]);
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
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    // This smoke owns a scratch profile and must not start the operator's data server.
    /* The host default route is a PROFILE ROW at dsh 0.2.0: without
     * `profileContext` the face mounts no `configEditor`, and
     * `agentDefaultModel.saveSelection` then returns without writing anything
     * (NEW packages/core/agent-default-model/src/index.ts:74-91; PLAN D1/D2).
     * So the scratch profile names the stub route up front, the same way the
     * operator names theirs, and the boot below asserts it took. */
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n` +
      `- id: agent-default-model\n  config:\n    provider: stub\n    model: host-default\n`);
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
      };
      const originalDefault = defaults.currentSelection();
      assert.deepEqual({ ...originalDefault }, { provider: "stub", model: "host-default" }, "the scratch profile's default route took");
      const presets = ctx.get("agentPresets") as { list(): Promise<{ id: string; broken?: string }[]> };
      const savedBots = () => listBots(bots, () => presets.list());
      const runtime = installBotRuntime(ctx, savedBots, { readJournal: (bot) => readBotJournal(bots, bot) });
      disposeRuntime = runtime.dispose;
      const registry = ctx.get("workspaceRegistry") as { create(path: string): Promise<{ id: string }> };
      /* 0.1.1's `readRaw`/`load` are gone with the handle-based seam
       * (bec6805d6a). A READ handle never takes ownership and, opened after a
       * flush, observes at least the flushed prefix (handle.ts:48-57). */
      const persistence = ctx.get("sessionPersistence") as {
        open(id: SessionId, access: "read"): Promise<{ read(): Promise<{ events: readonly Event[] }>; close(): Promise<void> }>;
      };
      const readStored = async (id: SessionId): Promise<readonly Event[]> => {
        const handle = await persistence.open(id, "read");
        try {
          return (await handle.read()).events;
        } finally {
          await handle.close();
        }
      };
      const ws = await registry.create(channelDir);
      await setBots(home, ws.id, ["alpha", "beta", "gamma"]);
      const deps = panelDeps(ctx, root, home);
      const engine = installRoom({ ctx: ctx as unknown as RoomContextLike, home, channelFor: deps.channelFor, listBots: savedBots });
      disposeRoom = () => engine.dispose();
      const base = `http://127.0.0.1:${ctx.webServer.port}`;
      mountClient(ctx);
      const cookie = await signIn(ctx, base);
      const rpc = (endpoint: string, args: object): Promise<Record<string, unknown>> =>
        remote<Record<string, unknown>>(base, cookie, endpoint, args);
      const created = await rpc("session/create", { request: { workspaceId: ws.id } });
      const roomId = SessionId(String(created.sessionId));
      assert.equal(created.agentPreset, "kairos");
      const room = ctx.agents.get(roomId)!;
      assert.ok(room);
      await rpc("session/prompt", { request: {
        requestId: `discussion-${crypto.randomUUID()}`, sessionId: roomId, mode: "queue",
        content: [{ type: "text", text: "Examine recurring demand and compare the cohort evidence." }],
      } });
      await waitFor("the completed synthesis", () => Boolean(synthesis)
        && room.session.snapshotEvents().some((event) => event.type === "assistant/message" && JSON.stringify(event.data).includes("DISCUSSION-SYNTHESIS")));
      await room.whenIdle();
      assert.ok(synthesis);
      assert.deepEqual(defaults.currentSelection(), originalDefault, "member routes never change the global default");

      const events: readonly Event[] = room.session.snapshotEvents();
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
        assert.equal(request.system, undefined, "loop-built requests carry the prompt as a system message");
        assert.ok(systemOf(request).length > 0, `${id}: the request carries a system-role prompt`);
        assert.doesNotMatch(systemOf(request), /PRIVATE-.*-JOURNAL/);
        for (const other of ["alpha", "beta", "gamma"].filter((other) => other !== id)) {
          assert.ok(!prompt.includes(`PRIVATE-${other.toUpperCase()}-JOURNAL`), `${id} never loads ${other}'s journal`);
        }
        const member = ctx.agents.get(request.sessionId!)!;
        await member.whenIdle();
        const memberEvents: readonly Event[] = member.session.snapshotEvents();
        const delta = memberEvents.find((event) => sourceOf(event)?.form === "delta");
        assert.deepEqual(sourceOf(delta!)?.brief, BRIEF, "structured brief source survives delivery");
        /* 0.1.1 logged `{kind:'plugin', plugin:'@deepseek-ai/dsh-system-prompt'}`;
         * the `plugin` kind is gone and the loop owns this message now. */
        const journalEvent = memberEvents.find((event) => event.type === "user/message"
          && sourceOf(event)?.kind === "runtime-context"
          && JSON.stringify(event.data).includes(`PRIVATE-${id.toUpperCase()}-JOURNAL`));
        assert.ok(journalEvent, `${id}: runtime context is in the canonical event log`);
        assert.equal(sourceOf(journalEvent)?.kind, "runtime-context");
        assert.equal(sourceOf(journalEvent)?.form, "snapshot");
        assert.ok((sourceOf(journalEvent)?.sections as { name: string }[]).some((section) => section.name === "bot-journal"));
        /* `inspect` refuses (409) unless the session's `agentPreset`
         * PROJECTION names this bot, so reaching the assertions below proves
         * bot-runtime's projection read (the `resolveSessionPreset`
         * successor) resolved the member to its bot. */
        const inspection = await runtime.inspect(id, String(request.sessionId));
        assert.ok("journal" in inspection);
        assert.equal(inspection.journal?.status, "loaded");
        /* The captured SOUL is the persona-PREFIX section (dsh 0.2.0 renamed
         * `deployment:persona`, NEW packages/core/system-prompt/src/index.ts:179);
         * a capture still matching the old name reads `soul: null` for every bot. */
        assert.match(String(inspection.soul), new RegExp(`You are ${id}, a fixture research voice`),
          `${id}: the inspected SOUL is the bot's own persona-prefix section`);
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

      // Flush through the public lifecycle barrier, then read the durable log
      // through a fresh persistence READ handle, independent of host memory
      // and the UI projection. (0.1.1 also read the raw artifact bytes via
      // `readRaw`; that method has no successor, and node:zlib decodes only
      // the FIRST Zstandard frame of the multi-frame v4 file, so the raw check
      // folds into this one.)
      await ctx.sessions.flush(room.session);
      const persisted = await readStored(roomId);
      assert.ok(JSON.stringify(persisted).includes("BETA-DISAGREEMENT"));
      assert.ok(JSON.stringify(persisted).includes("displayText"));
      const persistedAnswers = persisted.filter((event) => sourceOf(event)?.form === "answer").map(sourceOf);
      assert.deepEqual(persistedAnswers, answers, "source view/displayText/viewIssue fields survive durable reload");
      const persistedRound = persisted.find((event) => sourceOf(event)?.form === "round-end")!;
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
