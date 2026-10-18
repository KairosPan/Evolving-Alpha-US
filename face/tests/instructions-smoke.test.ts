/** What dsh-agent-instructions publishes onto a session's log at its first
 * request, on a real tree, after the face's agent-instructions patch (Task 2):
 * GRAVIT.md and GRAVIT.local.md from the .git root down to the cwd, never
 * AGENTS.md or CLAUDE.md, for Gravit, for a channel session and for a bot.
 * Own file, gated: one boot per process. */
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
import { createBot, renderComposition } from "../src/bots.ts";
import { makeBotsRoot, PLUGIN_ABS } from "./bots-fixture.ts";
import { mountClient, remote, signIn } from "./remote.ts";
import { StubAdapter } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
const MARK = { root: "GRAVIT_ROOT_7f3a", local: "GRAVIT_LOCAL_7f3a", channel: "GRAVIT_CHANNEL_7f3a", agents: "AGENTS_7f3a", claude: "CLAUDE_7f3a" };

test("instructions smoke: GRAVIT.md and its local twin reach every first request; AGENTS.md and CLAUDE.md never do", {
  skip: gated && "set FACE_SMOKE=1", timeout: 120_000,
}, async () => {
  const bots = await makeBotsRoot();
  const root = await realpath(await mkdtemp(join(tmpdir(), "face-instructions-root-")));
  const home = await mkdtemp(join(tmpdir(), "face-instructions-home-"));
  let dispose: (() => Promise<void>) | undefined;
  try {
    await mkdir(join(root, ".git"));
    await writeFile(join(root, "GRAVIT.md"), `# fixture\n${MARK.root}\n`);
    await writeFile(join(root, "GRAVIT.local.md"), `${MARK.local}\n`);
    await writeFile(join(root, "AGENTS.md"), `${MARK.agents}\n`);
    await writeFile(join(root, "CLAUDE.md"), `${MARK.claude}\n`);
    await mkdir(join(root, "strategies", "x"), { recursive: true });
    await writeFile(join(root, "strategies", "x", "GRAVIT.md"), `${MARK.channel}\n`);
    await createBot(bots, { id: "probe", name: "Probe", soul: "You are Probe, a test voice." });
    await writeFile(join(bots, "probe", "agent.cordis.yml"), renderComposition({ soul: "You are Probe, a test voice.", allow: ["read"], plugin: PLUGIN_ABS }));
    setupFaceProfile(home);
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n- id: agent-default-model\n  config:\n    provider: stub\n    model: echo\n`);
    const booted = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    dispose = booted.dispose;
    const { ctx } = booted;
    ctx.llm.registerAdapter(["stub"], new StubAdapter((_request: GenerateOptions) => ({ kind: "text", text: "ok" })));
    const base = `http://127.0.0.1:${ctx.webServer.port}`;
    mountClient(ctx);
    const cookie = await signIn(ctx, base);
    const baselineOf = async (request: { cwd: string; agentPreset?: string }): Promise<string> => {
      const { sessionId } = await remote<{ sessionId: string }>(base, cookie, "session/create", { request });
      await remote(base, cookie, "session/prompt", { request: { requestId: `instr-${crypto.randomUUID()}`, sessionId, mode: "queue", content: [{ type: "text", text: "hello" }] } });
      const agent = ctx.agents.get(SessionId(sessionId))!;
      await agent.whenIdle();
      const baseline = agent.session.snapshotEvents().filter((event) => event.type === "user/message"
        && ((event.data as { source?: { kind?: string } }).source?.kind === "agent-instructions"));
      assert.ok(baseline.length > 0, `${request.cwd}: an agent-instructions baseline was published`);
      return JSON.stringify(baseline);
    };
    const gravit = await baselineOf({ cwd: root });
    assert.ok(gravit.includes(MARK.root), "GRAVIT.md reaches Gravit");
    assert.ok(gravit.includes(MARK.local), "GRAVIT.local.md reaches Gravit");
    assert.equal(gravit.includes(MARK.agents), false, "AGENTS.md never does");
    assert.equal(gravit.includes(MARK.claude), false, "CLAUDE.md never does");
    const channel = await baselineOf({ cwd: join(root, "strategies", "x") });
    assert.ok(channel.includes(MARK.root) && channel.includes(MARK.channel), "a channel session gets the chain, root down to its own GRAVIT.md");
    assert.equal(channel.includes(MARK.agents) || channel.includes(MARK.claude), false);
    const bot = await baselineOf({ cwd: root, agentPreset: "probe" });
    assert.ok(bot.includes(MARK.root), "the row is host-plane: a bot reads GRAVIT.md too");
    assert.equal(bot.includes(MARK.agents), false);
  } finally {
    await dispose?.();
    await Promise.all([rm(bots, { recursive: true, force: true }), rm(root, { recursive: true, force: true }), rm(home, { recursive: true, force: true })]);
  }
});
