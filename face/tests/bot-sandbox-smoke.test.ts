/** S4: what does a file write from a `read-only` bot session produce?
 *
 * The spec accepted two answers - the sandbox's denial, or an approval card the
 * operator can grant - and refused one: a silently changed file. This test
 * PRINTS what actually happened, so the plan for rooms (plan 2) can word D12
 * from an observation rather than a reading. The approval service has no client
 * here, so a raised card could not be answered: the execute is raced against a
 * timeout, and the printed verdict distinguishes that case.
 *
 * MEASURED, and it is neither of the two the spec named: the tool call
 * SUCCEEDS (`isError: false`, no card) while the write is refused by the OS
 * under the sandbox and reported inside the tool's own content as
 * `[sandbox: file access denied under read-only mode]`
 * (`dsh-sandbox/lib/index.js:64`). So D12 must be worded off the CONTENT, not
 * off the result flag: a bot's write is denied loudly and visibly, but a caller
 * that reads only `isError` sees a success.
 *
 * That measurement is now recorded as fact (spec section 16, DEVELOPMENT.md
 * section 9 R10), so this test PINS it rather than accepting any of the three
 * outcomes: the sandbox marker must be in the content, and the command must
 * have run - a schema rejection reads like a denial while proving nothing.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { makeBotsRoot } from "./bots-fixture.ts";

const gated = process.env.FACE_SMOKE !== "1";

test("S4: a read-only session's write never lands silently", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const bots = await makeBotsRoot();
  const home = mkdtempSync(join(tmpdir(), "face-sandbox-"));
  setupFaceProfile(home);
  const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
  const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
  // This smoke owns a scratch profile and must not start the operator's data server.
  writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
  try {
    const base = `http://127.0.0.1:${ctx.webServer.port}`;
    const res = await fetch(`${base}/api/session.create`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "client-request", rpcId: "s4", method: "session.create", payload: { cwd: home } }),
    });
    const created = (await res.json() as { result: { value: { sessionId: string } } }).result.value;
    const agents = ctx.get("agents") as { get(id: string): { session: { events: { type: string }[] } } | undefined };
    const agent = agents.get(created.sessionId)!;
    const permission = ctx.get("permissionPresets") as {
      set(session: unknown, name: string): void;
      current(events: readonly { type: string }[]): string;
    };
    permission.set(agent.session, "read-only");
    /* The EFFECTIVE preset, not merely that an event was appended: `set` writes
     * `permission/preset` only when the name differs from the current one, and
     * a sighting of that row says nothing about the sandbox knob the probe
     * below depends on. `current(events)` folds the knobs and derives the
     * preset (dsh-permission-presets), which is the fact this test needs. */
    assert.equal(permission.current(agent.session.events), "read-only", "the session is actually read-only before the probe");

    const target = join(home, "s4-should-not-exist.txt");
    const tools = ctx.get("tools") as { execute(exec: object): Promise<{ isError: boolean; content?: { text?: string }[] }> };
    const outcome = await Promise.race([
      /* `description` is not decoration: dsh-tool-bash declares it required
       * (lib/index.js:268-271) and rejects the call on its own schema before any
       * sandbox runs - which reads as a denial while proving nothing. */
      tools.execute({ callId: "s4-write", name: "bash", arguments: { command: `printf x > ${JSON.stringify(target)}`, description: "S4 probe: write one file" }, agent, signal: new AbortController().signal }),
      new Promise<"timeout">((resolve) => setTimeout(() => resolve("timeout"), 8_000)),
    ]);
    const asked = agent.session.events.some((e) => e.type === "approval/asked");
    /* EVERY block, not `content[0]`: the denial marker is appended after the
     * command's own stderr, so reading the first block alone can miss it. */
    const text = outcome === "timeout"
      ? "(timed out - a card is pending, nobody to answer)"
      : (outcome.content ?? []).map((block) => block.text ?? "").join("\n");
    const denied = /sandbox: file access denied/.test(text);
    const verdict = outcome === "timeout" ? "PENDING CARD"
      : outcome.isError ? "DENIED"
      : denied ? "SANDBOX-DENIED (tool call ok, write refused in content)"
      : "ALLOWED?!";
    console.log(`S4 observed: ${verdict}; approval/asked in log: ${asked}; result: ${text.replace(/\s+/g, " ").slice(0, 240)}`);

    assert.equal(existsSync(target), false, "the file must not exist");
    /* Pinned to the shape §16 now records as measured fact, not to the union of
     * the three the spec was willing to accept: under `read-only` the write is
     * refused BY THE SANDBOX and reported inside the tool's own content. A
     * looser assertion would pass on a run where the command never executed at
     * all, which proves nothing about the sandbox - hence the second pin. */
    assert.ok(denied, `the sandbox refused the write inside the tool result; saw ${JSON.stringify(text.slice(0, 240))}`);
    assert.doesNotMatch(text, /invalid arguments/i, "the command actually ran");
  } finally {
    await dispose();
  }
});
