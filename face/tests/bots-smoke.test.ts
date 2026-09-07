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
    /* `{ agent, scope }`, not `{ scope }` alone: the loop assembles through
     * `assembleContextFor` (dsh-agent/lib/index.js:384-390), and the `cwd`
     * variable provider reads `context.agent` - not the scope
     * (dsh-agent-loop/lib/index.js:1026). With only a scope, renderPrompt throws
     * `prompt variable "{{cwd}}" has no value for this assembly`. */
    const systemPrompt = ctx.get("systemPrompt") as { assemble(context?: { scope?: object; agent?: object }): Promise<Parameters<typeof renderPrompt>[0]> };
    const names = (schemas: { name: string }[]) => schemas.map((s) => s.name).sort();

    /* S3 - Kairos: a session naming no preset joins `kairos` and keeps the host's tools. */
    const k = await call("session.create", { cwd: home });
    assert.equal(k.agentPreset, "kairos");
    const kairos = agents.get(String(k.sessionId))!;
    assert.equal(kairos.session.header.agentPreset, "kairos");
    assert.deepEqual(names(tools.schemas(kairos as object)), names(tools.schemas()), "the inert default adds and removes nothing");
    const kairosPrompt = renderPrompt(await systemPrompt.assemble({ agent: kairos as object, scope: kairos as object }));
    /* Compared up to the persona's first `{{`, not its first LINE: line 1 ends
     * `... your working directory is {{cwd}}.` and renderPrompt substitutes it
     * (measured: the rendered text carries this session's cwd). The prefix is
     * still read from the FILE, so rewriting the persona moves this assertion. */
    assert.ok(kairosPrompt.includes(readPersona(PERSONA_PATH).split("{{")[0]), "D11 closed: Kairos is told who it is");

    /* S1 + S2 - a bot: the gateway mounts the preset; the mask and the persona hold. */
    const p = await call("session.create", { cwd: join(bots, "probe", "journal"), agentPreset: "probe" });
    assert.equal(p.agentPreset, "probe");
    const probe = agents.get(String(p.sessionId))!;
    assert.equal(probe.session.header.agentPreset, "probe");
    assert.deepEqual(names(tools.schemas(probe as object)), ["ask_user_question", "bash", "read"], "allow ∩ tree, unknown names dropped (S2)");
    const probePrompt = renderPrompt(await systemPrompt.assemble({ agent: probe as object, scope: probe as object }));
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
