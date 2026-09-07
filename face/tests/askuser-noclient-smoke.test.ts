/** S7: with no client connected, does `ask_user_question` block or deny?
 *
 * The README records the APPROVAL card blocking with no browser; the question
 * service was never observed. This calls the service directly and races it
 * against a timeout; whichever happens is printed, and R6 in the spec is
 * worded from it. Nothing here needs a model.
 *
 * THE ASK MUST CARRY AN AGENT. The model-facing tool always passes one
 * (`dsh-tool-ask-user/lib/index.js:105`), and the web provider rejects an
 * agentless request up front with `ASK_MISSING_AGENT`
 * (`dsh-host-apiproxy/lib/index.js:1861-1863`) - so an agentless probe records
 * a branch no bot can ever take and says nothing about a missing client. The
 * session is created over the gateway, exactly as a real one is; nothing drives
 * it, so no model is reached.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { makeBotsRoot } from "./bots-fixture.ts";

const gated = process.env.FACE_SMOKE !== "1";

test("S7: ask() with no client either blocks or fails loud - never answers silently", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-askuser-"));
  setupFaceProfile(home);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: await makeBotsRoot() });
  try {
    const questions = ctx.get("userQuestions") as {
      ask(request: { questions: { id: string; question: string; options?: { label: string }[] }[]; agent?: object; signal?: AbortSignal }): Promise<{ answers: { id: string; selected: string[] }[] }>;
    };
    const item = { id: "q1", question: "S7 probe: is anyone there?", options: [{ label: "yes" }, { label: "no" }] };
    const settle = (promise: Promise<{ answers: { id: string; selected: string[] }[] }>) =>
      promise.then((answer) => ({ kind: "answered" as const, answer }), (err: unknown) => ({ kind: "rejected" as const, err }));

    /* The agent an `ask_user_question` call would carry. Created through the
     * gateway and never driven - `session.create` mounts the preset and starts
     * the loop, which idles until a turn is submitted. */
    const res = await fetch(`http://127.0.0.1:${ctx.webServer.port}/api/session.create`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "client-request", rpcId: "s7", method: "session.create", payload: { cwd: home } }),
    });
    const created = (await res.json() as { result: { value: { sessionId: string } } }).result.value;
    const agents = ctx.get("agents") as { get(id: string): object | undefined };
    const agent = agents.get(created.sessionId)!;

    const controller = new AbortController();
    const outcome = await Promise.race([
      settle(questions.ask({ questions: [item], agent, signal: controller.signal })),
      new Promise<{ kind: "timeout" }>((resolve) => setTimeout(() => resolve({ kind: "timeout" }), 5_000)),
    ]);
    controller.abort();
    console.log(`S7 observed: ${outcome.kind}${outcome.kind === "rejected" ? ` - ${String((outcome as { err: unknown }).err)}` : ""}`);
    assert.notEqual(outcome.kind, "answered", "no client can have answered");

    /* The other branch, recorded because it is the one a HOST caller hits: an
     * ask with no agent is refused immediately rather than parked. */
    const agentless = await settle(questions.ask({ questions: [item] }));
    console.log(`S7 also (agentless host ask): ${agentless.kind}${agentless.kind === "rejected" ? ` - ${String(agentless.err)}` : ""}`);
    assert.notEqual(agentless.kind, "answered", "no client can have answered an agentless ask either");
  } finally {
    await dispose();
  }
});
