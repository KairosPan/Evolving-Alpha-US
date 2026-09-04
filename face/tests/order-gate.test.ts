/** The order gate, drilled on a REAL composed tree.
 *
 * `orders.test.ts` proves the decision logic in isolation. This proves the part
 * isolation cannot: that the listener is actually REGISTERED on a booted face,
 * that it is outermost enough to decide, and that it leaves every other tool
 * alone. The two fail independently — a perfect pure function that `bootFace`
 * forgot to wire is exactly the shape of the `ask_user_question` outage this
 * codebase already lived through once.
 *
 * WHY A STAND-IN NAME, NOT THE REAL TOOL. `face/README.md` forbids drilling
 * with the order tools: arming `ALPACA_KIT_ENABLE_ORDERS` to exercise Gate 2
 * disarms Gate 1 to do it. The gate matches on the RAW name suffix, so
 * `mcp__drill__place_order` exercises the identical code path with nothing
 * behind it — no keys, no broker, no order. This is a better drill than the
 * real tool, not a weaker one.
 *
 * WHAT THIS DOES NOT PROVE: that the approval CARD renders. That needs a human
 * looking at a browser, and an ask with no connected client blocks rather than
 * denying (`dsh-host-apiproxy` stores the pending entry and pushes to an empty
 * mux set), so it cannot be automated here. That half is the operator drill in
 * `face/README.md`.
 *
 * Gated behind `FACE_SMOKE=1` and in its own FILE for the reason `smoke.test.ts`
 * states: `bootFace` sets `process.env.DSH_HOME` permanently, so one boot per
 * process, and `node --test` gives each file its own.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import type { PreToolDecision } from "../src/orders.ts";

const gated = process.env.FACE_SMOKE !== "1";

/** One pending call, shaped as `tools/pre-execute` receives it. `agent` is left
 * off deliberately: the registry denies an agentless call anyway, so the gate
 * must too — and must say so in its own words rather than reporting a refusal
 * nobody made. */
const pending = (name: string) => ({ name, signal: new AbortController().signal });

test("order gate: registered on a real tree, intercepts order tools, leaves everything else alone", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-ordergate-"));
  setupFaceProfile(home);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home });
  try {
    /* The registry's own terminal: whatever no listener claims is ALLOWED
     * (`dsh-tools/lib/index.js:3105`). Passing the same terminal here means a
     * `deny` below can only have come from a registered listener - the gate -
     * and an `allow` can only mean nothing claimed the call. */
    const fire = (name: string): Promise<PreToolDecision> =>
      (ctx as unknown as {
        waterfall(
          name: "tools/pre-execute",
          exec: { name: string; signal: AbortSignal },
          next: () => Promise<PreToolDecision>,
        ): Promise<PreToolDecision>;
      }).waterfall("tools/pre-execute", pending(name), () => Promise.resolve({ kind: "allow" }));

    // A mutating order tool is claimed. Nothing else in the tree does this.
    for (const name of ["mcp__drill__place_order", "mcp__drill__cancel_order"]) {
      const decision = await fire(name);
      assert.notEqual(decision.kind, "allow", `${name} must not reach dispatch unclaimed`);
    }

    /* The read-only listing must pass. This is the assertion that would catch a
     * substring match on "order" - gating a harmless query is a real cost, and
     * the kind of over-reach that gets a gate switched off wholesale. */
    assert.equal((await fire("mcp__drill__orders")).kind, "allow");

    // And the rest of the toolset is untouched.
    for (const name of ["bash", "ask_user_question", "mcp__drill__account"]) {
      assert.equal((await fire(name)).kind, "allow", name);
    }

    /* The gate is name-anchored, so an operator renaming their MCP server does
     * not open a hole. Drilled with a server name that shares no substring with
     * the real one. */
    assert.notEqual((await fire("mcp__whatever_they_call_it__place_order")).kind, "allow");
  } finally {
    await dispose();
  }
});
