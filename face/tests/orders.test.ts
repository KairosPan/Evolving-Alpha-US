import test from "node:test";
import assert from "node:assert/strict";
import {
  auditOrderTools, describeOrder, effectiveApprovalPolicy, hasApprovalGrant, isGatedTool,
  isOrderTool, orderApprovalDecision, orderGuardReason,
} from "../src/orders.ts";

/* --- which tools the gate claims ------------------------------------------ */

test("isOrderTool: the two mutating tools match, raw and as dsh mints them", () => {
  for (const raw of ["place_order", "cancel_order"]) {
    assert.equal(isOrderTool(raw), true, raw);
    assert.equal(isOrderTool(`mcp__alpaca-kit__${raw}`), true, `mcp__alpaca-kit__${raw}`);
  }
});

test("isOrderTool: a server rename cannot slip a live order tool past", () => {
  // The serverName is the operator's, in their cordis patch, not this repo's.
  assert.equal(isOrderTool("mcp__alpaca__place_order"), true);
  assert.equal(isOrderTool("mcp__broker_prod__cancel_order"), true);
});

test("isOrderTool: the read-only `orders` listing is NOT gated", () => {
  // The trap a substring test for "order" would fall into: `orders` only reads.
  assert.equal(isOrderTool("orders"), false);
  assert.equal(isOrderTool("mcp__alpaca-kit__orders"), false);
  // ...and neither are the other read-only tools that mention orders nowhere.
  assert.equal(isOrderTool("mcp__alpaca-kit__account"), false);
  assert.equal(isOrderTool("mcp__alpaca-kit__positions"), false);
});

/* --- the decision --------------------------------------------------------- */

test("orderApprovalDecision: anything that is not an order tool is none of our business", () => {
  // null, not allow: the caller must delegate to next(), leaving other
  // listeners' decisions intact rather than overriding them with an allow.
  assert.equal(orderApprovalDecision("mcp__alpaca-kit__orders", "ask"), null);
  assert.equal(orderApprovalDecision("bash", "ask"), null);
});

test("orderApprovalDecision: an order under policy `ask` raises a card", () => {
  const decision = orderApprovalDecision("mcp__alpaca-kit__place_order", "ask");
  assert.equal(decision?.kind, "ask");
});

test("orderApprovalDecision: under policy `never` it denies ITSELF, and says nobody was asked", () => {
  // Returning `ask` here would be worse than useless: ApprovalService
  // short-circuits on `never` before any answerer runs, and dsh-tools renders
  // that as `the user rejected tool "..."` - false, because nobody was asked.
  const decision = orderApprovalDecision("mcp__alpaca-kit__place_order", "never");
  assert.equal(decision?.kind, "deny");
  const reason = decision?.kind === "deny" ? decision.reason : "";
  assert.match(reason, /nobody was asked/i);
  assert.doesNotMatch(reason, /the user rejected/i);
  // It must name the way out, or the operator is stuck with a refusal they cannot explain.
  assert.match(reason, /danger-full-access/);
});

/* --- the policy this all turns on ----------------------------------------- */

test("effectiveApprovalPolicy: override wins, then config, then `ask`", () => {
  const session = {};
  assert.equal(
    effectiveApprovalPolicy({ overrideOf: () => "never", config: { policy: "ask" } }, session),
    "never",
  );
  assert.equal(
    effectiveApprovalPolicy({ overrideOf: () => undefined, config: { policy: "never" } }, session),
    "never",
  );
  assert.equal(effectiveApprovalPolicy({ overrideOf: () => undefined }, session), "ask");
});

test("effectiveApprovalPolicy: a runtime switch to danger-full-access disarms the card, so it denies", () => {
  // The whole reason the policy is read per call rather than once at boot.
  const approval = { overrideOf: () => "never" as const, config: { policy: "ask" as const } };
  const policy = effectiveApprovalPolicy(approval, {});
  assert.equal(orderApprovalDecision("mcp__alpaca-kit__place_order", policy)?.kind, "deny");
});

/* --- the registry cross-check --------------------------------------------- */

test("auditOrderTools: reports the covered order tools", () => {
  const audit = auditOrderTools([
    { name: "mcp__alpaca-kit__place_order", description: "submit a PAPER order (operator-gated)" },
    { name: "mcp__alpaca-kit__cancel_order", description: "cancel a paper order by id (operator-gated)" },
    { name: "mcp__alpaca-kit__orders", description: "list orders" },
    { name: "bash", description: "run a command" },
  ]);
  assert.deepEqual(audit.gated, ["mcp__alpaca-kit__place_order", "mcp__alpaca-kit__cancel_order"]);
  assert.deepEqual(audit.ungated, []);
});

test("auditOrderTools: a renamed operator-gated tool is reported as ungated, not silently missed", () => {
  // The failure the boot assertion exists for: alpaca-kit still marks it, but
  // the name no longer matches, so the gate would cover nothing while the face
  // came up healthy.
  const audit = auditOrderTools([
    { name: "mcp__alpaca-kit__submit_order", description: "submit a PAPER order (operator-gated)" },
  ]);
  assert.deepEqual(audit.gated, []);
  assert.deepEqual(audit.ungated, ["mcp__alpaca-kit__submit_order"]);
});

test("auditOrderTools: an order tool whose description lost the marker is still gated", () => {
  // The other direction of the cross-check: the name is what enforces.
  const audit = auditOrderTools([{ name: "mcp__alpaca-kit__place_order", description: "submit" }]);
  assert.deepEqual(audit.gated, ["mcp__alpaca-kit__place_order"]);
  assert.deepEqual(audit.ungated, []);
});

test("auditOrderTools: an empty registry is empty, not an error", () => {
  // Orders are OFF today - the flag is unset - so this is the normal case, and
  // it must not trip the boot assertion.
  assert.deepEqual(auditOrderTools([]), { gated: [], ungated: [] });
  assert.deepEqual(
    auditOrderTools([{ name: "mcp__alpaca-kit__account", description: "account snapshot" }]),
    { gated: [], ungated: [] },
  );
});

/* --- the grant check: a sighting is not an approval ----------------------- */

const asked = (id: string, callId: string, toolName = "mcp__x__place_order") =>
  ({ type: "approval/asked", data: { id, callId, toolName } });
const decided = (id: string, outcome: string) => ({ type: "approval/decided", data: { id, outcome } });

test("hasApprovalGrant: a logged allowed-once for THIS call is a grant", () => {
  assert.equal(hasApprovalGrant([asked("a1", "c1"), decided("a1", "allowed-once")], "c1"), true);
});

test("hasApprovalGrant: an ask with no decision yet is not a grant", () => {
  assert.equal(hasApprovalGrant([asked("a1", "c1")], "c1"), false);
});

test("hasApprovalGrant: a rejection is not a grant, and neither is a cancellation", () => {
  for (const outcome of ["rejected", "cancelled", "unavailable"]) {
    assert.equal(hasApprovalGrant([asked("a1", "c1"), decided("a1", outcome)], "c1"), false, outcome);
  }
});

test("hasApprovalGrant: a grant for a DIFFERENT call does not carry over", () => {
  // The whole point of matching on callId: one approval, one dispatch.
  const events = [asked("a1", "c1"), decided("a1", "allowed-once")];
  assert.equal(hasApprovalGrant(events, "c2"), false);
});

test("hasApprovalGrant: an unrelated decided event cannot satisfy it", () => {
  // A sandbox escalation approved in the same turn must not license an order.
  const events = [asked("other", "c9"), decided("other", "allowed-once")];
  assert.equal(hasApprovalGrant(events, "c1"), false);
});

test("hasApprovalGrant: no callId is never a grant", () => {
  assert.equal(hasApprovalGrant([asked("a1", "c1"), decided("a1", "allowed-once")], undefined), false);
});

/* --- the per-call gate test (what the guard asks) ------------------------- */

test("isGatedTool: an order name is gated whatever its description says", () => {
  assert.equal(isGatedTool("mcp__x__place_order", undefined), true);
  assert.equal(isGatedTool("mcp__x__place_order", "harmless"), true);
});

test("isGatedTool: a renamed tool still carrying the marker is gated", () => {
  // The late-registration and hash-suffix cases the boot audit can miss.
  assert.equal(isGatedTool("mcp__x__submit_order", "submit a PAPER order (operator-gated)"), true);
  assert.equal(isGatedTool("mcp__x__place_order_a1b2c3d4e5f6", "(operator-gated)"), true);
});

test("isGatedTool: the marker only counts on mcp__ tools, so one phrase cannot brick the face", () => {
  assert.equal(isGatedTool("bash", "runs things (operator-gated)"), false);
  assert.equal(isGatedTool("mcp__x__orders", "list orders"), false);
});

/* --- the card has to be readable ------------------------------------------ */

test("describeOrder: the card names the order, not just the tool", () => {
  const line = describeOrder("mcp__alpaca-kit__place_order", {
    symbol: "AAPL", qty: 10, side: "buy", order_type: "limit", limit_price: 195.5,
  });
  for (const fragment of ["AAPL", "qty=10", "side=buy", "limit", "195.5"]) {
    assert.match(line, new RegExp(fragment.replace(".", "\\.")), fragment);
  }
});

test("describeOrder: an unknown field is shown, not dropped", () => {
  // Rule 5: a tool that grows a field must not grow a silent one.
  assert.match(describeOrder("t", { symbol: "X", time_in_force: "gtc" }), /time_in_force=gtc/);
});

test("describeOrder: odd arguments degrade to the tool name, never throw", () => {
  for (const args of [undefined, null, "text", 42, []]) {
    assert.equal(describeOrder("mcp__x__place_order", args), "mcp__x__place_order");
  }
  assert.equal(describeOrder("t", {}), "t");
  assert.equal(describeOrder("t", { nested: { a: 1 } }), "t: nested=?");
});

test("orderApprovalDecision: the ask reason carries the order, so the card is decidable", () => {
  const decision = orderApprovalDecision("mcp__alpaca-kit__place_order", "ask", {
    symbol: "TSLA", qty: 3, side: "sell",
  });
  assert.equal(decision?.kind, "ask");
  assert.match(decision?.kind === "ask" ? decision.reason ?? "" : "", /TSLA/);
});

/* --- the guard: the monotonic half --------------------------------------- */

const granted = [asked("g", "c1"), decided("g", "allowed-once")];

test("orderGuardReason: an approved order passes", () => {
  assert.equal(orderGuardReason("mcp__x__place_order", undefined, granted, "c1"), undefined);
});

test("orderGuardReason: an order with NO grant is denied - a sighting is not an approval", () => {
  // The override case: a listener registered outside this gate takes our `ask`
  // and returns `allow`. The old witnessed-WeakSet guard waved that through,
  // having seen the call. Only the log proves a human said yes.
  const reason = orderGuardReason("mcp__x__place_order", undefined, [], "c1");
  assert.match(reason ?? "", /without a logged allowed-once/);
});

test("orderGuardReason: a rejected order is denied", () => {
  const events = [asked("g", "c1"), decided("g", "rejected")];
  assert.notEqual(orderGuardReason("mcp__x__place_order", undefined, events, "c1"), undefined);
});

test("orderGuardReason: a grant for another call does not let this one through", () => {
  assert.notEqual(orderGuardReason("mcp__x__place_order", undefined, granted, "c2"), undefined);
});

test("orderGuardReason: a marked tool the gate cannot name is denied, and the message says how to fix it", () => {
  // The late-registration / hash-suffix hole the boot audit cannot see, closed
  // per call. It can never be approved, so the denial must name the remedy.
  const reason = orderGuardReason("mcp__x__submit_order", "a PAPER order (operator-gated)", [], "c1");
  assert.match(reason ?? "", /ORDER_RAW_NAMES/);
});

test("hasApprovalGrant: a grant won for ANOTHER tool cannot be replayed onto an order", () => {
  // callId is the model's own tool-call id, so it is not by itself proof of
  // WHICH tool a human approved.
  const events = [asked("a1", "c1", "bash"), decided("a1", "allowed-once")];
  assert.equal(hasApprovalGrant(events, "c1", "mcp__x__place_order"), false);
  assert.equal(hasApprovalGrant(events, "c1", "bash"), true);
});

test("hasApprovalGrant: an id-less asked event cannot pair with an id-less decision", () => {
  const events = [
    { type: "approval/asked", data: { callId: "c1", toolName: "mcp__x__place_order" } },
    { type: "approval/decided", data: { outcome: "allowed-once" } },
  ];
  assert.equal(hasApprovalGrant(events, "c1", "mcp__x__place_order"), false);
});

test("describeOrder: a crafted field cannot run away with the operator's only line", () => {
  const line = describeOrder("t", { symbol: "X".repeat(200) });
  assert.ok(line.length < 80, `card line must stay readable; got ${line.length} chars`);
  assert.match(line, /…/);
});

test("orderGuardReason: everything else passes untouched", () => {
  for (const [name, description] of [["bash", "run"], ["mcp__x__orders", "list orders"]]) {
    assert.equal(orderGuardReason(name, description, [], "c1"), undefined, name);
  }
});
