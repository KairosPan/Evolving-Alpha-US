/** Bots on a REAL composed tree - spikes S1, S2, S3 of the spec made permanent.
 *
 * S1: a composition whose plugin row is a PATH (not a package) mounts, and the
 *     persona text the face wrote into it reaches the assembled prompt. Both
 *     path forms are exercised, and both reach dsh as absolute `file:` URLs
 *     because the FACE rebases them (src/bot-presets.ts; dsh 0.2.0 would
 *     resolve a relative row against the declaring context's base, the profile
 *     directory): the absolute one a temp root needs, and the SHIPPED relative
 *     `../../face/plugins/bot.js` - which is why this file's bots root is
 *     mkdtemp'd inside the repository, so the rebase lands on the real file.
 * S2: `tools.restrict({allow})` from a preset row masks every agent joined to
 *     the preset - a bot session sees exactly allow ∩ tree, Kairos sees all.
 *     The mask FOLLOWS the tree: presets activate when declared (NEW
 *     packages/preset/agent-preset-registry/src/index.ts:80-118), and
 *     plugins/bot.js re-expands on `tools/change`, so a tool registered after
 *     the declaration is admitted when the allow list names it.
 * S3: `kairos` is an empty composition and Kairos's sessions join it: their
 *     tool set is byte-identical to the host's global view.
 * Also: the roster lists a broken fixture with its reason and never `_template`;
 * a session created through the session controller with `agentPreset` carries
 * it on its header; and Gate 2 is tree-wide, refusing an order tool the bot's
 * own mask admits.
 *
 * Own file, gated: one boot per process (smoke.test.ts).
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { assembleContextFor, type Agent } from "@deepseek-ai/dsh-agent";
import { SessionId } from "@deepseek-ai/dsh-session";
import { renderPrompt } from "@deepseek-ai/dsh-system-prompt";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { BOT_PLUGIN_RELATIVE, DEFAULT_ALLOW, createBot, renderComposition } from "../src/bots.ts";
import { PERSONA_PATH, readPersona } from "../src/persona.ts";
import { expandAllow } from "../plugins/bot.js";
import { makeRepoBotsRoot, PLUGIN_ABS } from "./bots-fixture.ts";
import { mountClient, remote, remoteResult, signIn } from "./remote.ts";

const gated = process.env.FACE_SMOKE !== "1";

/** The order-gate drill's stand-in, verbatim: a name the pre-execute listener
 *  does NOT claim (so no card is raised - there is no client to answer one)
 *  carrying the marker alpaca-kit stamps on its mutating tools. Only the guard
 *  can refuse it, which is exactly the layer under test here. */
const STAND_IN = "mcp__drill__submit_order";

/** Past plugins/bot.js's coalesced re-expansion, which runs one timer turn
 *  after a burst of `tools/change`. */
const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 50));

test("bots smoke: roster, mask, persona, an inert default, the shipped plugin path, and Gate 2 from a bot", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  const bots = await makeRepoBotsRoot();
  try {
    /* `probe` names the plugin by an ABSOLUTE path the way the older fixture
     * did; `shipped` below is left exactly as `createBot` writes it, relative.
     * The face rebases both to `file:` URLs, and both are pinned. */
    await createBot(bots, { id: "probe", name: "Probe", soul: "You are Probe, a test voice." });
    await writeFile(join(bots, "probe", "agent.cordis.yml"),
      renderComposition({ soul: "You are Probe, a test voice.", allow: ["bash", "read", "ask_user_question", "no_such_tool"], plugin: PLUGIN_ABS }));
    await createBot(bots, { id: "shipped", name: "Shipped", soul: "You are Shipped, the relative-path probe." });
    /* The Gate-2 bot: its mask ADMITS the order stand-in. That is the point -
     * the guard must refuse it anyway, so the refusal cannot be credited to
     * the mask. */
    await createBot(bots, { id: "trader", name: "Trader", soul: "You are Trader, a masked-in order probe." });
    await writeFile(join(bots, "trader", "agent.cordis.yml"),
      renderComposition({ soul: "You are Trader, a masked-in order probe.", allow: ["bash", STAND_IN], plugin: PLUGIN_ABS }));
    await mkdir(join(bots, "cracked"));
    await writeFile(join(bots, "cracked", "agent.cordis.yml"), "not: a list\n");

    const home = mkdtempSync(join(tmpdir(), "face-botsmoke-"));
    setupFaceProfile(home);
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    // This smoke owns a scratch profile and must not start the operator's data server.
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
    const { ctx, dispose, botPresets } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    try {
      /* bootFace's declaration handle (PLAN S6) is what this smoke checks:
       * without it every non-default bot would be missing from the roster. */
      assert.ok(botPresets !== undefined, "bootFace returns the face's bot declarations");
      assert.deepEqual(botPresets.ids(), ["cracked", "probe", "shipped", "trader"], "every bot directory declared by the face - never _template, never kairos");
      assert.deepEqual([...botPresets.errors], [], "every composition here is readable");

      const presets = ctx.get("agentPresets") as { defaultId: string; list(): Promise<{ id: string; broken?: string }[]> };
      const roster = await presets.list();
      assert.deepEqual(roster.map((p) => p.id).sort(), ["cracked", "kairos", "probe", "shipped", "trader"], "listed - and never _template");
      assert.equal(presets.defaultId, "kairos");
      assert.match(roster.find((p) => p.id === "cracked")!.broken ?? "", /list/, "a broken preset carries dsh's reason (Rule 5)");

      const base = `http://127.0.0.1:${ctx.webServer.port}`;
      mountClient(ctx);
      const cookie = await signIn(ctx, base);
      const create = (request: { cwd: string; agentPreset?: string }) =>
        remote<{ sessionId: string; agentPreset?: string }>(base, cookie, "session/create", { request });
      const agentOf = (id: string): Agent => {
        const agent = ctx.agents.get(SessionId(id));
        assert.ok(agent, `agent ${id} is live`);
        return agent;
      };
      const tools = ctx.get("tools") as {
        schemas(scope?: object): { name: string }[];
        register(definition: unknown): () => void;
        execute(exec: object): Promise<{ isError: boolean; content?: { text?: string }[] }>;
      };
      /* `assembleContextFor` sets `agent` and `scope` together, as the loop
       * does (NEW packages/core/agent/src/dispatch.ts:167-176): the `cwd`
       * variable reads `context.agent` (NEW packages/core/agent-loop/src/
       * index.ts:372), so with only a scope renderPrompt would throw. */
      const promptOf = async (agent: Agent): Promise<string> =>
        renderPrompt(await ctx.systemPrompt.assemble(assembleContextFor(agent)));
      const names = (schemas: { name: string }[]) => schemas.map((s) => s.name).sort();

      /* S3 - Kairos: a session naming no preset joins `kairos` and keeps the host's tools. */
      const k = await create({ cwd: home });
      assert.equal(k.agentPreset, "kairos");
      const kairos = agentOf(k.sessionId);
      assert.equal(kairos.session.header.agentPreset, "kairos");
      assert.deepEqual(names(tools.schemas(kairos)), names(tools.schemas()), "the inert default adds and removes nothing");
      /* Compared up to the persona's first `{{`, not its first LINE: line 1 ends
       * `... your working directory is {{cwd}}.` and renderPrompt substitutes it
       * (measured: the rendered text carries this session's cwd). The prefix is
       * still read from the FILE, so rewriting the persona moves this assertion. */
      assert.ok((await promptOf(kairos)).includes(readPersona(PERSONA_PATH).split("{{")[0]), "D11 closed: Kairos is told who it is");

      /* S1 + S2 - a bot: the session controller mounts the preset; the mask and the persona hold. */
      const p = await create({ cwd: join(bots, "probe", "journal"), agentPreset: "probe" });
      assert.equal(p.agentPreset, "probe");
      const probe = agentOf(p.sessionId);
      assert.equal(probe.session.header.agentPreset, "probe");
      assert.deepEqual(names(tools.schemas(probe)), ["ask_user_question", "bash", "read"], "allow ∩ tree, unknown names dropped (S2)");
      const probePrompt = await promptOf(probe);
      assert.ok(probePrompt.includes("You are Probe, a test voice."), "the bot's persona shadows Kairos's (S1)");
      assert.equal(probePrompt.includes("You are Kairos"), false,
        "and Kairos's text is gone from the bot's prompt: bot.js's `deployment:persona-prefix` shadows the global prefix");

      /* S1, the SHIPPED form. `shipped`'s composition is untouched since
       * `createBot` wrote it, so its plugin row is the relative path every real
       * bot under `bots/` carries. Mounting it is the only proof that the
       * face's rebase lands it on the real file - `probe` above substitutes an
       * absolute one, which cannot fail the way a wrong relative path would. */
      const s = await create({ cwd: join(bots, "shipped", "journal"), agentPreset: "shipped" });
      const shipped = agentOf(s.sessionId);
      assert.equal(shipped.session.header.agentPreset, "shipped");
      const known = new Set(tools.schemas().map((schema) => schema.name));
      const expected = expandAllow([...DEFAULT_ALLOW], known).allow.slice().sort();
      assert.deepEqual(names(tools.schemas(shipped)), expected,
        `the shipped ${BOT_PLUGIN_RELATIVE} mounted and masked to DEFAULT_ALLOW ∩ tree`);
      assert.ok(expected.includes("bash"), "and the mask is not empty");
      assert.equal(names(tools.schemas(shipped)).includes("subagent"), false, "delegation is never in it");

      /* GATE 2 FROM A BOT SESSION (spec §8). The stand-in is registered here,
       * AFTER `trader`'s preset was declared and mounted - under 0.1.1 an allow
       * mask computed at the mount would have shut it out. plugins/bot.js
       * re-expands on `tools/change`, so `trader`'s mask, which names it, now
       * ADMITS it. The refusal below therefore cannot be the mask's: it is the
       * tree-wide guard, and it is the same refusal `order-gate.test.ts` drills
       * for a bare session. Gate 2 is tree-wide: a preset-joined agent whose
       * mask admits an order tool meets the same guard as Kairos (spec
       * decision 4). */
      let bodyRan = false;
      const unregister = tools.register({
        name: STAND_IN,
        description: "submit a PAPER order (operator-gated)",
        parameters: {},
        output: { schema: { type: "object" }, render: () => [{ type: "text", text: "ok" }] },
        execute: async () => { bodyRan = true; return {}; },
      });
      try {
        await settle();
        const t = await create({ cwd: join(bots, "trader", "journal"), agentPreset: "trader" });
        const trader = agentOf(t.sessionId);
        assert.ok(names(tools.schemas(trader)).includes(STAND_IN), "the bot's own mask ADMITS the order tool registered after its mount");
        const refused = await tools.execute({
          callId: "bot-guard", name: STAND_IN, arguments: {},
          agent: trader, signal: new AbortController().signal,
        });
        assert.equal(refused.isError, true, "and the guard refuses it anyway");
        assert.equal(bodyRan, false, "the tool body must never run");
        assert.match(refused.content?.[0]?.text ?? "", /ORDER_RAW_NAMES/);

        /* The other half of the gate, fired at the waterfall rather than
         * through `execute` for the reason `order-gate.test.ts` gives: an ask
         * with no connected client blocks instead of denying, so the card
         * cannot be answered here. The terminal is the registry's own ALLOW, so
         * an `ask` can only have come from the listener - and this call carries
         * a BOT's agent, which is what makes it the tree-wide claim. */
        const decision = await (ctx as unknown as {
          waterfall(name: "tools/pre-execute", exec: object, next: () => Promise<{ kind: string; reason?: string }>): Promise<{ kind: string; reason?: string }>;
        }).waterfall("tools/pre-execute", {
          name: "mcp__drill__place_order", callId: "bot-ask", arguments: { symbol: "AAPL", qty: 1, side: "buy" },
          agent: trader, signal: new AbortController().signal,
        }, () => Promise.resolve({ kind: "allow" }));
        assert.equal(decision.kind, "ask", "an order from a bot raises the same card Kairos's would");
        assert.match(decision.reason ?? "", /AAPL/);
      } finally {
        unregister();
      }

      /* A broken preset fails the session, visibly, and nothing else. */
      const broken = await remoteResult(base, cookie, "session/create", { request: { cwd: home, agentPreset: "cracked" } });
      assert.equal(broken.ok, false);
      assert.match(broken.ok ? "" : broken.error.code, /agent-preset/);
    } finally {
      await dispose();
    }
  } finally {
    await rm(bots, { recursive: true, force: true });
  }
});
