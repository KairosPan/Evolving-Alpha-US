/** S7: with no client connected, does `ask_user_question` block or deny?
 *
 * The README records the APPROVAL card blocking with no browser; the question
 * service was never observed at 0.1.1. This calls the service directly and
 * races it against a timeout; whichever happens is printed, and R6 in the spec
 * is worded from it. Nothing here needs a model.
 *
 * At dsh 0.2.0 the answer is known, so it is ASSERTED as well as printed:
 * - an ask that carries its agent BLOCKS. The overlay's `api-remotes` row
 *   forwards the scoped `user-questions/request` waterfall into the gateway,
 *   which parks it as a pending event; with zero `$events` clients nothing
 *   settles it until a client connects or the request signal aborts (NEW
 *   packages/api/remotes/src/index.ts:57-75; packages/api/gateway/src/
 *   index.ts:549-606, 599-602). A regression that lost the forwarder would
 *   make this REJECT at once - every question the model asks silently dying -
 *   which is why "never answered" alone is not enough here.
 * - an ask with NO agent is refused at once with `NO_PROVIDER`: api-remotes
 *   forwards only scoped dispatches (remotes/src/index.ts:62-63), so the
 *   unscoped waterfall reaches the service's terminal (NEW packages/
 *   interaction/user-questions/src/index.ts:317-329). At 0.1.1 the apiproxy
 *   refused it first with `ASK_MISSING_AGENT`; that package is gone.
 *
 * THE ASK MUST CARRY AN AGENT to test the branch a bot takes: the model-facing
 * tool always passes one (NEW packages/interaction/tool-ask-user/src/
 * index.ts:99-110), and the service insists it is the exact live ROOT
 * (user-questions/src/index.ts:131-144). The session is created over the
 * Remote wire, exactly as the browser creates one (`session/create`); nothing
 * drives it, so no model is reached.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { makeBotsRoot } from "./bots-fixture.ts";
import { mountClient, remote, signIn } from "./remote.ts";

const gated = process.env.FACE_SMOKE !== "1";

test("S7: ask() with no client either blocks or fails loud - never answers silently", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-askuser-"));
  setupFaceProfile(home);
  const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
  const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
  // This smoke owns a scratch profile and must not start the operator's data server.
  writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: await makeBotsRoot() });
  try {
    const questions = ctx.get("userQuestions") as {
      ask(request: { questions: { id: string; question: string; options?: { label: string }[] }[]; agent?: object; signal?: AbortSignal }): Promise<{ answers: { id: string; selected: string[] }[] }>;
    };
    const item = { id: "q1", question: "S7 probe: is anyone there?", options: [{ label: "yes" }, { label: "no" }] };
    const settle = (promise: Promise<{ answers: { id: string; selected: string[] }[] }>) =>
      promise.then((answer) => ({ kind: "answered" as const, answer }), (err: unknown) => ({ kind: "rejected" as const, err }));

    /* The agent an `ask_user_question` call would carry. Created through the
     * session controller and never driven - `session/create` composes the
     * default preset and leaves the agent idle until a prompt arrives. The
     * `/api` wire needs the browser session first (tests/remote.ts). */
    mountClient(ctx);
    const base = `http://127.0.0.1:${ctx.webServer.port}`;
    const cookie = await signIn(ctx, base);
    const created = await remote<{ sessionId: string }>(base, cookie, "session/create", { request: { cwd: home } });
    const agents = ctx.get("agents") as { get(id: string): object | undefined };
    const agent = agents.get(created.sessionId);
    assert.ok(agent !== undefined, `session/create must leave a live agent for ${created.sessionId}`);

    const controller = new AbortController();
    const outcome = await Promise.race([
      settle(questions.ask({ questions: [item], agent, signal: controller.signal })),
      new Promise<{ kind: "timeout" }>((resolve) => setTimeout(() => resolve({ kind: "timeout" }), 5_000)),
    ]);
    controller.abort();
    console.log(`S7 observed: ${outcome.kind}${outcome.kind === "rejected" ? ` - ${String((outcome as { err: unknown }).err)}` : ""}`);
    assert.notEqual(outcome.kind, "answered", "no client can have answered");
    assert.equal(
      outcome.kind,
      "timeout",
      "an agent-scoped ask with no client must BLOCK (parked by api-remotes in the gateway), not fail at once",
    );

    /* The other branch, recorded because it is the one a HOST caller hits: an
     * ask with no agent is refused immediately rather than parked. */
    const agentless = await settle(questions.ask({ questions: [item] }));
    console.log(`S7 also (agentless host ask): ${agentless.kind}${agentless.kind === "rejected" ? ` - ${String(agentless.err)}` : ""}`);
    assert.notEqual(agentless.kind, "answered", "no client can have answered an agentless ask either");
    assert.equal(agentless.kind, "rejected");
    assert.equal(
      (agentless as { err: { code?: unknown } }).err.code,
      "NO_PROVIDER",
      "an agentless ask is refused by the service's own terminal, NO_PROVIDER",
    );
  } finally {
    await dispose();
  }
});
