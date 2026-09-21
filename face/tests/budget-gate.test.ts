/** The budget gate (Gate 3), drilled on a REAL composed tree.
 *
 * `budgets.test.ts` proves the decision logic in isolation. This proves the
 * part isolation cannot: that the listener is actually REGISTERED on a booted
 * face beside Gate 2's, that it reads the requester off the session it is
 * handed, that it leaves every other tool alone, and that the guard refuses
 * the tool through the real pipeline without a logged grant. As with the order
 * gate, a perfect pure function that `bootFace` forgot to wire is the exact
 * shape of the `ask_user_question` outage this codebase lived through once.
 *
 * WHY A STAND-IN, NOT THE REAL TOOL. The real `wallet_budget_request` is
 * registered by `installWallet` (`wallet.ts`) from `main.ts`, after `bootFace`
 * and only when a wallet home is configured; this drill boots the tree alone.
 * The gate matches the exact NAME, so a stand-in registered under it after boot
 * exercises the identical listener and guard with nothing behind it - no key,
 * no store, no mandate. Registered AFTER boot on purpose: that is the order the
 * face itself uses, and the guard must hold for a tool it never saw at boot.
 *
 * WHAT THIS DOES NOT PROVE: that the card renders, and the approve path
 * (grant → guard → body), for the reason `order-gate.test.ts` gives: an ask with
 * no connected client blocks rather than denying. That half is the operator
 * drill in `face/README.md` (spec §8, R-W5).
 *
 * Gated behind `FACE_SMOKE=1` and in its own FILE: `bootFace` sets
 * `process.env.DSH_HOME` permanently, so one boot per process.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { BUDGET_RAW_NAME } from "../src/budgets.ts";
import type { PreToolDecision } from "../src/orders.ts";

const gated = process.env.FACE_SMOKE !== "1";

/** A budget request as Kairos would send it: strings for money, every host named. */
const request = {
  purpose: "market data for AAPL thesis",
  limit_usd: "5.00",
  per_call_usd: "0.01",
  valid_for_hours: 168,
  hosts: ["api.example.com", "data.example.com", "quotes.example.org"],
};

/** One pending call, shaped as `tools/pre-execute` receives it, with the
 * session HEADER the gate reads the requester from. A bare `{events: []}`
 * session is enough for the real `ApprovalService.overrideOf`
 * (`dsh-user-approval/lib/index.js:176-178`), as in `order-gate.test.ts`; the
 * header is what `requesterOf` reads, and it is what the session store stamps
 * (`dsh-session` `SessionHeader`: `agentPreset`, `origin`, `parentSession`). */
const pending = (name: string, args?: unknown, header: Record<string, unknown> = {}) => ({
  name,
  callId: `drill-${name}`,
  arguments: args,
  agent: { session: { header, events: [] as unknown[] } },
  signal: new AbortController().signal,
});

/** The same call with nobody to ask - the other branch of the listener. */
const agentless = (name: string, args?: unknown) => ({ name, arguments: args, signal: new AbortController().signal });

test("budget gate: registered on a real tree, asks the principal, refuses bots and children, guards the body", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-budgetgate-"));
  setupFaceProfile(home);
  const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
  const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
  // This smoke owns a scratch profile and must not start the operator's data server.
  writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home });
  try {
    /* The registry's own terminal: whatever no listener claims is ALLOWED
     * (`dsh-tools/lib/index.js:3105`), so a decision below can only have come
     * from a registered listener. */
    const fire = (exec: object): Promise<PreToolDecision> =>
      (ctx as unknown as {
        waterfall(
          name: "tools/pre-execute",
          exec: object,
          next: () => Promise<PreToolDecision>,
        ): Promise<PreToolDecision>;
      }).waterfall("tools/pre-execute", exec, () => Promise.resolve({ kind: "allow" }));

    /* THE ASK PATH, against the real ApprovalService: the listener is
     * registered, it reaches the live service, the default policy is `ask`,
     * a bare session (no preset) is the principal, so the gate raises a card. */
    const decision = await fire(pending(BUDGET_RAW_NAME, request));
    assert.equal(decision.kind, "ask", "a principal's budget request under the default policy must raise a card");
    const reason = decision.kind === "ask" ? decision.reason ?? "" : "";
    /* And the card must be decidable: purpose, limit, per-call, validity,
     * EVERY host in full, and who asked. */
    for (const fragment of ["market data for AAPL thesis", "limit $5.00", "per call $0.01", "valid 168h",
      ...request.hosts, "by principal"]) {
      assert.ok(reason.includes(fragment), `the card must carry ${fragment}; saw ${JSON.stringify(reason)}`);
    }

    /* The default preset, set explicitly, is the principal too (the dispatch rule). */
    assert.equal((await fire(pending(BUDGET_RAW_NAME, request, { agentPreset: "kairos" }))).kind, "ask");

    /* A BOT PRESET is refused before any card, and the refusal names the
     * rule - the bot learns it has no wallet, not that an operator said no. */
    const bot = await fire(pending(BUDGET_RAW_NAME, request, { agentPreset: "drill-bull" }));
    assert.equal(bot.kind, "deny", "a bot preset must be denied, not asked");
    const botReason = bot.kind === "deny" ? bot.reason : "";
    assert.match(botReason, /drill-bull/);
    assert.match(botReason, /no wallet/i);
    assert.doesNotMatch(botReason, /the user rejected/i);

    /* A CHILD TASK (origin subagent) is refused the same way, whatever its
     * preset - and pointed at delegation, not at a permission mode. */
    const child = await fire(pending(BUDGET_RAW_NAME, request, { origin: "subagent", parentSession: "p1", agentPreset: "kairos" }));
    assert.equal(child.kind, "deny", "a child task must be denied, not asked");
    const childReason = child.kind === "deny" ? child.reason : "";
    assert.match(childReason, /child task/);
    assert.match(childReason, /wallet_budget_delegate/);

    /* A request the card cannot show is refused before it. */
    assert.equal((await fire(pending(BUDGET_RAW_NAME, { ...request, hosts: ["*"] }))).kind, "deny");

    /* No session, nobody to ask: deny in our own words. */
    assert.equal((await fire(agentless(BUDGET_RAW_NAME, request))).kind, "deny");

    /* Every other tool passes - including the ungated wallet tools and Gate
     * 2's read-only listing. This is the assertion that a second prepended
     * listener leaves the first, and everything else, alone. */
    for (const name of ["bash", "ask_user_question", "wallet_budgets", "wallet_budget_delegate", "wallet_pay", "mcp__drill__orders"]) {
      assert.equal((await fire(pending(name))).kind, "allow", name);
    }
    /* ...and Gate 2 still decides its own tool through the same waterfall:
     * two listeners, no collision. */
    assert.equal((await fire(pending("mcp__drill__place_order", { symbol: "AAPL", qty: 1, side: "buy" }))).kind, "ask");

    /* THE GUARD, through the real pipeline. A stand-in registered under the
     * real name AFTER boot, exactly as `installWallet` registers the real one.
     * `execute` here carries no agent, so the listener denies for want of a
     * session - which the guard must ALSO deny, independently: mutation-proof
     * it by wrapping the waterfall so the listener's decision is overridden to
     * `allow`, the override case the guard exists for (a listener registered
     * outside the gate taking our decision and handing back allow). Only the
     * guard can then have produced the denial, and only the log could have
     * satisfied it. */
    const registry = ctx.get("tools") as {
      register(definition: unknown): () => void;
      execute(exec: object): Promise<{ isError: boolean; content?: { text?: string }[] }>;
    };
    let bodyRan = false;
    const unregister = registry.register({
      name: BUDGET_RAW_NAME,
      description: "drill stand-in: request a budget (nothing behind it)",
      parameters: { type: "object", properties: {}, additionalProperties: true },
      output: { schema: { type: "object" }, render: () => [{ type: "text", text: "ok" }] },
      execute: async () => {
        bodyRan = true;
        return {};
      },
    });
    const override = (ctx as unknown as {
      on(
        name: "tools/pre-execute",
        listener: (exec: { name: string }, next: () => Promise<PreToolDecision>) => Promise<PreToolDecision>,
        options?: { prepend?: boolean },
      ): () => boolean;
    }).on("tools/pre-execute", async (exec, next) => {
      if (exec.name !== BUDGET_RAW_NAME) return next();
      await next(); // let the gate speak, then throw its answer away
      return { kind: "allow" };
    }, { prepend: true });
    try {
      const result = await registry.execute({
        callId: "drill-budget-guard",
        name: BUDGET_RAW_NAME,
        arguments: request,
        signal: new AbortController().signal,
      });
      assert.equal(result.isError, true, "an un-granted budget request must not dispatch even when a listener allows it");
      assert.equal(bodyRan, false, "the tool body must never run");
      assert.match(result.content?.[0]?.text ?? "", /without a logged allowed-once approval/);
    } finally {
      override();
      unregister();
    }
  } finally {
    await dispose();
  }
});
